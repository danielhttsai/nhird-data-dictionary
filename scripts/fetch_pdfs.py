"""Crawl MOHW Department of Statistics database-manual download pages
(https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-N-20.html for N=1..6)
and download every PDF into raw_pdfs/, building manifest.json.

Each listing row carries TWO date columns (first-published, last-updated, ROC
calendar). The "version" we care about for content diffing is encoded in the
title itself (suffix markers like "(20250624起適用)" or period markers like
"2018年以後" for the cancer-registry files). We use those to build a stable
`version_id` per (code, version).

Idempotent: skip download if local sha matches remote.
"""
from __future__ import annotations
import hashlib
import json
import re
import time
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urljoin

import httpx
import urllib3
from selectolax.parser import HTMLParser

warnings.filterwarnings("ignore")
try:
    urllib3.disable_warnings()  # type: ignore
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw_pdfs"
MANIFEST = ROOT / "manifest.json"

LIST_PAGES = [
    f"https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-{n}-20.html"
    for n in range(1, 7)
]
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
    """Return (version_id, version_label) from the title text."""
    if "20250624" in name_zh or "20250624起適用" in name_zh:
        return ("post-20250624", "20250624 起適用")
    if "2018" in name_zh and ("以後" in name_zh or "起" in name_zh):
        return ("period-2018-later", "2018 年以後")
    if "2011" in name_zh and "2017" in name_zh:
        return ("period-2011-2017", "2011-2017 年")
    if "Pre-2010" in name_zh or "2010之前" in name_zh or "2010前" in name_zh:
        return ("period-pre-2010", "2010 年以前")
    return ("legacy", "legacy")


def normalize_code(title: str) -> tuple[str | None, str | None]:
    m = CODE_RE.match(title)
    if not m:
        return None, None
    category = m.group(1).capitalize()
    num = m.group(2)
    if "-" not in num and num.isdigit():
        num = num.zfill(2)
    return f"{category}{num}", category


def fetch_page(client: httpx.Client, url: str) -> str:
    r = client.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


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


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {RAW_DIR}")

    all_versions: list[PdfVersion] = []
    with httpx.Client(http2=False, timeout=60, verify=False) as client:
        for i, url in enumerate(LIST_PAGES, start=1):
            print(f"\n[{i}/6] Fetching listing page: {url}")
            html = fetch_page(client, url)
            page_versions = parse_listing(html, i)
            print(f"   parsed {len(page_versions)} rows")
            all_versions.extend(page_versions)
            time.sleep(0.4)

        all_versions = dedupe_versions(all_versions)
        all_versions.sort(key=lambda v: (v.category, v.code, v.version_id))
        print(f"\nTotal unique versions after dedupe: {len(all_versions)}")

        ok = fail = skipped = 0
        for j, v in enumerate(all_versions, start=1):
            label = f"{v.code} / {v.version_id}"
            print(f"\n[{j}/{len(all_versions)}] {label}")
            try:
                final_url, ct = follow_dl_link(client, v.detail_url)
                if not final_url:
                    print(f"   ! could not find file URL")
                    v.note = "file-url-unresolved"
                    fail += 1
                    continue
                v.pdf_url = final_url
                # Determine extension from final_url + content-type
                ext = ".zip" if (final_url.lower().endswith(".zip") or "zip" in (ct or "")) else ".pdf"
                v.file_type = "zip" if ext == ".zip" else "pdf"
                dst = RAW_DIR / f"{v.code}_{v.version_id}{ext}"
                r = client.get(final_url, headers={"User-Agent": UA}, timeout=120,
                               follow_redirects=True)
                r.raise_for_status()
                new_sha = hashlib.sha256(r.content).hexdigest()
                if dst.exists() and sha256_of(dst) == new_sha:
                    print(f"   cached: {dst.name}")
                    v.local_filename = dst.name
                    v.sha256 = new_sha
                    v.fetched_at = "cached"
                    skipped += 1
                    continue
                dst.write_bytes(r.content)
                v.local_filename = dst.name
                v.sha256 = new_sha
                v.fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                print(f"   downloaded: {dst.name} ({len(r.content)/1024:.0f} KB, {v.file_type})")
                ok += 1
                time.sleep(0.3)
            except Exception as e:
                print(f"   ! download error: {e}")
                v.note = f"error: {e}"
                fail += 1

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-1-20.html",
        "count": len(all_versions),
        "versions": [asdict(v) for v in all_versions],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote manifest with {len(all_versions)} entries to {MANIFEST}")
    print(f"downloaded={ok} cached={skipped} failed={fail}")


if __name__ == "__main__":
    main()
