"""Build the three Society10 (NHIS) survey code-tables that field descriptions
reference via 詳見「…代碼」譯碼說明 — extracted from the 102年 manual appendix
(clean text layer, pp.211-212). Attach to every Society10 field that cites them."""
import sys, io, json, glob, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SRC = '資料庫使用手冊 Society10-102年國民健康訪問調查檔 附錄·譯碼說明'

BODY = [  # 受傷部位代碼
 ('0','無','None'),('1','頭部(非臉部)','Head (non-facial)'),('2','臉部(頭部)','Face (head)'),
 ('3','眼部(頭部)','Eye (head)'),('4','鼻(頭部)','Nose (head)'),('5','嘴(頭部)','Mouth (head)'),
 ('6','牙齒(頭部)','Teeth (head)'),('7','頜、顎(頭部)','Jaw (head)'),('8','耳(頭部)','Ear (head)'),
 ('9','手肘(上肢)','Elbow (upper limb)'),('10','手指(上肢)','Finger (upper limb)'),
 ('11','手掌(上肢)','Hand/palm (upper limb)'),('12','前臂(上肢)','Forearm (upper limb)'),
 ('13','上臂(上肢)','Upper arm (upper limb)'),('14','大腿(下肢)','Thigh (lower limb)'),
 ('15','小腿(下肢)','Lower leg (lower limb)'),('16','膝(下肢)','Knee (lower limb)'),
 ('17','腳/腳掌(下肢)','Foot/sole (lower limb)'),('18','腳趾(下肢)','Toe (lower limb)'),
 ('19','腳踝(下肢)','Ankle (lower limb)'),('20','胸(上軀幹)','Chest (upper trunk)'),
 ('21','背部(上軀幹)','Back (upper trunk)'),('22','肩(上軀幹)','Shoulder (upper trunk)'),
 ('23','頸部(上軀幹)','Neck (upper trunk)'),('24','腰部(下軀幹)','Waist/lower back (lower trunk)'),
 ('25','臀(下軀幹)','Buttock (lower trunk)'),('26','髖部(下軀幹)','Hip (lower trunk)'),
 ('27','腹部(下軀幹)','Abdomen (lower trunk)'),('28','鼠蹊部(下軀幹)','Groin (lower trunk)'),
 ('29','會陰部(下軀幹)','Perineum (lower trunk)'),('30','其他部位','Other site'),
]
NATURE = [  # 受傷種類代碼
 ('0','無','None'),('1','骨折或脫臼','Fracture or dislocation'),
 ('2','扭傷、拉傷、挫傷','Sprain, strain, contusion'),('3','切、割傷','Cut / laceration'),
 ('4','擦傷','Abrasion'),('5','瘀傷','Bruise'),('6','燒燙傷','Burn / scald'),
 ('7','昆蟲咬傷','Insect bite'),('8','動物咬傷','Animal bite'),('9','內出血','Internal bleeding'),
 ('10','撕裂傷','Tear laceration'),('11','穿刺傷','Puncture wound'),('12','其他','Other'),
]
ALCOHOL = [  # 酒名種類代碼 (by alcohol concentration)
 ('1','啤酒/水果調味酒(如冰火)/涼酒等"濃度5%"以下的酒類','Beer / fruit-flavoured liquor / cooling liquor, ABV ≤5%'),
 ('2','維士比/保力達/藥酒類等"濃度6-10%"的酒類','Whisbih / Paolyta / medicinal liquor, ABV 6-10%'),
 ('3','玫瑰紅酒/紅、白葡萄酒/日本甜梅酒(choya)等"濃度11-15%"的酒類','Rosé / red & white wine / plum wine, ABV 11-15%'),
 ('4','紹興酒/紅露酒/烏梅酒/台灣米酒等"濃度16-20%"的酒類','Shaoxing / Hongloujiu / plum / Taiwan rice wine, ABV 16-20%'),
 ('5','參茸酒/鹿茸酒等"濃度21-29%"的酒類','Ginseng-antler liquor etc., ABV 21-29%'),
 ('6','高梁酒/白蘭地/威士忌/伏特加/竹葉青/米酒頭等"濃度30-49%"的酒類','Kaoliang / brandy / whisky / vodka etc., ABV 30-49%'),
 ('7','高梁酒/茅台酒/玉山二鍋頭/特級高梁酒等"濃度50%以上"的酒類','Kaoliang / Moutai / premium kaoliang, ABV ≥50%'),
 ('8','其他(不知濃度、無法歸類的酒類)','Other (unknown concentration / unclassifiable)'),
]
def mk(field_zh, rows):
    return {'field_zh': field_zh, 'source': SRC, 'source_url': None,
            'entries': [{'code': c, 'label_zh': z, 'label_en': e} for c, z, e in rows]}

TABLES = [  # (marker in description, codebook builder)
    ('受傷部位代碼', mk('受傷部位代碼', BODY)),
    ('受傷種類代碼', mk('受傷種類代碼', NATURE)),
    ('酒名種類代碼', mk('酒名種類代碼', ALCOHOL)),
]
VAR = re.compile(r'^[A-Za-z][A-Za-z0-9_]+$')   # real variable name, not 'Char' artifact

attached = 0
for f in glob.glob('extracted/Society10/*.json'):
    d = json.load(open(f, encoding='utf-8'))
    cbs = d.setdefault('codebooks', {})
    changed = False
    for x in d.get('fields', []):
        ne = (x.get('name_en') or '').strip()
        dz = x.get('description_zh') or ''
        if ne == 'Char' or not VAR.match(ne) or ne in cbs:
            continue
        for marker, cb in TABLES:
            if marker in dz:
                cbs[ne] = json.loads(json.dumps(cb))   # own copy per field
                attached += 1; changed = True
                break
    if changed:
        json.dump(d, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('Society10 codebook attachments:', attached)
