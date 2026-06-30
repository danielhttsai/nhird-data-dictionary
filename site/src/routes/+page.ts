import { base } from '$app/paths';

export const load = async ({ fetch }) => {
  const r = await fetch(`${base}/data/catalogue.json`);
  if (!r.ok) throw new Error(`failed to load catalogue: ${r.status}`);
  return { catalogue: await r.json() };
};
