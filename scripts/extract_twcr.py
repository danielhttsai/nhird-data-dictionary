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
TYPE_MAP = {"文字": "Char", "數值": "Number", "日期": "Date"}

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
                    typ = non_empty[4] if len(non_empty) > 4 else ""
                    fields.append({
                        "seq": seq,
                        "name_zh": name_zh,
                        "name_en": name_en,
                        "name_zh_en": name_en,   # already English — mark as translated
                        "type": TYPE_MAP.get(typ, typ),
                        "length": int(length) if length.isdigit() else length,
                        "description_zh": "",
                        "available_notes": [],
                    })
    return fields


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
    main()
