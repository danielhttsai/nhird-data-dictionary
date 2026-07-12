// Build the site/static/data/ payload from ../extracted and ../manifest.json.
// Runs before vite dev / build.
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const EXTRACTED = path.join(ROOT, 'extracted');
const MANIFEST = path.join(ROOT, 'manifest.json');
const QA = path.join(ROOT, 'qa_report.json');
const OUT = path.join(import.meta.dirname, 'static', 'data');

fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(path.join(OUT, 'file'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'fields'), { recursive: true });

// Mirror scripts/extract_all.py _safe(): make a filename-safe slug from a
// version_id (Unicode word chars + dash kept, everything else → "_", cap 80).
function safeName(name) {
  return String(name).replace(/[^\p{L}\p{N}_-]/gu, '_').slice(0, 80);
}

// Clean database-level title from the MOHW listing name, e.g.
// "Welfare08_婦女生活狀況調查" → "婦女生活狀況調查". Used for the card / file
// title so it never shows a per-version sub-table list or a mojibake codebook
// filename.
function cleanListingTitle(s) {
  if (!s) return '';
  let t = String(s)
    // Drop the code prefix incl. a "-N" suffix (Society12-1) and any separator
    // that follows it (underscore, space, or dash).
    .replace(/^(Health|Society|Welfare)\d+(?:-\d+)?[\s_–-]*/i, '')
    .replace(/\(20250624\s*起適用\)/g, '')
    .replace(/\(.*?版本\)/g, '')
    .replace(/_+|-{2,}/g, ' – ')
    .trim();
  return t;
}

// Pick the clean DB title: the main (zip / main-PDF, non-wave, non-xls) version's
// listing name, cleaned. Falls back to '' so callers can use another source.
function fileTitle(versions) {
  const mains = versions.filter(v =>
    v.file_type !== 'xls'
    && !v.version_id.includes('__wave_')
    && v.version_id !== 'appendix'              // 附錄 isn't the database's name
    && !(v.name_zh || '').includes('附錄'));
  // Prefer the shortest clean name (drops "(…版本)" / "(20250624…)" suffixes).
  mains.sort((a, b) => (a.name_zh || '').length - (b.name_zh || '').length);
  for (const v of mains) {
    const t = cleanListingTitle(v.name_zh);
    if (t && !t.includes('�')) return t;
  }
  return '';
}

// PDF-extracted English file names lose inter-word spaces (AMBULATORYCARE,
// byAdmissions) and are frequently ALL-CAPS. These are the site's most visible
// titles, so override them with clean canonical English names. Keys are the
// file code; both "Society12" and "Society12-1" are listed where the code varies.
const CANON_EN = {
  Health01: 'Ambulatory Care Expenditures by Visits',
  Health02: 'Inpatient Expenditures by Admissions',
  Health03: 'Expenditures for Prescriptions Dispensed at Contracted Pharmacies',
  Health04: 'Details of Ambulatory Care Orders',
  Health05: 'Details of Inpatient Orders',
  Health06: 'Details of Prescriptions Dispensed at Contracted Pharmacies',
  Health07: 'Registry for Beneficiaries',
  Health08: 'Registry for Catastrophic Illness Patients',
  Health09: 'Birth Reporting Database',
  Health10: 'Cause of Death Data',
  Health101: 'Lung Cancer Health Database',
  Health103: 'Cardiovascular Database — Main File',
  Health104: 'Liver Cancer Health Database',
  Health105: 'Lung Cancer Health Database',
  Health12: 'Health Services Utilization of Medical Facilities',
  Health13: 'Health Resources of Medical Facilities',
  Health14: 'Taiwan Cancer Registry — Long Form',
  Health15: 'Cancer Registration Database — Short Form',
  Health16: 'Cancer Registration Database — TCDB',
  Health17: 'Drug Data',
  Health25: 'Registry for Contracted Medical Facilities',
  Health29: 'Registry for Medical Personnel',
  Health30: 'Multiple Cause of Death Data',
  Health31: 'Delayed Report of Death Data',
  Health37: 'National Health Insurance Drug Price File',
  Health42: 'Monthly Claim Summary for Ambulatory Care Claims',
  Health43: 'Monthly Claim Summary for Inpatient Claims',
  Health48: 'Taiwan Birth Cohort Study',
  Health51: 'Reported Rare Disease Database',
  Health52: 'Artificial Reproduction Database',
  Health53: 'Delayed Report of Multiple Cause of Death Data',
  Health54: 'Pap Smear Test',
  Health55: 'Colorectal Cancer Screening',
  Health56: 'Breast Cancer Screening',
  Health57: 'Oral Mucosal Screening',
  Health59: 'National Genetic Diagnosis System Database',
  Health60: 'Maternal and Child Health Database',
  Health61: 'Notifiable Disease Dataset of Confirmed Cases',
  Health79: 'National Immunization Information System (NIIS)',
  Health73: 'Tuberculosis (TB) Database',
  Welfare20: 'Disabled Beneficiary Case Management — Case Manager Record',
  Health82: 'Colorectal Cancer Health Database',
  Health83: 'Breast Cancer Health Database',
  Health99: 'Adult Preventive Health Service Database',
  Society10: '2013 National Health Interview Survey',
  Society12: 'Social Environmental Biomarker of Aging Study (SEBAS)',
  'Society12-1': 'Social Environmental Biomarker of Aging Study (SEBAS)',
  Society17: 'Survey Questionnaires (by Age Group), Physical Examination & 24-Hour Diet Recall',
  Welfare04: 'Low-income and Middle-income Family Living Condition Survey',
  Welfare05: 'Senior Citizen Condition Survey 2013',
  Welfare06: 'Physically and Mentally Disabled Citizens Living and Demand Assessment Survey',
  Welfare08: "Women's Living Conditions Survey",
  Welfare11: 'Low-income and Middle-low-income Households — Disability',
  Welfare12: 'Family Violence Data',
  Welfare14: 'Reported Data of Protection of Children and Youths',
  Welfare15: 'Reported Data of Sexual Assault',
  Welfare19: 'Children and Youth Living Conditions Survey 2018',
};

const SMALL_WORDS = new Set(['a','an','and','as','at','by','for','from','in','of','on','or','the','to','with']);
// Best-effort cleanup for any English name not in CANON_EN: re-insert spaces lost
// at camelCase / letter-digit boundaries and normalise casing for readability.
// Cannot recover spaces inside a run of all-caps (AMBULATORYCARE) — that is what
// CANON_EN is for.
function cleanEnglishName(s) {
  if (!s) return '';
  let t = String(s)
    .replace(/([a-z])([A-Z])/g, '$1 $2')     // byAdmissions -> by Admissions
    .replace(/([A-Za-z])(\d)/g, '$1 $2')      // File2 -> File 2
    .replace(/\s+/g, ' ')
    .trim();
  if (!/[a-z]/.test(t)) t = t.toLowerCase();  // ALL CAPS -> lower, then title-case
  return t.split(' ').map((w, i) => {
    if (/^[A-Z]{2,}$/.test(w) && w.length <= 5) return w;      // keep acronyms (TCDB)
    const lw = w.toLowerCase();
    if (i > 0 && SMALL_WORDS.has(lw)) return lw;
    return w.charAt(0).toUpperCase() + w.slice(1);
  }).join(' ');
}

const manifest = JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
const qa = fs.existsSync(QA) ? JSON.parse(fs.readFileSync(QA, 'utf8')) : { entries: [] };
const qaByKey = new Map(qa.entries.map(e => [`${e.code}|${e.version_id}`, e]));

// Group manifest versions by code
const byCode = new Map();
for (const v of manifest.versions) {
  if (!byCode.has(v.code)) byCode.set(v.code, []);
  byCode.get(v.code).push(v);
}

// Topic-specific Health## that are subject-domain databases (not core claims)
const TOPIC_CODES = new Set(['Health82','Health83','Health101','Health103','Health104','Health102','Health48','Health49','Health60']);

const catalogue = [];   // top-level entries shown on the landing page
const allFields = [];   // for search index

// Chronological-ish sort key for a version_id. Handles:
//   legacy / post-20250624 ; period-pre-2010 / 2011-2017 / 2018-later (+_post) ;
//   ...__wave_ROC###_AD#### survey waves ; ...__wave_<name> supplementary docs.
function versionSortKey(vid) {
  const adm = vid.includes('post-20250624') ? 1 : 0;     // revision: legacy < post
  const adYear = vid.match(/AD(\d{4})/);
  if (adYear) return [2, parseInt(adYear[1], 10), adm];   // dated survey waves, by year
  const age = vid.match(/_age(\d+)/);
  if (age) return [2, 1900 + parseInt(age[1], 10), adm];  // TBCS age waves, ordered by age
  if (vid.includes('period-pre-2010')) return [1, 2009, adm];
  if (vid.includes('period-2011-2017')) return [1, 2011, adm];
  if (vid.includes('period-2018-later')) return [1, 2018, adm];
  if (vid.startsWith('legacy') || vid.startsWith('post-20250624')) return [1, 9000, adm];
  // supplementary docs (實施計畫/調查表/問卷…) — group at the end
  return [3, 9999, adm];
}
for (const [code, versions] of byCode) {
  const sorted = versions.slice().sort((a, b) => {
    const ka = versionSortKey(a.version_id), kb = versionSortKey(b.version_id);
    for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] - kb[i];
    return a.version_id.localeCompare(b.version_id);
  });

  // Load all extracted JSONs for this code (PDFs only — ZIPs have no extracted JSON)
  const codeDir = path.join(EXTRACTED, code);
  const extracted = {};
  if (fs.existsSync(codeDir)) {
    for (const f of fs.readdirSync(codeDir)) {
      if (!f.endsWith('.json') || f.startsWith('diff_')) continue;
      const data = JSON.parse(fs.readFileSync(path.join(codeDir, f), 'utf8'));
      extracted[data.version_id] = data;
    }
  }
  // Collect diff files
  const diffs = [];
  if (fs.existsSync(codeDir)) {
    for (const f of fs.readdirSync(codeDir)) {
      if (!f.startsWith('diff_') || !f.endsWith('.json')) continue;
      diffs.push({
        file: f,
        data: JSON.parse(fs.readFileSync(path.join(codeDir, f), 'utf8'))
      });
    }
  }

  // Some survey-wave PDFs use a non-Unicode font encoding pdfplumber can't map,
  // so their extracted text is mostly replacement characters (). Detect and
  // treat such versions as having no usable data.
  const isGarbled = (ex) => {
    const fsx = ex?.fields || [];
    if (!fsx.length) return false;
    const bad = fsx.filter(f => (`${f.name_zh || ''}${f.description_zh || ''}`).includes('�')).length;
    return bad / fsx.length > 0.3
      || (`${ex.data_description_zh || ''}${ex.notes_zh || ''}`).includes('�');
  };

  // Pick a "primary" version for catalogue display.
  //  - Core databases: newest PDF version that has fields (legacy → post-20250624).
  //  - Pure-survey codes (only Excel codebooks): the richest wave, so the card
  //    shows a representative variable count rather than a 3-field consent file.
  const withExtract = sorted.filter(v => extracted[v.version_id]);
  const withFields = withExtract.filter(v =>
    (extracted[v.version_id].fields?.length || 0) > 0 && !isGarbled(extracted[v.version_id]));
  const pdfWithFields = withFields.filter(v => v.file_type !== 'xls');
  let primary;
  if (pdfWithFields.length) {
    primary = pdfWithFields.at(-1);
  } else if (withFields.length) {
    primary = withFields.slice().sort((a, b) =>
      (extracted[b.version_id].fields.length - extracted[a.version_id].fields.length))[0];
  } else {
    primary = withExtract.at(-1) || sorted.at(-1);
  }
  const primaryExtracted = extracted[primary.version_id];

  const category = TOPIC_CODES.has(code) ? 'Topic' : primary.category;
  // Database-level title from the clean MOHW listing name (never a per-version
  // sub-table list or a mojibake codebook filename). Fall back to extracted name.
  const dbTitle = fileTitle(sorted)
    || cleanListingTitle(primaryExtracted?.name_zh || primary.name_zh) || '';
  // For catalogue display, prefer the PDF's English file name; fall back to the
  // LLM-translated Chinese name. Drop it if it's actually a sub-table list
  // (very long / repeated) so the card doesn't show a wall of text.
  const rawEn = (primaryExtracted?.name_en && primaryExtracted.name_en.trim())
    || primaryExtracted?.name_zh_en
    || '';
  // Curated canonical title wins; otherwise clean up the mangled PDF English.
  const enCandidate = CANON_EN[code] || cleanEnglishName(rawEn);
  const englishName = (enCandidate.length > 90 || /Questionnaire.*Questionnaire/i.test(enCandidate))
    ? '' : enCandidate;
  const item = {
    code,
    category,
    name_zh: dbTitle,
    name_en: englishName,
    code_short: primaryExtracted?.code_short || '',
    frequency: primaryExtracted?.frequency || '',
    field_count: primaryExtracted?.field_count_declared ?? primaryExtracted?.fields?.length ?? null,
    versions: sorted.map(v => ({
      version_id: v.version_id,
      version_label: v.version_label,
      file_type: v.file_type,
      pdf_url: v.pdf_url,
      doc_last_updated: v.doc_last_updated,
      has_extract: !!extracted[v.version_id],
      field_count: extracted[v.version_id]?.fields?.length ?? null,
      supplementary: !!extracted[v.version_id] && (extracted[v.version_id].fields?.length || 0) === 0,
      qa: qaByKey.get(`${v.code}|${v.version_id}`) || null
    })),
    has_diffs: diffs.length > 0
  };
  catalogue.push(item);

  // Split the per-code payload so the file page loads fast:
  //   data/file/<code>.json        — slim: metadata + version list (NO field arrays)
  //   data/fields/<code>__<vid>.json — one per version: { fields, codebooks }
  // Fields are fetched lazily by the file page when a version is selected.
  const metaOf = (ex) => {
    if (!ex) return null;
    const { raw_text_first_page, fields, codebooks, ...meta } = ex;
    return meta;
  };
  const slimVersions = sorted.map(v => {
    const ex = extracted[v.version_id];
    let fields_file = null;
    if (ex) {
      const fname = `${code}__${safeName(v.version_id)}.json`;
      fs.writeFileSync(
        path.join(OUT, 'fields', fname),
        JSON.stringify({ fields: ex.fields || [], codebooks: ex.codebooks || {} }, null, 0)
      );
      fields_file = fname;
    }
    const garbled = ex ? isGarbled(ex) : false;
    return {
      ...v,
      meta: metaOf(ex),
      fields_file,
      field_count: ex?.fields?.length ?? null,
      supplementary: !!ex && (ex.fields?.length || 0) === 0,
      garbled
    };
  });
  const filePayload = {
    code,
    category,
    name_zh: item.name_zh,
    name_en: item.name_en,
    versions: slimVersions
    // NB: precomputed diffs are no longer emitted — the compare page derives
    // added/removed/changed client-side from the per-version field files.
  };
  fs.writeFileSync(
    path.join(OUT, 'file', `${code}.json`),
    JSON.stringify(filePayload, null, 0)
  );

  // Per-field entries for the search index (names only + short description —
  // keeps search-fields.json small enough to load on the /search page).
  for (const v of sorted) {
    const ex = extracted[v.version_id];
    if (!ex || isGarbled(ex)) continue;
    for (const f of ex.fields || []) {
      allFields.push({
        c: code,
        v: v.version_id,
        s: f.seq,
        zh: (f.name_zh || '').slice(0, 70),
        ze: (f.name_zh_en || '').slice(0, 70),
        en: f.name_en || '',
        // Survey (xls) fields already carry their question text in name_zh,
        // so skip the description there to keep the global index lean.
        d: v.file_type === 'xls' ? '' : (f.description_zh || '').slice(0, 70)
      });
    }
  }
}

catalogue.sort((a, b) => {
  // Health → Society → Welfare → Topic → TWCR
  const order = { Health: 1, Society: 2, Welfare: 3, Topic: 4, TWCR: 5 };
  return ((order[a.category] || 9) - (order[b.category] || 9))
    || a.code.localeCompare(b.code, 'en', { numeric: true });
});

fs.writeFileSync(path.join(OUT, 'catalogue.json'), JSON.stringify({
  generated_at: manifest.generated_at,
  count: catalogue.length,
  items: catalogue
}, null, 2));

fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 0));
fs.writeFileSync(path.join(OUT, 'search-fields.json'), JSON.stringify(allFields, null, 0));
fs.writeFileSync(path.join(OUT, 'qa_report.json'), JSON.stringify(qa, null, 0));

// Build codebook index: code → [{ field_zh, code_label, source_codes_per_file }]
const codebookIndex = new Map();
for (const item of catalogue) {
  for (const v of item.versions) {
    if (!v.has_extract) continue;
    const codePath = path.join(EXTRACTED, item.code, `${safeName(v.version_id)}.json`);
    if (!fs.existsSync(codePath)) continue;
    const ex = JSON.parse(fs.readFileSync(codePath, 'utf8'));
    for (const [cbName, cb] of Object.entries(ex.codebooks || {})) {
      if (!codebookIndex.has(cbName)) codebookIndex.set(cbName, []);
      codebookIndex.get(cbName).push({
        code: item.code,
        version_id: v.version_id,
        field_zh: cb.field_zh,
        n_entries: cb.entries?.length || 0
      });
    }
  }
}
fs.writeFileSync(path.join(OUT, 'codebooks-index.json'),
  JSON.stringify({
    count: codebookIndex.size,
    items: Object.fromEntries([...codebookIndex.entries()].sort())
  }, null, 0));

console.log(`prepare-data: ${catalogue.length} files | ${allFields.length} fields | ${codebookIndex.size} codebooks`);
