"""Translate Chinese strings in extracted/*.json to English using a local
Qwen 2.5 14B (via Ollama at http://localhost:11434).

Cache: translations/cache.json -- maps a SHA-1 hash of the source string to
the translated text, so re-runs are cheap.

Translates: field name_zh, field description_zh, codebook label_zh,
data_description_zh, notes_zh, primary_keys_raw.
Result fields are written back into the same JSON as ``*_en`` / ``label_en``.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path

import httpx

# Force UTF-8 stdout/stderr so rare CJK in progress lines never crashes the run.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "extracted"
CACHE_DIR = ROOT / "translations"
CACHE_FILE = CACHE_DIR / "cache.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b-instruct-q4_K_M"   # 7B Q4 — ~3× faster than 14B on CPU, quality sufficient for short medical strings

SYSTEM_PROMPT = (
    "You are a medical/health-insurance terminology translator for Taiwan's NHIRD "
    "data dictionary. Translate Traditional Chinese strings to natural, concise "
    "English used in pharmacoepidemiology and claims-data research. Keep medical "
    "terms idiomatic (e.g. '住院' → 'inpatient', '門急診' → 'outpatient/ED', "
    "'重大傷病' → 'catastrophic illness'). For dates and codes preserve format. "
    "Do not add explanations or markdown. Reply ONLY with a JSON array of strings, "
    "same length and order as the input."
)


def sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def load_cache() -> dict[str, str]:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, str]):
    CACHE_DIR.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def has_chinese(s: str) -> bool:
    return bool(s) and any("一" <= c <= "鿿" for c in s)


def translate_batch(strings: list[str], retries: int = 2) -> list[str]:
    """Call Ollama with a JSON-array input; expect JSON-array output."""
    if not strings:
        return []
    payload_input = json.dumps(strings, ensure_ascii=False)
    prompt = f"{SYSTEM_PROMPT}\n\nInput:\n{payload_input}"
    for attempt in range(retries + 1):
        try:
            r = httpx.post(OLLAMA_URL, json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 4096}
            }, timeout=600)
            r.raise_for_status()
            resp = r.json()["response"].strip()
            # Strip markdown fences if present
            resp = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.strip())
            # Extract first JSON array
            m = re.search(r"\[[\s\S]*\]", resp)
            if not m:
                raise ValueError(f"no JSON array in response: {resp[:200]}")
            arr = json.loads(m.group(0))
            if len(arr) != len(strings):
                # On the last retry, accept a near-miss by translating one-by-one
                # for this batch instead of discarding all 40.
                if attempt >= retries:
                    print(f"      length mismatch (in={len(strings)}, out={len(arr)}) — "
                          f"falling back to per-string for this batch", file=sys.stderr)
                    return [translate_one(s) for s in strings]
                raise ValueError(f"length mismatch: in={len(strings)}, out={len(arr)}")
            return [str(x) for x in arr]
        except Exception as e:
            print(f"      ! attempt {attempt + 1} failed: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(1)
    return ["" for _ in strings]


def translate_one(s: str) -> str:
    """Translate a single string (used as fallback when batch length mismatches)."""
    prompt = (f"{SYSTEM_PROMPT}\n\nInput:\n" + json.dumps([s], ensure_ascii=False))
    try:
        r = httpx.post(OLLAMA_URL, json={
            "model": MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0, "num_predict": 512}
        }, timeout=120)
        r.raise_for_status()
        resp = re.sub(r"^```(?:json)?\s*|\s*```$", "", r.json()["response"].strip())
        m = re.search(r"\[[\s\S]*\]", resp)
        if m:
            arr = json.loads(m.group(0))
            if arr:
                return str(arr[0])
    except Exception:
        pass
    return ""


def collect_strings(only_files: list[str] | None = None, max_len: int | None = None,
                    include_long: bool = True) -> list[str]:
    """Walk extracted/*.json and return unique Chinese strings worth translating.

    With max_len, strings longer than that are skipped (use for cheap pre-pass).
    With include_long=False, file-level long blocks (description / notes / pk) are skipped.
    """
    def add(seen, v):
        v = (v or "").strip()
        if not has_chinese(v):
            return
        if max_len is not None and len(v) > max_len:
            return
        seen.add(v)

    seen: set[str] = set()
    for json_path in sorted(EXTRACTED.glob("*/*.json")):
        if json_path.name.startswith("diff_"):
            continue
        # Skip the huge survey-wave / Excel-codebook variable sets (tens of
        # thousands of long questionnaire strings, low value, mostly already
        # have English variable names). Focus on the core HWDC databases.
        if "__xls_" in json_path.stem or "__wave_" in json_path.stem:
            continue
        if only_files and json_path.parent.name not in only_files:
            continue
        d = json.loads(json_path.read_text(encoding="utf-8"))
        # Field-level
        for f in d.get("fields", []):
            add(seen, f.get("name_zh"))
            add(seen, f.get("description_zh"))
        # Codebook labels
        for _, cb in (d.get("codebooks") or {}).items():
            entries = cb.get("entries") if isinstance(cb, dict) else cb
            if entries:
                for e in entries:
                    add(seen, e.get("label_zh"))
            if isinstance(cb, dict):
                add(seen, cb.get("field_zh"))
        # File-level descriptive blocks
        add(seen, d.get("name_zh"))
        if include_long:
            for k in ("data_description_zh", "notes_zh", "primary_keys_raw"):
                add(seen, d.get(k))
    return sorted(seen)


def stamp_translations(cache: dict[str, str], only_files: list[str] | None = None):
    """Write *_en fields back into each extracted JSON using the cache."""
    def t(s):
        if not s:
            return ""
        return cache.get(sha(s), "")

    n_files = 0
    for json_path in sorted(EXTRACTED.glob("*/*.json")):
        if json_path.name.startswith("diff_"):
            continue
        if "__xls_" in json_path.stem or "__wave_" in json_path.stem:
            continue
        if only_files and json_path.parent.name not in only_files:
            continue
        d = json.loads(json_path.read_text(encoding="utf-8"))
        for f in d.get("fields", []):
            f["name_zh_en"] = t(f.get("name_zh", ""))
            f["description_en"] = t(f.get("description_zh", ""))
        for cb_name, cb in (d.get("codebooks") or {}).items():
            if isinstance(cb, dict):
                cb["field_en"] = t(cb.get("field_zh", ""))
                for e in cb.get("entries", []):
                    e["label_en"] = t(e.get("label_zh", ""))
            elif isinstance(cb, list):
                for e in cb:
                    e["label_en"] = t(e.get("label_zh", ""))
        d["data_description_en"] = t(d.get("data_description_zh", ""))
        d["notes_en"] = t(d.get("notes_zh", ""))
        d["primary_keys_en"] = t(d.get("primary_keys_raw", ""))
        # name_zh_en is mainly useful when PDF didn't give a name_en
        d["name_zh_en"] = t(d.get("name_zh", ""))
        json_path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        n_files += 1
    print(f"  stamped translations onto {n_files} JSON files")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=40,
                    help="strings per Ollama call (default 40)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap total strings translated this run")
    ap.add_argument("--only", nargs="*", default=None,
                    help="restrict to specific code dirs, e.g. Health01 Health02")
    ap.add_argument("--stamp-only", action="store_true",
                    help="don't translate, just write cached translations back into JSON")
    ap.add_argument("--max-len", type=int, default=None,
                    help="skip strings longer than N chars (use for fast first-pass)")
    ap.add_argument("--short-only", action="store_true",
                    help="shortcut for --max-len=30 + skip file-level long blocks")
    args = ap.parse_args()

    cache = load_cache()
    print(f"Cache: {len(cache)} entries")

    if not args.stamp_only:
        max_len = 30 if args.short_only else args.max_len
        include_long = not args.short_only
        strings = collect_strings(args.only, max_len=max_len, include_long=include_long)
        print(f"Unique Chinese strings in extracted JSONs: {len(strings)}")
        # Skip already-cached
        todo = [s for s in strings if sha(s) not in cache]
        print(f"Already translated: {len(strings) - len(todo)}, todo: {len(todo)}")
        if args.limit:
            todo = todo[:args.limit]
            print(f"Capped to {len(todo)} for this run")

        # Sort by length so big descriptions don't block early progress
        todo.sort(key=len)
        for i in range(0, len(todo), args.batch_size):
            batch = todo[i:i + args.batch_size]
            print(f"  [{i // args.batch_size + 1}/{(len(todo) + args.batch_size - 1) // args.batch_size}] "
                  f"translating {len(batch)} strings (sample: {batch[0][:30]!r})…")
            t0 = time.time()
            out = translate_batch(batch)
            dt = time.time() - t0
            for src, dst in zip(batch, out):
                if dst:
                    cache[sha(src)] = dst
            save_cache(cache)
            print(f"     done in {dt:.1f}s — cache now {len(cache)} entries")

    print("Stamping translations onto extracted JSONs…")
    stamp_translations(cache, args.only)


if __name__ == "__main__":
    main()
