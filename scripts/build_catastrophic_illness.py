import sys, io, json, glob, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Parsed from the official 附表一 全民健康保險重大傷病項目及其證明有效期限
# (113.9.16 發布修訂, 適用 114/1/1 起). See raw_pdfs/catastrophic_illness_items_113.9.16.pdf
ITEMS = json.load(open('raw_pdfs/catastrophic_illness_items_113.9.16.json', encoding='utf-8'))

# category 14's header line did not survive PDF extraction; fill from its items.
CAT_FIX = {14: '嚴重營養不良者，給予全靜脈營養已超過三十天，且病情已達穩定狀態，口攝飲食仍無法提供足量營養者'}
# concise English for each of the 30 categories (headers have no English in the source)
CAT_EN = {
 1:"Cancer requiring active or long-term treatment",2:"Hereditary coagulation-factor deficiency",
 3:"Severe hemolytic and aplastic anemia",4:"Chronic renal failure (uremia) on regular dialysis",
 5:"Systemic autoimmune syndromes requiring lifelong treatment",6:"Chronic psychiatric illness",
 7:"Congenital metabolic disorders (excl. G6PD deficiency)",
 8:"Congenital malformations and chromosomal abnormalities",
 9:"Burns over >=20% body surface, or facial burns with sensory-organ dysfunction",
 10:"Organ transplantation",11:"Complications of polio / cerebral palsy (moderate+ disability)",
 12:"Major trauma (Injury Severity Score >=16)",13:"Respiratory failure on long-term ventilator",
 14:"Severe malnutrition (on total parenteral nutrition >30 days)",
 15:"Severe decompression sickness or air embolism from diving",16:"Myasthenia gravis",
 17:"Congenital immunodeficiency",18:"Complications of spinal-cord injury/disease (moderate+ disability)",
 19:"Occupational diseases",20:"Acute cerebrovascular disease (within 1 month of onset)",
 21:"Multiple sclerosis",22:"Congenital muscular dystrophy",23:"Congenital malformations of the skin",
 24:"Hansen's disease (leprosy)",25:"Liver cirrhosis with specified complications",
 26:"Complications of prematurity",27:"Toxic effects of arsenic (blackfoot disease)",
 28:"Motor neuron disease (moderate+ disability or ventilator-dependent; incl. ALS)",
 29:"Creutzfeldt-Jakob disease",
 30:"Rare diseases designated under the Rare Disease Control and Orphan Drug Act (see the rare-disease list)",
}

# ---- HV_TYPE codebook: the 30 official categories ----
cat_zh = {}
for it in ITEMS:
    n = it['cat_no']
    z = (it.get('cat_zh') or '').strip() or CAT_FIX.get(n, '')
    if n not in cat_zh and z:
        cat_zh[n] = z
for n, z in CAT_FIX.items():
    cat_zh.setdefault(n, z)
hv_entries = [{'code': str(n), 'label_zh': cat_zh.get(n, ''), 'label_en': CAT_EN.get(n, '')}
              for n in range(1, 31)]
hv_codebook = {
    'field_zh': '重大傷病類別',
    'source': '全民健康保險重大傷病項目及其證明有效期限（附表一，113.9.16 發布修訂，114/1/1 起適用）— 共 30 類',
    'source_url': 'https://www.nhi.gov.tw/ch/cp-6086-caf5f-2957-1.html',
    'entries': hv_entries,
}

# ---- DISE_CODE codebook: the detailed ICD -> item table (診斷代碼對照) ----
def short_cat(n):
    z = cat_zh.get(n, '')
    z = z.split('〔')[0].split('，')[0].split('(')[0].strip()
    return f'{n}. {z}'
dc_entries = []
for it in ITEMS:
    icd = (it.get('icd') or '').strip()
    en = (it.get('item_en') or '').strip()
    val = (it.get('validity') or '').strip()
    label_en = en
    if val:
        label_en = (en + ' · ' if en else '') + f'證明有效期限 {val}'
    dc_entries.append({
        'code': icd or '—',
        'label_zh': (it.get('item_zh') or '').strip(),
        'label_en': label_en,
        'section': short_cat(it['cat_no']),
    })
dc_codebook = {
    'field_zh': '診斷代碼（重大傷病項目 ICD-10-CM 對照）',
    'source': '全民健康保險重大傷病項目及其證明有效期限（附表一，113.9.16 發布修訂）ICD-10-CM 2023 年版',
    'source_url': 'https://www.nhi.gov.tw/ch/cp-6086-caf5f-2957-1.html',
    'entries': dc_entries,
}

for f in glob.glob('extracted/Health08/*.json'):
    if os.path.basename(f).startswith('diff_'):
        continue
    d = json.load(open(f, encoding='utf-8'))
    names = {fl.get('name_en') for fl in d.get('fields', [])}
    if 'HV_TYPE' not in names:
        continue
    d.setdefault('codebooks', {})
    d['codebooks']['HV_TYPE'] = hv_codebook
    # the diagnosis-code field is named DISE_CODE in the legacy version and was
    # renamed ICD9CM_CODE in the 2025/06/24 version — attach to whichever exists.
    attached = [k for k in ('DISE_CODE', 'ICD9CM_CODE') if k in names]
    for k in attached:
        d['codebooks'][k] = dc_codebook
    json.dump(d, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'{os.path.basename(f)}: HV_TYPE={len(hv_entries)} cats, {"/".join(attached)}={len(dc_entries)} items')
