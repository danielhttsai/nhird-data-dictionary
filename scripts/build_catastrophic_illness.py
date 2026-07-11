import sys, io, json, glob, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 全民健康保險重大傷病範圍 — 30 categories (HV_TYPE / IIV_TYPE).
# zh verbatim from the public 重大傷病範圍; en = faithful translation.
CATS = [
 ("需積極或長期治療之癌症", "Cancer requiring active or long-term treatment"),
 ("遺傳性凝血因子缺乏", "Hereditary coagulation-factor deficiency"),
 ("嚴重溶血性及再生不良性貧血", "Severe hemolytic and aplastic anemia"),
 ("慢性腎衰竭（尿毒症），必須接受定期透析治療者", "Chronic renal failure (uremia) requiring regular dialysis"),
 ("需終身治療之全身性自體免疫症候群", "Systemic autoimmune syndromes requiring lifelong treatment"),
 ("慢性精神病", "Chronic psychiatric illness"),
 ("先天性新陳代謝異常疾病", "Congenital metabolic disorders"),
 ("心、肺、胃腸、腎臟、神經、骨骼系統等之先天性畸形及染色體異常", "Congenital malformations (cardiac, pulmonary, GI, renal, neurological, skeletal) and chromosomal abnormalities"),
 ("燒燙傷面積達全身百分之二十以上；或顏面燒燙傷合併五官功能障礙者", "Burns over >=20% of body surface, or facial burns with sensory-organ dysfunction"),
 ("接受器官移植", "Organ transplantation"),
 ("小兒麻痺、腦性麻痺所引起之神經、肌肉、骨骼、肺臟等之併發症者", "Complications of polio or cerebral palsy (neuro / muscular / skeletal / pulmonary)"),
 ("重大創傷且其嚴重程度到達創傷嚴重程度分數十六分以上者", "Major trauma with Injury Severity Score >=16"),
 ("因呼吸衰竭需長期使用呼吸器", "Respiratory failure requiring long-term ventilator use"),
 ("嚴重營養不良者", "Severe malnutrition"),
 ("因潛水、或減壓不當引起之嚴重型減壓病或空氣栓塞症", "Severe decompression sickness or air embolism from diving / improper decompression"),
 ("重症肌無力症", "Myasthenia gravis"),
 ("先天性免疫不全症", "Congenital immunodeficiency"),
 ("脊髓損傷或病變所引起之神經、肌肉、皮膚、骨骼、心肺、泌尿及腸胃等之併發症者", "Complications of spinal-cord injury or disease (neuro, muscular, skin, skeletal, cardiopulmonary, urinary, GI)"),
 ("職業病", "Occupational diseases"),
 ("急性腦血管疾病", "Acute cerebrovascular disease"),
 ("多發性硬化症", "Multiple sclerosis"),
 ("先天性肌肉萎縮症", "Congenital muscular dystrophy"),
 ("外皮之先天畸形", "Congenital malformations of the skin"),
 ("漢生病", "Hansen's disease (leprosy)"),
 ("肝硬化症，併有下列情形之一者", "Liver cirrhosis with one of the specified complications"),
 ("早產兒所引起之神經、肌肉、骨骼、心臟、肺臟等之併發症", "Complications of prematurity (neuro, muscular, skeletal, cardiac, pulmonary)"),
 ("砷及其化合物之毒性作用（烏腳病）", "Toxic effects of arsenic and its compounds (blackfoot disease)"),
 ("運動神經元疾病其身心障礙等級在中度以上或須使用呼吸器者", "Motor neuron disease (moderate-or-higher disability, or ventilator-dependent)"),
 ("庫賈氏病", "Creutzfeldt-Jakob disease"),
 ("經中央主管機關依罕見疾病防治及藥物法第三條第一項指定公告之罕見疾病", "Rare diseases designated by the central authority under the Rare Disease Control and Orphan Drug Act (see the rare-disease list on the RS_CODE fields)"),
]
entries = [{"code": str(i + 1), "label_zh": zh, "label_en": en} for i, (zh, en) in enumerate(CATS)]
codebook = {
    "field_zh": "重大傷病類別",
    "source": "全民健康保險重大傷病範圍（中央健康保險署重大傷病專區，共 30 類）",
    "source_url": "https://www.nhi.gov.tw/ch/cp-6086-caf5f-2957-1.html",
    "entries": entries,
}
for f in glob.glob('extracted/Health08/*.json'):
    if os.path.basename(f).startswith('diff_'):
        continue
    d = json.load(open(f, encoding='utf-8'))
    if not any(fl.get('name_en') == 'HV_TYPE' for fl in d.get('fields', [])):
        continue
    d.setdefault('codebooks', {})['HV_TYPE'] = codebook
    json.dump(d, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'attached HV_TYPE codebook ({len(entries)} categories) to {os.path.basename(f)}')
