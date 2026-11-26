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
import io
import json
import re
import sys
from pathlib import Path

import pdfplumber

import pdf_layout as L

# Force UTF-8 stdout/stderr so JSON printed for a parent subprocess is not
# mangled by Windows' cp950 default console encoding.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Labels we recognise in the page-1 header table
HEADER_LABELS = {
    "檔案代號", "中文檔名", "英文檔名", "資料筆數", "檔案大小", "欄位數",
    "屬性", "週期", "譯碼簿更新日期", "資料描述", "注意事項",
    "主鍵與比對欄位",
    # variant spellings that occur due to soft line breaks in source
    "譯碼簿\n更新日期", "譯碼簿", "更新日期",
    "主鍵與比\n對欄位", "主鍵與比", "對欄位", "主鍵與",
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

            try:
                items = L.read_items(pdf)
                sections = L.split_sections(items)
            except Exception as e:          # an unusual page: read it the older way
                out["qa"]["warnings"].append(f"page geometry unreadable ({type(e).__name__}); "
                                             "fields read row by row")
                items, sections = [], [[]]
            if len(sections) > 1:
                extract_tables(out, sections)
            else:
                sec = L.parse_section(items)
                fields = sec["fields"]
                if not plausible(fields, out["field_count_declared"]):
                    old = legacy_fields(pdf)
                    if len(old) > len(fields):
                        fields = old
                out["fields"] = split_files(out, fields)
                # Code tables: read from the text as before (the curated JSON was
                # built that way, and merge_upstream compares like with like);
                # a code table only the ruled-table reading finds is added.
                after = collect_text_from(pdf, marker="三、")
                out["codebooks"] = parse_codebooks(after, out["fields"]) if after else {}
                ruled = section_codebooks(sec, out["fields"])
                for k, cb in ruled.items():
                    if k not in out["codebooks"] or fuller(cb, out["codebooks"][k]):
                        out["codebooks"][k] = cb
                attach_grids(out["codebooks"], section_grids(sec))
                attach_prose(out["codebooks"], sec)
                out["printed"] = printed_counts(sec, ruled)
                if out["field_count_declared"] is not None and not out.get("tables"):
                    actual = len({f["seq"] for f in out["fields"]})   # numbered rows
                    if actual != out["field_count_declared"]:
                        out["qa"]["warnings"].append(
                            f"field count mismatch: header={out['field_count_declared']}, parsed={actual}")
                if not out["fields"]:
                    out["qa"]["warnings"].append("no fields parsed")
            link_named_tables(out)
            check_codebook_refs(out)
    except Exception as e:
        out["qa"]["errors"].append(f"extract failed: {type(e).__name__}: {e}")

    for f in out["fields"]:
        f["available_notes"] = parse_available_notes(f.get("description_zh") or "")

    # Parse update_history_raw into structured entries
    out["update_history"] = parse_update_history(out["update_history_raw"])

    return out


# ============== Fields: what the page geometry gives, and the older row reader ==============

def split_files(out: dict, fields: list[dict]) -> list[dict]:
    """A manual whose single header block covers several files, each with its own
    field table titled "name (CODE)" and numbered from 1 (Health55: _PD, _FOBT,
    _CUT, _CONF). Listed in out["tables"] like a multi-table manual; the header's
    per-file counts ("H_BHP_CCS_PD : 9") are read into each table. Code tables stay
    shared under their plain names. Fields of a single file are returned as they are."""
    subs = []
    for f in fields:
        s = f.pop("_sub", None)
        if s and s[1] not in [x[1] for x in subs]:
            subs.append(s)
        f["_t"] = s[1] if s else None
    if not subs and len(out.get("field_count_parts") or []) > 1:
        # no titles, but the header counts several files and the numbering starts
        # again at 1 for each (Society10 102年: 12, 793, 1424, 1427 columns)
        k, prev = 1, 0
        for f in fields:
            if f["seq"] == 1 and prev > 1:
                k += 1
            prev = f["seq"]
            f["_t"] = f"part{k}"
        if k > 1:
            parts = out["field_count_parts"]
            subs = [(f"第 {i} 檔", f"part{i}") for i in range(1, k + 1)]
            out["_part_counts"] = parts if len(parts) == k else None
    if len(subs) < 2 or any(f.get("_t") is None for f in fields):
        for f in fields:
            f.pop("_t", None)
        return dedupe_fields(fields)
    raw = out.get("raw_text_first_page") or ""
    tables, result = [], []
    for name, code in subs:
        fs = [f for f in fields if f.get("_t") == code]
        for f in fs:
            f.pop("_t", None)
            f["table"] = code
        fs = dedupe_fields(fs)
        result.extend(fs)

        # "H_BHP_CCS_PD : 9", "… : 1,267,979筆", "… : 44 MB" (the code may break: H_BHP_CCS_ CONF)
        code_re = r"\s*".join(map(re.escape, code))
        facts = {"": "", "筆": "", "B": ""}
        for num, unit in re.findall(code_re + r"\s*[:：]\s*([\d,.]+)\s*(筆|[KMG]B)?", raw):
            k = "B" if unit and unit.endswith("B") else (unit or "")
            facts[k] = facts[k] or (num + (" " + unit if k == "B" else unit or ""))
        declared = facts[""] if facts[""].isdigit() else ""
        if code.startswith("part") and out.get("_part_counts"):
            declared = str(out["_part_counts"][int(code[4:]) - 1])
        tables.append({
            "code_short": code, "name_zh": name, "name_en": "",
            "record_count_raw": facts["筆"],
            "field_count_declared": int(declared) if declared else None,
            "file_size_raw": facts["B"],
            "fields_parsed": len({f["seq"] for f in fs}),
        })
        if tables[-1]["field_count_declared"] is not None and \
                tables[-1]["fields_parsed"] != tables[-1]["field_count_declared"]:
            out["qa"]["warnings"].append(
                f"{code}: field count mismatch: header={declared}, parsed={tables[-1]['fields_parsed']}")
    out["tables"] = tables
    out.pop("_part_counts", None)
    ds = [t["field_count_declared"] for t in tables]
    if None not in ds:
        out["field_count_declared"] = sum(ds)
    return result


def plausible(fields: list[dict], declared: int | None) -> bool:
    """Is the geometric reading complete enough to use? It is when it found the
    declared number of fields, or (no count declared) any fields at all."""
    if not fields:
        return False
    if declared:
        return len({(f.get("_sub"), f["seq"]) for f in fields}) >= declared
    return True


def legacy_fields(pdf) -> list[dict]:
    """The row-by-row reader the extractor used before it read by position. Kept
    for layouts the geometric reader does not recognise (topic databases without
    a 中文欄位名稱 column, survey 過錄編碼簿)."""
    all_rows: list[dict] = []
    in_codebook = False
    for p in pdf.pages:
        text = p.extract_text() or ""
        if re.search(r"三、\s*欄位譯碼說明", text):
            in_codebook = True
        if in_codebook:
            continue
        for tbl in p.extract_tables() or []:
            all_rows.extend(parse_field_table(tbl))
    # Topic-specific databases (Health82/101/103/104, Health59):
    #   序號 / 欄位(EN) / 型態 / 來源 / 內容(ZH) / 描述   (no 長度 column)
    if not all_rows:
        for p in pdf.pages:
            for tbl in p.extract_tables() or []:
                all_rows.extend(parse_field_table_topic(tbl))
    # Survey codebook layout (Health49 過錄編碼簿):
    #   變項名稱 / 變項說明 / 選項數值說明 / 備註
    if not all_rows:
        cb_rows: list[dict] = []
        cb_cols: dict | None = None
        for p in pdf.pages:
            for tbl in p.extract_tables() or []:
                rows, cb_cols = parse_codebook_table(tbl, cb_cols)
                cb_rows.extend(rows)
        for i, f in enumerate(cb_rows, start=1):
            f["seq"] = i
        all_rows = cb_rows
    return all_rows


def _expand_codes(field_code: str) -> list[str]:
    """ABC1~ABC4 or ABC1~4 -> ABC1, ABC2, ABC3, ABC4; DIAG_DOT＆DSVC_DOT -> both."""
    parts = [p for p in re.split(r"\s*[＆&、,，]\s*", field_code) if p]
    if len(parts) > 1:
        return [c for p in parts for c in _expand_codes(p)]
    rng = re.match(r"([A-Z_]+?)(\d+)~(?:([A-Z_]+?))?(\d+)$", field_code)
    if rng and (rng.group(3) is None or rng.group(3) == rng.group(1)):
        base = rng.group(1)
        return [f"{base}{n}" for n in range(int(rng.group(2)), int(rng.group(4)) + 1)]
    return [field_code]


def section_codebooks(sec: dict, fields: list[dict], prefix: str = "") -> dict:
    """Code tables of one section: those printed as ruled tables, and for a
    heading with no ruled table, the code list read from the text."""
    out: dict = {}
    for (field_zh, code), entries in sec["codebooks"]:
        # a table whose first column is not codes (a grid with periods across, a
        # list of names) is not a code table this reader understands: leave it
        bad = sum(1 for e in entries if re.search(r"[一-鿿]", e["code"]) or len(e["code"]) > 15)
        if not entries or bad > 0.2 * len(entries):
            continue
        for c in _expand_codes(code):
            out.setdefault(prefix + c, {"field_zh": field_zh, "entries": []})["entries"].extend(
                [dict(e) for e in entries])
    have = {code for (_, code), _ in sec["codebooks"]}
    if any(code not in have for _, code in sec["cb_heads"]) and sec["cb_text"]:
        text = parse_codebooks(sec["cb_text"], fields)
        for k, cb in text.items():
            if prefix + k not in out:
                out[prefix + k] = cb
    return out


def section_grids(sec: dict, prefix: str = "") -> dict:
    """Every ruled code table of a section as printed: {"header": [...], "rows": [[...]]}."""
    out = {}
    for (field_zh, code), g in sec.get("grids") or []:
        for c in _expand_codes(code):
            out[prefix + c] = {"field_zh": field_zh, "grid": g}
    return out


def attach_prose(codebooks: dict, sec: dict, prefix: str = "") -> None:
    """A heading in 三、欄位譯碼 under which the manual writes rules rather than a
    code list (8.給藥日份（DRUG_DAY）(1)…(2)…): keep that text as the code table's
    "text", when no list or grid was read for it."""
    for (field_zh, code), text in sec.get("prose") or []:
        for c in _expand_codes(code):
            k = prefix + c
            cb = codebooks.get(k)
            if cb and (cb.get("entries") or cb.get("grid")):
                continue
            if text.strip():
                codebooks[k] = {**(cb or {"field_zh": field_zh, "entries": []}),
                                "text": L.cell_text(text, True)}   # rejoin wrapped lines


def attach_grids(codebooks: dict, grids: dict) -> None:
    """A code table the list reading could not take (a grid with a column per period,
    a list whose codes repeat) is kept as printed, under "grid"; a list already read
    keeps its entries."""
    for k, g in grids.items():
        cb = codebooks.get(k)
        entries = (cb or {}).get("entries") or []
        codes = [str(x["code"]) for x in entries]
        listed = entries and len(set(codes)) == len(codes) and len(entries) >= len(g["grid"]["rows"])
        if listed:
            continue
        if cb is None:
            codebooks[k] = {"field_zh": g["field_zh"], "entries": [], "grid": g["grid"]}
        else:
            cb["grid"] = g["grid"]


# ============== A manual that documents several tables ==============

TABLE_KEYS = ("code_short", "name_zh", "name_en", "record_count_raw", "field_count_declared",
              "file_size_raw", "attribute", "frequency", "update_history_raw",
              "data_description_zh", "notes_zh", "primary_keys_raw")


def extract_tables(out: dict, sections: list[list[dict]]) -> None:
    """Welfare20's manual describes ten tables, each with its own header block,
    field table and code tables. Every table is listed in out["tables"]; each
    field carries the code of its table, and a code table is stored under
    "<table code>.<field>", since the same column name (OBJID, STATUS) occurs in
    several tables."""
    tables, fields, codebooks = [], [], {}
    printed = {"field_rows": None, "code_tables": {}, "code_table_headings": []}
    for sec_items in sections:
        sec = L.parse_section(sec_items)
        hdr = {k: "" for k in TABLE_KEYS}
        hdr["field_count_declared"] = None
        parse_header_rows([L.table_texts(it, joined=True) for it in sec["header_items"]], hdr)
        code = hdr["code_short"]
        if not code:
            continue
        hdr["update_history"] = parse_update_history(hdr["update_history_raw"])
        hdr["page_start"] = sec_items[0]["page"] + 1 if sec_items else None
        sf = dedupe_fields(sec["fields"])
        for f in sf:
            f["table"] = code
        hdr["fields_parsed"] = len(sf)
        tables.append(hdr)
        fields.extend(sf)
        ruled = section_codebooks(sec, sf, prefix=f"{code}.")
        codebooks.update(ruled)
        attach_grids(codebooks, section_grids(sec, prefix=f"{code}."))
        attach_prose(codebooks, sec, prefix=f"{code}.")
        pc = printed_counts(sec, ruled, prefix=f"{code}.")
        printed["field_rows"] = (printed["field_rows"] or 0) + (pc["field_rows"] or 0)
        printed["code_tables"].update(pc["code_tables"])
        printed["code_table_headings"].extend(pc["code_table_headings"])
        rows = len({f["seq"] for f in sf})
        if hdr["field_count_declared"] is not None and rows != hdr["field_count_declared"]:
            out["qa"]["warnings"].append(
                f"{code}: field count mismatch: header={hdr['field_count_declared']}, parsed={rows}")
        if not sf:
            out["qa"]["warnings"].append(f"{code}: no fields parsed")
    out["tables"] = tables
    out["printed"] = printed
    out["fields"] = fields
    out["codebooks"] = codebooks
    declared = [t["field_count_declared"] for t in tables]
    out["field_count_declared"] = sum(declared) if declared and None not in declared else None


def fuller(ruled: dict, text: dict) -> bool:
    """Does the ruled-table reading of a code table hold everything the text
    reading has and more? The text reading runs the two halves of a two-column
    table into one label ("A 不識字 G 大學") and loses the second half's codes."""
    r = [str(e["code"]) for e in ruled["entries"]]
    t = [str(e["code"]) for e in text["entries"]]
    avg = lambda es: sum(len(e["label_zh"]) for e in es) / max(1, len(es))
    # codes that repeat mean a grid (periods side by side, HOS), or the reading ran
    # on into the next code table: not a list this reader can take over
    return (len(set(r)) == len(r) and set(t) <= set(r) and len(r) > len(t)
            and avg(ruled["entries"]) <= 1.5 * avg(text["entries"]) + 2)


def printed_counts(sec: dict, ruled: dict, prefix: str = "") -> dict:
    """What the PDF itself prints, read by position, for the completeness check
    (scripts/completeness_check.py): numbered rows of its field table, the rows of
    each ruled code table, and every code-table heading in 三、欄位譯碼."""
    seqs = {f["seq"] for f in sec["fields"]}
    return {
        "field_rows": len(seqs) or None,
        "code_tables": {k: len(cb["entries"]) for k, cb in ruled.items()},
        "code_table_headings": [prefix + c for _, code in sec["cb_heads"] for c in _expand_codes(code)],
    }


def field_key(f: dict) -> str:
    """How a field is addressed: its column name, prefixed with its table's code
    in a manual that documents several tables."""
    return f"{f['table']}.{f.get('name_en')}" if f.get("table") else (f.get("name_en") or "")


_REF = re.compile(r"[（(]\s*([A-Z][A-Z0-9_~]+)\s*[）)][^。\n]{0,12}?譯碼")


def link_named_tables(out: dict) -> None:
    """A field whose note cites a code table by name (詳見「行業分類表」譯碼說明) gets
    "codebook_ref" naming that table, when the manual prints it."""
    cbs = out.get("codebooks") or {}
    for f in out.get("fields") or []:
        if f.get("name_en") in cbs:
            continue
        pre = f"{f['table']}." if f.get("table") else ""
        for m in re.finditer(r"「([^」]{2,24})」", f.get("description_zh") or ""):
            n = re.sub(r"\s+", "", m.group(1))
            for k in (n, n + "代碼", n + "表", re.sub(r"(代碼|表)$", "", n)):
                if pre + k in cbs or k in cbs:
                    f["codebook_ref"] = pre + k if pre + k in cbs else k
                    break
            if f.get("codebook_ref"):
                break


def check_codebook_refs(out: dict) -> None:
    """A field whose note points to a code table (詳見…(CODE)譯碼說明) must have it."""
    have = set(out["codebooks"])
    for f in out["fields"]:
        for m in _REF.finditer(f.get("description_zh") or ""):
            ref = m.group(1)
            keys = [f"{f['table']}.{c}" if f.get("table") else c for c in _expand_codes(ref)]
            if not any(k in have for k in keys):
                out["qa"]["warnings"].append(
                    f"code table referenced but not extracted: {field_key(f)} -> {ref}")


# ============== Page-1 header parsing ==============

def _norm_label(s: str) -> str:
    return (s or "").replace("\n", "").replace(" ", "").strip()


def parse_page1_table(page, out: dict):
    """Pull labeled cells out of the page-1 header table(s)."""
    parse_header_rows(page.extract_tables() or [], out)


def parse_header_rows(tables: list, out: dict):
    """Labeled cells of header tables given as rows of cell text."""
    cells_by_label: dict[str, list[str]] = {}
    normalised_labels = {_norm_label(x) for x in HEADER_LABELS}
    multi_row_labels = {_norm_label(x) for x in {
        "資料描述", "注意事項", "主鍵與比對欄位", "更新日期", "譯碼簿更新日期", "主鍵與",
    }}

    def is_label_text(t: str) -> bool:
        """True if a cell's text is itself any of the known header labels (used to skip
        duplicated label cells in wider 12-column layouts where label appears twice)."""
        return _norm_label(t) in normalised_labels

    # Some labels span multiple rows; collect every (label, neighbour-right value) pair.
    for table in tables:
        for row_idx, row in enumerate(table):
            cells = list(row)
            for i, cell in enumerate(cells):
                lab = _norm_label(cell or "")
                if lab not in normalised_labels:
                    continue
                if lab in multi_row_labels:
                    bucket = []
                    for c2 in cells[i + 1:]:
                        t = (c2 or "").strip()
                        if not t or is_label_text(t):
                            continue
                        bucket.append(t)
                    if row_idx + 1 < len(table):
                        next_row = table[row_idx + 1]
                        # (a next row that carries a label of its own is not a continuation)
                        if (all(((c or "").strip() == "") for c in next_row[:i + 1])
                                and not any(is_label_text(c or "") for c in next_row)):
                            for c2 in next_row[i + 1:]:
                                t = (c2 or "").strip()
                                if not t or is_label_text(t):
                                    continue
                                bucket.append(t)
                    if bucket:
                        cells_by_label.setdefault(lab, []).append(" ".join(bucket))
                else:
                    # Take the next non-empty cell to the right whose text isn't itself a label
                    # (handles 12-col layouts where labels appear in both col i and col i+1).
                    for j in range(i + 1, len(cells)):
                        t = (cells[j] or "").strip()
                        if not t:
                            continue
                        if is_label_text(t):
                            continue
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
    if out["name_en"] in ("無", "无", "-", "—", "N/A"):        # "英文檔名 無": the manual has none
        out["name_en"] = ""
    out["record_count_raw"] = first(_norm_label("資料筆數")).replace("\n", " ")
    out["file_size_raw"] = first(_norm_label("檔案大小")).replace("\n", " ")
    fc = first(_norm_label("欄位數"))
    if fc.isdigit():
        out["field_count_declared"] = int(fc)
    else:
        # one count per file of a survey ("12欄、793欄 / 1424欄、1427欄", "805、94",
        # "W_MOHW_SeniorCitizen111：220 … carer111：76"): file sizes taken out
        rest = re.sub(r"[\d.,]+\s*(?:MB|KB|GB|M|K)\b", " ", fc)
        parts = [int(x.replace(",", "")) for x in re.findall(r"(?:[:：]\s*)?(\d[\d,]*)\s*欄", rest)]
        if not parts:
            parts = [int(x.replace(",", "")) for x in re.findall(r"[:：]\s*(\d[\d,]*)(?![\d.])", rest)]
        if not parts and re.fullmatch(r"[\d,\s、，]+", rest.strip() or "x"):
            parts = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", rest)]
        if len(parts) > 1:
            out["field_count_parts"] = parts
            out["field_count_declared"] = sum(parts)
        elif parts:
            out["field_count_declared"] = parts[0]
    out["attribute"] = first(_norm_label("屬性"))
    out["frequency"] = first(_norm_label("週期"))
    out["update_history_raw"] = (
        joined(_norm_label("譯碼簿更新日期"))
        or joined(_norm_label("譯碼簿"))
        or joined(_norm_label("更新日期"))
    )
    out["data_description_zh"] = first(_norm_label("資料描述"))
    out["notes_zh"] = first(_norm_label("注意事項"))
    out["primary_keys_raw"] = (first(_norm_label("主鍵與比對欄位"))
                               or first(_norm_label("主鍵與比")) or first(_norm_label("主鍵與")))


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

_TYPE_TOKENS = ("char", "varchar", "varchar2", "nvarchar", "nchar", "number",
                "num", "numeric", "date", "datetime", "decimal", "int",
                "integer", "float", "text")


def _is_type_token(s: str) -> bool:
    """True if a cell looks like a SQL/COBOL field type (Char, Number, Date…)."""
    t = (s or "").strip().lower()
    if not t:
        return False
    return any(t == tok or t.startswith(tok) for tok in _TYPE_TOKENS)


def _collapse_cjk_spaces(s: str) -> str:
    """Remove stray spaces pdfplumber inserts between adjacent CJK characters
    ('身 分證' → '身分證', '承保 檔' → '承保檔')."""
    if not s:
        return s
    return re.sub(r"(?<=[一-鿿])\s+(?=[一-鿿])", "", s).strip()


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
        # Try to interpret as a fresh field row: first cell is a sequence number,
        # possibly with trailing punctuation ("1", "1.", "1、").
        seq_m = re.fullmatch(r"(\d+)[.、)）]?", non_empty[0])
        if seq_m and len(non_empty) >= 4:
            seq = int(seq_m.group(1))
            # Base order: seq, name_zh, name_en, [來源], type, length, description.
            # Anchor on the 型態 token so an optional 來源 column (present in some
            # topic databases, e.g. Health103) doesn't shift type/length.
            parts = non_empty[1:]
            name_zh = parts[0] if len(parts) > 0 else ""
            name_en = parts[1] if len(parts) > 1 else ""
            # The row number sometimes leaks into the name cell ("1身分證字號").
            name_zh = re.sub(rf"^\s*{seq}\s*(?=[一-鿿])", "", name_zh)
            name_zh = _collapse_cjk_spaces(name_zh)
            rest = parts[2:]
            source = ""
            ti = next((i for i, c in enumerate(rest) if _is_type_token(c)), None)
            if ti is None:
                typ, length, desc = "", "", " ".join(rest)
            else:
                if ti > 0:
                    source = " ".join(rest[:ti])
                typ = rest[ti]
                after = rest[ti + 1:]
                if after and re.fullmatch(r"\d+", after[0]):
                    length, desc = after[0], " ".join(after[1:])
                else:
                    length, desc = "", " ".join(after)
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
            if source:
                new["source"] = source
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


def parse_field_table_topic(tbl: list[list]) -> list[dict]:
    """Parse the topic-specific-database field layout:
        序號 / 欄位(EN) / 型態 / 來源 / 內容(ZH) / 描述
    (used by Health82/101/103/104 and Health59 — no 長度 column, Chinese name is
    in the 內容 column rather than a 中文欄位名稱 column).
    Returns [] if this table doesn't look like that layout.
    """
    if not tbl or len(tbl) < 2:
        return []

    def joined(row):
        return "|".join((c or "").replace("\n", "").strip() for c in row)

    def is_topic_header(row):
        flat = joined(row)
        return ("欄位" in flat and "描述" in flat
                and ("來源" in flat or "內容" in flat)
                and "中文欄位名稱" not in flat)

    header_idx = None
    for i, row in enumerate(tbl[:5]):
        if is_topic_header(row):
            header_idx = i
            break
    if header_idx is None:
        return []

    rows: list[dict] = []
    last_field: dict | None = None
    for raw in tbl[header_idx + 1:]:
        non_empty = [(c or "").replace("\n", " ").strip() for c in raw if (c or "").strip()]
        if not non_empty:
            continue
        if non_empty[0].isdigit() and len(non_empty) >= 3:
            seq = int(non_empty[0])
            parts = non_empty[1:]
            # Expected: name_en, type, source, name_zh(content), description
            name_en = parts[0] if len(parts) > 0 else ""
            typ = parts[1] if len(parts) > 1 else ""
            source = _collapse_cjk_spaces(parts[2]) if len(parts) > 2 else ""
            name_zh = _collapse_cjk_spaces(parts[3]) if len(parts) > 3 else ""
            desc = " ".join(parts[4:]) if len(parts) > 4 else ""
            new = {
                "seq": seq,
                "name_zh": name_zh,
                "name_en": name_en,
                "type": typ,
                "length": "",
                "source": source,
                "description_zh": desc,
            }
            rows.append(new)
            last_field = new
        else:
            if not last_field:
                continue
            joined_text = " ".join(non_empty)
            if all(re.fullmatch(r"[一-鿿()（）、~：:0-9一二三四五六七八九十／/]+", x) for x in non_empty):
                last_field["name_zh"] = (last_field["name_zh"] + joined_text).strip()
            else:
                last_field["description_zh"] = (last_field.get("description_zh", "") + " " + joined_text).strip()
    return rows


def parse_codebook_table(tbl: list[list], cols: dict | None):
    """Parse a survey codebook table (Health49 過錄編碼簿):
        變項名稱 / 變項說明 / 選項數值說明 / 備註
    `cols` carries the column mapping discovered on the header table so that
    continuation tables on later pages (which lack a header) reuse it.
    Returns (rows, cols).
    """
    if not tbl or len(tbl) < 1:
        return [], cols

    def is_cb_header(row):
        flat = "|".join((c or "").replace("\n", "").strip() for c in row)
        name = any(k in flat for k in ("變項名稱", "變數名稱", "欄位名稱"))
        meat = any(k in flat for k in ("變項說明", "變數說明", "選項數值說明"))
        return name and meat and "中文欄位名稱" not in flat and "型態" not in flat

    start = 0
    if cols is None:
        # Look for the header row in this table
        for i, row in enumerate(tbl[:5]):
            if is_cb_header(row):
                cols = {}
                flat_cells = [(c or "").replace("\n", "").strip() for c in row]
                for ci, cell in enumerate(flat_cells):
                    if any(k in cell for k in ("變項名稱", "變數名稱", "欄位名稱")) and "name" not in cols:
                        cols["name"] = ci
                    elif any(k in cell for k in ("變項說明", "變數說明")) and "desc" not in cols:
                        cols["desc"] = ci
                    elif ("選項" in cell or "數值" in cell) and "values" not in cols:
                        cols["values"] = ci
                start = i + 1
                break
        if cols is None:
            return [], None

    rows: list[dict] = []
    last = None
    for raw in tbl[start:]:
        cells = [(c or "").replace("\n", " ").strip() for c in raw]
        if not any(cells):
            continue

        def at(role):
            ci = cols.get(role)
            return cells[ci].strip() if ci is not None and ci < len(cells) and cells[ci] else ""
        name = at("name")
        desc = at("desc")
        values = at("values")
        if name and re.search(r"[A-Za-z0-9_]", name):
            f = {
                "seq": 0,
                "name_zh": "",
                "name_en": name,
                "type": "",
                "length": "",
                "description_zh": _collapse_cjk_spaces(desc),
            }
            if values:
                f["value_labels"] = values
            f["available_notes"] = []
            rows.append(f)
            last = f
        elif last:
            if desc:
                last["description_zh"] = (last["description_zh"] + " " + desc).strip()
            if values:
                last["value_labels"] = (last.get("value_labels", "") + " " + values).strip()
    return rows, cols


def dedupe_fields(rows: list[dict]) -> list[dict]:
    """One field per (number, column name): a field read twice (a table printed
    again on the next page) keeps the reading with the longer description. Several
    columns under one number (a row that lists MH_1 … MH_8) stay apart."""
    by_key: dict[tuple, dict] = {}
    for r in rows:
        k = (r["seq"], re.sub(r"\s+", "", r.get("name_en") or ""))
        if k not in by_key:
            by_key[k] = r
        elif len(r.get("description_zh") or "") > len(by_key[k].get("description_zh") or ""):
            by_key[k] = r
    seqs = {}
    for k in by_key:
        seqs.setdefault(k[0], []).append(k)
    # the older row reader can read the same number twice with a broken name: keep
    # one reading per number unless the number holds several real column names
    out = []
    for seq in sorted(seqs):
        ks = seqs[seq]
        real = [k for k in ks if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", k[1])]
        if len(real) > 1:
            out.extend(by_key[k] for k in ks if k in real)
        else:
            best = max(ks, key=lambda k: len(by_key[k].get("description_zh") or ""))
            out.append(by_key[best])
    return out


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
