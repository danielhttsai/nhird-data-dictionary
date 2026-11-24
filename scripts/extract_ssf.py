"""Parse the TWCR Site-Specific Factors (SSF) coding manual into per-factor
code/definition tables + descriptive text, and attach each factor to the
matching Taiwan Cancer Registry long-form field (by 癌登欄位序號 = field seq).

Each SSF factor block looks like:
    癌症部位特定因子：頭頸部癌症
    SSF 1  欄位長度：3
    被侵犯的頸部淋巴結的大小   編碼範圍：000-988,...
    Size of Lymph Nodes (Involved)
    癌登欄位序號：8.1
    欄位敘述： ...  收錄目的： ...  編碼指引： ...
    <編碼 | 定義 tables>
"""
from __future__ import annotations
import io
import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SSF_PDF = ROOT / "raw_pdfs_twcr" / "TWCR_114_SSF.pdf"
EXTRACTED = ROOT / "extracted"

FACTOR_RE = re.compile(r"SSF\s*(\d+(?:-\d+)?)\s*欄位長度[:：]\s*(\d+)")
SEQ_RE = re.compile(r"癌登欄位序號[:：]\s*([\d.]+)")
CODE_RE = re.compile(r"^[0-9A-Za-z]{1,6}(?:-[0-9A-Za-z]{1,6})?$")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def parse_ssf():
    factors = []          # list of dicts
    cur = None
    site = ""             # 癌症部位特定因子：<site> heads each cancer site's factors
    with pdfplumber.open(SSF_PDF) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            sm_site = re.search(r"癌症部位特定因子[:：]\s*(\S+)", text)
            if sm_site:
                site = sm_site.group(1)
            # Detect a new factor block on this page
            m = FACTOR_RE.search(text)
            if m:
                # Find the header line index
                hi = next((i for i, l in enumerate(lines) if FACTOR_RE.search(l)), None)
                name_zh = name_en = ""
                field_seq = ""
                if hi is not None:
                    # name_zh: next line (strip trailing 編碼範圍…)
                    if hi + 1 < len(lines):
                        name_zh = re.split(r"編碼範圍", lines[hi + 1])[0].strip()
                    # name_en: the following line if it looks English
                    if hi + 2 < len(lines) and re.search(r"[A-Za-z]", lines[hi + 2]):
                        name_en = re.split(r"編碼範圍|癌登欄位", lines[hi + 2])[0].strip()
                sm = SEQ_RE.search(text)
                if sm:
                    field_seq = sm.group(1).rstrip(".")
                cur = {
                    "site": site,
                    "ssf_id": f"SSF{m.group(1)}",
                    "length": int(m.group(2)),
                    "name_zh": name_zh,
                    "name_en": name_en,
                    "field_seq": field_seq,
                    "entries": [],
                    "desc": "",
                }
                # Grab the descriptive blurb (欄位敘述 … up to first table)
                dm = re.search(r"欄位敘述[:：]([\s\S]{0,400})", text)
                if dm:
                    cur["desc"] = clean(dm.group(1))[:300]
                factors.append(cur)

            # Collect code/definition table rows for the current factor
            if cur is not None:
                for tbl in page.extract_tables() or []:
                    hdr = "|".join((c or "").replace("\n", "") for c in (tbl[0] if tbl else []))
                    if "編碼" not in hdr and "定義" not in hdr and "案例" not in hdr:
                        continue
                    for raw in tbl[1:]:
                        cells = [clean(c) for c in raw]
                        ne = [c for c in cells if c]
                        if len(ne) < 2:
                            continue
                        code = ne[0]
                        if not CODE_RE.match(code):
                            continue
                        definition = " ".join(ne[1:])[:200]
                        cur["entries"].append({"code": code, "label_zh": definition})
    # Keep only factors that got some content
    return [f for f in factors if f["entries"] or f["field_seq"]]


def main():
    factors = parse_ssf()
    print(f"Parsed {len(factors)} SSF factor blocks, {sum(len(f['entries']) for f in factors)} code rows")
    # 8.1 … 8.10 mean a different factor for each cancer site: keep every site's
    by_seq: dict[str, list] = {}
    for f in factors:
        if f["field_seq"]:
            by_seq.setdefault(f["field_seq"], []).append(f)
    print(f"  with a 癌登欄位序號: {len(by_seq)} fields, "
          f"{sum(len(v) for v in by_seq.values())} site factors")

    # The manual is the 114年 (2025) edition: it belongs to the 2025 long form only.
    for vf, attach in (("twcr_manual_LF129_2025", True), ("twcr_manual_LF115_2018", False)):
        p = EXTRACTED / "Health14" / f"{vf}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        codebooks = {k: v for k, v in (d.get("codebooks") or {}).items()
                     if not str(v.get("source", "")).startswith("TWCR SSF")}
        attached = 0
        for field in d.get("fields", []):
            field.pop("ssf", None)
            fs = by_seq.get(str(field.get("seq", ""))) if attach else None
            if not fs:
                continue
            field["ssf"] = [{"site": f["site"], "ssf_id": f["ssf_id"], "name_zh": f["name_zh"],
                             "name_en": f["name_en"], "desc": f["desc"], "n_codes": len(f["entries"])}
                            for f in fs]
            entries = [{**e, "section": f"{f['site']} · {f['ssf_id']} {f['name_zh']}".strip()}
                       for f in fs for e in f["entries"]]
            if entries:
                codebooks[field.get("name_en") or fs[0]["ssf_id"]] = {
                    "field_zh": field.get("name_zh", ""),
                    "field_en": field.get("name_en", ""),
                    "source": "TWCR SSF 114年版 (by cancer site)",
                    "entries": entries,
                }
            attached += 1
        d["codebooks"] = codebooks
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {vf}: SSF on {attached} fields")



if __name__ == "__main__":
    main()
