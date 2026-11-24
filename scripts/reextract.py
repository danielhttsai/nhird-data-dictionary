"""Re-extract curated files from their PDFs with the current extractor, keeping
the curation.

extract_all.py never re-extracts over a curated JSON and merge_upstream.py only
applies what differs between two PDFs, so an improvement to the extractor does
not reach the files already in extracted/. This script does, for the files named:

  * every value the extractor reads from the PDF (header facts, fields, the
    tables of a multi-table manual, code tables it reads, "printed" counts, qa)
    follows the new extraction;
  * English is kept where the Chinese did not change (whitespace aside) and
    otherwise taken from translations/cache.json; a string the cache does not
    know is left without English and reported (gap_check.py reports it too);
  * whatever the extractor does not produce is kept: hand-added keys on the file
    and on fields (refs, section, value_labels, notes), and every code table the
    new extraction lacks or reads with fewer codes (code tables built from other
    sources, OCR'd tables);
  * a field the new extraction no longer has is reported, not silently lost:
    with --keep-missing it is kept;
  * with --base-dir (the previous extractor's output for the same PDFs, as
    <code>__<version>.json), a value edited by hand (curated differs from what
    the previous extractor read) is kept and reported instead of replaced.

usage: python scripts/reextract.py --only Health01,Health02 [--dry-run]
OCR-recovered files are skipped (the extractor cannot read those PDFs).
"""
from __future__ import annotations
import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from merge_upstream import (load_cache, sha_text, _safe, FILE_EN, FIELD_EN, CB_EN, ENTRY_EN,  # noqa: E402
                            ALL_EN, _field_key, unify)

W = re.compile(r"\s+")
HAN = re.compile(r"[一-鿿]")
PDF_FIELD_KEYS = {"seq", "name_zh", "name_en", "type", "length", "description_zh", "source",
                  "available_notes", "table", "value_labels"}


def sq(s):
    return W.sub("", unify(s)) if isinstance(s, str) else s


def english(zh: str, old_zh: str | None, old_en: str | None, cache: dict, known: dict) -> str:
    zh = (zh or "").strip()
    if not zh:
        return ""
    if old_en and old_zh is not None and sq(old_zh) == sq(zh):
        return old_en
    return cache.get(sha_text(zh)) or known.get(sq(zh), "")


def readable(entries: list) -> bool:
    """The rule extract_pdf.section_codebooks applies: codes that look like codes."""
    bad = sum(1 for e in entries if HAN.search(str(e.get("code"))) or len(str(e.get("code"))) > 15)
    return bool(entries) and bad <= 0.2 * len(entries)


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def known_english() -> dict:
    """Chinese (whitespace removed) -> English, from every curated pair."""
    pairs = list(FILE_EN.items()) + list(FIELD_EN.items()) + list(CB_EN.items()) + list(ENTRY_EN.items())
    out = {}
    for p in sorted((ROOT / "extracted").glob("*/*.json")):
        if p.name.startswith("diff_"):
            continue
        for o in walk(json.loads(p.read_text(encoding="utf-8"))):
            for zk, ek in pairs:
                z, e = o.get(zk), o.get(ek)
                if isinstance(z, str) and isinstance(e, str) and z.strip() and e.strip():
                    out.setdefault(sq(z), e)
    return out


def stamp(obj: dict, old: dict | None, en_map: dict, cache, known, missing: list, where: str):
    for zk, ek in en_map.items():
        if zk not in obj:
            continue
        obj[ek] = english(obj.get(zk), (old or {}).get(zk), (old or {}).get(ek), cache, known)
        if HAN.search(obj.get(zk) or "") and not obj[ek]:
            missing.append(f"{where}.{zk}")


def hand_edited(cur, base_val) -> bool:
    return base_val is not None and isinstance(cur, (str, int)) and sq(str(cur)) != sq(str(base_val))


def rebuild(old: dict, new: dict, cache, known, keep_missing: bool, report: list,
            base: dict | None = None) -> dict:
    out = dict(old)
    pr = new.get("printed") or {}
    if pr.get("code_tables"):
        cb_new = new.get("codebooks") or {}
        pr["code_tables"] = {k: n for k, n in pr["code_tables"].items()
                             if readable((cb_new.get(k) or {}).get("entries") or [])}
    for k, v in new.items():
        if k in ("fields", "codebooks", "tables"):
            continue
        if base is not None and k in FILE_EN and hand_edited(old.get(k), base.get(k)) and sq(old.get(k)) != sq(v):
            report.append(f"file.{k}: kept the hand-edited value")
            continue
        out[k] = v
    missing: list[str] = []
    stamp(out, old, FILE_EN, cache, known, missing, "file")

    # tables of a multi-table manual
    if new.get("tables"):
        old_t = {t.get("code_short"): t for t in old.get("tables") or []}
        tables = []
        for t in new["tables"]:
            o = old_t.get(t["code_short"], {})
            nt = {**{k: v for k, v in o.items() if k not in t and k not in ALL_EN}, **t}
            stamp(nt, o, FILE_EN, cache, known, missing, f"table {t['code_short']}")
            tables.append(nt)
        out["tables"] = tables

    # fields
    old_f = {_field_key(f): f for f in old.get("fields") or []}
    # a field that has moved into a table (Health103, Health55) is found by its column name
    names = [f.get("name_en") for f in old.get("fields") or []]
    by_name = {f.get("name_en"): f for f in old.get("fields") or [] if names.count(f.get("name_en")) == 1}
    base_f = {_field_key(f): f for f in (base or {}).get("fields") or []}
    fields = []
    for f in new.get("fields") or []:
        o = old_f.get(_field_key(f)) or (by_name.get(f.get("name_en"), {}) if f.get("table") else {})
        nf = dict(f)
        b = base_f.get(_field_key(f))
        if b is not None and o:
            for k in ("name_zh", "type", "length", "description_zh"):
                # a length that is not a number, a type that is not a type, is no correction
                if k == "length" and not str(o.get(k, "")).isdigit():
                    continue
                if k == "type" and not re.fullmatch(r"(?i)(char|num|number|date|varchar\d*|int|decimal|text)\w*", str(o.get(k, ""))):
                    continue
                if k == "description_zh" and sq(str(o.get(k))) in (str(nf.get("length")), sq(nf.get("type") or "")):
                    continue                  # a length or type that slipped into the note
                if hand_edited(o.get(k), b.get(k)) and sq(str(o.get(k))) != sq(str(nf.get(k))):
                    report.append(f"{_field_key(f)}.{k}: kept the hand-edited value")
                    nf[k] = o[k]
        for k, v in o.items():               # hand-added keys (refs, section, …)
            if k not in PDF_FIELD_KEYS and k not in ALL_EN and k not in nf:
                nf[k] = v
        stamp(nf, o, FIELD_EN, cache, known, missing, _field_key(f))
        fields.append(nf)
    have = {_field_key(f) for f in fields} | {f.get("name_en") for f in fields}
    gone = [k for k in old_f if k not in have]
    if gone:
        report.append(f"fields no longer read: {gone}")
        if keep_missing:
            fields.extend(old_f[k] for k in gone)
    out["fields"] = fields

    # code tables: the new reading where it has at least every code we had
    cbs = dict(old.get("codebooks") or {})
    for name, ncb in (new.get("codebooks") or {}).items():
        if not readable(ncb.get("entries") or []):
            continue
        ocb = cbs.get(name)
        if isinstance(ocb, dict) and ocb.get("source"):
            continue                          # built from another source: keep
        o_codes = [sq(str(e.get("code"))) for e in (ocb or {}).get("entries") or []]
        n_codes = [sq(str(e.get("code"))) for e in ncb.get("entries") or []]
        if ocb and not (set(o_codes) <= set(n_codes) and len(n_codes) >= len(o_codes)
                        and len(set(n_codes)) == len(n_codes)):
            continue
        cb = json.loads(json.dumps(ncb, ensure_ascii=False))
        stamp(cb, ocb, CB_EN, cache, known, missing, f"codebook {name}")
        o_by = {(sq(str(e.get("code"))), sq(e.get("label_zh"))): e for e in (ocb or {}).get("entries") or []}
        for e in cb.get("entries") or []:
            stamp(e, o_by.get((sq(str(e.get("code"))), sq(e.get("label_zh")))), ENTRY_EN, cache, known,
                  missing, f"codebook {name} {e.get('code')}")
        for k, v in (ocb or {}).items():
            if k not in cb:
                cb[k] = v
        if ocb is None or len(n_codes) != len(o_codes) or o_by.keys() != {
                (sq(str(e.get("code"))), sq(e.get("label_zh"))) for e in cb["entries"]}:
            report.append(f"codebook {name}: {len(o_codes)} -> {len(n_codes)} codes")
        cbs[name] = cb
    # code tables kept as printed (grids): add the grid, keep any entries we have
    for name, ncb in (new.get("codebooks") or {}).items():
        if ncb.get("text") and not ncb.get("entries") and not ncb.get("grid"):
            cb = cbs.setdefault(name, {"field_zh": ncb.get("field_zh", ""), "entries": []})
            if not cb.get("source") and not cb.get("entries"):
                cb["text"] = ncb["text"]
            continue
        if ncb.get("grid"):
            if name not in cbs:
                cbs[name] = {"field_zh": ncb.get("field_zh", ""), "entries": [], "grid": ncb["grid"]}
                report.append(f"codebook {name}: added as printed ({len(ncb['grid']['rows'])} rows)")
            elif not cbs[name].get("source"):
                cbs[name]["grid"] = ncb["grid"]
    out["codebooks"] = cbs
    if missing:
        report.append(f"{len(missing)} strings without English (e.g. {missing[:3]})")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", required=True, help="comma-separated codes")
    ap.add_argument("--versions", default="", help="comma-separated version_ids (default: all)")
    ap.add_argument("--keep-missing", action="store_true")
    ap.add_argument("--waves", action="store_true", help="also the survey-wave PDFs unpacked from ZIPs")
    ap.add_argument("--base-dir", default="", help="previous extractor output, <code>__<version>.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--extracted-dir", default="", help="use extractions already made, <code>__<version>.json")
    args = ap.parse_args()
    only = set(args.only.split(","))
    vers = set(filter(None, args.versions.split(",")))
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    cache, known = load_cache(), known_english()
    for v in manifest["versions"]:
        lf = v.get("local_filename") or ""
        if v["code"] not in only or v.get("file_type") != "pdf" or not lf:
            continue
        # survey-wave manuals unpacked from a ZIP (process_zips.py) only when asked
        if ("/" in lf) and not (args.waves and lf.startswith("raw_pdfs_zip/")):
            continue
        if vers and v["version_id"] not in vers:
            continue
        path = ROOT / "extracted" / v["code"] / f"{_safe(v['version_id'])}.json"
        if not path.exists():
            continue
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("_ocr_recovered"):
            print(f"  [SKIP] {v['code']} / {v['version_id']}: OCR-recovered")
            continue
        pre = Path(args.extracted_dir) / f"{v['code']}__{v['version_id']}.json" if args.extracted_dir else None
        if pre and pre.exists():
            raw = pre.read_text(encoding="utf-8")
        else:
            pdf_path = ROOT / lf if "/" in lf else ROOT / "raw_pdfs" / lf
            if not pdf_path.exists():
                print(f"  [SKIP] {v['code']} / {v['version_id']}: {lf} not unpacked")
                continue
            proc = subprocess.run([sys.executable, str(SCRIPTS / "extract_pdf.py"), str(pdf_path)],
                                  capture_output=True, timeout=args.timeout)
            raw = proc.stdout.decode("utf-8", "replace")
        # CJK compatibility forms (U+F900-FAFF) as the merge writes them: unified
        new = json.loads(unify(raw))
        if new["qa"]["errors"]:
            print(f"  [ERR ] {v['code']} / {v['version_id']}: {new['qa']['errors']}")
            continue
        report: list[str] = []
        bp = Path(args.base_dir) / f"{v['code']}__{v['version_id']}.json" if args.base_dir else None
        base = json.loads(bp.read_text(encoding="utf-8")) if bp and bp.exists() else None
        out = rebuild(old, new, cache, known, args.keep_missing, report, base)
        print(flush=True)
        print(f"  [OK  ] {v['code']} / {v['version_id']}: fields {len(old.get('fields') or [])} -> "
              f"{len(out['fields'])}; qa {new['qa']['warnings'][:3]}")
        for r in report:
            print(f"         {r}")
        if not args.dry_run:
            path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
