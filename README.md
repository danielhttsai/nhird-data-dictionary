# NHIRD / HWDC Data Dictionary

A browsable, version-controlled visualization of every field in every public **MOHW Health and Welfare Data Center (HWDC)** database manual — the same PDFs at
<https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-1-20.html>.

For each file (Health01, Welfare10, Society17, …) the site shows:
- File-level metadata (CHN / EN name, record count, frequency, primary keys)
- Every field — Chinese name, English code, type, length, description
- Codebook lookups (CASE_TYPE, GAVE_KIND, …)
- When each field appears / changes ("since ROC year 107 = AD 2018, format becomes numeric")
- Diff between any two official release versions of the same file

## Live site
<!-- https://<user>.github.io/nhird-data-dictionary/ -->
(deployment URL will appear after first GH Pages publish)

## How it stays current
A weekly GitHub Action re-crawls the MOHW page; if a PDF changed, the diff lands in git history and the live site auto-rebuilds.

## Project layout
```
raw_pdfs/        official PDFs as downloaded
extracted/       normalized JSON per file × version
manifest.json    catalogue of every PDF (URL, sha256, effective date)
scripts/         Python pipeline (fetch / extract / diff / index)
site/            SvelteKit static site (deployed to GH Pages)
```

## Local dev
```
pip install pdfplumber httpx selectolax
python scripts/fetch_pdfs.py        # crawl + download
python scripts/extract_all.py       # PDFs → JSON
python scripts/diff_versions.py     # build diff files
cd site && pnpm install && pnpm dev # http://localhost:5173
```

## Not in scope
- Any individual-level data — this is metadata about the data only.
- LLM translation of Chinese descriptions. English column codes come from the PDFs as-is.

## Source
All content is derived from MOHW Department of Statistics public PDFs. Files in `raw_pdfs/` are unmodified copies for reproducibility.
