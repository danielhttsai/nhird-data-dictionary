"""One-shot translation runner for the Windows Scheduled Task.

Runs the focused (core-HWDC) translation to completion:
  1. short strings (field names + codebook labels)
  2. long descriptions (file-level blocks)
  3. final stamp onto the extracted JSONs
Idempotent — resumes from translations/cache.json, so safe to re-run.
Writes a heartbeat to translations/run_task.log.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# translate.py wraps sys.stdout/stderr as UTF-8 on import — don't double-wrap.
import translate as T  # noqa: E402


def run_pass(max_len, include_long, label, batch_size=12):
    cache = T.load_cache()
    strings = T.collect_strings(None, max_len=max_len, include_long=include_long)
    todo = [s for s in strings if T.sha(s) not in cache]
    todo.sort(key=len)
    print(f"[{label}] {len(strings)} strings, {len(todo)} to translate", flush=True)
    BATCH = batch_size
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        out = T.translate_batch(batch)
        for src, dst in zip(batch, out):
            if dst:
                cache[T.sha(src)] = dst
        T.save_cache(cache)
        print(f"[{label}] {min(i + BATCH, len(todo))}/{len(todo)} — cache {len(cache)}", flush=True)
    return cache


def deploy():
    """Rebuild the site and push so the finished translations go live.
    Best-effort: logs failures but does not raise (translations are already
    stamped on disk, so a manual redeploy can finish the job)."""
    def run(cmd, cwd, shell=False):
        print(f"$ {cmd}", flush=True)
        r = subprocess.run(cmd, cwd=cwd, shell=shell, capture_output=True, text=True)
        tail = (r.stdout or "")[-300:] + (r.stderr or "")[-300:]
        print(tail, flush=True)
        return r.returncode
    try:
        # Commit the stamped translations first, then sync with any commits
        # pushed in the meantime (UI tweaks etc.) before pushing.
        run('git add -A', ROOT, shell=True)
        run('git commit -m "Auto: completed core translations (scheduled task)"', ROOT, shell=True)
        run('git pull --rebase --autostash', ROOT, shell=True)
        run("npm run build", ROOT / "site", shell=True)
        run('git add -A', ROOT, shell=True)
        run('git commit -m "Auto: rebuild after translation"', ROOT, shell=True)
        run("git push", ROOT, shell=True)
        print("=== deploy pushed ===", flush=True)
    except Exception as e:
        print(f"deploy failed (translations still stamped): {e}", flush=True)


def main():
    t0 = time.time()
    print("=== translation task start ===", flush=True)
    # Pass 1: short strings (names + labels) — 12 per batch
    run_pass(max_len=30, include_long=False, label="short", batch_size=12)
    # Pass 2: long descriptions — 6 per batch (large paragraphs overflow a
    # 12-string batch's token budget on CPU and stall).
    run_pass(max_len=None, include_long=True, label="long", batch_size=6)
    # Final stamp
    cache = T.load_cache()
    T.stamp_translations(cache, None)
    print(f"=== translated in {(time.time() - t0) / 60:.0f} min, cache {len(cache)} ===", flush=True)
    # Rebuild + deploy
    deploy()
    print(f"=== ALL DONE in {(time.time() - t0) / 60:.0f} min ===", flush=True)


if __name__ == "__main__":
    main()
