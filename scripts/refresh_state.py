"""State shared by the weekly refresh scripts (fetch_pdfs.py, merge_upstream.py,
refresh_report.py).

refresh_pending.json (committed) — upstream changes the refresh saw but did not
apply, so that each one is reported once and not every week:
    held      revisions that could not be merged into extracted/ safely
    unlisted  files the MOHW listing no longer shows (kept in the repo)

.refresh/ (git-ignored) — what the current run did, for the run summary.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PENDING = ROOT / "refresh_pending.json"
STATE_DIR = ROOT / ".refresh"

ABOUT = ("Upstream changes the weekly refresh saw but did not apply. 'held': revisions "
         "that could not be merged into extracted/ safely — the repo still holds the "
         "previous file and JSON; delete an entry to have the next run try it again. "
         "'unlisted': files the MOHW listing no longer shows; they are kept.")


def load_pending() -> dict:
    """{'held': [...], 'unlisted': [...]}"""
    d = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else {}
    return {"held": d.get("held") or [], "unlisted": d.get("unlisted") or []}


def save_pending(p: dict):
    key = lambda e: (e["code"], e["version_id"])
    held, unlisted = sorted(p.get("held") or [], key=key), sorted(p.get("unlisted") or [], key=key)
    if not held and not unlisted:
        PENDING.unlink(missing_ok=True)
        return
    PENDING.write_text(json.dumps({"about": ABOUT, "held": held, "unlisted": unlisted},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_state(name: str, data: dict):
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                            encoding="utf-8")


def read_state(name: str) -> dict:
    p = STATE_DIR / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
