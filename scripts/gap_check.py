"""Cheap, local-only gap scan. Prints only what's wrong (or 'CLEAN').
Run periodically to spot regressions/omissions without any network or LLM cost.

Reports DISTINCT missing named code-tables (the actionable unit), not per-field
mentions — a field that says '詳見 X 譯碼說明' is only a gap when NO codebook
anywhere defines X (cross-references to a sibling field's codebook are ignored)."""
import sys, io, json, glob, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
U = chr(0xFFFD)
# a *named* table reference: 「name」… or  name+對照表/代碼表/分類表/一覽表
NAMED = re.compile(r'「([^」]{2,20})」\s*(?:譯碼說明|代碼|對照表)'
                   r'|([一-鿿]{2,14}?)(對照表|代碼表|分類表|一覽表)')

def norm(s):
    s = re.sub(r'^(詳見|詳|見|參考|請參考|參)', '', s or '')
    s = re.sub(r'(代碼|對照|一覽|分類|之|的|說明|譯碼|序號|別)', '', s)
    s = s.replace('鄉鎮市區', '鄉鎮').replace('縣市鄉鎮', '鄉鎮').replace('鄉鎮市', '鄉鎮')
    return s.replace('表', '').strip()

HAN = re.compile(r'[一-鿿]')
def zh(s): return bool(s) and bool(HAN.search(s))

garbled = untr_name = untr_desc = half_en = untr_label = untr_cbt = untr_file = 0
sg, su, sh, sl = [], [], [], []
cb_names = set()          # every table a codebook already defines (by field_zh)
refs = {}                 # normalized table name -> example "code:field"
for f in glob.glob('extracted/*/*.json'):
    if os.path.basename(f).startswith('diff_'):
        continue
    code = os.path.basename(os.path.dirname(f))
    d = json.load(open(f, encoding='utf-8'))
    for nm, cb in (d.get('codebooks') or {}).items():
        if isinstance(cb, dict):
            cb_names.add(norm(cb.get('field_zh', '')))
            cb_names.add(norm(nm))
            if zh(cb.get('field_zh')) and not (cb.get('field_en') or '').strip():
                untr_cbt += 1
            for e in cb.get('entries', []):
                lz = (e.get('label_zh') or '').strip()
                if zh(lz) and U not in lz and not (e.get('label_en') or '').strip():
                    untr_label += 1
                    if len(sl) < 5: sl.append(f'{code}:{nm}:{lz[:14]}')
    for kz, ke in [('data_description_zh', 'data_description_en'), ('notes_zh', 'notes_en'),
                   ('primary_keys_raw', 'primary_keys_en'), ('name_zh', 'name_zh_en')]:
        if zh(d.get(kz)) and not (d.get(ke) or '').strip():
            untr_file += 1
    for x in d.get('fields', []):
        nz = (x.get('name_zh') or '').strip()
        if not nz:
            continue
        if U in nz:
            garbled += 1
            if len(sg) < 5: sg.append(f'{code}:{x.get("name_en")}')
            continue
        if not (x.get('name_zh_en') or '').strip():
            untr_name += 1
            if len(su) < 5: su.append(f'{code}:{nz[:12]}')
        dz = (x.get('description_zh') or '').strip()
        de = (x.get('description_en') or '').strip()
        if len(dz) >= 8 and U not in dz and not de:
            untr_desc += 1
        if len(re.findall(r'[一-鿿]', de)) >= 2:   # English that still carries Chinese = failed translation
            half_en += 1
            if len(sh) < 6: sh.append(f'{code}:{x.get("name_en")}')
        for m in NAMED.finditer(dz):
            nm = norm(m.group(1) or m.group(2))
            if len(nm) >= 2:
                refs.setdefault(nm, f'{code}:{x.get("name_en")}')

# known references that are NOT embeddable local tables (external standards, huge
# per-record free-text, or survey docs not shipped in the source package):
WHITELIST = {
    '適應症',            # Health59 — external per-drug-licence indications (free text)
    '血液腫瘤細詳血液腫瘤',  # Health14 HIST — WHO ICD-O-3 morphology standard (Topography IS built)
    '小時飲食食物',       # Society17 — food-classification doc, not in source ZIP
    '集區',              # Society17 — survey-internal sampling-block codes, not in source ZIP
}
# a referenced table is missing only if no codebook name contains/equals it
missing = {nm: ex for nm, ex in refs.items()
           if nm not in WHITELIST
           and not any(nm in c or c in nm for c in cb_names if c)}

gaps = []
if garbled: gaps.append(f'garbled names: {garbled} {sg}')
if untr_name: gaps.append(f'untranslated names: {untr_name} {su}')
if untr_desc: gaps.append(f'untranslated descriptions: {untr_desc}')
if half_en: gaps.append(f'English descriptions still containing Chinese: {half_en} {sh}')
if untr_label: gaps.append(f'codebook labels missing English: {untr_label} {sl}')
if untr_cbt: gaps.append(f'codebook table titles missing English: {untr_cbt}')
if untr_file: gaps.append(f'file-level blocks missing English: {untr_file}')
if missing:
    gaps.append(f'named code-tables referenced but NOT built: {len(missing)}')
    for nm, ex in sorted(missing.items()):
        gaps.append(f'    · {nm}  (e.g. {ex})')

if gaps:
    print('GAPS FOUND:')
    for g in gaps: print('  -' if not g.startswith('    ') else '', g)
else:
    print('CLEAN — no garbled/untranslated/missing-table gaps.')
