"""Meaningful periodic spot-check: (1) run the local gap scan, and (2) poll the
live MOHW listing for databases added/removed since the last tick. Only the live
listing can actually change between runs, so this is what's worth re-checking.
Prints a one-line status unless something changed. Baseline is a gitignored dotfile."""
import sys, io, os, re, json, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASELINE = os.path.join(HERE, '.listing_baseline.json')
CODE = re.compile(r'(Health|Society|Welfare)\s*[_-]?\s*(\d+)', re.I)
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36'}

def live_codes():
    import httpx
    codes = set()
    with httpx.Client(verify=False, timeout=40, headers=H, follow_redirects=True) as c:
        for pg in range(1, 7):
            u = f'https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-{pg}-20.html'
            for m in CODE.finditer(c.get(u).text):
                codes.add(f'{m.group(1).title()}{int(m.group(2))}')
    return codes

# 1) local scan
local = subprocess.run([sys.executable, os.path.join(HERE, 'gap_check.py')],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT).stdout.strip()

# 2) live listing delta
try:
    now = live_codes()
    prev = set(json.load(open(BASELINE))) if os.path.exists(BASELINE) else None
    json.dump(sorted(now), open(BASELINE, 'w'))
    if prev is None:
        listing = f'listing baseline set: {len(now)} databases'
    else:
        added, removed = sorted(now - prev), sorted(prev - now)
        listing = ('MOHW LISTING CHANGED — added: %s  removed: %s' % (added or '—', removed or '—')
                   if (added or removed) else f'listing unchanged: {len(now)} databases')
except Exception as e:
    listing = f'listing check skipped ({type(e).__name__})'

print(local)
print(listing)
