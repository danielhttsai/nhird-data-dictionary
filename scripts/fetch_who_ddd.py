"""Keep drug_codes/who_atc_ddd.json in step with the WHO ATC/DDD index.

    python scripts/fetch_who_ddd.py [--max N]

The index (https://atcddd.fhi.no/atc_ddd_index/) has one page per ATC 4th-level
group, listing the substances in it with their defined daily doses. This script
reads the ATC codes in drug_codes/nhi_drug_codes.json, fetches the pages of the
groups it has not seen yet, and then re-reads the oldest pages it holds, up to
N pages a run (default 40), so the whole file is renewed every few months. The
index itself changes once a year.

The site asks crawlers to wait 10 seconds between requests (robots.txt), and
this script does. Its terms allow non-commercial use with reference to the WHO
Collaborating Centre for Drug Statistics Methodology and forbid changing the
material, so names, doses, units, routes and notes are stored exactly as shown.

Only the standard library is used. A page that cannot be read is skipped and
tried again on the next run; what is already stored is never removed.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "drug_codes" / "nhi_drug_codes.json"
OUT = ROOT / "drug_codes" / "who_atc_ddd.json"
PAGE = "https://atcddd.fhi.no/atc_ddd_index/?code={}&showdescription=no"
AGENT = "Mozilla/5.0 (compatible; nhird-data-dictionary weekly refresh)"
DELAY = 10  # seconds, the Crawl-Delay in the site's robots.txt
GROUP = re.compile(r"^[A-Z]\d{2}[A-Z]{2}")
LEVEL = re.compile(r"(?:</p>|<br/>)\s*([A-Z]\d{0,2}[A-Z]{0,2})\s*<b><a [^>]*>(.*?)</a></b>")
ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
UPDATED = re.compile(r"Last updated:\s*([\d-]+)")


def text(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).replace("\xa0", " ").strip()


def parse(page: str, group: str) -> dict | None:
    """Names of the group and its parents, and one row per defined daily dose."""
    start = page.find('id="content"')
    if start < 0:
        return None
    body = page[start:]
    names = {code: text(name) for code, name in LEVEL.findall(body)}
    if group not in names:
        return None  # not a group the index knows
    rows, code, name = [], "", ""
    for tr in ROW.findall(body):
        cells = [text(c) for c in CELL.findall(tr)]
        if len(cells) != 6 or cells[0] == "ATC code":
            continue
        code, name = cells[0] or code, cells[1] or name  # a second dose of the same substance leaves these empty
        rows.append([code, name, cells[2], cells[3], cells[4], cells[5]])
    m = UPDATED.search(body)
    return {"names": names, "rows": rows, "updated": m.group(1) if m else ""}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40, help="pages to fetch in this run")
    args = ap.parse_args()

    store = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {
        "source": "WHO Collaborating Centre for Drug Statistics Methodology, ATC/DDD Index",
        "source_url": "https://atcddd.fhi.no/atc_ddd_index/",
        "pages": {},
    }
    pages = store["pages"]
    wanted = sorted({a[:5] for a in json.loads(PAYLOAD.read_text(encoding="utf-8"))["atc"] if GROUP.match(a)})
    new = [g for g in wanted if g not in pages]
    old = sorted((g for g in wanted if g in pages), key=lambda g: pages[g]["fetched"])
    todo = (new + old)[: args.max]
    print(f"{len(wanted)} groups in use, {len(new)} not fetched yet; fetching {len(todo)}", flush=True)

    today, done, failed = date.today().isoformat(), 0, []
    for i, group in enumerate(todo):
        if i:
            time.sleep(DELAY)
        try:
            req = urllib.request.Request(PAGE.format(group), headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                parsed = parse(r.read().decode("utf-8", "replace"), group)
        except Exception as e:  # noqa: BLE001 - try again next run
            failed.append(f"{group}: {e!r}")
            continue
        if parsed is None:
            parsed = {"names": {}, "rows": [], "updated": ""}  # NHI uses a group the index does not have
        pages[group] = {"fetched": today, **parsed}
        done += 1
        if done % 20 == 0:
            OUT.write_text(json.dumps(store, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
            print(f"  {done}/{len(todo)}", flush=True)
    OUT.write_text(json.dumps(store, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    print(f"fetched {done} pages; {len(pages)} stored", flush=True)
    for line in failed:
        print("  failed", line, file=sys.stderr)
    if failed and not done:
        raise SystemExit("the WHO index could not be reached")


if __name__ == "__main__":
    main()
