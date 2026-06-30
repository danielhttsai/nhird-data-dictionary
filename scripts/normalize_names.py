"""Post-process extracted/*.json: when the PDF header gave a junk file name
(e.g. the label '中文檔名' itself, '中文檔', '無', or empty), fall back to the
name taken from the MOHW listing page (name_zh_from_listing), stripped of the
leading code prefix. Also blank out junk English names.
"""
from __future__ import annotations
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "extracted"

JUNK_ZH = {"中文檔名", "中文檔", "英文檔名", "英文檔", "無", "資料筆數", "檔案大小", ""}
JUNK_EN = {"英文檔名", "英文檔", "中文檔名", "無", "Y", "N", ""}

CODE_PREFIX = re.compile(r"^(Health|Society|Welfare)[\w\-]*?[_\-]", re.IGNORECASE)


def clean_listing_name(s: str) -> str:
    s = (s or "").strip()
    s = CODE_PREFIX.sub("", s)            # drop "Health102_" etc.
    s = re.sub(r"\(20250624起適用\)", "", s)
    s = re.sub(r"\(.*?版本\)", "", s)      # drop "(2018年以後版本)"
    return s.strip(" _-—")


def main():
    fixed = 0
    for p in sorted(EXTRACTED.glob("*/*.json")):
        if p.name.startswith("diff_"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        changed = False

        nz = (d.get("name_zh") or "").strip()
        if nz in JUNK_ZH:
            fallback = clean_listing_name(d.get("name_zh_from_listing", ""))
            if fallback:
                d["name_zh"] = fallback
                changed = True

        ne = (d.get("name_en") or "").strip()
        if ne in JUNK_EN:
            d["name_en"] = ""
            changed = True

        if changed:
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            fixed += 1
            print(f"  fixed {d.get('code')}/{d.get('version_id')}: "
                  f"name_zh={d.get('name_zh','')[:30]!r} name_en={d.get('name_en','')[:30]!r}")

    print(f"\nNormalized {fixed} files.")


if __name__ == "__main__":
    main()
