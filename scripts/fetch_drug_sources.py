"""Download what build_drug_codes.py needs, from the two public sources.

    python scripts/fetch_drug_sources.py OUT_DIR

1. NHI drug item query (健保用藥品項查詢, https://info.nhi.gov.tw/INAE3000/INAE3000S01).
   The page reads a JSON API that returns one row per drug code and price
   period, at most 1,000 rows a call. All pages are saved as
   OUT_DIR/nhi_drug_items.jsonl.gz, one row per line.
2. TFDA open data (https://data.fda.gov.tw, Open Government Data License):
   datasets 36, 37 (licences), 43 (licence formula) and 41 (ATC code per licence),
   saved as OUT_DIR/<number>_2.csv.zip.

Only the standard library is used. The run fails, and leaves no partial file
behind, when a source cannot be reached or the NHI pages do not add up to the
total the API reports, so a broken download never reaches the build.
"""
from __future__ import annotations

import gzip
import json
import math
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

NHI_API = "https://info.nhi.gov.tw/api/INAE3000/INAE3000S01/SQL0001"
NHI_PAGE = "https://info.nhi.gov.tw/INAE3000/INAE3000S01"
NHI_FILTERS = ("DRUG_CODE DRUG_NAME DRUG_DOSE DRUG_CLASSIFY_NAME DRUG_ING DRUG_ING_QTY DRUG_ING_UNIT DRUG_STD_QTY "
               "DRUG_STD_UNIT DRUGGIST_NAME MIXTURE PAY_START_DATE_YEAR PAY_START_DATE_MON ORAL_TYPE ATC_CODE SHOWTYPE").split()
PAGE_SIZE = 1000
TFDA = "https://data.fda.gov.tw/opendata/exportDataList.do?method=ExportData&InfoId={}&logType=2"
TFDA_SETS = (36, 37, 41, 43)
AGENT = "Mozilla/5.0 (compatible; nhird-data-dictionary weekly refresh)"
DROP = ("pdfList", "druG_UFILE_NAME_LIST")  # links to payment-rule PDFs; not used


def get(req: urllib.request.Request, timeout: int, tries: int = 5) -> bytes:
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - network errors of any kind are retried
            if attempt == tries:
                raise
            wait = 5 * 2 ** (attempt - 1)
            print(f"  attempt {attempt} failed ({e!r}); retrying in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


def nhi_page(page: int) -> dict:
    body = json.dumps({**dict.fromkeys(NHI_FILTERS, ""), "CURPAGE": page, "PAGESIZE": PAGE_SIZE}).encode()
    req = urllib.request.Request(NHI_API, body, {
        "Accept": "application/json", "Content-Type": "application/json; charset=utf-8",
        "User-Agent": AGENT, "Origin": "https://info.nhi.gov.tw", "Referer": NHI_PAGE})
    return json.loads(get(req, 120))


def fetch_nhi(out: Path) -> None:
    first = nhi_page(1)
    total = int(first["total"])
    pages = math.ceil(total / PAGE_SIZE)
    print(f"NHI: {total:,} rows in {pages} pages", flush=True)
    rows = list(first["data"])
    for page in range(2, pages + 1):
        rows.extend(nhi_page(page)["data"])
        if page % 25 == 0:
            print(f"  page {page}/{pages}", flush=True)
        time.sleep(0.3)  # be gentle with a public service
    seen = {(r["druG_CODE"], r["paY_S_DATE"], r["paY_E_DATE"], r["paY_PRICE"]) for r in rows}
    if len(rows) != total or len(seen) < total * 0.999:
        raise SystemExit(f"NHI: got {len(rows):,} rows ({len(seen):,} distinct) but the API reports {total:,}; "
                         "the list changed during the download or a page was repeated. Run again.")
    tmp = out.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps({k: v for k, v in r.items() if k not in DROP and v not in (None, "")},
                                ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(out)
    print(f"NHI: wrote {out.name}, {out.stat().st_size / 1e6:.1f} MB", flush=True)


def fetch_tfda(folder: Path) -> None:
    for n in TFDA_SETS:
        data = get(urllib.request.Request(TFDA.format(n), headers={"User-Agent": AGENT}), 600)
        path = folder / f"{n}_2.csv.zip"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        with zipfile.ZipFile(tmp) as z:  # a zip with one CSV, or the download is not what we asked for
            names = z.namelist()
            if len(names) != 1 or z.testzip() is not None:
                raise SystemExit(f"TFDA dataset {n}: unexpected archive {names}")
        tmp.replace(path)
        print(f"TFDA {n}: {len(data) / 1e6:.1f} MB", flush=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    folder = Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    fetch_tfda(folder)
    fetch_nhi(folder / "nhi_drug_items.jsonl.gz")


if __name__ == "__main__":
    main()
