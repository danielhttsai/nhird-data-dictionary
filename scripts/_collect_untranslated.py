import sys, io, json, glob, os, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
def sha(s): return hashlib.sha1(s.encode('utf-8')).hexdigest()[:16]
cache = json.load(open('translations/cache.json', encoding='utf-8'))

def keep(s):
    s = (s or '').strip()
    return s and '�' not in s and sha(s) not in cache

uniq = {}   # sha -> zh   (pool names + descriptions; both stamp from cache the same way)
n_names = n_desc = 0
for f in glob.glob('extracted/*/*.json'):
    if os.path.basename(f).startswith('diff_'):
        continue
    d = json.load(open(f, encoding='utf-8'))
    for fld in d.get('fields', []):
        nz = (fld.get('name_zh') or '').strip()
        if keep(nz) and any(ch > '　' for ch in nz):  # has CJK-ish content worth translating
            if sha(nz) not in uniq:
                uniq[sha(nz)] = nz; n_names += 1
        dz = (fld.get('description_zh') or '').strip()
        if len(dz) >= 4 and keep(dz):
            if sha(dz) not in uniq:
                uniq[sha(dz)] = dz; n_desc += 1

items = sorted(uniq.items(), key=lambda kv: kv[1])
lens = [len(v) for v in uniq.values()]
lens.sort()
print(f"unique untranslated strings: {len(items)}  (new names ~{n_names}, new descriptions ~{n_desc})")
if lens:
    print(f"length: min={lens[0]} median={lens[len(lens)//2]} p90={lens[int(len(lens)*0.9)]} max={lens[-1]}")

# chunk by CHARACTER budget so long descriptions don't blow the output-token cap
outdir = 'translations/_fill'
os.makedirs(outdir, exist_ok=True)
for old in glob.glob(f'{outdir}/*.json'):
    os.remove(old)
BUDGET = 17000  # chars of Chinese input per chunk (English out stays well under the cap)
chunk = {}; sz = 0; n = 0
def flush():
    global chunk, sz, n
    if chunk:
        json.dump(chunk, open(f'{outdir}/_in_{n:03d}.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        n += 1; chunk = {}; sz = 0
for h, v in items:
    if sz + len(v) > BUDGET and chunk:
        flush()
    chunk[h] = v; sz += len(v)
flush()
print(f"wrote {n} chunks to {outdir} (budget {BUDGET} chars each)")
