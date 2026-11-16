"""Build drug_codes/nhi_drug_codes.json — the payload behind the /drugs lookup page.

    python scripts/build_drug_codes.py path/to/nhi.db [--snapshot YYYY-MM-DD]

Source: the public NHI drug item query (健保用藥品項查詢,
https://info.nhi.gov.tw/INAE3000/INAE3000S01), scraped into a local SQLite file
whose `formulary` table has one row per drug code x price period. That file is
large and lives outside this repo, so this script is run by hand when a new
scrape is available and its JSON output is committed. `site/prepare-data.js`
copies the JSON into the static payload at build time.

Only reference attributes are kept (code, product name, ingredient and strength,
form, manufacturer, ATC, listing dates). Prices are left out on purpose: they
change every quarter and the official query is the place to read them.

The output is columnar with dictionary-encoded strings, which keeps 45,000 codes
under a few megabytes before gzip.

Ingredient names are cleaned on the way in (see `clean_ingredient`): the source
writes the same ingredient in several spellings, mixes Chinese qualifiers into
English names, and leaves the label empty for some old compound products. Any
name that still contains Chinese after cleaning is printed as a warning, so a
new scrape that brings a new pattern is noticed.

Each ingredient label is also split into components (see `components`), so a
compound product can be found by any one of its ingredients. A label can say
that a component may be absent ("HYDROCHLOROTHIAZIDE 0-12.5MG", "+- RIBAVIRIN")
or name two alternatives ("OMEPRAZOLE/ESOMEPRAZOLE"); those are kept apart from
the components that are always present, and the page decides per product.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "drug_codes" / "nhi_drug_codes.json"
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


def components(name: str) -> tuple[list[str], list[str], list[str], str]:
    """Split a cleaned label into (always present, possibly absent, alternatives, label without the possibly absent parts)."""
    if name in CLASS_COMPONENTS:
        return list(CLASS_COMPONENTS[name]), [], [], name
    parts = split_plus(name) if name else []
    req, opt, alt, kept = [], [], [], []
    for k, (part, optional) in enumerate(parts):
        optional = optional or bool(FROM_ZERO.search(part))
        if not optional:
            kept.append(part)
        c = component_name(part, len(parts) > 1 and k == len(parts) - 1)
        if not optional and EITHER.fullmatch(c):
            for x in re.split(r"\s*/\s*", c):
                if x not in alt:
                    alt.append(x)
        elif c and c not in req and c not in opt:
            (opt if optional else req).append(c)
    if not req and not alt and opt:  # a label cannot be made of optional parts only
        req.append(opt.pop(0))
        kept = [parts[0][0]]
    return req, opt, alt, " + ".join(kept)


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
    ap.add_argument("db", help="SQLite file with the scraped `formulary` table")
    ap.add_argument("--snapshot", default=date.today().isoformat(), help="date the scrape was taken (YYYY-MM-DD)")
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    snap = args.snapshot

    # ATC level-1 / level-2 names, when the scrape ships them.
    atc_names: dict[str, list[str]] = {}
    try:
        for prefix, level, name_en, name_zh in con.execute("SELECT atc_prefix, level, name_en, name_zh FROM atc_lookup"):
            atc_names[prefix] = [name_en or "", name_zh or ""]
    except sqlite3.Error:
        pass

    rows = con.execute(
        """
        SELECT drug_code, drug_name_en, group_name, mixture, price_NTD, start_date, end_date,
               manufacturer, dosage_form, drug_classification, atc_code
        FROM formulary
        ORDER BY drug_code, start_date
        """
    ).fetchall()

    dicts: dict[str, dict[str, int]] = {k: {} for k in ("ingredient", "strength", "form", "mfr", "cls", "atc")}

    def idx(kind: str, value: str | None) -> int:
        v = clean_text(value)
        d = dicts[kind]
        if v not in d:
            d[v] = len(d)
        return d[v]

    out_rows = []
    cur = None
    acc: dict = {}

    def flush() -> None:
        if not acc:
            return
        ing, dose = split_group(acc["group"])
        out_rows.append([
            acc["code"],
            acc["name"],
            clean_ingredient(ing),  # replaced by its index once spellings are merged
            idx("strength", dose),
            idx("form", acc["form"]),
            idx("mfr", acc["mfr"]),
            idx("cls", acc["cls"]),
            idx("atc", acc["atc"]),
            1 if acc["mixture"] == "複方" else 0,
            acc["first"],           # first listing month, YYYY-MM
            acc["last_priced"],     # last month with a price above zero; "" if never; "open" if still priced
        ])

    for code, name, group, mixture, price, start, end, mfr, form, cls, atc in rows:
        if code != cur:
            flush()
            cur = code
            acc = {"code": code, "name": (name or "").strip(), "group": group or "", "mixture": mixture,
                   "form": form, "mfr": mfr, "cls": cls, "atc": atc, "first": (start or "")[:7], "last_priced": ""}
        # latest attributes win (rows are in start-date order)
        acc.update({"name": (name or acc["name"]).strip(), "group": group or acc["group"], "mixture": mixture,
                    "form": form, "mfr": mfr, "cls": cls, "atc": atc})
        s, e = (start or "")[:10], (end or "")[:10]
        if price and price > 0 and s <= snap:
            if e.startswith(OPEN_END) or e >= snap:
                acc["last_priced"] = "open"
            elif acc["last_priced"] != "open":
                acc["last_priced"] = e[:7]
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

    # Components of every ingredient label, as indexes into one component list.
    comp_index: dict[str, int] = {}
    parts, single_label = [], {}
    for i, name in enumerate(sorted(dicts["ingredient"], key=dicts["ingredient"].get)):
        req, opt, alt, kept = components(name)
        parts.append([[comp_index.setdefault(c, len(comp_index)) for c in group] for group in (req, opt, alt)])
        if opt and len(req) == 1:  # a single-ingredient product in this group is just `kept`
            single_label[str(i)] = kept

    def as_list(kind: str) -> list[str]:
        d = dicts[kind]
        return [k for k, _ in sorted(d.items(), key=lambda kv: kv[1])]

    payload = {
        "meta": {
            "source": "National Health Insurance Administration, 健保用藥品項查詢",
            "source_url": "https://info.nhi.gov.tw/INAE3000/INAE3000S01",
            "snapshot": snap,
            "n_codes": len(out_rows),
            "n_priced": sum(1 for r in out_rows if r[10] == "open"),
            "n_no_ingredient": sum(1 for r in out_rows if r[2] == 0),
            "n_components": len(comp_index),
            "columns": ["code", "name", "ingredient", "strength", "form", "mfr", "cls", "atc", "compound", "first", "last_priced"],
        },
        "ingredient": as_list("ingredient"),
        # per ingredient: [always present, possibly absent, alternatives], as indexes into "component"
        "parts": parts,
        "component": sorted(comp_index, key=comp_index.get),
        # per ingredient with one fixed and some possibly absent parts: the label of a single-ingredient product
        "single_label": single_label,
        "strength": as_list("strength"),
        "form": as_list("form"),
        "mfr": as_list("mfr"),
        "cls": as_list("cls"),
        "atc": as_list("atc"),
        "atc_names": atc_names,
        "rows": out_rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    m = payload["meta"]
    print(f"wrote {OUT.relative_to(ROOT)}: {m['n_codes']} codes, {m['n_priced']} priced at {snap}, "
          f"{len(payload['ingredient']) - 1} ingredients ({m['n_no_ingredient']} codes without one), "
          f"{m['n_components']} components, "
          f"{len(payload['atc'])} ATC codes, {OUT.stat().st_size/1e6:.2f} MB")


if __name__ == "__main__":
    main()
