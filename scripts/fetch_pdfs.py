"""Crawl the MOHW Department of Statistics database-manual listing
(https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-N-20.html, N = 1, 2, …)
and bring raw_pdfs/ and manifest.json up to date with it.

Each listing row carries TWO date columns (first-published, last-updated, ROC
calendar). The "version" we care about for content diffing is encoded in the
title itself (suffix markers like "(20250624起適用)" or period markers like
"2018年以後" for the cancer-registry files). We use those to build a stable
`version_id` per (code, version).

manifest.json is MERGED, never rebuilt. Besides the listing it catalogues what
was unpacked from the survey ZIPs, the TWCR manuals and files added by hand,
and none of those can be re-derived from the listing. So:
  * an entry the listing does not show is kept as it is;
  * an unchanged file (same sha256) keeps its entry, including fetched_at;
  * a download that fails leaves the entry and the file alone;
  * a revised PDF replaces the file and updates the entry — merge_upstream.py
    then merges the revision into the curated JSON, or puts the PDF back;
  * a revised ZIP is not written at all: it is recorded in refresh_pending.json.
A run that finds nothing new writes nothing.

Writes .refresh/fetch.json for refresh_report.py.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
import time
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urljoin

import httpx
import urllib3
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from refresh_state import load_pending, save_pending, write_state

warnings.filterwarnings("ignore")
try:
    urllib3.disable_warnings()  # type: ignore
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw_pdfs"
MANIFEST = ROOT / "manifest.json"

LIST_URL = "https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-{n}-20.html"
MAX_LIST_PAGES = 40
UA = "nhird-data-dictionary-fetcher/0.1 (https://github.com)"

# Code at the start of the title: e.g. "Health01_..." or "Welfare10_..." or "Society12-1_..."
CODE_RE = re.compile(r"^(Health|Society|Welfare)0*(\d+(?:-\d+)?)", re.IGNORECASE)
ROC_DATE_RE = re.compile(r"(\d{3})[\-./](\d{1,2})[\-./](\d{1,2})")


@dataclass
class PdfVersion:
    code: str                  # canonical: "Health01", "Welfare10", "Society12-1"
    category: str              # Health/Society/Welfare
    name_zh: str               # full Chinese title from the listing
    version_id: str            # stable id for this version of the spec
    version_label: str         # human-readable label
    detail_url: str            # dl-XXXXX-...html landing page
    pdf_url: str = ""          # resolved direct PDF/ZIP URL
    file_type: str = "pdf"     # "pdf" or "zip"
    doc_first_published: str = ""    # ISO date (from listing column 1)
    doc_last_updated: str = ""       # ISO date (from listing column 2)
    sha256: str = ""
    local_filename: str = ""
    fetched_at: str = ""
    listing_page: int = 0
    note: str = ""


def roc_to_ad(year_str: str) -> int:
    return int(year_str) + 1911


def parse_roc_date(s: str) -> str:
    """ROC date like '115-05-25' → '2026-05-25'."""
    m = ROC_DATE_RE.search(s)
    if not m:
        return ""
    return f"{roc_to_ad(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def detect_version(name_zh: str) -> tuple[str, str]:
    """Return (version_id, version_label).

    Three orthogonal axes:
      - revision: legacy vs post-20250624 (whole-page edit at 2025-06-24)
      - period:   pre-2010 / 2011-2017 / 2018-later  (cancer registry only)
      - kind:     spec vs appendix (附錄)
    Combined as ``[period_][kind_]revision`` -- but legacy spec is just ``legacy``.
    Examples:
      ``legacy``, ``post-20250624``, ``period-2018-later``,
      ``period-2018-later_post-20250624``, ``appendix``.
    """
    is_appendix = "附錄" in name_zh
    revision = "post-20250624" if ("20250624" in name_zh) else "legacy"

    period = None
    if "2018" in name_zh and ("以後" in name_zh or "起" in name_zh):
        period = ("period-2018-later", "2018 年以後")
    elif "2011" in name_zh and "2017" in name_zh:
        period = ("period-2011-2017", "2011-2017 年")
    elif ("Pre-2010" in name_zh or "2010之前" in name_zh or "2010前" in name_zh
          or "2010 年以前" in name_zh or "2010年以前" in name_zh
          or ("2007" in name_zh and "2010" in name_zh)):
        period = ("period-pre-2010", "2010 年以前")

    if is_appendix:
        if period:
            return (f"{period[0]}_appendix", f"{period[1]} · 附錄")
        return ("appendix", "附錄")

    if period:
        vid, lbl = period
        if revision == "post-20250624":
            return (f"{vid}_post-20250624", f"{lbl} · 20250624 起適用")
        return (vid, lbl)
    return (revision, "20250624 起適用" if revision == "post-20250624" else "legacy")


def normalize_code(title: str) -> tuple[str | None, str | None]:
    m = CODE_RE.match(title)
    if not m:
        return None, None
    category = m.group(1).capitalize()
    num = m.group(2)
    if "-" not in num and num.isdigit():
        num = num.zfill(2)
    return f"{category}{num}", category


def follow_dl_link(client: httpx.Client, dl_html_url: str) -> tuple[str | None, str | None]:
    """Resolve a 'dl-XXXXX-...html' link. Returns (final_url, content_type)."""
    try:
        r = client.get(dl_html_url, headers={"User-Agent": UA}, timeout=30,
                       follow_redirects=True)
        ct = r.headers.get("content-type", "").lower()
        if "pdf" in ct or "zip" in ct or "octet-stream" in ct:
            return (str(r.url), ct)
        # otherwise look for inline links
        tree = HTMLParser(r.text)
        for a in tree.css("a"):
            href = a.attributes.get("href", "")
            if href.lower().endswith((".pdf", ".zip")):
                return (urljoin(str(r.url), href), "")
        for m in tree.css("meta[http-equiv='refresh']"):
            content = m.attributes.get("content", "")
            mm = re.search(r"url=([^;]+\.(?:pdf|zip))", content, re.IGNORECASE)
            if mm:
                return (urljoin(str(r.url), mm.group(1)), "")
    except httpx.HTTPError as e:
        print(f"   ! could not resolve {dl_html_url}: {e}")
    return (None, None)


def parse_listing(html: str, page_no: int) -> list[PdfVersion]:
    tree = HTMLParser(html)
    versions: list[PdfVersion] = []

    for li in tree.css("li, tr, .item, .news-item, .data-item"):
        # Look at this row's HTML for a dl-XXX link
        node_html = li.html or ""
        if "/dl-" not in node_html:
            continue
        text_parts = [t.strip() for t in li.text(separator="|", strip=True).split("|") if t.strip()]
        if not text_parts:
            continue
        # Title is typically the first long text part
        title = ""
        for t in text_parts:
            if CODE_RE.match(t):
                title = t
                break
        if not title:
            continue

        code, category = normalize_code(title)
        if not code:
            continue

        # Date columns: filter parts that match ROC date pattern
        roc_dates = [p for p in text_parts if ROC_DATE_RE.fullmatch(p)]
        first_pub = parse_roc_date(roc_dates[0]) if len(roc_dates) >= 1 else ""
        last_upd = parse_roc_date(roc_dates[1]) if len(roc_dates) >= 2 else first_pub

        # Find the dl-* link
        link = None
        for a in li.css("a[href]"):
            href = a.attributes.get("href", "")
            if "/dl-" in href:
                link = href if href.startswith("http") else urljoin(
                    "https://www.mohw.gov.tw/", href)
                break
        if not link:
            continue

        version_id, version_label = detect_version(title)

        versions.append(PdfVersion(
            code=code,
            category=category or "Unknown",
            name_zh=title,
            version_id=version_id,
            version_label=version_label,
            detail_url=link,
            doc_first_published=first_pub,
            doc_last_updated=last_upd,
            listing_page=page_no,
        ))
    return versions


def dedupe_versions(versions: list[PdfVersion]) -> list[PdfVersion]:
    """De-dupe by (code, version_id), keeping the entry with later doc_last_updated."""
    by_key: dict[tuple[str, str], PdfVersion] = {}
    for v in versions:
        key = (v.code, v.version_id)
        existing = by_key.get(key)
        if existing is None or (v.doc_last_updated or "") > (existing.doc_last_updated or ""):
            by_key[key] = v
    return list(by_key.values())


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def get(client: httpx.Client, url: str, timeout: int = 60, tries: int = 3) -> httpx.Response:
    """GET with retries: the MOHW server drops connections now and then."""
    for attempt in range(tries):
        try:
            r = client.get(url, headers={"User-Agent": UA}, timeout=timeout,
                           follow_redirects=True)
            r.raise_for_status()
            return r
        except httpx.HTTPError:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def crawl_listing(client: httpx.Client) -> list[PdfVersion]:
    """Walk the listing pages until one adds nothing new (past the last page the
    site serves the last page again)."""
    versions: list[PdfVersion] = []
    seen: set[str] = set()
    for n in range(1, MAX_LIST_PAGES + 1):
        url = LIST_URL.format(n=n)
        r = get(client, url)
        r.encoding = "utf-8"
        rows = [v for v in parse_listing(r.text, n) if v.detail_url not in seen]
        print(f"[page {n}] {url}  new rows: {len(rows)}")
        if not rows:
            break
        seen.update(v.detail_url for v in rows)
        versions.extend(rows)
        time.sleep(0.4)
    return versions


def listing_managed(v: dict) -> bool:
    """An entry this script owns: a file taken straight from the listing, as
    opposed to one unpacked from a ZIP, taken from TWCR or added by hand."""
    lf = v.get("local_filename") or ""
    return (bool(v.get("listing_page")) and not v.get("parent_zip_version")
            and not str(v.get("fetched_at", "")).startswith(("from-", "twcr"))
            and "/" not in lf and "\\" not in lf)


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    old = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"versions": []}
    before = json.dumps(old.get("versions"), ensure_ascii=False, sort_keys=True)
    versions: list[dict] = old.get("versions") or []
    by_key = {(v["code"], v["version_id"]): v for v in versions}
    pending = load_pending()
    held = pending["held"]
    held_sha = {(p["code"], p["version_id"]): p["sha256"] for p in held}
    today = time.strftime("%Y-%m-%d", time.gmtime())
    report = {"changed": [], "new": [], "failed": [], "zip_changed": [], "unlisted": []}

    with httpx.Client(http2=False, timeout=60, verify=False) as client:
        listed = dedupe_versions(crawl_listing(client))
        listed.sort(key=lambda v: (v.category, v.code, v.version_id))
        ours = sum(1 for v in versions if listing_managed(v))
        print(f"\nListing: {len(listed)} versions (manifest has {ours} from the listing)")
        if len(listed) * 2 < ours:
            # A maintenance page or a changed layout: do not conclude that half
            # the databases were withdrawn.
            sys.exit(f"The listing shows only {len(listed)} of {ours} known versions; "
                     f"refusing to update the manifest from it.")

        for j, lv in enumerate(listed, start=1):
            key = (lv.code, lv.version_id)
            prev = by_key.get(key)
            label = f"[{j}/{len(listed)}] {lv.code} / {lv.version_id}"
            try:
                final_url, ct = follow_dl_link(client, lv.detail_url)
                if not final_url:
                    raise RuntimeError("could not find the file URL on the download page")
                content = get(client, final_url, timeout=120).content
            except Exception as e:
                print(f"{label}  ! {e}")
                report["failed"].append({"code": lv.code, "version_id": lv.version_id,
                                         "error": str(e)[:200]})
                if prev is None:                      # listed but never fetched: say so
                    lv.note = f"error: {e}"
                    by_key[key] = asdict(lv)
                    versions.append(by_key[key])
                continue                              # a known entry stays as it is

            ext = ".zip" if (final_url.lower().endswith(".zip") or "zip" in (ct or "")) else ".pdf"
            new_sha = hashlib.sha256(content).hexdigest()
            dst = RAW_DIR / f"{lv.code}_{lv.version_id}{ext}"
            listing_fields = {
                "category": lv.category, "name_zh": lv.name_zh,
                "version_label": lv.version_label, "detail_url": lv.detail_url,
                "pdf_url": final_url, "doc_first_published": lv.doc_first_published,
                "doc_last_updated": lv.doc_last_updated, "listing_page": lv.listing_page,
            }
            if prev is not None and prev.get("sha256") == new_sha:      # unchanged upstream
                if not (dst.exists() and sha256_of(dst) == new_sha):
                    dst.write_bytes(content)          # the local copy was missing or damaged
                prev.update(listing_fields)
                if key in held_sha:                   # resolved since it was held
                    held = [p for p in held if (p["code"], p["version_id"]) != key]
                continue
            if held_sha.get(key) == new_sha:
                continue                              # this revision is already held for review
            if prev is not None and (prev.get("file_type") == "zip" or ext == ".zip"):
                # A survey bundle: its PDFs and Excel codebooks were unpacked and
                # curated by hand (process_zips.py, extract_xls.py). Keep ours.
                print(f"{label}  ZIP revised upstream — held for review")
                entry = {"code": lv.code, "version_id": lv.version_id, "sha256": new_sha,
                         "doc_last_updated": lv.doc_last_updated, "pdf_url": final_url,
                         "reason": "ZIP bundle revised; survey bundles are unpacked and curated by hand",
                         "held_on": today}
                held = [p for p in held if (p["code"], p["version_id"]) != key] + [entry]
                report["zip_changed"].append(entry)
                continue

            dst.write_bytes(content)
            entry = prev if prev is not None else asdict(lv)
            entry.update(listing_fields)
            entry.update({"file_type": "zip" if ext == ".zip" else "pdf", "sha256": new_sha,
                          "local_filename": dst.name, "note": "",
                          "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            if prev is None:
                by_key[key] = entry
                versions.append(entry)
            report["new" if prev is None else "changed"].append(
                {"code": lv.code, "version_id": lv.version_id, "file": dst.name,
                 "file_type": entry["file_type"], "doc_last_updated": lv.doc_last_updated})
            print(f"{label}  {'new' if prev is None else 'revised'}: {dst.name} "
                  f"({len(content) / 1024:.0f} KB)")
            time.sleep(0.3)

    # Entries the listing no longer shows are kept; say so once.
    listed_keys = {(v.code, v.version_id) for v in listed}
    gone = [v for v in versions if listing_managed(v) and (v["code"], v["version_id"]) not in listed_keys]
    known = {(u["code"], u["version_id"]): u for u in pending["unlisted"]}
    unlisted = []
    for v in gone:
        k = (v["code"], v["version_id"])
        if k not in known:
            report["unlisted"].append({"code": v["code"], "version_id": v["version_id"]})
        unlisted.append(known.get(k) or {"code": v["code"], "version_id": v["version_id"], "since": today})

    after = json.dumps(versions, ensure_ascii=False, sort_keys=True)
    if after != before:
        MANIFEST.write_text(json.dumps({
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": LIST_URL.format(n=1),
            "count": len(versions),
            "versions": versions,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    save_pending({"held": held, "unlisted": unlisted})
    write_state("fetch", report)
    print(f"\nrevised={len(report['changed'])} new={len(report['new'])} "
          f"failed={len(report['failed'])} zip_held={len(report['zip_changed'])} "
          f"unlisted={len(gone)}; manifest {'updated' if after != before else 'unchanged'} "
          f"({len(versions)} entries)")


if __name__ == "__main__":
    main()
