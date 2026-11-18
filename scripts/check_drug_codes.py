"""Quality checks on the drug lookup payload, run after every weekly refresh.

    python scripts/check_drug_codes.py [--strict]

The build already refuses to write a payload that lost a large part of the
list. These checks look at what a refresh can quietly get wrong instead: a new
spelling pattern in NHI's labels, a code left without any component, a column
that came back empty. Each check prints one line. With --strict the script
exits 1 when any check has a finding, which fails the workflow run and makes
GitHub email the repository owner; the refreshed data is committed before this
step runs, so a finding never holds the update back.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "drug_codes" / "nhi_drug_codes.json"
PRICES = ROOT / "drug_codes" / "nhi_drug_prices.json"
CJK = re.compile(r"[一-鿿]")
CODE = re.compile(r"^[A-Z0-9]{10}$")
ATC = re.compile(r"^[A-Z](\d{2}([A-Z]{1,2}(\d{2})?)?)?$")

findings = 0


def check(name: str, bad: list, limit: int = 0, show: int = 5) -> None:
    """A check passes when it has at most `limit` offending items."""
    global findings
    ok = len(bad) <= limit
    findings += not ok
    detail = "" if not bad else " e.g. " + "; ".join(str(b)[:70] for b in bad[:show])
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {len(bad)}" + (f" (allowed {limit})" if limit else "") + detail)


def main() -> None:
    d = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    prices = json.loads(PRICES.read_text(encoding="utf-8"))
    rows, m = d["rows"], d["meta"]
    comp, sets = d["component"], d["sets"]
    known = set(comp) | set(d["alias"])

    check("drug codes that are not 10 letters and digits", [r[0] for r in rows if not CODE.match(r[0])])
    seen, dup = set(), []
    for r in rows:
        if r[0] in seen:
            dup.append(r[0])
        seen.add(r[0])
    check("drug codes listed twice", dup)
    check("ingredient names that still contain Chinese", [n for n in d["ingredient"] if CJK.search(n)])
    check("ingredient names with lower-case letters", [n for n in d["ingredient"] if n != n.upper()])
    check("component names that contain Chinese or lower case", [n for n in comp if CJK.search(n) or n != n.upper()])
    check("component names shorter than 3 characters", [n for n in comp if len(n) < 3])
    check("other names that point at no component", [a for a, i in d["alias"].items() if not 0 <= i < len(comp)])
    used = {c for s in sets for group in s for c in group}
    check("components no product contains", [comp[i] for i in range(len(comp)) if i not in used])
    # A handful of old products have neither a label, a list nor a formula; more than that is a new gap.
    check("codes without any component", [r[0] for r in rows if not sets[r[11]][0] and not sets[r[11]][1]], limit=10)
    check("codes that rely on the group label alone", list(range(m["n_label_only"])), limit=50, show=0)
    check("codes without a product name", [r[0] for r in rows if not r[1]], limit=20)
    check("codes without an ATC code", [r[0] for r in rows if not d["atc"][r[7]]], limit=20)
    check("ATC codes that are not shaped like one", [a for a in d["atc"] if a and not ATC.match(a)], limit=10)
    check("priced codes without a price", [r[0] for r in rows if r[10] == "open" and not r[14]])
    check("codes with a price but not marked as priced", [r[0] for r in rows if r[14] and r[10] != "open"])
    check("codes missing from the price history", [r[0] for r in rows if r[0] not in prices])
    check("price histories that are not start, end, price triples", [c for c, p in prices.items() if len(p) % 3 or not p])
    check("defined daily doses for ATC codes not in use", [a for a in d.get("ddd", {}) if a not in set(d["atc"])])
    share = sum(1 for r in rows if d["atc"][r[7]] in d.get("ddd", {})) / len(rows)
    check("share of codes with a defined daily dose below 50 %", [f"{share:.0%}"] if share < 0.5 else [])
    check("licence formula found for fewer than 95 % of codes",
          [m["n_with_formula"]] if m["n_with_formula"] < 0.95 * m["n_codes"] else [])
    # every component and every other name must be reachable by exact search
    check("names that an exact search would not find", [n for n in known if n != n.strip() or "  " in n])

    print(f"{m['n_codes']} codes at {m['snapshot']}; {findings} check(s) with findings")
    if findings and "--strict" in sys.argv:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
