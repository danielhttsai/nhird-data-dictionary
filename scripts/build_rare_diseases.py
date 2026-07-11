import sys, io, json, zipfile, os, re
from xml.etree import ElementTree as ET
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ODT = 'raw_pdfs/rare_diseases_HPA_20260324.odt'   # HPA 公告罕見疾病名單暨 ICD-10-CM 編碼一覽表
TBL = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'

root = ET.fromstring(zipfile.ZipFile(ODT).read('content.xml').decode('utf-8'))
def celltext(c): return ''.join(c.itertext()).strip()
def row_cells(tr):
    # Preserve column alignment: expand number-columns-repeated and treat
    # covered-table-cell (the shadow of a merged span) as an empty placeholder.
    out = []
    for el in tr:
        tag = el.tag
        if tag.endswith('}table-cell') or tag.endswith('}covered-table-cell'):
            rep = int(el.get(TBL + 'number-columns-repeated', '1'))
            txt = celltext(el) if tag.endswith('}table-cell') else ''
            if not txt:
                rep = min(rep, 8)   # avoid huge trailing-empty repeats; we only need 5 cols
            out.extend([txt] * rep)
    return out
rows = []
for tbl in root.iter(TBL + 'table'):
    for tr in tbl.iter(TBL + 'table-row'):
        cells = row_cells(tr)
        if any(cells):
            rows.append(cells)

CJK = re.compile(r'[一-鿿]')
ICD = re.compile(r'^[A-TV-Z][0-9]')       # ICD-10-CM code start, e.g. E72.20
GRP = re.compile(r'^[A-Z]\d+$')            # group prefix, e.g. A1, A11, N1
entries = []
group = ''; group_prefix = ''
for r in rows:
    joined = ''.join(r)
    if '中文病名' in joined or joined.strip().startswith('分類'):
        continue
    nonempty = [c.strip() for c in r if c.strip()]
    if not nonempty:
        continue
    # top-level category "A.先天性代謝異常" (single meaningful cell, letter+dot)
    if len(nonempty) == 1 and re.match(r'^[A-Z]\.', nonempty[0]):
        continue
    # sub-group header "◎A1 尿素循環代謝異常..."
    if nonempty[0].startswith('◎'):
        group = nonempty[0].lstrip('◎').strip()
        gm = re.match(r'^([A-Z]\d+)', group)
        if gm:
            group_prefix = gm.group(1)
        continue
    # a bare group-prefix cell updates the running prefix
    if GRP.match(r[0].strip() if r else ''):
        group_prefix = r[0].strip()
    # classify remaining cells by content
    seq = zh = en = icd = ''
    for c in nonempty:
        if GRP.match(c):                      # the group-prefix cell itself
            continue
        if not seq and re.fullmatch(r'\d{1,3}', c):
            seq = c; continue
        if not icd and ICD.match(c) and not CJK.search(c):
            icd = c; continue
        if not zh and CJK.search(c):
            zh = c; continue
        if not en and re.search(r'[A-Za-z]', c) and not CJK.search(c):
            en = c; continue
    if not zh:
        continue
    code = f'{group_prefix}-{seq}' if (group_prefix and seq) else (group_prefix or icd or str(len(entries) + 1))
    label_en = en
    if icd:
        label_en = (en + ' · ' if en else '') + f'ICD-10-CM: {icd}'
    entries.append({'code': code, 'label_zh': zh, 'label_en': label_en, 'section': group})

print('rare-disease entries:', len(entries))
print('sample:', entries[0], '...', entries[-1])

codebook = {
    'field_zh': '罕見疾病序號 / 疾病代碼',
    'source': '衛生福利部國民健康署《公告罕見疾病名單暨 ICD-10-CM 編碼一覽表》(2026-03-24 更新)',
    'source_url': 'https://www.hpa.gov.tw/Pages/List.aspx?nodeid=4970',
    'entries': entries,
}
# Attach to Health51 (D_CODE) and Health08 (RS_CODE_A / RS_CODE_B)
def attach(code_dir, field_keys):
    import glob
    for f in glob.glob(f'extracted/{code_dir}/*.json'):
        if os.path.basename(f).startswith('diff_'): continue
        d = json.load(open(f, encoding='utf-8'))
        if not d.get('fields'): continue
        d.setdefault('codebooks', {})
        for k in field_keys:
            # only attach if the field exists in this version
            if any((fl.get('name_en') == k) for fl in d['fields']):
                d['codebooks'][k] = codebook
        json.dump(d, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f'  attached rare codebook to {code_dir}:{os.path.basename(f)} -> {field_keys}')

attach('Health51', ['D_CODE'])
attach('Health08', ['RS_CODE_A', 'RS_CODE_B'])
