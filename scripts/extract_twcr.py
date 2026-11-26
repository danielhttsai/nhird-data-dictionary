"""Extract the field-spec tables from the Taiwan Cancer Registry (TWCR) manuals
(raw_pdfs_twcr/*.pdf) and register them as catalogue entries.

TWCR manuals use a clean, already-bilingual field table:
    序號 | 欄位名稱 | 英文欄位名稱 | 長度 | 資料型態
with hierarchical sequence numbers (1.1, 4.1.4). The field table sits in the
first pages; the rest of each 200-page manual is coding rules (kept as the
linked source PDF, not parsed).

Writes extracted/<code>/<version>.json + manifest entries, category "TWCR".
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
TWCR_DIR = ROOT / "raw_pdfs_twcr"
EXTRACTED = ROOT / "extracted"
MANIFEST = ROOT / "manifest.json"

SEQ_RE = re.compile(r"^\d+(?:\.\d+)*\.?$")
TYPE_MAP = {"文字": "Char", "數值": "Number", "數字": "Number", "日期": "Date"}

# (pdf filename, code, version_id, version_label, name_zh, name_en, source_url)
MANUALS = [
    ("TWCR_114_longform_129.pdf", "TWCR_LF", "y2025_129",
     "114 年版長表 (129 欄)", "台灣癌症登記 長表", "Taiwan Cancer Registry — Long Form",
     "https://twcr.tw/wp-content/uploads/2025/12/Longform-Manual_Official-version_20251224_W-1.pdf"),
    ("TWCR_107_longform_115.pdf", "TWCR_LF", "y2018_115",
     "107 年版長表 (115 欄, 113 修訂)", "台灣癌症登記 長表", "Taiwan Cancer Registry — Long Form",
     "https://twcr.tw/wp-content/uploads/2025/01/Longform-Manual_Official-version_20250121_W.pdf"),
    ("TWCR_114_shortform_50.pdf", "TWCR_SF", "y2025_50",
     "114 年版短表 (50 欄)", "台灣癌症登記 短表", "Taiwan Cancer Registry — Short Form",
     "https://twcr.tw/wp-content/uploads/2025/12/Shortform-Manual_Official-version_20251204_W.pdf"),
    ("TWCR_107_shortform_45.pdf", "TWCR_SF", "y2018_45",
     "107 年版短表 (45 欄, 113 修訂)", "台灣癌症登記 短表", "Taiwan Cancer Registry — Short Form",
     "https://twcr.tw/wp-content/uploads/2025/01/Shortform-Manual_Official-version_20250102_W.pdf"),
    ("TWCR_114_SSF.pdf", "TWCR_SSF", "y2025",
     "114 年版 部位特定因子 (SSF)", "台灣癌症登記 部位特定因子", "Taiwan Cancer Registry — Site-Specific Factors",
     "https://twcr.tw/wp-content/uploads/2025/12/Cancer-SSF-Manual_Official-version_20251204_W.pdf"),
]


def is_field_header(row) -> bool:
    flat = "|".join((c or "").replace("\n", "") for c in row)
    return "序號" in flat and "欄位名稱" in flat and "英文" in flat


def clean(s: str) -> str:
    return re.sub(r"(?<=[一-鿿])\s+(?=[一-鿿])", "", (s or "").replace("\n", " ").strip()).strip()


def extract_fields(pdf_path: Path) -> list[dict]:
    fields = []
    seen_seq = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                if not tbl or not is_field_header(tbl[0]):
                    continue
                for raw in tbl[1:]:
                    cells = [clean(c) for c in raw]
                    non_empty = [c for c in cells if c]
                    if len(non_empty) < 3 or not SEQ_RE.match(non_empty[0]):
                        continue
                    seq = non_empty[0].rstrip(".")
                    if seq in seen_seq:
                        continue
                    seen_seq.add(seq)
                    name_zh = non_empty[1] if len(non_empty) > 1 else ""
                    name_en = non_empty[2] if len(non_empty) > 2 else ""
                    length = non_empty[3] if len(non_empty) > 3 else ""
                    # the 107 manuals add 欄位 起 / 訖 (record positions) before 資料型態
                    pos = non_empty[4:6] if len(non_empty) > 6 else []
                    typ = non_empty[-1] if len(non_empty) > 4 else ""
                    fields.append({
                        "seq": seq,
                        "name_zh": name_zh,
                        "name_en": name_en,
                        "name_zh_en": name_en,   # already English — mark as translated
                        "type": TYPE_MAP.get(typ, typ),
                        "length": int(length) if length.isdigit() else length,
                        "description_zh": f"欄位位置：{pos[0]}–{pos[1]}" if pos else "",
                        "description_en": f"Record position {pos[0]}–{pos[1]}" if pos else "",
                        "available_notes": [],
                    })
    return fields


def fix_shipped():
    """The shipped JSON (extracted/Health14|15/twcr_manual_*.json) carries
    curation (ICD-O, SSF, AJCC references); bring only the field-table values
    read here into it: type, and the record positions of the 107 manuals."""
    ship = {"TWCR_114_longform_129.pdf": "Health14/twcr_manual_LF129_2025",
            "TWCR_107_longform_115.pdf": "Health14/twcr_manual_LF115_2018",
            "TWCR_114_shortform_50.pdf": "Health15/twcr_manual_SF50_2025",
            "TWCR_107_shortform_45.pdf": "Health15/twcr_manual_SF45_2018"}
    for pdf_name, rel in ship.items():
        p = ROOT / "extracted" / f"{rel}.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        new = {f["seq"]: f for f in extract_fields(ROOT / "raw_pdfs_twcr" / pdf_name)}
        n = 0
        for f in d["fields"]:
            g = new.get(str(f.get("seq")))
            if not g:
                continue
            for k in ("type", "length", "description_zh", "description_en"):
                if g.get(k) not in (None, "") and f.get(k) != g[k]:
                    f[k] = g[k]
                    n += 1
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {rel}: {n} values corrected")



# ---------------------------------------------------------------- coding guides

_SEC = re.compile(r"癌登欄位序號\s*#\s*([\d.]+)")
_TITLE = re.compile(r"欄位長度\s*[:：]")
_PAGE = re.compile(r"^(\d+\s*)?第[一二三四五六七八九十]+部[份分].*?(\s*\d+)?$")
_PARTS = (("description", "欄位敘述"), ("purpose", "收錄目的"), ("instructions", "編碼指引"))


def parse_guides(pdf_path: Path) -> dict:
    """The coding guide of each data item (第二部份編碼指引): from its
    "癌登欄位序號 #seq" line to the next item's title, the 欄位敘述 / 收錄目的 /
    編碼指引 text and the 編碼 / 定義 code table(s). {seq: {...}}"""
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parent))
    import pdf_layout as L
    with pdfplumber.open(pdf_path) as pdf:
        items = L.read_items(pdf)
    out, cur, part, cols, examples = {}, None, None, None, False
    for it in items:
        if it["kind"] == "line":
            t = it["text"].strip()
            if out and re.match(r"^附錄\s*[A-Z一二三四五六七八九十]", t):
                break                         # the appendices (revision notes …) quote item numbers too
            m = _SEC.search(t)
            if m:
                cur = out.setdefault(m.group(1).rstrip("."), {k: [] for k, _ in _PARTS} | {"entries": []})
                part, cols, examples = None, None, False
                continue
            if cur is None:
                continue
            if _TITLE.search(t):            # the next item's title: this guide has ended
                # (its name may sit on the line before "欄位長度")
                if part and cur[part] and len(cur[part][-1]) <= 16 and not re.search(r"[。，；：:、]", cur[part][-1])                         and t.lstrip().startswith("欄位長度"):
                    cur[part].pop()
                cur, part = None, None
                continue
            if _PAGE.match(t) or re.match(r"^NAACCR Item", t) or re.fullmatch(r"\d{1,3}", t):
                continue
            hit = next((k for k, label in _PARTS if t.startswith(label)), None)
            if hit:
                part = hit
                rest = re.sub(r"^\S+?[:：]", "", t).strip()
                if rest:
                    cur[part].append(rest)
                continue
            if re.fullmatch(r"編碼\s+定義", t):
                part = None
                continue
            if t.startswith("範例"):       # examples follow: their tables are not the code list
                examples = True
                part = "instructions"
                cur[part].append(t)
                continue
            if part:
                cur[part].append(t)
        elif cur is not None:
            rows = it["rows"]
            if examples:
                for r in rows:
                    cells = [L.cell_text(c, False) for c in r if c and c["text"].strip()]
                    if cells:
                        cur["instructions"].append("：".join(cells[:1]) + ("：" + " ".join(cells[1:]) if cells[1:] else ""))
                continue
            start = None
            for k, r in enumerate(rows[:2]):
                c = L.code_table_columns(r)
                if c:
                    cols, start = c, k + 1
                    break
            if start is not None:
                cur["entries"].extend(L.code_rows(rows[start:], cols))
            elif cols and L.aligned(rows, cols):
                cur["entries"].extend(L.code_rows(rows, cols))
            elif cols:
                cur["entries"].extend(L.loose_code_rows(rows, len(cols)))
    for g in out.values():
        for k, _ in _PARTS:
            g[k] = L.cell_text("\n".join(g[k]), True)
    return out


def attach_guides():
    """Put each item's coding guide into the shipped TWCR JSON: 欄位敘述 as the
    field's description, 收錄目的 and 編碼指引 as purpose_zh / guide_zh, and the
    code table as the field's code table (one built from another source, ICD-O
    or SSF, stays)."""
    ship = {"TWCR_114_longform_129.pdf": "Health14/twcr_manual_LF129_2025",
            "TWCR_107_longform_115.pdf": "Health14/twcr_manual_LF115_2018",
            "TWCR_114_shortform_50.pdf": "Health15/twcr_manual_SF50_2025",
            "TWCR_107_shortform_45.pdf": "Health15/twcr_manual_SF45_2018"}
    import hashlib
    cache = json.loads((ROOT / "translations" / "cache.json").read_text(encoding="utf-8"))
    for pdf_name, rel in ship.items():
        p = ROOT / "extracted" / f"{rel}.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        guides = parse_guides(ROOT / "raw_pdfs_twcr" / pdf_name)
        cbs = d.setdefault("codebooks", {})
        n = ncb = 0
        for f in d["fields"]:
            g = guides.get(str(f.get("seq")))
            if not g:
                continue
            n += 1
            # keep the record-position line the field table gave (107 manuals)
            pos = next((x for x in str(f.get("description_zh", "")).split("\n") if x.startswith("欄位位置")), "")
            f["description_zh"] = "\n".join(x for x in (g["description"], pos) if x)
            f["purpose_zh"] = g["purpose"]
            f["guide_zh"] = g["instructions"]
            # English from the translation cache (empty until written; gap_check reports it)
            for zk, ek in (("description_zh", "description_en"), ("purpose_zh", "purpose_en"),
                           ("guide_zh", "guide_en")):
                f[ek] = cache.get(hashlib.sha1(f[zk].strip().encode("utf-8")).hexdigest()[:16], "") if f[zk] else ""
            key = f.get("name_en") or str(f.get("seq"))
            src = (cbs.get(key) or {}).get("source", "")
            if g["entries"] and (not src or "編碼指引" in src):
                cbs[key] = {"field_zh": f.get("name_zh", ""), "field_en": f.get("name_en", ""),
                            "source": f"TWCR {pdf_name.split('_')[1]}年 編碼指引 #{f.get('seq')}",
                            "entries": g["entries"]}
                ncb += 1
        # what the manual prints, for scripts/completeness_check.py
        d["printed"] = {"field_rows": len(d["fields"]), "guides": len(guides),
                        "guide_code_tables": {k: len(g["entries"]) for k, g in guides.items() if g["entries"]}}
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {rel}: {len(guides)} guides in the PDF, {n} attached to fields, {ncb} code tables")


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    versions = manifest["versions"]
    have = {(v["code"], v["version_id"]) for v in versions}

    added = 0
    for fn, code, vid, vlabel, name_zh, name_en, url in MANUALS:
        p = TWCR_DIR / fn
        if not p.exists():
            print(f"  missing {fn}")
            continue
        fields = extract_fields(p)
        print(f"  {code}/{vid}: {len(fields)} fields  ({fn})")
        data = {
            "code": code, "category": "TWCR", "code_short": "",
            "name_zh": name_zh, "name_en": name_en,
            "name_zh_en": name_en,
            "version_id": vid, "version_label": vlabel,
            "record_count_raw": "", "field_count_declared": None,
            "frequency": "年", "attribute": "癌症登記手冊 (TWCR)",
            "update_history": [], "data_description_zh": "",
            "notes_zh": "", "primary_keys_raw": "",
            "fields": fields, "codebooks": {},
            "pdf_url": url,
            "qa": {"errors": [], "warnings": [] if fields else ["no fields parsed"]},
        }
        out_dir = EXTRACTED / code
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{vid}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if (code, vid) not in have:
            versions.append({
                "code": code, "category": "TWCR", "name_zh": name_zh,
                "version_id": vid, "version_label": vlabel,
                "detail_url": "https://twcr.tw/?page_id=1809",
                "pdf_url": url, "file_type": "pdf",
                "doc_first_published": "", "doc_last_updated": "",
                "sha256": "", "local_filename": f"raw_pdfs_twcr/{fn}",
                "fetched_at": "twcr", "note": "Taiwan Cancer Registry manual",
            })
            have.add((code, vid))
            added += 1

    manifest["versions"] = versions
    manifest["count"] = len(versions)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAdded {added} TWCR manifest entries.")


if __name__ == "__main__":
    if "--fix-shipped" in sys.argv:
        fix_shipped()
    elif "--guides" in sys.argv:
        attach_guides()
    else:
        main()
