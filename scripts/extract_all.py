"""Batch-run extract_pdf over every PDF listed in manifest.json.
Writes extracted/<code>/<version_id>.json + a top-level qa_report.json.
ZIP entries are skipped (they're multi-file survey bundles handled separately).
"""
from __future__ import annotations
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_pdf import extract_pdf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest.json"
RAW = ROOT / "raw_pdfs"
OUT = ROOT / "extracted"
QA_OUT = ROOT / "qa_report.json"


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    versions = manifest["versions"]

    OUT.mkdir(exist_ok=True)
    qa: list[dict] = []
    pdf_count = 0
    zip_count = 0
    ok = 0
    fail = 0

    for v in versions:
        if v.get("file_type") == "zip":
            zip_count += 1
            qa.append({
                "code": v["code"],
                "version_id": v["version_id"],
                "type": "zip",
                "note": "multi-file bundle (survey waves) — not auto-extracted",
            })
            continue
        if not v.get("local_filename"):
            qa.append({
                "code": v["code"],
                "version_id": v["version_id"],
                "type": "missing",
                "note": v.get("note") or "no local file",
            })
            fail += 1
            continue
        pdf_path = RAW / v["local_filename"]
        if not pdf_path.exists():
            qa.append({
                "code": v["code"],
                "version_id": v["version_id"],
                "type": "missing",
                "note": f"file not found: {pdf_path}",
            })
            fail += 1
            continue

        pdf_count += 1
        try:
            data = extract_pdf(pdf_path)
            # Stamp manifest fields onto the extracted JSON
            data["code"] = v["code"]
            data["category"] = v["category"]
            data["version_id"] = v["version_id"]
            data["version_label"] = v["version_label"]
            data["pdf_url"] = v.get("pdf_url", "")
            data["pdf_sha256"] = v.get("sha256", "")
            data["doc_first_published"] = v.get("doc_first_published", "")
            data["doc_last_updated"] = v.get("doc_last_updated", "")
            data["name_zh_from_listing"] = v.get("name_zh", "")

            code_dir = OUT / v["code"]
            code_dir.mkdir(exist_ok=True)
            (code_dir / f"{v['version_id']}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # QA flags
            qa_entry = {
                "code": v["code"],
                "version_id": v["version_id"],
                "type": "ok" if not data["qa"]["warnings"] and not data["qa"]["errors"] else "warn",
                "field_count_declared": data.get("field_count_declared"),
                "fields_parsed": len(data["fields"]),
                "codebooks_parsed": len(data["codebooks"]),
                "warnings": data["qa"]["warnings"],
                "errors": data["qa"]["errors"],
            }
            qa.append(qa_entry)
            ok += 1
            print(f"  [OK ] {v['code']:14s} {v['version_id']:18s}  "
                  f"fields={len(data['fields']):>3} cb={len(data['codebooks']):>2} "
                  f"{'WARN' if data['qa']['warnings'] else ''}")
        except Exception as e:
            tb = traceback.format_exc()
            qa.append({
                "code": v["code"],
                "version_id": v["version_id"],
                "type": "error",
                "error": str(e),
                "trace": tb.splitlines()[-5:],
            })
            fail += 1
            print(f"  [ERR] {v['code']:14s} {v['version_id']:18s}  {e}")

    QA_OUT.write_text(json.dumps({
        "pdf_files": pdf_count,
        "zip_files": zip_count,
        "ok": ok,
        "failed": fail,
        "warned": sum(1 for q in qa if q.get("type") == "warn"),
        "entries": qa,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nSummary: {ok} extracted | {fail} failed | {zip_count} zips skipped")
    print(f"  warnings: {sum(1 for q in qa if q.get('type') == 'warn')}")
    print(f"QA report: {QA_OUT}")


if __name__ == "__main__":
    main()
