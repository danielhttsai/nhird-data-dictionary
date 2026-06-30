"""For each code with ≥2 extracted versions, produce a structured diff
listing added / removed / modified fields between consecutive versions.

Output: extracted/<code>/diff_<earlier>__<later>.json
And a top-level diffs_index.json with a summary.
"""
from __future__ import annotations
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "extracted"
INDEX_OUT = ROOT / "diffs_index.json"


def load_versions(code_dir: Path) -> list[dict]:
    versions = []
    for p in sorted(code_dir.glob("*.json")):
        if p.name.startswith("diff_"):
            continue
        try:
            versions.append({
                "version_id": p.stem,
                "path": p,
                "data": json.loads(p.read_text(encoding="utf-8")),
            })
        except Exception:
            continue
    return versions


def diff_versions(earlier: dict, later: dict) -> dict:
    """Compute a structural diff between two extracted JSON dicts.
    Field identity = name_en (English code). Falls back to seq if name_en is missing."""
    def key(f):
        return f.get("name_en") or f"seq:{f.get('seq')}"
    e_fields = {key(f): f for f in earlier.get("fields", [])}
    l_fields = {key(f): f for f in later.get("fields", [])}
    e_keys = set(e_fields)
    l_keys = set(l_fields)

    added = [l_fields[k] for k in sorted(l_keys - e_keys, key=lambda k: l_fields[k].get("seq", 0))]
    removed = [e_fields[k] for k in sorted(e_keys - l_keys, key=lambda k: e_fields[k].get("seq", 0))]

    modified = []
    for k in sorted(e_keys & l_keys, key=lambda k: l_fields[k].get("seq", 0)):
        e = e_fields[k]
        l = l_fields[k]
        changes = {}
        for attr in ("name_zh", "type", "length", "description_zh"):
            if e.get(attr) != l.get(attr):
                changes[attr] = {"from": e.get(attr), "to": l.get(attr)}
        if changes:
            modified.append({"key": k, "seq_later": l.get("seq"), "changes": changes})

    return {
        "code": later.get("code"),
        "earlier_version_id": earlier.get("version_id"),
        "later_version_id": later.get("version_id"),
        "earlier_field_count": len(e_fields),
        "later_field_count": len(l_fields),
        "added": added,
        "removed": removed,
        "modified": modified,
    }


def main():
    summary = []
    code_dirs = [p for p in EXTRACTED.iterdir() if p.is_dir()]
    for code_dir in sorted(code_dirs):
        versions = load_versions(code_dir)
        if len(versions) < 2:
            continue
        # Stamp version_id onto data dict so diff knows
        for v in versions:
            v["data"]["version_id"] = v["version_id"]
            v["data"]["code"] = code_dir.name
        # Diff each consecutive pair (legacy → post-20250624, plus any period-* chain)
        # Plus: always diff first vs last for a "full timeline" view
        pairs = []
        for i in range(len(versions) - 1):
            pairs.append((versions[i], versions[i + 1]))
        if len(versions) > 2:
            pairs.append((versions[0], versions[-1]))

        for earlier, later in pairs:
            d = diff_versions(earlier["data"], later["data"])
            out_name = f"diff_{earlier['version_id']}__{later['version_id']}.json"
            (code_dir / out_name).write_text(
                json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            summary.append({
                "code": code_dir.name,
                "diff_file": out_name,
                "earlier": earlier["version_id"],
                "later": later["version_id"],
                "added": len(d["added"]),
                "removed": len(d["removed"]),
                "modified": len(d["modified"]),
            })
            print(f"  {code_dir.name:14s}  {earlier['version_id']} → {later['version_id']}  "
                  f"+{len(d['added']):>2}  -{len(d['removed']):>2}  ~{len(d['modified']):>2}")

    INDEX_OUT.write_text(json.dumps({
        "count": len(summary),
        "diffs": summary,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(summary)} diff files, index: {INDEX_OUT}")


if __name__ == "__main__":
    main()
