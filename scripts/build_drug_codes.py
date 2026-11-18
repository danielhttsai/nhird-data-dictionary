"""Build the payload behind the /drugs lookup page.

    python scripts/fetch_drug_sources.py work/drugs
    python scripts/build_drug_codes.py work/drugs

The first command downloads the two public sources; this script turns them into
drug_codes/nhi_drug_codes.json (one row per drug code) and
drug_codes/nhi_drug_prices.json (the price periods of each code). Both run every
week in .github/workflows/refresh-drug-codes.yml, which commits the result, so
nothing here is done by hand. `site/prepare-data.js` copies the two files into
the static payload at build time.

Sources
  NHI drug item query (健保用藥品項查詢, https://info.nhi.gov.tw/INAE3000/INAE3000S01):
  one row per drug code and price period, with the product names, the price
  group label, the ingredients NHI records for the product, the ATC code and
  the licence number.
  TFDA open data (https://data.fda.gov.tw, Open Government Data License):
    36, 37  licences (product name per licence number)
    43      藥品詳細處方成分資料集, the formula of each licence
    41      藥品藥理治療分類ATC碼資料集, the ATC code of each licence

The main file is columnar with dictionary-encoded strings, which keeps 45,000
codes at a few megabytes before gzip.

Ingredient names are cleaned on the way in (see `clean_ingredient`): the source
writes the same ingredient in several spellings, mixes Chinese qualifiers into
English names, and leaves the label empty for some old compound products. Any
name that still contains Chinese after cleaning is printed as a warning, so a
download that brings a new pattern is noticed.

What a product contains is worked out from three records, in this order of
trust: the licence formula, the ingredients NHI lists for the product, and the
price group label. The label can say that a component may be absent
("HYDROCHLOROTHIAZIDE 0-12.5MG", "+- RIBAVIRIN") or name two alternatives
("OMEPRAZOLE/ESOMEPRAZOLE"); the other two settle which it is. A licence number
can be reused, so a formula counts only when the product names agree.
`drug_substances.py` puts the salt forms and synonyms of one substance under
one name.

The ATC code is NHI's. Where NHI gives none or only a group (fewer than 7
characters), the licence's own ATC code is used when it does not contradict
NHI's, and the row is flagged. ATC names and defined daily doses are those of
the WHO ATC/DDD index, read from drug_codes/who_atc_ddd.json, which
`fetch_who_ddd.py` keeps up to date; they are copied unchanged.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drug_substances import EXCIPIENT, SOLVENT_SECTION, Substances  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "drug_codes" / "nhi_drug_codes.json"
OUT_PRICES = ROOT / "drug_codes" / "nhi_drug_prices.json"
OUT_STATUS = ROOT / "drug_codes" / "refresh.json"  # when the sources were last checked, and last found changed
ATC_GROUPS = ROOT / "drug_codes" / "atc_groups.json"  # Chinese names of the ATC main groups and second levels
WHO_DDD = ROOT / "drug_codes" / "who_atc_ddd.json"     # kept by fetch_who_ddd.py
OPEN_END = "2910"  # NHI writes open-ended periods as 2910-12-31


CJK = re.compile(r"[一-鿿]")
FORM_CLASS = re.compile(r"^[一-鿿、]+劑$")  # a form class repeated where the strength should be

# Chinese qualifiers that NHI writes inside otherwise English ingredient names.
QUALIFIERS = {
    "(高純度)": "(HIGH PURITY)",
    "(中純度)": "(INTERMEDIATE PURITY)",
    "(基因型)": "(RECOMBINANT)",
    "(含ω-3 FATTY ACID)": "(WITH OMEGA-3 FATTY ACID)",
    "(用於加護病房需連續性腎臟替代療法之病人)": " (FOR CONTINUOUS RENAL REPLACEMENT THERAPY IN INTENSIVE CARE)",
}

# Whole labels that are NHI class descriptions rather than ingredient names,
# and two labels the source garbled. Keys are the label after `clean_text`.
WHOLE_LABELS = {
    "含ANTIHISTAMINE或NASAL DECONGESTANT之複方製劑": "ANTIHISTAMINE OR NASAL DECONGESTANT COMBINATION PRODUCTS",
    "含DEXTROMETHORPHAN複方鎮咳劑": "DEXTROMETHORPHAN COMBINATION ANTITUSSIVES",
    "含CODEINE複方鎮咳劑": "CODEINE COMBINATION ANTITUSSIVES",
    "SORAFENIB TOSYLATE 274MG(= sorafenib..200.0 mg )": "SORAFENIB TOSYLATE 274MG (=SORAFENIB 200MG)",
    # first component written twice and two plus signs missing in the source
    "CYANOCOBALAMIN (=VIT B12) 10MCG/ML (=UG/ML)CYANOCOBALAMIN (=VIT B12) 10MCG/ML (=UG/ML)+PANTOTHENATE CALCIUM 5MG/MLNIACINAMIDE (=NICOTINAMIDE) 30MG/ML+PYRIDOXINE HCL 3MG/ML+BIOTIN 100MCG/ML (=UG/ML)+LIDOCAINE HCL (MONOHYDRATE) 5MG/ML+COCARBOXYLASE (THIAMINE PYROPHOSPHATE) 5MG/ML":
        "CYANOCOBALAMIN (=VIT B12) 10MCG/ML + PANTOTHENATE CALCIUM 5MG/ML + NIACINAMIDE (=NICOTINAMIDE) 30MG/ML + PYRIDOXINE HCL 3MG/ML + BIOTIN 100MCG/ML + LIDOCAINE HCL (MONOHYDRATE) 5MG/ML + COCARBOXYLASE (THIAMINE PYROPHOSPHATE) 5MG/ML",
}

# Component names the source cut off at 20 characters.
TRUNCATED = {
    "CHLORPHENIRAMINE MAL ": "CHLORPHENIRAMINE MALEATE ",
    "POTASSIUM GUAIACOLSU ": "POTASSIUM GUAIACOLSULFONATE ",
    "GUAIACOL GLYCERYL ET ": "GUAIACOL GLYCERYL ETHER ",
    "ANTIMONY POTASSIUM T ": "ANTIMONY POTASSIUM TARTRATE ",
}

# Spelling mistakes and names the source cut off, fixed after the spacing rules.
TYPOS = {
    "DEXTROXE ": "DEXTROSE ",
    "2MG/MLL ": "2MG/ML ",
    "EPHEDRINE 1.0MG/ML AMMONIUM CHLORIDE": "EPHEDRINE 1.0MG/ML + AMMONIUM CHLORIDE",
    "GINKGO BILOBA EXTRACT(=9.6MG GINKGO FLAVONGLYCOSIDE ": "GINKGO BILOBA EXTRACT (=9.6MG GINKGO FLAVONGLYCOSIDE) ",
    "DROTRERECOGIN ALPHA (=COMBINANT HUMAN": "DROTRECOGIN ALFA (=RECOMBINANT HUMAN",
    "PROPANE SULFONATE (MONOHYD ": "PROPANE SULFONATE (MONOHYDRATE) ",
    "PROPANE-1-SULPHONIC ACID, SO ": "PROPANE-1-SULPHONIC ACID, SODIUM SALT ",
    "PREDNISOLONE1. 25MG/GM": "PREDNISOLONE 1.25MG/GM",
    "+ B1 5MG/ML + B2 5MG/ML + B6 5MG/ML": "+ VITAMIN B1 5MG/ML + VITAMIN B2 5MG/ML + VITAMIN B6 5MG/ML",
    "CHLRPHEIRAMINE ": "CHLORPHENIRAMINE ",
}

UNIT = r"(?:MG|MCG|UG|GM|G|ML|L|IU|KIU|MIU|MEQ|MMOL|U|%)"
DOSE_ONLY = re.compile(rf"^[\d.]+\s*{UNIT}(?:/[A-Z]+)?$", re.I)  # "5.00 MG/ML" written as part of the name


def clean_text(s: str | None) -> str:
    """Full-width characters, HTML leftovers and stray whitespace."""
    s = unicodedata.normalize("NFKC", s or "").replace("&nbsp;", " ")
    s = s.replace("\uf848", " TO ").replace("〜", " TO ")  # ">=3% [to] <4%"; \uf848 is a lost Big5 character
    s = re.sub(r"\s+", " ", s).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def clean_ingredient(label: str) -> str:
    """One spelling per ingredient: upper case, no Chinese, regular spacing."""
    s = clean_text(label)
    if s in WHOLE_LABELS:
        return WHOLE_LABELS[s]
    for zh, en in QUALIFIERS.items():
        s = s.replace(unicodedata.normalize("NFKC", zh), en)
    if s.startswith("含"):  # "含methyl testosterone 10mg" = "containing ..."
        s = s[1:]
    s = s.replace("ω", "OMEGA").upper()
    s = re.sub(r"\s*\+\s*/?-\s*", " +- ", s)            # "+-" and "+/-" = with or without
    s = re.sub(r"\s*\+(?!-)\s*", " + ", s)
    s = re.sub(r"\+(?:\s*\+)+", "+", s)                  # doubled plus sign
    s = re.sub(r"\s*\+\s*$", "", s)                      # plus sign with nothing after it
    s = re.sub(r"(\d), (?=\d)", r"\1,", s)               # "2, 3-BIS" -> "2,3-BIS" (chemical names)
    s = re.sub(r"\(=\s+", "(=", s)
    s = re.sub(r"\s*&\s*", " & ", s)
    s = re.sub(rf"(\d)\s+({UNIT})(?![A-Z])", r"\1\2", s)  # "100 MG/ML" -> "100MG/ML"
    s = re.sub(r"([<>]=?)\s+(?=\d)", r"\1", s)           # "<= 50MG" -> "<=50MG"
    s = re.sub(r"(?<=[A-Z])(?=[<>])", " ", s)              # "DEXTROSE<=50MG" -> "DEXTROSE <=50MG"
    s = re.sub(r"%(?=[A-Z])", "% ", s)                     # "<3%AMINO ACIDS" -> "<3% AMINO ACIDS"
    s = re.sub(rf"({UNIT})\s+/\s*(?=[A-Z])", r"\1/", s)    # "8.6MG /ML" -> "8.6MG/ML"
    s = re.sub(rf"(?<=[A-Z]{{3}})(?=\d+(?:\.\d+)?{UNIT}(?![A-Z]))", " ", s)  # "RHIZOMA40MG" -> "RHIZOMA 40MG"
    s = s + " "
    for table in (TRUNCATED, TYPOS):
        for wrong, right in table.items():
            s = s.replace(wrong, right)
    return re.sub(r"\s+", " ", s).strip()


# ---- components of a label ----------------------------------------------------------

CUNIT = r"(?:MG|MCG|UG|NG|GM|G|ML|MCL|L|IU|KIU|MIU|MU|MEQ|MMOL|UNITS?|USP-U|U|%|PH\.EUR\. UNITS)"
PER = r"(?:ML|MCL|NL|GM|G|L|MG|KG|DOSE|TAB|CAP|VIAL)"
NUM = r"\d+(?:[.,]\d+)*"
# "10MG", "0.5MG/ML", "5-10MG", "0MG-1000MG", "<=50MG/ML", "3.0~3.3MG/ML", "160 (320) MCG/DOSE", "16.7%(W/W)", "20/ML"
DOSE = re.compile(
    rf"\*?(?:[<>]=?\s*)?{NUM}\s*(?:{CUNIT})?\s*(?:\({NUM}\)\s*)?(?:[-~]\s*{NUM}\s*)?"
    rf"(?:{CUNIT}(?:\s*/\s*{PER})?|/\s*(?:ML|GM))(?![A-Z])(?:\s*\(=UG/ML\))?(?:\s*\(W/W\))?")
FROM_ZERO = re.compile(rf"(?<![\d.])0(?:\.0+)?\s*(?:{CUNIT})?\s*-\s*\d")  # "0-12.5MG": the component may be absent
EITHER = re.compile(r"[A-Z]{5,}(?:\s*/\s*[A-Z]{5,})+")                    # "OMEPRAZOLE/ESOMEPRAZOLE": one or the other

# Class labels: the named component they are sure to contain, if any.
CLASS_COMPONENTS = {
    "ANTIHISTAMINE OR NASAL DECONGESTANT COMBINATION PRODUCTS": [],
    "DEXTROMETHORPHAN COMBINATION ANTITUSSIVES": ["DEXTROMETHORPHAN"],
    "CODEINE COMBINATION ANTITUSSIVES": ["CODEINE"],
}


def split_plus(name: str) -> list[tuple[str, bool]]:
    """Split a label on " + " and " +- " outside brackets -> [(part, with_or_without)]."""
    parts, depth, start, optional, i = [], 0, 0, False, 0
    while i < len(name):
        ch = name[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and name.startswith(" +- ", i):
            parts.append((name[start:i], optional))
            optional, start, i = True, i + 4, i + 3
        elif depth == 0 and name.startswith(" + ", i):
            parts.append((name[start:i], optional))
            optional, start, i = False, i + 3, i + 2
        i += 1
    parts.append((name[start:], optional))
    return parts


def component_name(part: str, last_of_many: bool) -> str:
    """The substance named in one part of a label, without dose, bracketed salt or synonym."""
    c = re.sub(r"\s*\(=[^()]*(?:\)|$)", " ", part)           # synonym "(=VIT B2)", also when cut off
    c = re.sub(r"^\s*(?:(?:TO\s+|-\s*)?(?:[<>]=?\s*)?[\d.]+\s*%\s*)+", "", c)  # "10.0% AMINO ACIDS", ">=3% TO <4% AMINO ACIDS"
    c = DOSE.sub(" ", c)
    c = re.sub(r"(?<=\S)\s*\([^()]*\)(?=\s|$)", " ", c)       # "(VALERATE)", "(RECOMBINANT)"; not "BIS(SULPHANYL)PROPANE"
    c = re.sub(r",\s*PENFILL\b", "", c)
    if last_of_many:
        c = re.sub(r"\s+SOLUTIONS?(?: FOR (?:PERIPHERAL )?INFUSION)?\s*$", "", c)
    c = re.sub(r"^VIT(?:AMINE?)?\.?\s*(?=[A-Z]\d{0,2}\b)", "VITAMIN ", c.strip())  # "VIT B6", "VITAMINE B12"
    return re.sub(r"\s+", " ", c).strip(" ,*")


def components(name: str) -> tuple[list[str], list[str], list[str], str, dict[str, list[str]]]:
    """Split a cleaned label into (always present, possibly absent, alternatives,
    label without the possibly absent parts, synonyms the label states per component)."""
    if name in CLASS_COMPONENTS:
        return list(CLASS_COMPONENTS[name]), [], [], name, {}
    parts = split_plus(name) if name else []
    req, opt, alt, kept = [], [], [], []
    stated: dict[str, list[str]] = {}
    for k, (part, optional) in enumerate(parts):
        optional = optional or bool(FROM_ZERO.search(part))
        if not optional:
            kept.append(part)
        c = component_name(part, len(parts) > 1 and k == len(parts) - 1)
        if c:
            stated.setdefault(c, []).extend(re.findall(r"\(=\s*([^()]+)\)", DOSE.sub(" ", part)))
        if not optional and EITHER.fullmatch(c):
            for x in re.split(r"\s*/\s*", c):
                if x not in alt:
                    alt.append(x)
        elif c and c not in req and c not in opt:
            (opt if optional else req).append(c)
    if not req and not alt and opt:  # a label cannot be made of optional parts only
        req.append(opt.pop(0))
        kept = [parts[0][0]]
    return req, opt, alt, " + ".join(kept), stated


# ---- TFDA licence formulas --------------------------------------------------------------

# First two characters of NHI's licence field -> the wording of the licence number.
LICENCE_TYPE = {
    "01": "衛署藥製", "02": "衛署藥輸", "12": "內衛藥製", "13": "內衛藥輸", "51": "衛部藥製", "52": "衛部藥輸",
    "09": "衛署菌疫製", "10": "衛署菌疫輸", "59": "衛部菌疫製", "60": "衛部菌疫輸", "20": "衛署罕藥輸", "21": "衛署罕藥製",
    "70": "衛部罕藥輸", "71": "衛部罕藥製", "22": "衛署罕菌疫輸", "23": "衛署罕菌疫製", "72": "衛部罕菌疫輸",
}


def licence_number(doh_id: str | None) -> str:
    kind = LICENCE_TYPE.get((doh_id or "")[:2])
    return f"{kind}字第{doh_id[2:]}號" if kind else ""


def tfda_rows(folder: Path, number: int):
    """Rows of one TFDA dataset in `folder`, whether the download is still zipped or not."""
    for path in sorted(folder.glob(f"{number}_*")) + sorted(folder.glob(f"*{number}*.zip")):
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as fh:
                yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))
            return
        if path.suffix.lower() == ".csv":
            with open(path, encoding="utf-8-sig", newline="") as fh:
                yield from csv.DictReader(fh)
            return
    raise SystemExit(f"TFDA dataset {number} not found in {folder}")


def price(v: str | None) -> float:
    """NHI writes a period without a price as "0.00" or "-"."""
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


def group_label(name: str | None) -> str:
    """NHI's price group label with one way of writing its separators.

    The source separates ingredient, form class and strength with ", ", " , " or
    a full-width comma, depending on the row; `split_group` expects " , ".
    """
    s = (name or "").replace("，", ",").replace("　", " ").replace("\xa0", " ")
    s = re.sub(r"\s*,\s*", " , ", s)
    return re.sub(r"\s+", " ", s).strip()


# Names in NHI's per-product ingredient list that are not ingredients, and spelling mistakes in it.
NOT_AN_INGREDIENT = re.compile(r"^(OPADRY\b|O-PHOSPHORIC ACID)", re.I)
LISTED_TYPOS = {
    "TETRAHYOROBIOPTERIN": "TETRAHYDROBIOPTERIN",
    "SODIUM PHENYLBUTRATE": "SODIUM PHENYLBUTYRATE",
}


def listed_names(raw: str) -> list[tuple[str, bool]]:
    """One entry of NHI's per-product ingredient list as (name, possibly absent) pairs.

    The field is free text cut at 50 characters: it can carry a "+/-" prefix
    (the component is optional), a synonym after "=", a purity note, a trailing
    concentration, or two ingredients joined by "AND".
    """
    name = clean_text(raw).upper()
    optional = bool(re.match(r"^\+\s*/?\s*-", name))
    name = re.sub(r"^\+\s*/?\s*-\s*", "", name)
    name = re.sub(r"^\(PURE\)\s*", "", name)
    name = name.replace("【", " (").replace("】", ") ")
    if len(raw) >= 50:  # cut off by the source: keep the part before the qualifier that was being written
        head = re.split(r",(?!\d)|\s\(", name)[0].strip()
        name = head if len(head) >= 5 else name
    name = re.sub(r"\s+[\d.]+\s*%(\s*/\s*[\d.]+\s*%)*\s*$", "", name)  # "... 10%/10%"
    out = []
    for part in re.split(r"\s+AND\s+", name):
        part = LISTED_TYPOS.get(part.strip(), part.strip())
        m = re.match(r"^([^=]+?)\s*=\s*([^=()]+)$", part)  # "FOLINATE (CALCIUM)=LEUCOVORIN"
        if m:
            part = f"{m.group(1)} (={m.group(2).strip()})"
        if part and not NOT_AN_INGREDIENT.match(part):
            out.append((part, optional))
    return out


def nhi_rows(path: Path):
    """The downloaded NHI rows as plain tuples, in code and start-date order."""
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            listed = [r.get("druG_ING")] + [r.get(f"druG_ING_{i}") for i in range(1, 6)]
            rows.append((
                r["druG_CODE"], r.get("druG_ENAME"), r.get("druG_CNAME"), group_label(r.get("druG_GROUP_NAME")),
                r.get("mixture"),
                price(r.get("paY_PRICE")), (r.get("paY_S_DATE") or "")[:10], (r.get("paY_E_DATE") or "")[:10],
                r.get("druggisT_NAME"), r.get("druG_DOSE"), r.get("druG_CLASSIFY_NAME"), r.get("atC_CODE"),
                r.get("doH_ID"), tuple(x.strip() for x in listed if x and x.strip()),
            ))
    rows.sort(key=lambda t: (t[0], t[6]))
    return rows


def num(v: float):
    """262.0 -> 262, 1.5 -> 1.5: prices as short as they can be written."""
    return int(v) if v == int(v) else v


def same_product(nhi_name: str, licence_name: str) -> bool:
    """A licence number can be reused; trust it only when the product names agree."""
    a, b = (re.sub(r"[^A-Z0-9]", "", x.upper()) for x in (nhi_name, licence_name))
    return not a or not b or SequenceMatcher(None, a, b).ratio() > 0.5


def merge_spellings(counts: Counter) -> dict[str, str]:
    """Map every cleaned name to one spelling per ingredient.

    Names that differ only in spacing ("BETAMETHASONE(VALERATE) 1MG/GM" and
    "BETAMETHASONE (VALERATE)1MG/GM") become the spelling with the most spaces,
    which is the readable one; ties go to the spelling used by most codes.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for name in counts:
        groups[re.sub(r"\s+", "", name)].append(name)
    out = {}
    for names in groups.values():
        best = max(names, key=lambda n: (n.count(" "), counts[n], n))
        for n in names:
            out[n] = best
    return out


def split_group(group: str) -> tuple[str, str]:
    """Split NHI's group label into (ingredient, strength).

    The label reads "INGREDIENT , <form class in Chinese> , strength [, volume]".
    Ingredient names can themselves contain " , ", so the form class (the first
    part written in CJK) is used as the separator rather than a fixed position.
    """
    parts = [p.strip() for p in (group or "").split(" , ")]
    suffix = ""
    if "單、複方製劑" in parts[1:]:  # "single or combination products": part of the name, not a form class
        parts.remove("單、複方製劑")
        suffix = " (SINGLE OR COMBINATION PRODUCTS)"
    for i, part in enumerate(parts):
        if i > 0 and CJK.search(part):
            name = parts[:i]
            rest = [x for x in parts[i + 1:] if x.strip(" ,") and not FORM_CLASS.match(x)]
            while len(name) > 1 and DOSE_ONLY.match(name[-1]):  # "KANAMYCIN , 5.00 MG/ML , <form> , 5.00 ML"
                rest.insert(0, name.pop())
            return ", ".join(name) + suffix, ", ".join(rest)
    head = parts[0] if parts else ""
    rest = [x for x in parts[1:] if x.strip(" ,")]
    # A few labels run the form class into the name: "ENTECAVIR 一般錠劑膠囊劑".
    m = re.match(r"^([^一-鿿]+?)\s+[一-鿿]+\s*(.*)$", head)
    if m and not head.startswith("含"):
        head = m.group(1).strip()
        if m.group(2).strip():
            rest.insert(0, m.group(2).strip())
    return head + suffix, ", ".join(rest)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="folder written by fetch_drug_sources.py")
    ap.add_argument("--date", default=date.today().isoformat(), help="date of the download (YYYY-MM-DD)")
    args = ap.parse_args()
    folder = Path(args.src)
    snap = args.date

    # Names of the ATC main groups and second levels; the names of the codes
    # themselves come with the TFDA ATC dataset further down.
    atc_names: dict[str, list[str]] = json.loads(ATC_GROUPS.read_text(encoding="utf-8")) if ATC_GROUPS.exists() else {}

    rows = nhi_rows(folder / "nhi_drug_items.jsonl.gz")

    dicts: dict[str, dict[str, int]] = {k: {} for k in ("ingredient", "strength", "form", "mfr", "cls", "atc")}
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    previous = old.get("meta", {})

    def idx(kind: str, value: str | None) -> int:
        v = clean_text(value)
        d = dicts[kind]
        if v not in d:
            d[v] = len(d)
        return d[v]

    out_rows = []
    licence: dict[str, str] = {}  # drug code -> licence number
    cname: dict[str, str] = {}    # drug code -> Chinese product name
    listed: dict[str, tuple] = {}  # drug code -> the ingredients NHI records for the product
    price_now: dict[str, float] = {}
    periods: dict[str, list] = {}  # drug code -> [start, end, price, ...]; end "" when open
    cur = None
    acc: dict = {}

    def flush() -> None:
        if not acc:
            return
        ing, dose = split_group(acc["group"])
        licence[acc["code"]] = licence_number(acc["doh"])
        cname[acc["code"]] = clean_text(acc["cname"])
        listed[acc["code"]] = acc["listed"]
        out_rows.append([
            acc["code"],
            acc["name"],
            clean_ingredient(ing),  # replaced by its index once spellings are merged
            idx("strength", dose),
            idx("form", acc["form"]),
            idx("mfr", acc["mfr"]),
            idx("cls", acc["cls"]),
            clean_text(acc["atc"]).upper(),  # replaced by its index once completed from the licence
            1 if acc["mixture"] == "複方" else 0,
            acc["first"],           # first listing month, YYYY-MM
            acc["last_priced"],     # last month with a price above zero; "" if never; "open" if still priced
        ])

    for code, name, zh, group, mixture, price, start, end, mfr, form, cls, atc, doh, ings in rows:
        if code != cur:
            flush()
            cur = code
            acc = {"code": code, "name": (name or "").strip(), "cname": zh or "", "group": group or "", "mixture": mixture,
                   "doh": doh, "form": form, "mfr": mfr, "cls": cls, "atc": atc, "first": start[:7], "last_priced": "",
                   "listed": ings}
            periods[code] = []
        # latest attributes win (rows are in start-date order)
        acc.update({"name": (name or acc["name"]).strip(), "cname": zh or acc["cname"], "group": group or acc["group"],
                    "mixture": mixture, "form": form, "mfr": mfr, "cls": cls, "atc": atc, "doh": doh or acc["doh"],
                    "listed": ings or acc["listed"]})
        periods[code] += [start, "" if end.startswith(OPEN_END) else end, price]
        if price > 0 and start <= snap:
            if end.startswith(OPEN_END) or end >= snap:
                acc["last_priced"] = "open"
                price_now[code] = price
            elif acc["last_priced"] != "open":
                acc["last_priced"] = end[:7]
    flush()

    # One spelling per ingredient, indexed in order of first appearance. Index 0 is
    # the empty name: old compound products that NHI lists without an ingredient label.
    canonical = merge_spellings(Counter(r[2] for r in out_rows))
    idx("ingredient", "")
    for r in out_rows:
        r[2] = idx("ingredient", canonical[r[2]])
    leftover = sorted(n for n in dicts["ingredient"] if CJK.search(n))
    if leftover:
        print(f"WARNING: {len(leftover)} ingredient names still contain Chinese; add them to QUALIFIERS or WHOLE_LABELS:")
        for n in leftover:
            print("   ", n)

    # ---- what each product contains ---------------------------------------------------
    subst = Substances()

    # 1. The NHI label: components always present, possibly absent, or alternatives.
    codes_per_label = Counter(r[2] for r in out_rows)
    label_parts: list[list[list[str]]] = []
    single_label: dict[str, str] = {}
    for i, name in enumerate(sorted(dicts["ingredient"], key=dicts["ingredient"].get)):
        req, opt, alt, kept, stated = components(name)
        keyed = []
        for group in (req, opt, alt):
            keys = []
            for c in group:
                key = subst.add(c + "".join(f" (={syn})" for syn in stated.get(c, [])), codes_per_label[i], preferred=True)
                if key and key not in keys:
                    keys.append(key)
            keyed.append(keys)
        label_parts.append(keyed)
        if opt:  # the label of a product in this group that has none of the possibly absent parts
            single_label[str(i)] = kept

    # 2. The licence formula, where TFDA has one for the same product.
    formula: dict[str, list[str]] = {}
    by_licence: dict[str, list[str]] = defaultdict(list)
    for t in tfda_rows(folder, 43):
        key = subst.add(t["成分名稱"], 1, code=t["成分代碼"])
        if key and not SOLVENT_SECTION.search(t["處方標示"]) and key not in by_licence[t["許可證字號"]]:
            by_licence[t["許可證字號"]].append(key)
    product = {t["許可證字號"]: t["英文品名"] for n in (36, 37) for t in tfda_rows(folder, n)}
    same_licence = {r[0]: same_product(r[1], product.get(licence[r[0]], "")) for r in out_rows}
    renamed = 0
    for r in out_rows:
        keys = by_licence.get(licence[r[0]])
        if not keys:
            continue
        if not same_licence[r[0]]:
            renamed += 1
            continue
        formula[r[0]] = [k for k in keys if not EXCIPIENT.match(k)] or keys
    print(f"licence formula for {len(formula)} of {len(out_rows)} codes "
          f"({renamed} licences left out: the product name differs)")

    # 3. The ingredients NHI records for the product itself (at most six), for the codes without a formula.
    nhi_list: dict[str, tuple[list[str], list[str]]] = {}  # code -> (components, possibly absent components)
    for r in out_rows:
        if r[0] in formula or not listed[r[0]]:
            continue
        sure, perhaps = [], []
        for raw in listed[r[0]]:
            for name, optional in listed_names(raw):
                key = subst.add(name, 1)
                group = perhaps if optional else sure
                if key and not EXCIPIENT.match(key) and key not in sure and key not in perhaps:
                    group.append(key)
        if sure or perhaps:
            nhi_list[r[0]] = (sure, perhaps)
    print(f"NHI's own ingredient list used for {len(nhi_list)} codes without a formula; "
          f"{len(out_rows) - len(formula) - len(nhi_list)} codes rely on the group label alone")

    for r in out_rows:  # one product, one substance, two names: evidence that the names are synonyms
        req, opt, alt = label_parts[r[2]]
        if len(req) == 1 and not opt and not alt and len(formula.get(r[0], [])) == 1:
            subst.observe(req[0], formula[r[0]][0])
    subst.close()

    # 4. ATC: NHI's code, completed from the licence where NHI gives none or only a group.
    ATC_FULL = re.compile(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
    ATC_PART = re.compile(r"^[A-Z](\d{2}([A-Z]{1,2})?)?$")
    FROM_LICENCE = 4
    licence_atc: dict[str, str] = {}
    atc_label: dict[str, Counter] = defaultdict(Counter)
    for t in tfda_rows(folder, 41):
        code = t["代碼"].strip().upper()
        if t["英文分類名稱"].strip():
            atc_label[code][t["英文分類名稱"].strip()] += 1
        if t["主或次項"] == "主" and ATC_FULL.match(code):
            licence_atc.setdefault(t["許可證字號"], code)
    atc_flag: dict[str, int] = {}
    for r in out_rows:
        nhi = r[7]
        full = licence_atc.get(licence[r[0]], "")
        if not ATC_FULL.match(nhi) and full and same_licence[r[0]] and (not nhi or (ATC_PART.match(nhi) and full.startswith(nhi))):
            r[7] = full
            atc_flag[r[0]] = FROM_LICENCE
    n_short = sum(1 for r in out_rows if not ATC_FULL.match(r[7]))
    print(f"ATC: {len(atc_flag)} codes completed from the licence; {n_short} still without a full 7-character code "
          f"({sum(1 for r in out_rows if not r[7])} with none at all)")
    # Names and defined daily doses from the WHO index; a TFDA name only where WHO has none.
    who = json.loads(WHO_DDD.read_text(encoding="utf-8"))["pages"] if WHO_DDD.exists() else {}
    who_name: dict[str, str] = {}
    who_ddd: dict[str, list[list[str]]] = defaultdict(list)
    for page in who.values():
        who_name.update(page["names"])
        for code, name, dose, unit, route, note in page["rows"]:
            who_name[code] = name
            if dose:
                who_ddd[code].append([dose, unit, route, note])
    for prefix, names in atc_names.items():  # the Chinese group names stay; the English ones are WHO's
        names[0] = who_name.get(prefix, names[0])
    ddd: dict[str, list[list[str]]] = {}
    for r in out_rows:
        code = r[7]
        for part in {code, code[:5], code[:4], code[:3], code[:1]}:
            if part and part not in atc_names:
                name = who_name.get(part) or (atc_label[part].most_common(1)[0][0] if atc_label.get(part) else "")
                if name:
                    atc_names[part] = [name, ""]
        if code in who_ddd:
            ddd[code] = who_ddd[code]
        r[7] = idx("atc", code)
    updated = max((p["updated"] for p in who.values()), default="")
    print(f"WHO index: names for {sum(1 for c in dicts['atc'] if c in who_name)} of {len(dicts['atc'])} ATC codes, "
          f"a defined daily dose for {len(ddd)}; index last updated {updated or 'unknown'}")

    def canon(keys: list[str]) -> list[str]:
        out = []
        for k in keys:
            c = subst.canonical.get(k, k)
            if c not in out:
                out.append(c)
        return out

    # 5. Per product: components it has, components it may have, and other names of the same substance.
    SHORT_LABEL, COMPOUND_UNNAMED = 1, 2
    comp_index: dict[str, int] = {}
    set_index: dict[tuple, int] = {}
    tally, unmatched = Counter(), Counter()
    for r in out_rows:
        req, opt, alt = (canon(g) for g in label_parts[r[2]])
        made_of = canon(formula[r[0]]) if r[0] in formula else None
        extra, extra_opt = (canon(g) for g in nhi_list.get(r[0], ([], [])))
        yes, maybe, also, flags = list(req), [], [], atc_flag.get(r[0], 0)
        if made_of is None:
            # No formula. NHI's own list for the product adds to what the label names; without
            # one, NHI's single/compound mark settles a possibly absent component when the
            # label has one fixed component.
            if len(req) == 1 and len(extra) == 1 and not extra_opt:
                also = [c for c in extra if c != req[0]]  # one substance under two names
            else:
                yes += [c for c in extra if c not in yes]
            if opt and not any(o in yes for o in opt):
                if any(o in extra_opt for o in opt):
                    maybe += opt
                elif len(req) == 1 and (not r[8] or extra):
                    flags |= SHORT_LABEL
                elif len(req) == 1 and len(opt) == 1:
                    yes += opt
                else:
                    maybe += opt
            if alt and not any(a in yes for a in alt):
                maybe += [a for a in alt if a not in maybe]
            maybe += [c for c in extra_opt if c not in yes and c not in maybe]
            if r[8] and len(yes) + len(maybe) <= 1:
                flags |= COMPOUND_UNNAMED
        else:
            if len(req) == 1 and len(made_of) == 1:
                # one substance; if the two sources name it differently, keep the licence name for searching
                also = [c for c in made_of if c != req[0]]
            else:
                yes += [c for c in made_of if c not in yes]
                if alt and not any(a in yes for a in alt):  # the formula names neither alternative
                    maybe += alt
                if len(yes) > max(len(req), len(made_of)):  # a label name the formula does not have: often a synonym
                    unmatched.update(c for c in req if c not in made_of)
            if opt and not any(o in yes for o in opt):
                flags |= SHORT_LABEL
            tally["single by NHI, several in the formula" if not r[8] and len(yes) > 1 and len(req) <= 1 else
                  "compound by NHI, one in the formula" if r[8] and len(yes) == 1 else "consistent"] += 1
        maybe = [m for m in maybe if m not in yes]
        key = tuple(tuple(comp_index.setdefault(c, len(comp_index)) for c in group) for group in (yes, maybe, also))
        r.append(set_index.setdefault(key, len(set_index)))
        r.append(flags)
        r.append(cname[r[0]])
        r.append(num(price_now.get(r[0], 0)))
    if tally:
        print("NHI mark against the licence formula:", dict(tally))
        print(f"label components missing from a compound's formula ({sum(unmatched.values())} cases), most frequent:",
              ", ".join(f"{c} {n}" for c, n in unmatched.most_common(40)))

    # Other names of each component (salt forms, synonyms), for searching by exact name.
    alias: dict[str, int] = {}
    for name, i in comp_index.items():
        for other in subst.members.get(name, []):
            if other != name and other not in comp_index:
                alias[other] = i

    def as_list(kind: str) -> list[str]:
        d = dicts[kind]
        return [k for k, _ in sorted(d.items(), key=lambda kv: kv[1])]

    n_codes = len(out_rows)
    payload = {
        "meta": {
            "source": "National Health Insurance Administration, 健保用藥品項查詢",
            "source_url": "https://info.nhi.gov.tw/INAE3000/INAE3000S01",
            "snapshot": snap,
            "n_codes": n_codes,
            "n_priced": sum(1 for r in out_rows if r[10] == "open"),
            "n_no_ingredient": sum(1 for r in out_rows if r[2] == 0),
            "n_components": len(comp_index),
            "n_with_formula": len(formula),
            "n_from_nhi_list": len(nhi_list),
            "n_label_only": n_codes - len(formula) - len(nhi_list),
            "n_atc_from_licence": len(atc_flag),
            "n_atc_short": n_short,
            "n_atc_with_ddd": len(ddd),
            "ddd_source": "WHO Collaborating Centre for Drug Statistics Methodology, ATC/DDD Index" if who else "",
            "ddd_url": "https://atcddd.fhi.no/atc_ddd_index/" if who else "",
            "ddd_updated": updated,
            "formula_source": "Taiwan Food and Drug Administration open data, 藥品詳細處方成分資料集",
            "formula_url": "https://data.fda.gov.tw",
            "formula_snapshot": snap,
            "columns": ["code", "name", "ingredient", "strength", "form", "mfr", "cls", "atc", "compound", "first",
                        "last_priced", "set", "flags", "name_zh", "price"],
        },
        "ingredient": as_list("ingredient"),
        "component": sorted(comp_index, key=comp_index.get),
        # other names of a component -> its index in "component"
        "alias": alias,
        # per product (row column "set"): [components, possible components, other names of the same substance]
        "sets": [list(map(list, k)) for k in sorted(set_index, key=set_index.get)],
        # row column "flags": 1 = show the label without its possibly absent parts ("single_label");
        #                     2 = compound by NHI's mark, but only one component is named and there is no formula;
        #                     4 = the ATC code was completed from the TFDA licence
        "single_label": single_label,
        "strength": as_list("strength"),
        "form": as_list("form"),
        "mfr": as_list("mfr"),
        "cls": as_list("cls"),
        "atc": as_list("atc"),
        "atc_names": atc_names,
        # per ATC code: [dose, unit, route, note] for each defined daily dose, as the WHO index shows them
        "ddd": ddd,
        "rows": out_rows,
    }
    m = payload["meta"]

    # A download that lost a large part of the list must not replace a good file.
    problems = []
    if previous.get("n_codes") and n_codes < previous["n_codes"] * 0.98:
        problems.append(f"{n_codes} codes, down from {previous['n_codes']}")
    if len(formula) < n_codes * 0.9:
        problems.append(f"a licence formula for only {len(formula)} of {n_codes} codes")
    if m["n_priced"] < n_codes * 0.2:
        problems.append(f"only {m['n_priced']} codes with a current price")
    if problems:
        raise SystemExit("Refusing to write the payload: " + "; ".join(problems))

    def day(d: str) -> int:
        return int(d.replace("-", "")) if d else 0

    prices = {code: [day(v) if i % 3 < 2 else num(v) for i, v in enumerate(p)] for code, p in periods.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # The sources are checked every week but change less often. The big files are
    # rewritten only when their content changes, so the history stays small; the
    # date of the check goes into a small file of its own.
    def content(p: dict) -> str:
        dated = ("snapshot", "formula_snapshot")
        return json.dumps({**p, "meta": {k: v for k, v in p.get("meta", {}).items() if k not in dated}},
                          ensure_ascii=False, sort_keys=True)

    changed = content(payload) != content(old)
    if changed:
        OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    else:
        print(f"no change since {previous['snapshot']}; {OUT.name} left as it is")
    # per code: start, end, price, start, end, price, ... as YYYYMMDD; end 0 = still running
    text = json.dumps(prices, separators=(",", ":"))
    if not OUT_PRICES.exists() or OUT_PRICES.read_text(encoding="utf-8") != text:
        OUT_PRICES.write_text(text, encoding="utf-8")
    OUT_STATUS.write_text(json.dumps({"checked": snap, "changed": snap if changed else previous["snapshot"]}) + "\n",
                          encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {m['n_codes']} codes, {m['n_priced']} priced at {snap}, "
          f"{len(payload['ingredient']) - 1} ingredients ({m['n_no_ingredient']} codes without one), "
          f"{m['n_components']} components (+{len(alias)} other names), {len(set_index)} compositions, "
          f"{len(payload['atc'])} ATC codes, {OUT.stat().st_size/1e6:.2f} MB; "
          f"{OUT_PRICES.name} {OUT_PRICES.stat().st_size/1e6:.2f} MB")


if __name__ == "__main__":
    main()
