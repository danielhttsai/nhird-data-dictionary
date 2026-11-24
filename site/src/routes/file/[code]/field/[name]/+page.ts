// Field detail pages are too numerous (~tens of thousands) to prerender.
// Serve via 404.html SPA fallback — the static adapter writes 404.html and
// GitHub Pages serves it for unknown routes, where the client router renders.
import { base } from '$app/paths';

export const prerender = false;
export const ssr = false;

export const load = async ({ fetch, params, url }) => {
  const r = await fetch(`${base}/data/file/${params.code}.json`);
  if (!r.ok) throw new Error(`failed to load file ${params.code}: ${r.status}`);
  const file = await r.json();

  // Pick the version: the one named in ?v=, else the newest with fields.
  const wanted = url.searchParams.get('v');
  const withFields = (file.versions || []).filter((v) => v.fields_file);
  const target =
    withFields.find((v) => v.version_id === wanted) ||
    withFields.filter((v) => v.file_type !== 'xls').at(-1) ||
    withFields.at(-1);

  const occurrences = [];
  if (target) {
    const fr = await fetch(`${base}/data/fields/${target.fields_file}`);
    if (fr.ok) {
      const fd = await fr.json();
      // In a manual that documents several tables (Welfare20) a field is
      // addressed as <table code>.<column>, since OBJID, STATUS … recur.
      const key = (x) => (x.table ? `${x.table}.${x.name_en}` : x.name_en);
      const f = (fd.fields || []).find((x) => key(x) === params.name);
      if (f) {
        occurrences.push({
          version_id: target.version_id,
          version_label: target.version_label,
          doc_last_updated: target.doc_last_updated,
          field: f,
          table: f.table ? (target.meta?.tables || []).find((t) => t.code_short === f.table) || { code_short: f.table } : null,
          codebook: fd.codebooks?.[params.name] || null
        });
      }
    }
  }

  return {
    code: file.code,
    category: file.category,
    name_zh: file.name_zh,
    name_en: file.name_en,
    fieldName: params.name,
    occurrences
  };
};
