"""Unpack each *.zip in raw_pdfs/ into raw_pdfs_zip/<basename>/, then add an
entry to manifest.json for every PDF inside (one per survey wave / sub-file).

The PDF version_id is derived from the filename: looks for patterns like
``YYYY年``, ``_YYYY.pdf`` (ROC year), or ``19YY/20YY``. Falls back to the
filename stem.

After running this script, extract_all.py picks up the new entries naturally.
"""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw_pdfs"
UNZIP_DIR = ROOT / "raw_pdfs_zip"
MANIFEST = ROOT / "manifest.json"


def fix_zip_name(name: str) -> str:
    """ZIP entries may be encoded in cp437 (default) but the bytes are actually
    cp950 / big5 (MOHW uses Big5 / UTF-8 mix). Try a few decodings."""
    if not name:
        return name
    for enc in ("utf-8", "cp950"):
        try:
            return name.encode("cp437").decode(enc)
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
    return name


def derive_wave_id(stem: str) -> tuple[str, str]:
    """Return (wave_id, wave_label) from a PDF filename stem."""
    s = stem
    # 102年 / 102 年 (ROC year)
    m = re.search(r"(\d{2,3})\s*年", s)
    if m:
        roc = int(m.group(1))
        ad = roc + 1911
        return (f"wave_ROC{roc}_AD{ad}", f"民國 {roc} 年 ({ad})")
    # _YYYY.pdf at end
    m = re.search(r"_(\d{4})$", s)
    if m:
        y = int(m.group(1))
        return (f"wave_AD{y}", f"{y} 年")
    # Just take the stem cleaned up
    clean = re.sub(r"[^\w一-鿿\-]+", "_", s)[:50]
    return (f"wave_{clean}", s)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    versions = manifest["versions"]
    UNZIP_DIR.mkdir(exist_ok=True)

    zips = [v for v in versions if v.get("file_type") == "zip" and v.get("local_filename")]
    print(f"Processing {len(zips)} ZIP bundles")

    new_entries = []
    for v in zips:
        zip_path = RAW_DIR / v["local_filename"]
        if not zip_path.exists():
            print(f"  skip {v['code']}: zip missing {zip_path}")
            continue
        target = UNZIP_DIR / zip_path.stem
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

        # Extract with safe filenames (decode cp437→cp950/utf-8)
        try:
            with zipfile.ZipFile(zip_path) as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    fname = fix_zip_name(info.filename)
                    out_path = target / fname
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as src, out_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
        except Exception as e:
            print(f"  ERR unzip {zip_path}: {e}")
            continue

        # Find every PDF in the extracted tree, depth-first
        pdfs = sorted(target.rglob("*.pdf"))
        print(f"  {v['code']}/{v['version_id']}: {len(pdfs)} PDFs inside")
        for p in pdfs:
            stem = p.stem
            # Skip clearly-derivative files (cover letter, ISCO codebook, etc.)
            # but still register them so the user can see they exist.
            wave_id, wave_label = derive_wave_id(stem)
            # Avoid collision with parent ZIP's version_id
            sub_version_id = f"{v['version_id']}__{wave_id}"
            sha = sha256_of(p)
            new_entries.append({
                "code": v["code"],
                "category": v["category"],
                "name_zh": stem,
                "version_id": sub_version_id,
                "version_label": f"{v['version_label']} · {wave_label}",
                "detail_url": v["detail_url"],
                "pdf_url": v.get("pdf_url", ""),
                "file_type": "pdf",
                "doc_first_published": v.get("doc_first_published", ""),
                "doc_last_updated": v.get("doc_last_updated", ""),
                "sha256": sha,
                "local_filename": str(p.relative_to(ROOT)).replace("\\", "/"),
                "fetched_at": "from-zip",
                "listing_page": v.get("listing_page", 0),
                "note": f"unpacked from {v['local_filename']}",
                "parent_zip_version": v["version_id"],
            })

    # Dedupe by (code, version_id) keeping the first; merge with existing manifest
    have = {(x["code"], x["version_id"]) for x in versions}
    added = 0
    for e in new_entries:
        key = (e["code"], e["version_id"])
        if key in have:
            continue
        versions.append(e)
        have.add(key)
        added += 1

    manifest["versions"] = versions
    manifest["count"] = len(versions)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAdded {added} sub-PDF entries from ZIPs.")
    print(f"Manifest now has {len(versions)} versions.")


if __name__ == "__main__":
    main()
