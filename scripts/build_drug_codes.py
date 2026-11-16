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
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "drug_codes" / "nhi_drug_codes.json"
OPEN_END = "2910"  # NHI writes open-ended periods as 2910-12-31


def split_group(group: str) -> tuple[str, str]:
    """Split NHI's group label into (ingredient, strength).

    The label reads "INGREDIENT , <form class in Chinese> , strength [, volume]".
    Ingredient names can themselves contain " , ", so the form class (the first
    part written in CJK) is used as the separator rather than a fixed position.
    """
    parts = [p.strip() for p in (group or "").split(" , ")]
    for i, part in enumerate(parts):
        if i > 0 and re.search(r"[一-鿿]", part):
            return ", ".join(parts[:i]), ", ".join(x for x in parts[i + 1:] if x.strip(" ,"))
    head = parts[0] if parts else ""
    rest = [x for x in parts[1:] if x.strip(" ,")]
    # A few labels run the form class into the name: "ENTECAVIR 一般錠劑膠囊劑".
    m = re.match(r"^([^一-鿿]+?)\s+[一-鿿]+\s*(.*)$", head)
    if m and not head.startswith("含"):
        head = m.group(1).strip()
        if m.group(2).strip():
            rest.insert(0, m.group(2).strip())
    return head, ", ".join(rest)


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
        v = (value or "").strip()
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
            idx("ingredient", ing),
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
            "columns": ["code", "name", "ingredient", "strength", "form", "mfr", "cls", "atc", "compound", "first", "last_priced"],
        },
        "ingredient": as_list("ingredient"),
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
          f"{len(payload['ingredient'])} ingredients, {len(payload['atc'])} ATC codes, {OUT.stat().st_size/1e6:.2f} MB")


if __name__ == "__main__":
    main()
