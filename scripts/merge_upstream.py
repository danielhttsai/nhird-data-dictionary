"""Bring upstream PDF revisions into the curated JSON without re-extracting over it.

The files in extracted/ are not raw extractor output: they carry translations,
hand corrections, OCR-recovered tables and code tables built from other sources.
Re-running the extractor over them would throw all of that away, so a revised
PDF is merged three ways instead:

    base   = extractor output for the PDF the JSON was built from (git HEAD)
    theirs = extractor output for the PDF that fetch_pdfs.py just downloaded
    ours   = the committed, curated JSON

Only what differs between base and theirs is applied to ours. A JSON is stale
when its ``pdf_sha256`` differs from the manifest's ``sha256``.

What counts as a difference
  * Text is compared ignoring whitespace, page furniture (page numbers,
    "YYYY年MM月DD日修訂" footers) and CJK compatibility forms: MOHW re-renders
    PDFs and the extracted spacing and glyphs shift with no change in content.
    Where the text did change, only the changed span is taken from the new PDF;
    the rest keeps our spacing.
  * A text change has to show in the PDFs themselves: words the new extraction
    drops must be gone from the new PDF, or words it adds must be absent from
    the old one. Otherwise the extractor only cut a cell differently (a note
    truncated at a page break, a neighbouring row swept in) and ours is kept.
    The same goes for a code-table row that appears or disappears.
  * A value that the new extraction leaves empty never blanks ours.
  * Something we edited by hand (ours differs from base) is never overwritten or
    removed; the upstream change is reported as a conflict instead.
  * A code table whose rows the extractor merely split differently (every row
    that appears or disappears is printed in the other PDF too) is left alone.

A file is HELD when the merge cannot be trusted — the raw PDF and its manifest
entry are put back to HEAD, the JSON is not touched, and the file is listed in
refresh_pending.json so the same revision is not re-attempted every week:
  * the old PDF is not in git HEAD under the sha the JSON was built from,
  * the JSON is OCR-recovered (the extractor cannot read that PDF),
  * the extractor fails on either PDF,
  * fields appear or disappear in the extraction although the PDFs print them
    on both sides, or a third of the fields are lost (the extractor read the
    two layouts differently; that is not a revision).
A held file is retried when MOHW revises it again, or when its entry is deleted
from refresh_pending.json. A timeout is not recorded there: the file is put back
and tried again on the next run.

Where the Chinese changed, the English is re-stamped from translations/cache.json;
a string the cache does not know is left without English (the site then shows
the Chinese) and gap_check.py reports it.

Writes .refresh/merge.json for refresh_report.py.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from refresh_state import load_pending, save_pending, write_state

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.json"
RAW = ROOT / "raw_pdfs"
OUT = ROOT / "extracted"
CACHE_FILE = ROOT / "translations" / "cache.json"
EXTRACT_PY = SCRIPTS / "extract_pdf.py"

# Chinese source attribute -> its English companion
FILE_EN = {"data_description_zh": "data_description_en", "notes_zh": "notes_en",
           "primary_keys_raw": "primary_keys_en", "name_zh": "name_zh_en"}
FIELD_EN = {"name_zh": "name_zh_en", "description_zh": "description_en"}
CB_EN = {"field_zh": "field_en"}
ENTRY_EN = {"label_zh": "label_en"}
ALL_EN = set(FILE_EN.values()) | set(FIELD_EN.values()) | set(CB_EN.values()) | set(ENTRY_EN.values())

FILE_SKIP = {"fields", "codebooks", "source_pdf"}
# Derived wholesale from the PDF and never curated: always follow the new PDF
FILE_DERIVED = {"raw_text_first_page", "qa", "page_count", "update_history",
                "update_history_raw"}

_WS = re.compile(r"\s+")
# Page furniture the extractor sweeps into cells that sit at a page break
_FURNITURE = re.compile(
    r"頁\s*\d+\s*/\s*\d+"
    r"|\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*修訂"
    r"|版本日期\s*[:：]\s*\d{4}/\d{1,2}/\d{1,2}")
_HAN = re.compile(r"[一-鿿]")
# CJK compatibility ideographs (U+F900–FAFF): some PDF fonts emit 臨 as U+F9F6
_COMPAT = re.compile(r"[豈-﫿]")
MIN_SPAN = 6            # shortest run of text worth looking up in a PDF


def _safe(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name, flags=re.UNICODE)[:80]


def unify(s: str) -> str:
    return _COMPAT.sub(lambda m: unicodedata.normalize("NFKC", m.group()), s)


def squash(v):
    """Text with whitespace and page furniture removed and compatibility forms
    unified; other values as they are."""
    return _WS.sub("", _FURNITURE.sub("", unify(v))) if isinstance(v, str) else v


def same(a, b) -> bool:
    return squash(a) == squash(b)


def empty(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def printed_in(span: str, text: str) -> bool:
    """Is this (squashed) run of text printed in that (squashed) PDF text? Table
    cells and page text are not read in the same order — a side label or a page
    break can sit in the middle of a paragraph — so the run is looked up in
    overlapping 8-character pieces, and four out of five have to be there."""
    if len(span) <= 8:
        return span in text
    pieces = [span[i:i + 8] for i in range(0, len(span) - 7, 4)]
    return sum(pc in text for pc in pieces) * 5 >= len(pieces) * 4


def sha_text(s: str) -> str:            # same key as translate.py
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def load_cache() -> dict[str, str]:
    return json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}


def stamp_english(data: dict, cache: dict[str, str]) -> None:
    """Give a freshly extracted file the English the cache already knows
    (what translate.py --stamp-only does, for one file)."""
    def t(obj, en_map):
        for zh_key, en_key in en_map.items():
            zh = (obj.get(zh_key) or "").strip()
            obj[en_key] = cache.get(sha_text(zh), "") if zh else ""
    t(data, FILE_EN)
    for f in data.get("fields") or []:
        t(f, FIELD_EN)
    for cb in (data.get("codebooks") or {}).values():
        if isinstance(cb, dict):
            t(cb, CB_EN)
            for e in cb.get("entries") or []:
                t(e, ENTRY_EN)


def splice(ours: str, new: str) -> str:
    """Rewrite ``ours`` to say what ``new`` says, keeping our spacing wherever
    the text (whitespace aside) is unchanged."""
    def chars(s):                       # [(char, whitespace before it)]
        out, ws = [], ""
        for c in s:
            if c.isspace():
                ws += c
            else:
                out.append((c, ws))
                ws = ""
        return out
    a, b = chars(ours), chars(unify(new))
    sm = SequenceMatcher(None, [c for c, _ in a], [c for c, _ in b], autojunk=False)
    out, after_change = [], False
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                c, ws = a[i1 + k]
                if k == 0 and after_change:     # the text before it is new: use new spacing
                    ws = b[j1][1]
                out.append(ws + c)
            after_change = False
        else:
            out.extend(ws + c for c, ws in b[j1:j2])
            after_change = True
    return "".join(out).strip()


def _short(v, n: int = 70) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = _WS.sub(" ", s or "")
    return "“" + (s if len(s) <= n else s[:n] + "…") + "”"


def _change(b, n) -> str:
    """'old → new', cut down to the span that differs when the strings are long."""
    if isinstance(b, str) and isinstance(n, str) and max(len(b), len(n)) > 70:
        sb, sn = _WS.sub(" ", b), _WS.sub(" ", n)
        i = 0
        while i < min(len(sb), len(sn)) and sb[i] == sn[i]:
            i += 1
        j = 0
        while j < min(len(sb), len(sn)) - i and sb[-1 - j] == sn[-1 - j]:
            j += 1
        lo = max(0, i - 12)
        cut = lambda s: ("…" if lo else "") + s[lo:len(s) - max(0, j - 12)] + ("…" if j > 12 else "")
        return f"{_short(cut(sb), 110)} → {_short(cut(sn), 110)}"
    return f"{_short(b)} → {_short(n)}"


def _field_key(f: dict) -> str:
    return _WS.sub("", f.get("name_en") or "") or f"seq:{f.get('seq')}"


def _entry_key(e: dict) -> str:
    return _WS.sub("", str(e.get("code")))


def _index(items: list, keyfn) -> dict:
    """{(key, nth occurrence): item} — codes are not always unique in a file."""
    out, seen = {}, {}
    for it in items:
        k = keyfn(it)
        seen[k] = seen.get(k, 0) + 1
        out[(k, seen[k])] = it
    return out


def _keyname(key) -> str:
    return key[0] if key[1] == 1 else f"{key[0]}#{key[1]}"


def _curated(base: dict, ours: dict) -> bool:
    """Did we change this item by hand (anything but its English)?"""
    keys = (set(base) | set(ours)) - ALL_EN
    return any(not same(base.get(k), ours.get(k)) for k in keys)


class Merge:
    """One file's merge. Collects what happened for the report."""

    def __init__(self, cache: dict[str, str], old_text: str, new_text: str):
        self.cache = cache
        self.old_text, self.new_text = old_text, new_text   # squashed full PDF text
        self.changes: list[str] = []      # upstream changes applied
        self.conflicts: list[str] = []    # upstream changed something we had edited: kept ours
        self.kept: list[str] = []         # not applied on purpose (empty value, re-cut text)
        self.untranslated: list[str] = []

    # -- attributes -------------------------------------------------------
    def attrs(self, where: str, base: dict, ours: dict, new: dict,
              en_map: dict, skip=(), derived=()):
        for k in list(dict.fromkeys(list(base) + list(new))):
            if k in skip:
                continue
            b, n = base.get(k), new.get(k)
            if k in derived:
                if b != n and k in new:
                    ours[k] = n
                continue
            if same(b, n):
                continue
            o = ours.get(k)
            if same(o, n):
                continue                              # already says so
            if empty(n) and not empty(o):
                self.kept.append(f"{where}.{k}: the new extraction is empty; kept {_short(o)}")
                continue
            if isinstance(b, str) and isinstance(n, str) and b and not self.reflected(b, n):
                self.kept.append(f"{where}.{k}: the PDFs do not show this change (the extractor "
                                 f"cut the text differently); kept {_short(o)}")
                continue
            if not same(o, b):                        # we edited it, upstream changed it
                self.conflicts.append(f"{where}.{k}: kept ours {_short(o)}; upstream {_change(b, n)}")
                continue
            if isinstance(o, str) and isinstance(n, str) and o and n:
                ours[k] = splice(o, n)
            else:
                ours[k] = unify(n) if isinstance(n, str) else n
            self.changes.append(f"{where}.{k}: {_change(b, n)}")
            if k in en_map:
                self.restamp(where, ours, k, en_map[k])

    def reflected(self, b: str, n: str) -> bool:
        """Do the PDFs bear out the change from b to n? Text the new extraction
        drops must be gone from the new PDF, or text it adds must be absent from
        the old one. A span too short to look up counts as real."""
        x, y = squash(b), squash(n)
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, x, y, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            gone, came = x[i1:i2], y[j1:j2]
            if gone and (len(gone) < MIN_SPAN or not printed_in(gone, self.new_text)):
                return True
            if came and (len(came) < MIN_SPAN or not printed_in(came, self.old_text)):
                return True
        return False

    def printed(self, item: dict, text: str) -> bool:
        """Is this code-table row (its label) printed in that PDF?"""
        lab = squash(item.get("label_zh") or "")
        return len(lab) >= MIN_SPAN and printed_in(lab, text)

    def restamp(self, where: str, obj: dict, zh_key: str, en_key: str):
        zh = (obj.get(zh_key) or "").strip()
        en = self.cache.get(sha_text(zh), "") if zh else ""
        obj[en_key] = en
        if zh and not en and _HAN.search(zh):
            self.untranslated.append(f"{where}.{zh_key}: {zh}")

    def stamp_new(self, where: str, obj: dict, en_map: dict):
        for zh_key, en_key in en_map.items():
            if zh_key in obj:
                self.restamp(where, obj, zh_key, en_key)

    # -- keyed lists (fields, codebook entries) ----------------------------
    def keyed(self, where: str, base: list, ours: list, new: list, keyfn,
              en_map: dict, label: str) -> list:
        bk, ok, nk = _index(base, keyfn), _index(ours, keyfn), _index(new, keyfn)
        out, placed = [], set()
        for key, n in nk.items():
            name = _keyname(key)
            if key in ok:
                o = ok[key]
                self.attrs(f"{where}{name}", bk.get(key, {}), o, n, en_map)
                out.append(o)
                placed.add(key)
            elif key in bk:
                pass                                  # we removed it on purpose
            elif label == "code" and self.printed(n, self.old_text):
                self.kept.append(f"{where}{name}: row new in the extraction, but the old PDF "
                                 f"printed it already; not added")
            else:
                item = {k: (unify(v) if isinstance(v, str) else v) for k, v in n.items()}
                self.stamp_new(f"{where}{name}", item, en_map)
                out.append(item)
                self.changes.append(f"{where}{name}: {label} added")
        prev = None                                   # the item before it in ours
        for key, o in ok.items():
            if key in placed:
                prev = o
                continue
            if key in bk:
                if label == "code" and self.printed(bk[key], self.new_text):
                    self.kept.append(f"{where}{_keyname(key)}: row missing from the extraction, "
                                     f"but the new PDF still prints it; kept")
                elif not _curated(bk[key], o):
                    self.changes.append(f"{where}{_keyname(key)}: {label} removed upstream")
                    continue
                else:
                    self.conflicts.append(f"{where}{_keyname(key)}: {label} removed upstream, "
                                          f"but we had edited it; kept ours")
            pos = next((i + 1 for i, x in enumerate(out) if x is prev), 0)
            out.insert(pos, o)
            prev = o
        return out

    def resplit(self, base_entries: list, new_entries: list) -> bool:
        """True when the two extractions list different rows for a code table but
        each row found on one side only is printed in the other PDF as well: the
        extractor cut the same table differently, the table itself did not change."""
        bk, nk = _index(base_entries, _entry_key), _index(new_entries, _entry_key)
        only_b = [bk[k] for k in bk if k not in nk]
        only_n = [nk[k] for k in nk if k not in bk]
        if not only_b and not only_n:
            return False
        return (all(self.printed(e, self.new_text) for e in only_b)
                and all(self.printed(e, self.old_text) for e in only_n))

    # -- whole file -------------------------------------------------------
    def file(self, base: dict, ours: dict, new: dict) -> dict:
        self.attrs("file", base, ours, new, FILE_EN, skip=FILE_SKIP, derived=FILE_DERIVED)
        ours["fields"] = self.keyed("", base.get("fields") or [], ours.get("fields") or [],
                                    new.get("fields") or [], _field_key, FIELD_EN, "field")
        bcb, ocb, ncb = (base.get("codebooks") or {}, ours.get("codebooks") or {},
                         new.get("codebooks") or {})
        for name, n in ncb.items():
            if name in ocb:
                b, o = bcb.get(name, {}), ocb[name]
                if self.resplit(b.get("entries") or [], n.get("entries") or []):
                    self.kept.append(f"codebook {name}: the extractor split the same table "
                                     f"differently; kept ours")
                    continue
                self.attrs(f"codebook {name}", {k: v for k, v in b.items() if k != "entries"},
                           o, {k: v for k, v in n.items() if k != "entries"}, CB_EN)
                o["entries"] = self.keyed(f"codebook {name} ", b.get("entries") or [],
                                          o.get("entries") or [], n.get("entries") or [],
                                          _entry_key, ENTRY_EN, "code")
            elif name not in bcb:
                cb = json.loads(unify(json.dumps(n, ensure_ascii=False)))
                self.stamp_new(f"codebook {name}", cb, CB_EN)
                for e in cb.get("entries") or []:
                    self.stamp_new(f"codebook {name} {e.get('code')}", e, ENTRY_EN)
                ocb[name] = cb
                self.changes.append(f"codebook {name}: added ({len(cb.get('entries') or [])} codes)")
        for name in [k for k in ocb if k in bcb and k not in ncb]:
            if _curated(bcb[name], ocb[name]):
                self.conflicts.append(f"codebook {name}: removed upstream, but we had edited it; kept ours")
                continue
            del ocb[name]
            self.changes.append(f"codebook {name}: removed upstream")
        ours["codebooks"] = ocb
        return ours


# ---------------------------------------------------------------------------

def run_extract(pdf_path: Path, timeout: int) -> dict:
    proc = subprocess.run([sys.executable, str(EXTRACT_PY), str(pdf_path)],
                          capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-300:])
    return json.loads(proc.stdout.decode("utf-8", "replace"))


def pdf_text(pdf_path: Path, timeout: int) -> str:
    """Whole-document text, squashed. Run in a child process (see prepare)."""
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--text", str(pdf_path)],
                          capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-300:])
    return proc.stdout.decode("utf-8", "replace")


def git_show(path: str) -> bytes | None:
    p = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{path}"], capture_output=True)
    return p.stdout if p.returncode == 0 else None


def unstable(base: dict, new: dict, old_text: str, new_text: str) -> str:
    """Why the two extractions cannot be compared field by field, or ''."""
    b = {_field_key(f) for f in base.get("fields") or []}
    n = {_field_key(f) for f in new.get("fields") or []}
    if b and len(b - n) * 3 > len(b):
        return f"the new extraction lost {len(b - n)} of {len(b)} fields"
    gone = sorted(k for k in b - n if not k.startswith("seq:") and k in new_text)
    if gone:
        return "fields missing from the new extraction but still printed in the new PDF: " + ", ".join(gone)
    came = sorted(k for k in n - b if not k.startswith("seq:") and k in old_text)
    if came:
        return "fields new in the extraction although the old PDF already printed them: " + ", ".join(came)
    return ""


def prepare(job: dict, timeout: int) -> dict:
    """Extract both PDFs of one stale file. Returns the job with base / new /
    old_text / new_text, or with a reason why it has to be held."""
    v, ours, old_bytes = job["v"], job["ours"], job["old_bytes"]
    lf = v["local_filename"]
    if ours.get("_ocr_recovered"):
        return {**job, "reason": "OCR-recovered file; the extractor cannot read this PDF"}
    if old_bytes is None or hashlib.sha256(old_bytes).hexdigest() != ours.get("pdf_sha256"):
        return {**job, "reason": "the PDF this JSON was built from is not in git HEAD"}
    try:
        with tempfile.TemporaryDirectory() as td:
            old_pdf = Path(td) / lf
            old_pdf.write_bytes(old_bytes)
            base = run_extract(old_pdf, timeout)
            old_text = pdf_text(old_pdf, timeout)
        new = run_extract(RAW / lf, timeout)
        new_text = pdf_text(RAW / lf, timeout)
    except subprocess.TimeoutExpired:
        return {**job, "reason": f"extraction exceeded {timeout}s; will retry next run", "retry": True}
    except Exception as e:
        return {**job, "reason": f"extraction failed: {str(e)[:200]}"}
    return {**job, "base": base, "new": new, "old_text": old_text, "new_text": new_text,
            "reason": unstable(base, new, old_text, new_text)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=600, help="seconds per extraction step")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    head_raw = git_show("manifest.json")
    head = {(v["code"], v["version_id"]): v
            for v in json.loads(head_raw.decode("utf-8"))["versions"]} if head_raw else {}
    cache = load_cache()
    state = load_pending()
    pending = {(p["code"], p["version_id"]): p for p in state["held"]}

    jobs = []
    for v in manifest["versions"]:
        lf = v.get("local_filename") or ""
        if v.get("file_type") != "pdf" or not lf or "/" in lf or "\\" in lf or not v.get("sha256"):
            continue
        key = (v["code"], v["version_id"])
        out_path = OUT / v["code"] / f"{_safe(v['version_id'])}.json"
        if not out_path.exists():
            continue                                   # new file: extract_all.py's job
        ours = json.loads(out_path.read_text(encoding="utf-8"))
        if ours.get("pdf_sha256") == v["sha256"]:
            pending.pop(key, None)                     # resolved since
            continue
        jobs.append({"v": v, "key": key, "out_path": out_path, "ours": ours,
                     "old_bytes": git_show(f"raw_pdfs/{lf}")})

    print(f"{len(jobs)} revised PDF(s) to merge", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as pool:
        jobs = list(pool.map(lambda j: prepare(j, args.timeout), jobs))

    merged, held = [], []
    for job in jobs:
        v, key, ours, out_path = job["v"], job["key"], job["ours"], job["out_path"]
        label = f"{v['code']} / {v['version_id']}"
        if not job["reason"]:
            m = Merge(cache, job["old_text"], job["new_text"])
            ours = m.file(job["base"], ours, job["new"])
            ours["pdf_sha256"] = v["sha256"]
            ours["pdf_url"] = v.get("pdf_url", "")
            ours["doc_first_published"] = v.get("doc_first_published", "")
            ours["doc_last_updated"] = v.get("doc_last_updated", "")
            ours["name_zh_from_listing"] = v.get("name_zh", "")
            if not args.dry_run:
                out_path.write_text(json.dumps(ours, ensure_ascii=False, indent=2), encoding="utf-8")
            pending.pop(key, None)
            merged.append({"code": v["code"], "version_id": v["version_id"],
                           "doc_last_updated": v.get("doc_last_updated", ""),
                           "changes": m.changes, "conflicts": m.conflicts,
                           "kept": m.kept, "untranslated": m.untranslated})
            print(f"  [MERGED] {label:46s} changes={len(m.changes):3d} conflicts={len(m.conflicts)} "
                  f"kept={len(m.kept)} untranslated={len(m.untranslated)}")
        else:
            entry = {"code": v["code"], "version_id": v["version_id"], "sha256": v["sha256"],
                     "doc_last_updated": v.get("doc_last_updated", ""), "pdf_url": v.get("pdf_url", ""),
                     "reason": job["reason"], "held_on": time.strftime("%Y-%m-%d", time.gmtime())}
            held.append(entry)
            if not job.get("retry"):
                pending[key] = entry
            print(f"  [HELD  ] {label:46s} {job['reason']}")
            if not args.dry_run:                       # put the PDF and its entry back
                if job["old_bytes"] is not None:
                    (RAW / v["local_filename"]).write_bytes(job["old_bytes"])
                prev = head.get(key)
                if prev:
                    v.clear()
                    v.update(prev)

    if not args.dry_run:
        if held:
            MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        save_pending({"held": list(pending.values()), "unlisted": state["unlisted"]})
        write_state("merge", {"merged": merged, "held": held})
    print(f"\nSummary: {len(merged)} merged | {len(held)} held")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--text":
        import pdfplumber
        with pdfplumber.open(sys.argv[2]) as _pdf:
            sys.stdout.write(squash("\n".join((_p.extract_text() or "") for _p in _pdf.pages)))
        sys.exit(0)
    main()
