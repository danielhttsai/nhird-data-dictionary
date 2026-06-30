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
    .replace(/^(Health|Society|Welfare)[\w-]*?[_-]/i, '')  // drop code prefix
    .replace(/\(20250624\s*起適用\)/g, '')
    .replace(/\(.*?版本\)/g, '')
    .replace(/_+|-{2,}/g, ' – ')
    .trim();
  return t;
}

// Pick the clean DB title: the main (zip / main-PDF, non-wave, non-xls) version's
// listing name, cleaned. Falls back to '' so callers can use another source.
function fileTitle(versions) {
  const mains = versions.filter(v => v.file_type !== 'xls' && !v.version_id.includes('__wave_'));
  // Prefer the legacy main (shortest, no "(20250624…)" suffix).
  mains.sort((a, b) => (a.name_zh || '').length - (b.name_zh || '').length);
  for (const v of mains) {
    const t = cleanListingTitle(v.name_zh);
    if (t && !t.includes('�')) return t;
  }
  return '';
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
const TOPIC_CODES = new Set(['Health82','Health83','Health101','Health103','Health104','Health102','Health48','Health49']);

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

  // Pick a "primary" version for catalogue display.
  //  - Core databases: newest PDF version that has fields (legacy → post-20250624).
  //  - Pure-survey codes (only Excel codebooks): the richest wave, so the card
  //    shows a representative variable count rather than a 3-field consent file.
  const withExtract = sorted.filter(v => extracted[v.version_id]);
  const withFields = withExtract.filter(v => (extracted[v.version_id].fields?.length || 0) > 0);
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
  const dbTitle = fileTitle(sorted) || primaryExtracted?.name_zh || primary.name_zh || '';
  // For catalogue display, prefer the PDF's English file name; fall back to the
  // LLM-translated Chinese name. Drop it if it's actually a sub-table list
  // (very long / repeated) so the card doesn't show a wall of text.
  const enCandidate = (primaryExtracted?.name_en && primaryExtracted.name_en.trim())
    || primaryExtracted?.name_zh_en
    || '';
  const englishName = (enCandidate.length > 60 || /Questionnaire.*Questionnaire/i.test(enCandidate))
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
    return {
      ...v,
      meta: metaOf(ex),
      fields_file,
      field_count: ex?.fields?.length ?? null,
      supplementary: !!ex && (ex.fields?.length || 0) === 0
    };
  });
  const filePayload = {
    code,
    category,
    name_zh: item.name_zh,
    name_en: item.name_en,
    versions: slimVersions,
    diffs
  };
  fs.writeFileSync(
    path.join(OUT, 'file', `${code}.json`),
    JSON.stringify(filePayload, null, 0)
  );

  // Per-field entries for the search index (names only + short description —
  // keeps search-fields.json small enough to load on the /search page).
  for (const v of sorted) {
    const ex = extracted[v.version_id];
    if (!ex) continue;
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
  // Health → Society → Welfare → Topic
  const order = { Health: 1, Society: 2, Welfare: 3, Topic: 4 };
  return (order[a.category] - order[b.category])
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
