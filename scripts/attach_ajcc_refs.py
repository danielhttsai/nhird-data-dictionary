"""Attach AJCC staging reference-document links to the cancer-registry staging
fields (clinical/pathologic T/N/M, stage group, other staging systems).

These AJCC docs are narrative coding rules (not code→definition tables), so they
are surfaced as reference links (field.refs) rather than codebooks.
"""
import io, json, re, sys, glob
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "extracted"

AJCC_REFS = [
    {"label": "AJCC 第9版 TNM 與期別編碼對應表 (2026)",
     "url": "https://twcr.tw/wp-content/uploads/2026/04/ajcc-v9-20260415.pdf"},
    {"label": "AJCC 第8版 期別編碼規則與操作型定義",
     "url": "https://twcr.tw/wp-content/uploads/2021/12/AJCC%E7%AC%AC8%E7%89%88%E6%9C%9F%E5%88%A5%E7%B7%A8%E7%A2%BC%E7%9B%B8%E9%97%9C%E8%A6%8F%E5%89%87%E8%88%87%E6%93%8D%E4%BD%9C%E5%9E%8B%E5%AE%9A%E7%BE%A9.pdf"},
]

# Field-name patterns that reference AJCC staging.
STAGE_RE = re.compile(r"(病理|臨床).?[TNM]$|[TNM]$|期別|分期|Stage|Staging|AJCC", re.IGNORECASE)


def is_stage_field(name_zh: str, name_en: str) -> bool:
    nz = name_zh or ""
    ne = name_en or ""
    if re.search(r"(病理|臨床)[TNM]", nz):
        return True
    if "期別" in nz or "分期" in nz:
        return True
    if re.search(r"\b(Clinical|Pathologic)\s+[TNM]\b", ne) or "Stage" in ne:
        return True
    return False


def main():
    files = []
    for code in ("Health14", "Health15", "Health16"):
        files += [p for p in glob.glob(str(EXTRACTED / code / "*.json")) if "diff_" not in p]
    total = 0
    for p in files:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        n = 0
        for f in d.get("fields", []):
            if is_stage_field(f.get("name_zh", ""), f.get("name_en", "")):
                f["refs"] = AJCC_REFS
                n += 1
        if n:
            Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            total += n
            print(f"  {Path(p).parent.name}/{Path(p).stem}: {n} staging fields")
    print(f"\nAttached AJCC refs to {total} field instances.")


if __name__ == "__main__":
    main()
