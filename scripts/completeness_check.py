"""Has everything the manuals print been brought in? A local, offline check of
every curated JSON against what its PDF declares and prints.

For each manual (each table of a multi-table manual):
  fields    the number of fields equals the 欄位數 its header declares, and is
            not below the numbered rows its field table prints ("printed",
            recorded by extract_pdf.py and refreshed by every merge);
  code refs every field whose note points to a code table (詳見…(CODE)…譯碼)
            has that code table;
  headings  every code table headed in 三、欄位譯碼 is present;
  rows      no code table has fewer codes than the ruled table the PDF prints
            (a code table kept as printed, cell by cell, under "grid" is whole).

A difference that is legitimate (the header counts something else, the code
table is published elsewhere) is listed with its reason in qa_exceptions.json
and is not reported. Anything else is a finding; with --strict the script exits
1 (watch.py runs it that way in the weekly refresh, so the run fails loudly).

Survey codebooks (__xls_ / __wave_ versions), OCR-recovered files and the TWCR
registry manuals are checked by their own builders, not here.
"""
from __future__ import annotations
import argparse
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
EXC = ROOT / "qa_exceptions.json"
REF = re.compile(r"[（(]\s*([A-Z][A-Z0-9_]+(?:\s*~\s*[A-Z0-9_]+)?)\s*[）)][^。\n]{0,12}?譯碼")


def expand(code: str) -> list[str]:
    code = re.sub(r"\s+", "", code)
    parts = [p for p in re.split(r"[＆&、,，]", code) if p]
    if len(parts) > 1:
        return [c for p in parts for c in expand(p)]
    m = re.match(r"([A-Z_]+?)(\d+)~(?:([A-Z_]+?))?(\d+)$", code)
    if m and (m.group(3) is None or m.group(3) == m.group(1)):
        return [f"{m.group(1)}{n}" for n in range(int(m.group(2)), int(m.group(4)) + 1)]
    return [code]


def check(d: dict) -> list[tuple[str, str]]:
    """[(check id, message)] for one curated JSON."""
    out = []
    fields = d.get("fields") or []
    cbs = d.get("codebooks") or {}
    tables = d.get("tables") or []
    if tables:
        for t in tables:
            n = len({f["seq"] for f in fields if f.get("table") == t["code_short"]})
            if t.get("field_count_declared") is not None and n != t["field_count_declared"]:
                out.append((f"fields:{t['code_short']}",
                            f"{t['code_short']}: header declares {t['field_count_declared']} fields, shown {n}"))
    # a numbered row can hold several columns (Health09: 14 = MH_1 … MH_OTHER): count rows
    rows = len({(f.get("table"), f.get("seq")) for f in fields})
    if not tables and d.get("field_count_declared") is not None and rows != d["field_count_declared"]:
        out.append(("fields", f"header declares {d['field_count_declared']} fields, shown {rows}"))
    printed = d.get("printed") or {}
    if printed.get("field_rows") and rows < printed["field_rows"]:
        out.append(("printed_fields", f"the field table prints {printed['field_rows']} rows, shown {rows}"))

    def has_cb(key: str, table: str | None) -> bool:
        k = f"{table}.{key}" if table else key
        if k in cbs or key in cbs:
            return True
        # a range heading (ICD9CM_1~ICD9CM_3) stored under its own name
        return any(key in expand(name.split(".")[-1]) for name in cbs)

    for f in fields:
        for m in REF.finditer(f.get("description_zh") or ""):
            for c in expand(m.group(1)):
                if not has_cb(c, f.get("table")):
                    who = f"{f['table']}.{f.get('name_en')}" if f.get("table") else f.get("name_en")
                    out.append((f"ref:{c}", f"{who} points to code table {c}, which is not extracted"))
    for h in printed.get("code_table_headings") or []:
        table, _, key = h.rpartition(".")
        if not has_cb(key, table or None):
            out.append((f"heading:{h}", f"code table {h} is headed in the PDF but not extracted"))
    for k, n in (printed.get("code_tables") or {}).items():
        if (cbs.get(k) or {}).get("grid"):
            continue                          # kept cell by cell as printed
        have = len((cbs.get(k) or {}).get("entries") or [])
        if have and have < n:
            out.append((f"rows:{k}", f"code table {k}: the PDF's ruled table has {n} rows, shown {have}"))
    # one finding per (check, message)
    return list(dict.fromkeys(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    ap.add_argument("--all", action="store_true", help="also list excepted differences")
    ap.add_argument("--json", default="", help="write the full result here")
    args = ap.parse_args()
    exc = json.loads(EXC.read_text(encoding="utf-8")) if EXC.exists() else {}
    exc.pop("about", None)
    rows, findings, excepted, files = [], 0, 0, 0
    for p in sorted((ROOT / "extracted").glob("*/*.json")):
        if p.name.startswith("diff_") or "__xls_" in p.stem or "__wave_" in p.stem or p.stem.startswith("twcr_"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("_ocr_recovered") or not d.get("fields") and not d.get("field_count_declared"):
            continue
        files += 1
        key = f"{p.parent.name}/{p.stem}"
        ex = exc.get(key, {})
        for cid, msg in check(d):
            why = ex.get(cid)
            rows.append({"file": key, "check": cid, "message": msg, "excepted": why or ""})
            if why:
                excepted += 1
                if args.all:
                    print(f"  ok   {key}: {msg} — {why}")
            else:
                findings += 1
                print(f"  FIND {key}: {msg}")
    stale = [f"{k}:{c}" for k, v in exc.items() for c in v
             if not any(r["file"] == k and r["check"] == c for r in rows)]
    for s in stale:
        print(f"  STALE exception (no longer needed): {s}")
    print(f"COMPLETENESS: {files} manuals checked, {findings} findings, {excepted} legitimate "
          f"differences on record, {len(stale)} stale exceptions")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if args.strict and (findings or stale) else 0)


if __name__ == "__main__":
    main()
