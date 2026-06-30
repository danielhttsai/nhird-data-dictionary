import { base } from '$app/paths';

export const entries = async () => {
  const fs = await import('node:fs');
  const path = await import('node:path');
  const dir = path.join(process.cwd(), 'static/data/file');
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f => f.endsWith('.json'))
    .map(f => ({ code: f.replace('.json', '') }));
};

export const load = async ({ fetch, params }) => {
  const r = await fetch(`${base}/data/file/${params.code}.json`);
  if (!r.ok) throw new Error(`failed to load file ${params.code}: ${r.status}`);
  return { file: await r.json() };
};
