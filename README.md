# NHIRD / HWDC Data Dictionary

A browsable, version-controlled visualization of every field in every public **MOHW Health and Welfare Data Center (HWDC)** database manual — the same PDFs at
<https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-1-20.html>.

For each file (Health01, Welfare10, Society17, …) the site shows:
- File-level metadata (CHN / EN name, record count, frequency, primary keys)
- Every field — Chinese name, English code, type, length, description
- Codebook lookups (CASE_TYPE, GAVE_KIND, …)
- When each field appears / changes ("since ROC year 107 = AD 2018, format becomes numeric")
- Diff between any two official release versions of the same file

It also carries a **drug code lookup** (`/drugs`): 45,000 NHI drug codes with product name in English and Chinese, ingredient, strength, form, manufacturer, ATC code, defined daily dose, current NHI price and price history, searchable in every direction (code → ATC, ATC or ingredient → every matching code) with copy and CSV export. The search box needs no syntax: an ingredient name finds every product that contains it, alone or in a compound, under any salt form or synonym; an ATC code matches by prefix; anything else matches as text. Sources: the public NHI drug item query (健保用藥品項查詢, <https://info.nhi.gov.tw/INAE3000/INAE3000S01>) for codes, names, prices and NHI's ingredient list; TFDA open data (<https://data.fda.gov.tw>, Open Government Data License) for licence formulas and licence ATC codes; and the WHO Collaborating Centre for Drug Statistics Methodology ATC/DDD Index (<https://atcddd.fhi.no/atc_ddd_index/>) for ATC names and DDDs, copied unchanged for non-commercial use with reference, as its terms require. Nothing is refreshed by hand: `.github/workflows/refresh-drug-codes.yml` runs every Monday, downloads the sources (`scripts/fetch_drug_sources.py`, `scripts/fetch_who_ddd.py`), rebuilds the payload (`scripts/build_drug_codes.py`), commits it when something changed and redeploys the site. To run it locally: `python scripts/fetch_drug_sources.py work/drugs && python scripts/build_drug_codes.py work/drugs`.

## Live site
<!-- https://<user>.github.io/nhird-data-dictionary/ -->
(deployment URL will appear after first GH Pages publish)

## How it stays current
`.github/workflows/refresh-mohw-pdfs.yml` runs every Monday. It re-crawls the MOHW listing, commits what changed and redeploys the site.

The JSON in `extracted/` is curated: it carries the translations, hand corrections, OCR-recovered tables and code tables built from other sources. So a revised PDF is never re-extracted over it. `scripts/merge_upstream.py` extracts the old and the new PDF, and applies to the curated JSON only what differs between the two; a value edited by hand is kept and the upstream change reported instead. `manifest.json` is merged the same way: entries that do not come from the listing (files unpacked from the survey ZIPs, the TWCR manuals, files added by hand) are left alone.

What the action will not do by itself, it records in `refresh_pending.json` and reports once, by failing the run after the commit (GitHub then emails the repository owner; the run summary says what and why):
- a revision it cannot merge safely, because the extractor reads the old and the new layout differently. The repo keeps the previous PDF and JSON. Delete the entry from `refresh_pending.json` to have the next run try again;
- a revised survey ZIP (these are unpacked and curated by hand with `process_zips.py` and `extract_xls.py`);
- a file that has left the listing (it is kept).

Chinese text that changed upstream gets its English from `translations/cache.json`; a string the cache does not have yet is shown in Chinese, and `scripts/gap_check.py` (part of the same run) reports it until it is translated.

## Project layout
```
raw_pdfs/        official PDFs as downloaded
extracted/       normalized JSON per file × version
manifest.json    catalogue of every PDF (URL, sha256, effective date)
refresh_pending.json  upstream changes the weekly refresh saw but did not apply (absent when there are none)
drug_codes/      payload behind the /drugs lookup, refreshed weekly by an action (JSON)
scripts/         Python pipeline (fetch / extract / diff / index)
site/            SvelteKit static site (deployed to GH Pages)
```

## Local dev
```
pip install -r requirements.txt
python scripts/fetch_pdfs.py        # crawl the listing; download new and revised files
python scripts/merge_upstream.py    # merge revised PDFs into the curated JSON
python scripts/extract_all.py       # extract files that are new (existing JSON is skipped)
python scripts/diff_versions.py     # build diff files
python scripts/refresh_report.py    # what the run did → .refresh/summary.md
cd site && pnpm install && pnpm dev # http://localhost:5173
```

## Not in scope
- Any individual-level data — this is metadata about the data only.
- LLM translation of Chinese descriptions. English column codes come from the PDFs as-is.

## Source
All content is derived from MOHW Department of Statistics public PDFs. Files in `raw_pdfs/` are unmodified copies for reproducibility.
