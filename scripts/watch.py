"""Meaningful periodic spot-check: (1) run the local gap scan, (2) compare the
live MOHW listing against what the repo covers (extracted/ dirs) — an absolute
check that needs no baseline, so it works in CI — plus a delta vs the last tick
when a baseline dotfile exists, and (3) check the deployed site answers 200.

With --strict, exit 1 on any finding (for CI: a failed step notifies via GitHub).
Prints one line per check. Baseline is a gitignored dotfile."""
import sys, io, os, re, json, glob, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASELINE = os.path.join(HERE, '.listing_baseline.json')
CODE = re.compile(r'(Health|Society|Welfare)\s*[_-]?\s*(\d+)', re.I)
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36'}
SITE = 'https://danielhttsai.github.io/nhird-data-dictionary/'
STRICT = '--strict' in sys.argv
bad = False

def live_codes():
    import httpx
    codes = set()
    with httpx.Client(verify=False, timeout=40, headers=H, follow_redirects=True) as c:
        for pg in range(1, 7):
            u = f'https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-{pg}-20.html'
            for m in CODE.finditer(c.get(u).text):
                codes.add(f'{m.group(1).title()}{int(m.group(2))}')
    return codes

def norm_dir(name):
    m = CODE.match(name)
    return f'{m.group(1).title()}{int(m.group(2))}' if m else name

# 1) local scan
local = subprocess.run([sys.executable, os.path.join(HERE, 'gap_check.py')],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT).stdout.strip()
print(local)
if not local.startswith('CLEAN'):
    bad = True

# 2) live listing: absolute coverage check + delta vs baseline
try:
    now = live_codes()
    covered = {norm_dir(os.path.basename(d)) for d in glob.glob(os.path.join(ROOT, 'extracted', '*')) if os.path.isdir(d)}
    uncovered = sorted(now - covered)
    if uncovered:
        print(f'MOHW LISTS DATABASES WE DO NOT COVER: {uncovered}')
        bad = True
    prev = set(json.load(open(BASELINE))) if os.path.exists(BASELINE) else None
    json.dump(sorted(now), open(BASELINE, 'w'))
    if prev is not None:
        added, removed = sorted(now - prev), sorted(prev - now)
        if added or removed:
            print(f'MOHW LISTING CHANGED since last tick — added: {added or "—"}  removed: {removed or "—"}')
            bad = True
        else:
            print(f'listing unchanged: {len(now)} databases, all covered')
    else:
        print(f'listing baseline set: {len(now)} databases, uncovered: {len(uncovered)}')
except Exception as e:
    print(f'listing check skipped ({type(e).__name__})')

# 3) deployed site health
try:
    import httpx
    r = httpx.get(SITE, timeout=30, follow_redirects=True)
    print(f'site: HTTP {r.status_code}')
    if r.status_code != 200:
        bad = True
except Exception as e:
    print(f'site check skipped ({type(e).__name__})')

sys.exit(1 if (STRICT and bad) else 0)
