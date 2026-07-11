"""Remove PDF line-wrap spaces that landed between two CJK characters
(e.g. '病房點 數' -> '病房點數'). Because the cleaned string hashes differently,
migrate any existing English translation from the old key to the new one so the
field keeps its English."""
import sys, io, json, glob, os, re, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
def sha(s): return hashlib.sha1(s.encode('utf-8')).hexdigest()[:16]

CJK = r'[㐀-鿿豈-﫿぀-ヿ]'   # ideographs (+ rare kana)
SPACE = re.compile(rf'(?<={CJK})[ \t　]+(?={CJK})')   # space between two CJK chars only
def clean(s): return SPACE.sub('', s) if s else s

cache = json.load(open('translations/cache.json', encoding='utf-8'))
MIG = [0]; CHG = [0]
def proc(val):
    if not isinstance(val, str) or not val:
        return val, False
    c = clean(val)
    if c == val:
        return val, False
    CHG[0] += 1
    if sha(val) in cache and sha(c) not in cache:   # keep the English
        cache[sha(c)] = cache[sha(val)]; MIG[0] += 1
    return c, True

for f in glob.glob('extracted/*/*.json'):
    if os.path.basename(f).startswith('diff_'):
        continue
    d = json.load(open(f, encoding='utf-8'))
    dirty = False
    for key in ('name_zh', 'notes_zh', 'data_description_zh', 'primary_keys_raw'):
        if isinstance(d.get(key), str):
            nv, ch = proc(d[key])
            if ch: d[key] = nv; dirty = True
    for fld in d.get('fields', []):
        for key in ('name_zh', 'description_zh'):
            if isinstance(fld.get(key), str):
                nv, ch = proc(fld[key])
                if ch: fld[key] = nv; dirty = True
    for cb in (d.get('codebooks') or {}).values():
        entries = []
        if isinstance(cb, dict):
            if isinstance(cb.get('field_zh'), str):
                nv, ch = proc(cb['field_zh'])
                if ch: cb['field_zh'] = nv; dirty = True
            entries = cb.get('entries', []) or []
        elif isinstance(cb, list):
            entries = cb
        for e in entries:
            if isinstance(e, dict) and isinstance(e.get('label_zh'), str):
                nv, ch = proc(e['label_zh'])
                if ch: e['label_zh'] = nv; dirty = True
    if dirty:
        json.dump(d, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

json.dump(cache, open('translations/cache.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(f'cleaned field values: {CHG[0]} | cache entries migrated: {MIG[0]}')
