"""Read a MOHW database manual by the position of what is printed on the page.

Used by extract_pdf.py. Cell borders are taken from the black rules only (see
_is_white_fill), every value is put in the column whose header it sits under,
and a manual that documents several tables (one 檔案代號 header block each, as
Welfare20 does) is split into one section per table.
"""
from __future__ import annotations
import re

# ---------------------------------------------------------------- page cleaning

def _is_white_fill(o) -> bool:
    """Word draws every table cell as a white-filled rectangle under the black
    rules. pdfplumber takes those rectangles' sides as cell borders, which cuts one
    printed row into several and puts a vertically centred value on another row
    than its label. Only the black rules separate cells."""
    if o.get("object_type") not in ("rect", "curve"):
        return False
    if not o.get("fill") or o.get("stroke"):
        return False
    c = o.get("non_stroking_color")
    if c is None:
        return False
    if not isinstance(c, (list, tuple)):
        c = (c,)
    try:
        c = tuple(float(x) for x in c)
    except (TypeError, ValueError):     # a pattern fill, not a colour
        return False
    if len(c) == 1:
        return c[0] >= 0.99
    if len(c) == 3:
        return min(c) >= 0.99
    if len(c) == 4:                      # CMYK white
        return max(c) <= 0.01
    return False


def clean_page(page):
    return page.filter(lambda o: not _is_white_fill(o))


# ---------------------------------------------------------------- text joining

_CJK = r"[一-鿿㐀-䶿豈-﫿　-〿＀-￯（）「」『』【】、，。：；？！]"
_ITEM = re.compile(r"^\s*(?:[A-Za-z0-9][A-Za-z0-9.\-_]{0,9}\s*[：:]|\(?\d{1,3}[.、)）](?!\d)|[（(][一二三四五六七八九十\d]+[）)]|※|＊|\*|[-•●○◎■□]\s)")


def join_wrapped(a: str, b: str) -> str:
    """Join two lines of one wrapped cell: no space between CJK text, one space
    between Latin words."""
    a, b = a.rstrip(), b.lstrip()
    if not a:
        return b
    if not b:
        return a
    if re.match(_CJK, a[-1]) or re.match(_CJK, b[0]):
        return a + b
    if a.endswith(("-", "/", "(", "（")):
        return a + b
    return a + " " + b


def cell_text(cell, keep_items: bool) -> str:
    """Text of one table cell (a cell dict from page_items, or plain text).

    Names (keep_items False) are joined into one line. In a note (keep_items
    True) a line that starts a code-list item (``1：…``, ``A：…``, ``2.``, ``※``)
    starts a new line; any other line is joined to the one above when that line
    ran to the right edge of the cell (the cell wrapped it) and kept on its own
    line when it stopped short (the author broke the line)."""
    if not cell:
        return ""
    if isinstance(cell, dict):
        s, ends, right = cell.get("text") or "", cell.get("ends"), cell.get("right")
    else:
        s, ends, right = cell, None, None
    raw = s.split("\n")
    if ends is not None and len(ends) != len([x for x in raw if x.strip()]):
        ends = None
    out: list[str] = []
    k = -1
    prev_full = True
    for ln in raw:
        ln = ln.strip()
        if not ln:
            continue
        k += 1
        if not out:
            out.append(ln)
        elif not keep_items:
            out[-1] = join_wrapped(out[-1], ln)
        elif _ITEM.match(ln):
            out.append(ln)
        elif ends is None or prev_full:
            out[-1] = join_wrapped(out[-1], ln)
        else:
            out.append(ln)
        if ends is not None:
            x1, size = ends[k]
            prev_full = x1 >= right - 6 - 1.6 * size
    return "\n".join(out).strip()


def _line_ends(chars, bbox):
    """[(right edge, font size)] of each text line inside a cell, top to bottom."""
    x0, top, x1, bottom = bbox
    inside = [c for c in chars
              if x0 <= (c["x0"] + c["x1"]) / 2 <= x1 and top <= (c["top"] + c["bottom"]) / 2 <= bottom
              and c["text"].strip()]
    inside.sort(key=lambda c: (c["top"], c["x0"]))
    lines: list[list] = []
    for c in inside:
        if lines and abs(c["top"] - lines[-1][0]) <= max(2.0, 0.4 * c["size"]):
            lines[-1][1] = max(lines[-1][1], c["x1"])
            lines[-1][2] = max(lines[-1][2], c["size"])
        else:
            lines.append([c["top"], c["x1"], c["size"]])
    return [(r, s) for _, r, s in lines]


def append_text(a: str, b: str, keep_items: bool) -> str:
    """Append the part of a cell continued on the next page."""
    if not a:
        return b
    if not b:
        return a
    if keep_items and _ITEM.match(b):
        return a + "\n" + b
    return join_wrapped(a, b)


# ---------------------------------------------------------------- reading stream

def page_items(page, pno: int) -> list[dict]:
    """Tables and the text lines outside them, top to bottom."""
    cp = clean_page(page)
    items = []
    tables = cp.find_tables()
    chars = cp.chars if tables else []
    boxes = []
    for t in tables:
        rows = []
        for r, texts in zip(t.rows, t.extract()):
            rows.append([None if bbox is None else
                         {"bbox": bbox, "text": txt or "", "right": bbox[2],
                          "ends": _line_ends(chars, bbox) if "\n" in (txt or "") else None}
                         for bbox, txt in zip(r.cells, texts)])
        items.append({"kind": "table", "page": pno, "top": t.bbox[1], "bottom": t.bbox[3],
                      "bbox": t.bbox, "rows": rows})
        boxes.append(t.bbox)
    for ln in cp.extract_text_lines(return_chars=False):
        cy = (ln["top"] + ln["bottom"]) / 2
        cx = (ln["x0"] + ln["x1"]) / 2
        if any(b[0] - 1 <= cx <= b[2] + 1 and b[1] - 1 <= cy <= b[3] + 1 for b in boxes):
            continue
        items.append({"kind": "line", "page": pno, "top": ln["top"], "text": ln["text"]})
    items.sort(key=lambda it: (it["top"], 0 if it["kind"] == "table" else 1))
    return items


def table_texts(item, joined: bool = False) -> list[list[str]]:
    """Cell texts of a table; joined: lines the cell wrapped put back together."""
    if joined:
        return [[(cell_text(c, True) if c else None) for c in r] for r in item["rows"]]
    return [[(c["text"] if c else None) for c in r] for r in item["rows"]]


# ================================================================ field tables

def _flat(s):
    return re.sub(r"\s+", "", s or "")

# header label -> role. Order matters: first match wins.
ROLE_PATTERNS = [
    ("seq", re.compile(r"^(序號?|編號|項次|序次|No\.?)$")),
    ("name_zh", re.compile(r"(中文.*(欄位|名稱|檔名)|欄位中文|欄位說明$)")),
    ("name_en", re.compile(r"(英文.*(欄位|名稱)|欄位英文|欄位代號|變項名稱|欄位名稱$)")),
    # 型/長 alone: a header split over two rows (序/號, 型/態, 長/度)
    ("type", re.compile(r"^(資料)?(型態|類型|格式|型別|屬性|型)$")),
    ("length", re.compile(r"^(欄位)?(長度|長)$")),
    ("source", re.compile(r"^來源$")),
    ("desc", re.compile(r"(備註|資料描述|描述|說明|代碼|內容|值域)")),
]


def header_roles(row) -> dict | None:
    """{role: (x0, x1)} when this row is a field-table header."""
    roles = {}
    for c in row:
        if not c:
            continue
        t = _flat(c["text"])
        if not t:
            continue
        for role, pat in ROLE_PATTERNS:
            if pat.search(t) and role not in roles:
                roles[role] = (c["bbox"][0], c["bbox"][2])
                break
    if "name_zh" in roles and "name_en" in roles and ("type" in roles or "length" in roles or "seq" in roles):
        return roles
    return None


def assign(cell_bbox, roles) -> str | None:
    """The role whose header column overlaps this cell most."""
    x0, x1 = cell_bbox[0], cell_bbox[2]
    best, ov = None, 0.0
    for role, (a, b) in roles.items():
        o = min(x1, b) - max(x0, a)
        if o > ov:
            best, ov = role, o
    if best is None:
        return None
    # a merged cell spanning several columns goes to the one holding its centre
    if x1 - x0 > 1.6 * (roles[best][1] - roles[best][0]):
        cx = (x0 + x1) / 2
        for role, (a, b) in roles.items():
            if a <= cx <= b:
                return role
    return best


def same_columns(roles, row) -> bool:
    """Does a header-less table continue a field table with these columns? Every
    cell of its first full row must line up with a header column edge."""
    xs = sorted({round(x) for a, b in roles.values() for x in (a, b)})
    cells = [c for c in row if c]
    if len(cells) < min(3, len(roles)):
        return False
    def near(x):
        return any(abs(x - e) <= 3 for e in xs)
    return all(near(c["bbox"][0]) and near(c["bbox"][2]) for c in cells)


_SEQ = re.compile(r"^(\d{1,4})[.、)）]?$")


def row_values(row, roles):
    vals = {}
    for c in row:
        if not c or not c["text"].strip():
            continue
        role = assign(c["bbox"], roles)
        if role is None:
            continue
        keep = role == "desc"
        t = cell_text(c, keep)
        vals[role] = append_text(vals[role], t, keep) if role in vals else t
    return vals


def make_field(vals) -> dict:
    seq = int(_SEQ.match(_flat(vals.get("seq", ""))).group(1))
    length = _flat(vals.get("length", ""))
    f = {
        "seq": seq,
        "name_zh": vals.get("name_zh", ""),
        "name_en": _flat(vals.get("name_en", "")) if re.fullmatch(r"[\x21-\x7e\s]+", vals.get("name_en", "") or "x") else vals.get("name_en", ""),
        "type": _flat(vals.get("type", "")),
        "length": int(length) if length.isdigit() else length,
        "description_zh": vals.get("desc", ""),
    }
    if vals.get("source"):
        f["source"] = vals["source"]
    return f


def extend_field(f, vals):
    """A row without a number continues the field above (a cell carried over a
    page break)."""
    for role, key, keep in (("name_zh", "name_zh", False), ("desc", "description_zh", True),
                            ("source", "source", False)):
        if vals.get(role):
            f[key] = append_text(f.get(key, ""), vals[role], keep)
    if vals.get("name_en") and re.fullmatch(r"[A-Za-z0-9_]+", _flat(vals["name_en"])):
        f["name_en"] = f["name_en"] + _flat(vals["name_en"])
    if vals.get("type") and not f.get("type"):
        f["type"] = _flat(vals["type"])
    if vals.get("length") and f.get("length") in ("", None):
        ln = _flat(vals["length"])
        f["length"] = int(ln) if ln.isdigit() else ln


# ---------------------------------------------------------------- code tables

_CODE_HDR = re.compile(r"^(代碼|代號|編碼|代碼值|數值|值|Code|CODE|代碼內容|類別代碼|編號)$")
_LABEL_HDR = re.compile(r"(名稱|說明|內容|意義|定義|描述|中文|Label)")


def code_table_columns(row):
    """[(code_x, [label_x ...]), ...] when this row heads a code table
    (代碼 名稱 [代碼 名稱 ...])."""
    cells = [c for c in row if c and _flat(c["text"])]
    if len(cells) < 2:
        return None
    pairs, cur = [], None
    for c in cells:
        t = _flat(c["text"])
        if _CODE_HDR.match(t):
            cur = [(c["bbox"][0], c["bbox"][2]), []]
            pairs.append(cur)
        elif cur is not None and _LABEL_HDR.search(t):
            cur[1].append((c["bbox"][0], c["bbox"][2]))
        elif cur is not None and cur[1]:
            cur[1].append((c["bbox"][0], c["bbox"][2]))     # 備註 etc.
        else:
            return None
    if not pairs or not all(p[1] for p in pairs):
        return None
    return pairs


def code_rows(rows, pairs):
    """Entries of a code table (header row excluded), reading each column pair
    top to bottom, left pair first."""
    out = []
    for code_x, label_xs in pairs:
        lo = code_x[0] - 2
        hi = (label_xs[-1][1]) + 2
        last = None
        for row in rows:
            code, labels = "", []
            for c in row:
                if not c:
                    continue
                x0, x1 = c["bbox"][0], c["bbox"][2]
                cx = (x0 + x1) / 2
                if not (lo <= cx <= hi):
                    continue
                if code_x[0] - 2 <= cx <= code_x[1] + 2:
                    code = _flat(c["text"])
                else:
                    t = cell_text(c, False)
                    if t:
                        labels.append(t)
            label = " ".join(labels).strip()
            if code:
                last = {"code": code, "label_zh": label}
                out.append(last)
            elif label and last is not None:
                last["label_zh"] = join_wrapped(last["label_zh"], label)
    return out


# ================================================================ sections

_CB_HEAD = re.compile(r"^\s*(\d+)\s*[.．、]\s*(.+?)\s*[（(]\s*([A-Z][A-Z0-9_~]+)\s*[）)]")
_PHASE3 = re.compile(r"^\s*三\s*、\s*欄位")


def is_header_table(item) -> bool:
    flat = "".join(_flat(c) for r in table_texts(item) for c in r if c)
    return "檔案代號" in flat and ("欄位數" in flat or "中文檔名" in flat)


def header_code(item) -> str:
    for r in table_texts(item):
        cells = [c for c in r]
        for i, c in enumerate(cells):
            if _flat(c) == "檔案代號":
                for c2 in cells[i + 1:]:
                    if _flat(c2):
                        return _flat(c2)
    return ""


def read_items(pdf) -> list[dict]:
    items = []
    for i, p in enumerate(pdf.pages):
        items.extend(page_items(p, i))
    return items


def split_sections(items) -> list[list[dict]]:
    """One list of items per table the manual describes. A manual with a single
    header block (or none) is one section."""
    starts = [k for k, it in enumerate(items) if it["kind"] == "table" and is_header_table(it)]
    codes = [header_code(items[k]) for k in starts]
    if len(starts) < 2 or len(set(codes)) < 2:
        return [items]
    # the title lines printed just above a header table belong to its section
    cut = []
    for k in starts:
        j = k
        while j > 0 and items[j - 1]["kind"] == "line" and items[j - 1]["page"] == items[k]["page"]:
            j -= 1
        cut.append(j)
    cut[0] = 0
    return [items[a:b] for a, b in zip(cut, cut[1:] + [len(items)])]


def parse_section(items) -> dict:
    """Field rows and code tables of one section."""
    fields, codebooks, cb_order = [], {}, []
    phase = "fields"
    roles = None            # columns of the field table being read
    last = None
    cb_cur = None           # (field_zh, codes) of the code table being read
    cb_cols = None
    cb_heads = []           # every code-table heading printed (for the QA check)
    cb_lines = []           # code-table section text outside ruled tables
    header_items = []
    for it in items:
        if it["kind"] == "line":
            t = it["text"]
            if _PHASE3.match(t):
                phase, roles = "codebooks", None
                cb_lines.append(t)
                continue
            if phase == "codebooks":
                cb_lines.append(t)
                m = _CB_HEAD.match(t)
                if m:
                    cb_cur = (m.group(2).strip(), m.group(3).strip())
                    cb_heads.append(cb_cur)
                    cb_cols = None
            continue
        # table
        if is_header_table(it):
            header_items.append(it)
            continue
        rows = it["rows"]
        if phase == "fields":
            start = None
            for k, r in enumerate(rows[:4]):
                h = header_roles(r)
                if h:
                    roles, start = h, k + 1
                    # a header split over two rows (序/號, 型/態)
                    while start < len(rows) and all(not c or _flat(c["text"]) in ("", "號", "態", "度", "稱")
                                                    for c in rows[start]):
                        start += 1
                    break
            if start is None:
                full = next((r for r in rows if sum(1 for c in r if c) >= 3), None)
                if roles is None or full is None or not same_columns(roles, full):
                    continue
                start = 0
            for r in rows[start:]:
                vals = row_values(r, roles)
                if not vals:
                    continue
                if _SEQ.match(_flat(vals.get("seq", ""))):
                    last = make_field(vals)
                    fields.append(last)
                elif last is not None:
                    extend_field(last, vals)
        else:
            if cb_cur is None:
                continue
            start = None
            for k, r in enumerate(rows[:2]):
                cols = code_table_columns(r)
                if cols:
                    cb_cols, start = cols, k + 1
                    break
            if start is None:
                if cb_cols is None:
                    continue
                start = 0
            entries = code_rows(rows[start:], cb_cols)
            if entries:
                key = cb_cur
                if key not in codebooks:
                    codebooks[key] = []
                    cb_order.append(key)
                codebooks[key].extend(entries)
    return {"fields": fields, "codebooks": [(k, codebooks[k]) for k in cb_order],
            "cb_heads": cb_heads, "cb_text": "\n".join(cb_lines), "header_items": header_items}
