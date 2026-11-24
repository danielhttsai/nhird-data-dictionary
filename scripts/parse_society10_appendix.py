"""Read the code tables of the Society10 102年 manual's appendix (六) 欄位(變項)譯碼
into scripts/data/society10_102_appendix.json, which build_society10_tables.py
attaches. The PDF comes from raw_pdfs/Society10_legacy.zip (process_zips.py
unpacks it into raw_pdfs_zip/)."""
import io, json, re, sys, unicodedata
from pathlib import Path
import pdfplumber

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
PDF = next((ROOT / "raw_pdfs_zip" / "Society10_legacy").rglob("資料庫使用手冊Society10-102年國民健康訪問調查檔.pdf"))
OUT = ROOT / "scripts" / "data" / "society10_102_appendix.json"

with pdfplumber.open(PDF) as pdf:
    text = "\n".join(p.extract_text() or "" for p in pdf.pages[-10:])
# CJK compatibility forms (the PDF's font emits 不 as U+F967) as the standard characters
text = re.sub(r"[豈-﫿]", lambda m: unicodedata.normalize("NFKC", m.group()), text)
text = text[text.index("欄位(變項)譯碼"):]
lines = [ln.strip() for ln in text.split("\n") if ln.strip() and not re.match(r"^\d{4}年\d{2}月\d{2}日修訂$|^\d{1,3}$", ln.strip())]


def block(start: str, end: str) -> list[str]:
    i = next(k for k, ln in enumerate(lines) if ln.startswith(start))
    j = next(k for k, ln in enumerate(lines) if k > i and ln.startswith(end))
    return lines[i + 1:j]


# 1. 縣市代碼: name code pairs, four to a line
city = []
for ln in block("1. 縣市代碼", "2. 鄉鎮市區代碼"):
    if ln.startswith(("縣市別", "*")):
        continue
    for name, code in re.findall(r"(\S+?)\s+(\d{2})(?=\s|$)", ln):
        city.append({"code": code, "label_zh": name})
city.sort(key=lambda e: e["code"])

# 2. 鄉鎮市區代碼: name code pairs; "台北市 12" (a county and its town count) heads a group
town, county, notes = [], "", []
for ln in block("2. 鄉鎮市區代碼", "3. 教育程度代碼"):
    if re.search(r"\d{4}/\d{2}/\d{2}|修正|補充", ln) and not re.search(r"\s\d{4}(\s|$)", ln.split("2014")[0] if "2014" in ln else ""):
        notes.append(ln)
        continue
    ln = ln.replace("福 建 省", "").replace("Δ 為山地鄉", "")
    ln = re.sub(r"(\S)\s+Δ", r"\1Δ", ln)                       # 信義鄉 Δ -> 信義鄉Δ
    ln = re.sub(r"\d+【(\S+?)】", r"\1 00", ln)                  # 6【金門縣】 -> a county heading
    for name, code, _, whole in re.findall(r"(\S+?)\s+(\d{1,4})(\s*[(（]不分區(\d{3})[)）])?", ln):
        if len(code) == 4:
            town.append({"code": code, "label_zh": name})
        elif whole:                                  # 新竹市 3 (不分區600): the city's own code
            town.append({"code": "0" + whole, "label_zh": f"{name}（不分區）"})

# the table runs in six columns, so a county heading does not head the lines
# beside it: a town's county is the 縣市代碼 its code begins with
cities = {e["code"]: e["label_zh"].rstrip("*") for e in city}
for e in town:
    e["section"] = cities.get(e["code"][:2], "")

# 3. 教育程度代碼
edu = []
for ln in block("3. 教育程度代碼", "4. 受傷部位代碼"):
    m = re.match(r"^(\d{1,2})\s+(.+)$", ln)
    if m:
        edu.append({"code": m.group(1), "label_zh": m.group(2)})

# 7. 運動種類代碼: two pairs a line; a line without a code finishes the label above
sport, last = {}, None
for ln in lines[next(k for k, x in enumerate(lines) if x.startswith("7. 運動種類代碼")) + 1:]:
    if ln.startswith("代碼"):
        continue
    pairs = re.findall(r"(\d{1,2})\s+(.+?)(?=\s+\d{1,2}\s|$)", ln)
    if not pairs:
        if "(" in sport.get("30", "") and ")" not in sport["30"]:
            sport["30"] += ln
        continue
    for code, label in pairs:
        sport[code] = label.strip()
sport = [{"code": c, "label_zh": sport[c]} for c in sorted(sport, key=int)]

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps({"source": PDF.name, "縣市代碼": city, "鄉鎮市區代碼": town,
                           "教育程度代碼": edu, "運動種類代碼": sport, "notes": notes},
                          ensure_ascii=False, indent=1), encoding="utf-8")
print(f"縣市 {len(city)} | 鄉鎮市區 {len(town)} | 教育程度 {len(edu)} | 運動種類 {len(sport)} | notes {len(notes)}")
