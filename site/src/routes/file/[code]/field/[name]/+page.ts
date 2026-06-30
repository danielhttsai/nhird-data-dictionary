// Field detail pages are too numerous (~thousands) to prerender economically.
// Serve via 404.html SPA fallback — the static adapter writes 404.html and
// GitHub Pages serves it for unknown routes, where the client router renders.
export const prerender = false;
export const ssr = false;

export const load = async ({ fetch, params }) => {
  const r = await fetch(`${base}/data/file/${params.code}.json`);
  if (!r.ok) throw new Error(`failed to load file ${params.code}: ${r.status}`);
  const file = await r.json();

  // Slim down: only carry the data this page actually renders.
  const occurrences = [];
  for (const v of file.versions || []) {
    if (!v.extracted) continue;
    const f = v.extracted.fields?.find((x) => x.name_en === params.name);
    if (!f) continue;
    occurrences.push({
      version_id: v.version_id,
      version_label: v.version_label,
      doc_last_updated: v.doc_last_updated,
      field: f,
      codebook: v.extracted.codebooks?.[params.name] || null
    });
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
