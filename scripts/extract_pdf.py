"""Extract structured metadata + field tables + codebooks from one MOHW
database-manual PDF.

Layout (per pilot of Health01):
  Page 1 has a header table with cells labeled 檔案代號 / 中文檔名 / 英文檔名 /
  資料筆數 / 檔案大小 / 欄位數 / 屬性 / 週期 / 譯碼簿更新日期 / 資料描述 /
  注意事項 / 主鍵與比對欄位.
  Page 2+ contains the field table with 6 logical columns:
    序號 / 中文欄位名稱 / 英文欄位名稱 / 型態 / 長度 / 資料描述
  but pdfplumber returns it as ~13 cells per row because of merged/empty
  layout cells. We collapse to the non-empty values.
  After section "三、欄位譯碼說明", codebook tables per field appear.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

import pdfplumber

# Labels we recognise in the page-1 header table
HEADER_LABELS = {
    "檔案代號", "中文檔名", "英文檔名", "資料筆數", "檔案大小", "欄位數",
    "屬性", "週期", "譯碼簿更新日期", "資料描述", "注意事項",
    "主鍵與比對欄位",
    # variant spellings that occur due to soft line breaks in source
    "譯碼簿\n更新日期", "譯碼簿", "更新日期",
    "主鍵與比\n對欄位", "主鍵與比", "對欄位",
}

ROC_YEAR_RE = re.compile(r"(\d{1,3})\s*年(起|前|以後|(?:含)?以前)?")


def roc_to_ad(roc_year: int) -> int:
    return roc_year + 1911


def extract_pdf(pdf_path: Path) -> dict:
    out: dict = {
        "source_pdf": pdf_path.name,
        "code_short": "",
        "name_zh": "",
        "name_en": "",
        "record_count_raw": "",
        "field_count_declared": None,
        "file_size_raw": "",
        "frequency": "",
        "attribute": "",
        "update_history_raw": "",
        "update_history": [],
        "data_description_zh": "",
        "notes_zh": "",
        "primary_keys_raw": "",
        "fields": [],
        "codebooks": {},
        "raw_text_first_page": "",
        "qa": {"errors": [], "warnings": []},
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            out["page_count"] = len(pdf.pages)

            page0 = pdf.pages[0]
            out["raw_text_first_page"] = page0.extract_text() or ""
            parse_page1_table(page0, out)
            # Fallback: regex on raw text if table-based parse missed essentials
            backfill_from_text(out["raw_text_first_page"], out)

            # Field table — walk all pages
            all_rows: list[dict] = []
            in_codebook = False
            for p in pdf.pages:
                text = p.extract_text() or ""
                if re.search(r"三、\s*欄位譯碼說明", text):
                    in_codebook = True
                if in_codebook:
                    continue
                for tbl in p.extract_tables() or []:
                    rows = parse_field_table(tbl)
                    all_rows.extend(rows)
            out["fields"] = dedupe_fields(all_rows)

            # Codebooks (from codebook section onwards)
            after = collect_text_from(pdf, marker="三、")
            if after:
                out["codebooks"] = parse_codebooks(after, out["fields"])

            # QA
            if out["field_count_declared"] is not None:
                actual = len(out["fields"])
                if actual != out["field_count_declared"]:
                    out["qa"]["warnings"].append(
                        f"field count mismatch: header={out['field_count_declared']}, parsed={actual}")
            if not out["fields"]:
                out["qa"]["warnings"].append("no fields parsed")
    except Exception as e:
        out["qa"]["errors"].append(f"extract failed: {type(e).__name__}: {e}")

    for f in out["fields"]:
        f["available_notes"] = parse_available_notes(f.get("description_zh") or "")

    # Parse update_history_raw into structured entries
    out["update_history"] = parse_update_history(out["update_history_raw"])

    return out


# ============== Page-1 header parsing ==============

def _norm_label(s: str) -> str:
    return (s or "").replace("\n", "").replace(" ", "").strip()


def parse_page1_table(page, out: dict):
    """Pull labeled cells out of the page-1 header table(s)."""
    tables = page.extract_tables() or []
    cells_by_label: dict[str, list[str]] = {}
    # Some labels span multiple rows; collect every (label, neighbour-right value) pair.
    for table in tables:
        for row_idx, row in enumerate(table):
            cells = list(row)
            for i, cell in enumerate(cells):
                lab = _norm_label(cell or "")
                if lab in {_norm_label(x) for x in HEADER_LABELS}:
                    # Value: the next non-empty cell to the right on this same row,
                    # OR, for the wide bottom-half rows (資料描述, etc.), every cell after it.
                    if lab in {_norm_label(x) for x in {
                        "資料描述", "注意事項", "主鍵與比對欄位", "更新日期", "譯碼簿更新日期",
                    }}:
                        # take everything to the right, plus the row below if blank-prefixed
                        bucket = []
                        for c2 in cells[i + 1:]:
                            t = (c2 or "").strip()
                            if t:
                                bucket.append(t)
                        # If the row after is mostly empty but contains a continuation
                        if row_idx + 1 < len(table):
                            next_row = table[row_idx + 1]
                            if all(((c or "").strip() == "") for c in next_row[:i + 1]):
                                for c2 in next_row[i + 1:]:
                                    t = (c2 or "").strip()
                                    if t:
                                        bucket.append(t)
                        if bucket:
                            cells_by_label.setdefault(lab, []).append(" ".join(bucket))
                    else:
                        # take the next single non-empty cell to the right
                        for j in range(i + 1, len(cells)):
                            t = (cells[j] or "").strip()
                            if t:
                                cells_by_label.setdefault(lab, []).append(t)
                                break

    def first(label_norm: str) -> str:
        vals = cells_by_label.get(label_norm) or []
        return vals[0] if vals else ""

    def joined(label_norm: str) -> str:
        vals = cells_by_label.get(label_norm) or []
        return " ".join(vals)

    out["code_short"] = first(_norm_label("檔案代號"))
    out["name_zh"] = first(_norm_label("中文檔名")).replace("\n", "")
    name_en = first(_norm_label("英文檔名")).replace("\n", " ")
    # MOHW puts the English name without spaces in some renderings: "AMBULATORYCARE EXPENDITURES BY VISITS"
    # Best-effort split at camel boundary if missing space
    out["name_en"] = re.sub(r"\s{2,}", " ", name_en).strip()
    out["record_count_raw"] = first(_norm_label("資料筆數")).replace("\n", " ")
    out["file_size_raw"] = first(_norm_label("檔案大小")).replace("\n", " ")
    fc = first(_norm_label("欄位數"))
    if fc.isdigit():
        out["field_count_declared"] = int(fc)
    out["attribute"] = first(_norm_label("屬性"))
    out["frequency"] = first(_norm_label("週期"))
    out["update_history_raw"] = (
        joined(_norm_label("譯碼簿更新日期"))
        or joined(_norm_label("譯碼簿"))
        or joined(_norm_label("更新日期"))
    )
    out["data_description_zh"] = first(_norm_label("資料描述"))
    out["notes_zh"] = first(_norm_label("注意事項"))
    out["primary_keys_raw"] = first(_norm_label("主鍵與比對欄位"))


def backfill_from_text(text: str, out: dict):
    """Regex backfill for fields the table-based parse missed."""
    if not out["code_short"]:
        m = re.search(r"檔案代號\s*([A-Za-z][\w_]*)", text)
        if m:
            out["code_short"] = m.group(1).strip()
    if not out["field_count_declared"]:
        # require that the digit is NOT followed by '.' (which indicates a list marker like "1.")
        m = re.search(r"欄位數\s*(\d+)(?!\s*\.)", text)
        if m:
            out["field_count_declared"] = int(m.group(1))
    if not out["frequency"]:
        m = re.search(r"週期\s*([一-鿿]+)", text)
        if m:
            out["frequency"] = m.group(1).strip()


def parse_update_history(raw: str) -> list[dict]:
    """Parse strings like '2010/11/01 初版 2026/01/27 修訂' into structured entries."""
    if not raw:
        return []
    out = []
    pat = re.compile(r"(\d{4}/\d{1,2}/\d{1,2})\s*([一-鿿]+)?")
    for m in pat.finditer(raw):
        out.append({"date": m.group(1), "note": (m.group(2) or "").strip()})
    return out


# ============== Field table parsing ==============

def parse_field_table(tbl: list[list]) -> list[dict]:
    """Parse one extracted-table object. Returns field rows or [] if not a field table."""
    if not tbl or len(tbl) < 2:
        return []

    def joined(row):
        return "|".join((c or "").replace("\n", "").strip() for c in row)

    def is_header(row):
        flat = joined(row)
        zh_label = ("中文欄位名稱" in flat) or ("中文檔案名稱" in flat) or ("中文名稱" in flat)
        en_label = ("英文欄位名稱" in flat) or ("英文檔案名稱" in flat) or ("英文名稱" in flat)
        if zh_label and en_label:
            return True
        # split header — "序"/"號" + zh_label
        return zh_label and ("序" in flat or "型" in flat)

    header_idx = None
    for i, row in enumerate(tbl[:5]):
        if is_header(row):
            header_idx = i
            break
    if header_idx is None:
        return []

    rows: list[dict] = []
    last_field: dict | None = None
    # Skip the header row(s); header may span 2 rows when 序號/型態/長度 are vertically rendered
    start = header_idx + 1
    if start < len(tbl):
        # peek next row to see if it's a header continuation (only "號"/"態"/"度" chars)
        next_joined = joined(tbl[start])
        if next_joined in {"||號||態|||度||"} or all(
            (c or "").strip() in {"", "號", "態", "度"} for c in tbl[start]
        ):
            start += 1

    for raw in tbl[start:]:
        # Compact to non-empty cells
        non_empty = [(c or "").replace("\n", " ").strip() for c in raw if (c or "").strip()]
        if not non_empty:
            continue
        # Try to interpret as a fresh field row: first cell is a digit
        if non_empty[0].isdigit() and len(non_empty) >= 4:
            seq = int(non_empty[0])
            # Expected order: seq, name_zh, name_en, type, length, description
            # Some rows have less (e.g. no description), some have description split into many cells
            parts = non_empty[1:]
            name_zh = parts[0] if len(parts) > 0 else ""
            name_en = parts[1] if len(parts) > 1 else ""
            typ = parts[2] if len(parts) > 2 else ""
            length = parts[3] if len(parts) > 3 else ""
            desc = " ".join(parts[4:]) if len(parts) > 4 else ""
            try:
                length_val = int(length) if length.isdigit() else length
            except (AttributeError, ValueError):
                length_val = length
            new = {
                "seq": seq,
                "name_zh": name_zh,
                "name_en": name_en,
                "type": typ,
                "length": length_val,
                "description_zh": desc,
            }
            rows.append(new)
            last_field = new
        else:
            # Continuation row → append to last_field's description, OR if it looks like a Chinese
            # name continuation, append to name_zh
            if not last_field:
                continue
            joined_text = " ".join(non_empty)
            # Heuristic: if all non_empty are pure Chinese / parens, treat as name_zh continuation
            if all(re.fullmatch(r"[一-鿿()（）、~：:0-9一二三四五六七八九十]+", x) for x in non_empty):
                last_field["name_zh"] = (last_field["name_zh"] + joined_text).strip()
            else:
                last_field["description_zh"] = (last_field["description_zh"] + " " + joined_text).strip()
    return rows


def dedupe_fields(rows: list[dict]) -> list[dict]:
    by_seq: dict[int, dict] = {}
    for r in rows:
        if r["seq"] not in by_seq:
            by_seq[r["seq"]] = r
        else:
            existing = by_seq[r["seq"]]
            # Prefer the entry with the longer description (likely the one with continuations merged)
            if len(r.get("description_zh") or "") > len(existing.get("description_zh") or ""):
                by_seq[r["seq"]] = r
    return [by_seq[k] for k in sorted(by_seq)]


# ============== Codebook parsing ==============

def collect_text_from(pdf, marker: str) -> str:
    out_chunks = []
    started = False
    for p in pdf.pages:
        t = p.extract_text() or ""
        if not started and marker in t:
            started = True
            t = t[t.index(marker):]
        if started:
            out_chunks.append(t)
    return "\n".join(out_chunks)


def parse_codebooks(text: str, fields: list[dict]) -> dict:
    """Parse codebook section. Section header pattern in MOHW PDFs:

        三、欄位（變項）譯碼
        1.<chinese_field_name>（CODE）
        代號 名稱
        01 <label_zh>
        02 <label_zh>
        ...
        2.<another_chinese_name>（OTHER_CODE）
        ...
    """
    out: dict = {}

    # Discard everything before the section header
    sec_start = re.search(r"三、\s*欄位[\s\S]{0,40}?譯碼", text)
    if not sec_start:
        return out
    body = text[sec_start.end():]

    # Split into per-codebook chunks at lines like "1.XXX（CODE）"
    parts = re.split(r"(?m)^(?=\d+\.\s*[^\n]+?[（(][A-Z][A-Z0-9_~]+[）)])", body)
    for part in parts:
        head = re.match(r"^(\d+)\.\s*(.+?)\s*[（(]([A-Z][A-Z0-9_~]+)[）)]", part)
        if not head:
            continue
        field_zh = head.group(2).strip()
        field_code = head.group(3).strip()

        # Expand ranges like ABC1~ABC4 or ABC1~4 → ABC1, ABC2, ABC3, ABC4
        codes = [field_code]
        rng = re.match(r"([A-Z_]+?)(\d+)~(?:([A-Z_]+?))?(\d+)$", field_code)
        if rng and (rng.group(3) is None or rng.group(3) == rng.group(1)):
            base = rng.group(1)
            codes = [f"{base}{n}" for n in range(int(rng.group(2)), int(rng.group(4)) + 1)]

        # Find code/label pairs in the remaining text
        entries: list[dict] = []
        last_entry: dict | None = None
        for raw in part.split("\n")[1:]:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("代號") and "名稱" in line:
                continue
            if re.match(r"^\d+\.\s*[^\n]+?[（(][A-Z]", line):
                # next codebook header — shouldn't normally hit because of split
                break
            # Match "<CODE>  <Chinese label>"
            mm = re.match(r"^([A-Z0-9]{1,8})\s+(\S.*?)$", line)
            if mm:
                code = mm.group(1)
                label = mm.group(2).strip()
                last_entry = {"code": code, "label_zh": label}
                entries.append(last_entry)
            else:
                # Continuation of previous label (label wrapped to next line)
                if last_entry and re.search(r"[一-鿿]", line):
                    last_entry["label_zh"] = (last_entry["label_zh"] + " " + line).strip()

        if entries:
            for c in codes:
                out.setdefault(c, {"field_zh": field_zh, "entries": []})["entries"].extend(entries)
    return out


def parse_available_notes(description: str) -> list[dict]:
    notes = []
    for m in ROC_YEAR_RE.finditer(description):
        year = int(m.group(1))
        if year < 50 or year > 150:
            continue
        marker = m.group(2) or ""
        notes.append({
            "roc_year": year,
            "ad_year": roc_to_ad(year),
            "marker": marker,
        })
    return notes


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_pdf.py <pdf-path>", file=sys.stderr)
        sys.exit(2)
    p = Path(sys.argv[1])
    data = extract_pdf(p)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
