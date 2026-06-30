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

  // Pick a "primary" version for catalogue display: prefer the newest version
  // that actually has fields (avoids landing on a 0-field supplementary survey
  // doc such as 實施計畫/問卷). Fall back to any extracted, then last manifest.
  const withExtract = sorted.filter(v => extracted[v.version_id]);
  const withFields = withExtract.filter(v => (extracted[v.version_id].fields?.length || 0) > 0);
  const primary = withFields.at(-1) || withExtract.at(-1) || sorted.at(-1);
  const primaryExtracted = extracted[primary.version_id];

  const category = TOPIC_CODES.has(code) ? 'Topic' : primary.category;
  // For catalogue display, prefer the PDF's English file name; fall back to the
  // LLM-translated Chinese name.
  const englishName = (primaryExtracted?.name_en && primaryExtracted.name_en.trim())
    || primaryExtracted?.name_zh_en
    || '';
  const item = {
    code,
    category,
    name_zh: primaryExtracted?.name_zh || primary.name_zh || '',
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

  // Per-code full payload — strip heavy fields that aren't surfaced in the UI
  const stripExtracted = (ex) => {
    if (!ex) return null;
    const { raw_text_first_page, ...rest } = ex;
    return rest;
  };
  const filePayload = {
    code,
    category,
    name_zh: item.name_zh,
    name_en: item.name_en,
    versions: sorted.map(v => ({
      ...v,
      extracted: stripExtracted(extracted[v.version_id])
    })),
    diffs
  };
  fs.writeFileSync(
    path.join(OUT, 'file', `${code}.json`),
    JSON.stringify(filePayload, null, 0)
  );

  // Per-field entries for the search index
  for (const v of sorted) {
    const ex = extracted[v.version_id];
    if (!ex) continue;
    for (const f of ex.fields || []) {
      allFields.push({
        id: `${code}|${v.version_id}|${f.name_en || f.seq}`,
        code,
        version_id: v.version_id,
        seq: f.seq,
        name_zh: f.name_zh || '',
        name_zh_en: f.name_zh_en || '',
        name_en: f.name_en || '',
        type: f.type || '',
        length: f.length ?? '',
        description_zh: (f.description_zh || '').slice(0, 200),
        description_en: (f.description_en || '').slice(0, 200)
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
    const codePath = path.join(EXTRACTED, item.code, `${v.version_id}.json`);
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
