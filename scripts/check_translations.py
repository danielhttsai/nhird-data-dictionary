"""Check the English in extracted/ against its Chinese for errors a machine
translation makes and a reader cannot see: a different place, institution,
number, year, unit or drug name than the Chinese says.

Each (Chinese, English) pair is tested by rules:
  place        every county/city the Chinese names is in the English, and the
               English names no county/city the Chinese does not (Taoyuan
               rendered as Taichung);
  institution  NHIA / HPA / CDC / MOHW … named in the Chinese are in the English;
  number       every number in the Chinese is in the English (a ROC year may
               appear as its AD year, 萬/千 amounts as their value);
  latin        every Latin word of the Chinese (drug, test, code names) is kept;
  unit         a unit in the Chinese (公克, 公分, 毫升, 歲 …) has its English.

usage: check_translations.py [--json out.json] [--strict]
Prints the counts per rule and examples; --json writes every flagged pair."""
from __future__ import annotations
import argparse
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
PAIRS = [("name_zh", "name_zh_en"), ("description_zh", "description_en"), ("label_zh", "label_en"),
         ("field_zh", "field_en"), ("data_description_zh", "data_description_en"), ("notes_zh", "notes_en"),
         ("primary_keys_raw", "primary_keys_en")]

PLACES = {  # Chinese forms -> English forms accepted
    ("臺北", "台北"): ("Taipei",), ("新北",): ("New Taipei",), ("桃園",): ("Taoyuan",),
    ("臺中", "台中"): ("Taichung",), ("臺南", "台南"): ("Tainan",), ("高雄",): ("Kaohsiung",),
    ("基隆",): ("Keelung", "Jilong"), ("新竹",): ("Hsinchu", "Xinzhu"), ("苗栗",): ("Miaoli",),
    ("彰化",): ("Changhua", "Zhanghua"), ("南投",): ("Nantou",), ("雲林",): ("Yunlin",),
    ("嘉義",): ("Chiayi", "Jiayi"), ("屏東",): ("Pingtung", "Pingdong"), ("宜蘭",): ("Yilan", "Ilan"),
    ("花蓮",): ("Hualien", "Hualian"), ("臺東", "台東"): ("Taitung", "Taidong"),
    ("澎湖",): ("Penghu",), ("金門",): ("Kinmen", "Jinmen"), ("連江", "馬祖"): ("Lienchiang", "Matsu", "Lianjiang"),
}
# English city names that must not appear unless the Chinese names that place
EN_CITY = {en: zhs for zhs, ens in PLACES.items() for en in ens}
INSTITUTIONS = {
    ("健保署", "健保局", "中央健康保險署", "中央健康保險局"): ("NHIA", "National Health Insurance", "NHI Administration", "NHI Bureau", "Bureau of National Health Insurance", "health insurance"),
    ("國民健康署", "國健署", "國民健康局", "國健局"): ("HPA", "Health Promotion", "BHP"),
    ("疾病管制署", "疾管署", "疾病管制局"): ("CDC", "Centers for Disease Control", "Disease Control"),
    ("衛生福利部", "衛福部"): ("MOHW", "Ministry of Health and Welfare", "Ministry of Health"),
    ("主計總處",): ("DGBAS", "Budget, Accounting and Statistics", "Accounting and Statistics"),
}
UNITS = {"公克": ("g", "gram"), "公斤": ("kg", "kilogram"), "公分": ("cm", "centimet"), "毫升": ("ml", "mL", "millilit"),
         "毫克": ("mg", "milligram"), "歲": ("year", "age", "aged", "yr", "y/o", "old")}
NUM = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?!\d|\.\d)")   # "903." at a sentence end is 903


def numbers_ok(zh: str, en: str) -> list[str]:
    en_nums = set(NUM.findall(en.replace(",", "")))
    # item numbers ("1.", "2、", "(3)") are not values
    zh = re.sub(r"(^|[\s：:；;。，,(（])\d{1,2}\s*[.、．)）](?!\d)", " ", zh)
    zh = re.sub(r"(^|[\s：:；;。，,])\d{1,2}\s*[.．](?=\d{2,3}\s*年)", " ", zh)
    bad = []
    for m in NUM.finditer(zh.replace(",", "")):
        n = m.group()
        after = zh.replace(",", "")[m.end():m.end() + 1]
        # a single digit is checked only as a code ("1：是"); words like 第1 may be spelled out
        if len(n) == 1 and after not in "：:":
            continue
        if n in en_nums or n.lstrip("0") in {x.lstrip("0") for x in en_nums}:
            continue
        tail = zh.replace(",", "")[m.end():m.end() + 2]
        if n.isdigit() and 30 <= int(n) <= 150 and str(int(n) + 1911) in en_nums:
            continue                                      # ROC year shown as AD
        if tail[:1] in "萬千" or n in ("0",):
            continue
        bad.append(n)
    return bad


def check(zh: str, en: str) -> list[tuple[str, str]]:
    out = []
    low = en.lower()
    for zhs, ens in PLACES.items():
        if any(z in zh for z in zhs) and not any(e.lower() in low for e in ens):
            # 新竹/嘉義/台中 … as part of a longer place name is still that place
            out.append(("place", f"names {zhs[0]} but the English has none of {ens}"))
    for en_name, zhs in EN_CITY.items():
        if re.search(r"\b" + re.escape(en_name.lower()) + r"\b", low) and not any(z in zh for z in zhs):
            if en_name == "Taipei" and "New Taipei" in en and "新北" in zh:
                continue
            out.append(("place", f"the English names {en_name}, the Chinese does not"))
    for zhs, ens in INSTITUTIONS.items():
        if any(z in zh for z in zhs) and not any(e.lower() in low for e in ens):
            out.append(("institution", f"{zhs[0]} not rendered"))
    bad = numbers_ok(zh, en)
    if bad:
        out.append(("number", f"numbers missing from the English: {bad[:6]}"))
    for w in set(re.findall(r"[A-Za-z][A-Za-z\-]{3,}", zh)):
        if w.lower() not in low:
            out.append(("latin", f"'{w}' not kept"))
    for u, ens in UNITS.items():
        if u in zh and not any(e.lower() in low for e in ens):
            out.append(("unit", f"{u} not rendered"))
    return out


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def pairs():
    seen = set()
    for p in sorted((ROOT / "extracted").glob("*/*.json")):
        if p.name.startswith("diff_"):
            continue
        for o in walk(json.loads(p.read_text(encoding="utf-8"))):
            for zk, ek in PAIRS:
                z, e = o.get(zk), o.get(ek)
                if isinstance(z, str) and isinstance(e, str) and z.strip() and e.strip() \
                        and re.search(r"[一-鿿]", z) and (z, e) not in seen:
                    seen.add((z, e))
                    yield p.parent.name, z, e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--only", default="", help="a file of Chinese strings (JSON list) to restrict to")
    args = ap.parse_args()
    only = set(json.loads(Path(args.only).read_text(encoding="utf-8"))) if args.only else None
    flagged, n, counts = [], 0, {}
    for code, z, e in pairs():
        if only is not None and z.strip() not in only:
            continue
        n += 1
        f = check(z, e)
        if f:
            flagged.append({"code": code, "zh": z, "en": e, "issues": f})
            for r, _ in f:
                counts[r] = counts.get(r, 0) + 1
    print(f"{n} pairs checked, {len(flagged)} flagged: {counts}")
    for x in flagged[:12]:
        print(" ", x["code"], "|", x["zh"][:50].replace("\n", " "), "=>", x["en"][:70].replace("\n", " "), "|", x["issues"][0][1])
    if args.json:
        Path(args.json).write_text(json.dumps(flagged, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
