"""Summarise what the weekly refresh did, from .refresh/fetch.json and
.refresh/merge.json (written by fetch_pdfs.py and merge_upstream.py).

Writes
  .refresh/summary.md           the full account (also appended to the GitHub
                                Actions job summary when run there)
  .refresh/commit_message.txt   subject + a short body for the data commit
and sets the step output ``attention=true`` when something was left for a
person: a revision that could not be merged, a hand-edited value that changed
upstream, a revised survey ZIP, a file that left the listing, a failed
download, a new survey ZIP. Each of these is raised once — refresh_pending.json
remembers what has been reported.
"""
from __future__ import annotations
import io
import os
import sys

from refresh_state import STATE_DIR, load_pending, read_state

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MAX_LINES = 12          # per file in the summary, per list


def one_line(s: str, n: int = 140) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "…"


def name(e: dict) -> str:
    return f"{e['code']} / {e['version_id']}"


def bullets(items: list[str], out: list[str], indent: str = "  "):
    for s in items[:MAX_LINES]:
        out.append(f"{indent}- {s}")
    if len(items) > MAX_LINES:
        out.append(f"{indent}- … and {len(items) - MAX_LINES} more")


def main():
    fetch, merge = read_state("fetch"), read_state("merge")
    merged, held = merge.get("merged") or [], merge.get("held") or []
    new = fetch.get("new") or []
    failed, zips, unlisted = (fetch.get("failed") or [], fetch.get("zip_changed") or [],
                              fetch.get("unlisted") or [])
    new_zips = [e for e in new if e.get("file_type") == "zip"]
    conflicts = [(m, c) for m in merged for c in m["conflicts"]]
    untranslated = sorted({u.split(": ", 1)[1] for m in merged for u in m["untranslated"]})
    pending = load_pending()

    md: list[str] = ["## Weekly refresh of MOHW PDFs", ""]
    if not (merged or held or new or failed or zips or unlisted):
        md.append("Nothing changed upstream.")
    if merged:
        md.append(f"### Revised upstream and merged into the curated JSON ({len(merged)})")
        for m in merged:
            md.append(f"- **{name(m)}** (MOHW date {m['doc_last_updated'] or '?'}): "
                      f"{len(m['changes'])} change(s)")
            bullets(m["changes"], md)
            if m["kept"]:
                md.append("  - not applied, on purpose:")
                bullets(m["kept"], md, "    ")
        md.append("")
    if new:
        md.append(f"### New on the listing ({len(new)})")
        md += [f"- **{name(e)}** → `{e['file']}`" for e in new] + [""]

    attention: list[str] = []
    if held:
        attention.append(f"**{len(held)} revision(s) could not be merged safely** — the repo keeps "
                         f"the previous PDF and JSON (listed in `refresh_pending.json`):")
        attention += [f"  - {name(h)}: {h['reason']}" for h in held]
    if conflicts:
        attention.append(f"**{len(conflicts)} hand-edited value(s) changed upstream** — ours was kept:")
        attention += [f"  - {name(m)} · {c}" for m, c in conflicts]
    if zips:
        attention.append("**Survey ZIP bundle(s) revised upstream** — not downloaded; they are "
                         "unpacked and curated by hand (`process_zips.py`, `extract_xls.py`):")
        attention += [f"  - {name(z)} (MOHW date {z.get('doc_last_updated') or '?'})" for z in zips]
    if new_zips:
        attention.append("**New survey ZIP bundle(s)** — downloaded, but not unpacked "
                         "(`process_zips.py`):")
        attention += [f"  - {name(z)}" for z in new_zips]
    if unlisted:
        attention.append("**No longer on the MOHW listing** — kept in the repo:")
        attention += [f"  - {name(u)}" for u in unlisted]
    if failed:
        attention.append("**Download failed** — the previous file was kept:")
        attention += [f"  - {name(f)}: {f['error']}" for f in failed]
    if attention:
        md += ["### Needs a person", ""] + [a if a.startswith("  ") else f"- {a}" for a in attention] + [""]
    if untranslated:
        md.append(f"### Chinese text without English yet ({len(untranslated)})")
        md.append("Not in `translations/cache.json`; the site shows the Chinese until translated.")
        bullets([f"`{one_line(u)}`" for u in untranslated], md, "")
        md.append("")
    still = [h for h in pending["held"] if (h["code"], h["version_id"]) not in
             {(x["code"], x["version_id"]) for x in held + zips}]
    if still or pending["unlisted"]:
        md.append(f"_Still pending from earlier runs: {len(still)} held revision(s), "
                  f"{len(pending['unlisted'])} unlisted file(s) — see `refresh_pending.json`._")

    summary = "\n".join(md) + "\n"
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    # Commit message: what a reader of `git log` needs, not the whole account.
    parts = []
    if merged:
        parts.append(f"{len(merged)} revised")
    if new:
        parts.append(f"{len(new)} new")
    if held or zips:
        parts.append(f"{len(held) + len(zips)} held for review")
    subject = "chore(data): refresh MOHW PDFs — " + (", ".join(parts) if parts else "bookkeeping")
    body: list[str] = []
    if merged:
        body.append("Revised upstream, merged into the curated JSON (scripts/merge_upstream.py):")
        body += [f"- {name(m)}: {len(m['changes'])} change(s), MOHW date {m['doc_last_updated'] or '?'}"
                 for m in merged]
    if new:
        body += ["", "New on the listing:"] + [f"- {name(e)}" for e in new]
    if held or zips:
        body += ["", "Held for review, previous file kept (refresh_pending.json):"]
        body += [f"- {name(h)}: {h['reason']}" for h in held + zips]
    if conflicts:
        body += ["", f"{len(conflicts)} hand-edited value(s) changed upstream; ours kept."]
    if untranslated:
        body += ["", f"{len(untranslated)} changed Chinese string(s) have no English yet."]
    (STATE_DIR / "commit_message.txt").write_text(
        subject + "\n\n" + "\n".join(body).strip() + "\n", encoding="utf-8")

    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"attention={'true' if attention else 'false'}\n")


if __name__ == "__main__":
    main()
