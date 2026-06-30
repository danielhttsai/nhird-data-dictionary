"""Batch-run extract_pdf over every PDF listed in manifest.json.
Writes extracted/<code>/<version_id>.json + a top-level qa_report.json.

Robustness:
- Resumable: skip a (code, version_id) whose output JSON already exists, unless
  --force is given.
- Per-PDF timeout: each PDF is extracted in a child process via subprocess so a
  single pathological table layout can't hang the whole batch. Default 90s.

ZIP entries themselves are skipped (their sub-PDFs are separate manifest entries
added by process_zips.py).
"""
from __future__ import annotations
import argparse
import io
import json
import re as _re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.json"
RAW = ROOT / "raw_pdfs"
OUT = ROOT / "extracted"
QA_OUT = ROOT / "qa_report.json"
EXTRACT_PY = SCRIPTS / "extract_pdf.py"


def _safe(name: str) -> str:
    name = _re.sub(r"[^\w\-]", "_", name, flags=_re.UNICODE)
    return name[:80]


def run_one(pdf_path: Path, timeout: int) -> dict:
    """Extract a single PDF in a child process. Raises on timeout / error."""
    proc = subprocess.run(
        [sys.executable, str(EXTRACT_PY), str(pdf_path)],
        capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-400:]
        raise RuntimeError(f"exit {proc.returncode}: {err}")
    return json.loads(proc.stdout.decode("utf-8", "replace"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=90, help="seconds per PDF")
    ap.add_argument("--force", action="store_true", help="re-extract even if JSON exists")
    ap.add_argument("--only", default="", help="comma-separated codes to restrict to")
    args = ap.parse_args()

    only = {c.strip() for c in args.only.split(",") if c.strip()}

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    versions = manifest["versions"]
    OUT.mkdir(exist_ok=True)

    qa: list[dict] = []
    pdf_count = zip_count = ok = fail = skipped = 0

    for v in versions:
        if only and v["code"] not in only:
            continue
        if v.get("file_type") == "zip":
            zip_count += 1
            qa.append({"code": v["code"], "version_id": v["version_id"],
                       "type": "zip", "note": "multi-file bundle — sub-PDFs handled separately"})
            continue
        if not v.get("local_filename"):
            qa.append({"code": v["code"], "version_id": v["version_id"],
                       "type": "missing", "note": v.get("note") or "no local file"})
            fail += 1
            continue

        out_dir = OUT / v["code"]
        out_path = out_dir / f"{_safe(v['version_id'])}.json"
        if out_path.exists() and not args.force:
            skipped += 1
            continue

        lf = v["local_filename"]
        pdf_path = (ROOT / lf) if ("/" in lf or "\\" in lf) else (RAW / lf)
        if not pdf_path.exists():
            qa.append({"code": v["code"], "version_id": v["version_id"],
                       "type": "missing", "note": f"file not found: {pdf_path}"})
            fail += 1
            continue

        pdf_count += 1
        t0 = time.time()
        try:
            data = run_one(pdf_path, args.timeout)
            data["code"] = v["code"]
            data["category"] = v["category"]
            data["version_id"] = v["version_id"]
            data["version_label"] = v["version_label"]
            data["pdf_url"] = v.get("pdf_url", "")
            data["pdf_sha256"] = v.get("sha256", "")
            data["doc_first_published"] = v.get("doc_first_published", "")
            data["doc_last_updated"] = v.get("doc_last_updated", "")
            data["name_zh_from_listing"] = v.get("name_zh", "")

            out_dir.mkdir(exist_ok=True)
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            warn = bool(data.get("qa", {}).get("warnings")) or bool(data.get("qa", {}).get("errors"))
            qa.append({"code": v["code"], "version_id": v["version_id"],
                       "type": "warn" if warn else "ok",
                       "field_count_declared": data.get("field_count_declared"),
                       "fields_parsed": len(data.get("fields", [])),
                       "codebooks_parsed": len(data.get("codebooks", {})),
                       "warnings": data.get("qa", {}).get("warnings", []),
                       "errors": data.get("qa", {}).get("errors", [])})
            ok += 1
            print(f"  [OK ] {v['code']:14s} {v['version_id'][:28]:28s} "
                  f"fields={len(data.get('fields', [])):>3} cb={len(data.get('codebooks', {})):>2} "
                  f"{time.time()-t0:4.0f}s")
        except subprocess.TimeoutExpired:
            qa.append({"code": v["code"], "version_id": v["version_id"],
                       "type": "timeout", "note": f"exceeded {args.timeout}s"})
            fail += 1
            print(f"  [TMO] {v['code']:14s} {v['version_id'][:28]:28s} >{args.timeout}s — skipped")
        except Exception as e:
            qa.append({"code": v["code"], "version_id": v["version_id"],
                       "type": "error", "error": str(e)[:300]})
            fail += 1
            print(f"  [ERR] {v['code']:14s} {v['version_id'][:28]:28s} {str(e)[:80]}")

    # Merge with any prior QA report so resumed runs don't lose earlier entries
    QA_OUT.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pdf_files_this_run": pdf_count, "zip_files": zip_count,
        "ok": ok, "failed": fail, "skipped_existing": skipped,
        "entries": qa,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nSummary: {ok} extracted | {fail} failed | {skipped} skipped(existing) | {zip_count} zips")
    print(f"QA report: {QA_OUT}")


if __name__ == "__main__":
    main()
