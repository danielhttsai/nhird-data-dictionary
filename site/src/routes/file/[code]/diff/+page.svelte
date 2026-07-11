<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const file = data.file;

  // Versions that actually have a field table (query targets).
  const versions = (file.versions || []).filter((v) => v.fields_file && (v.field_count || 0) > 0);
  const mains = versions.filter((v) => v.file_type !== 'xls' && !v.version_id.includes('__wave_'));

  function fmtDate(s) {
    const m = String(s || '').match(/(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[1]}/${m[2]}/${m[3]}` : s;
  }
  function vLabel(v) {
    if (!v) return '';
    if (v.file_type === 'xls') return (v.version_label || '').replace(/^Excel codebook · /, '');
    if (v.version_id.includes('__wave_')) return (v.version_label || '').replace(/^legacy · /, '').replace(/^post-20250624 · /, '');
    if (v.version_id.includes('post-20250624')) {
      const p = (v.version_label || '').match(/(2010 年以前|2011-2017 年|2018 年以後)/);
      return (p ? p[1] + ' · ' : '') + '2025/06/24 起適用';
    }
    const p = (v.version_label || '').match(/(2010 年以前|2011-2017 年|2018 年以後)/);
    if (p) return p[1];
    if (v.doc_first_published) return `${fmtDate(v.doc_first_published)} 起`;
    return v.version_label || v.version_id;
  }
  const byId = (id) => versions.find((v) => v.version_id === id);

  const pool = mains.length > 1 ? mains : versions;
  let fromId = $state(pool[0]?.version_id ?? '');
  let toId = $state(pool.at(-1)?.version_id ?? '');
  let q = $state('');

  const cache = new Map();
  async function loadFields(id) {
    const v = byId(id);
    if (!v) return [];
    if (cache.has(id)) return cache.get(id);
    const r = await fetch(`${base}/data/fields/${v.fields_file}`);
    const d = r.ok ? await r.json() : { fields: [] };
    const f = d.fields || [];
    cache.set(id, f);
    return f;
  }

  let result = $state(null);
  let loading = $state(false);
  let token = 0;
  async function compute(a, b) {
    const t = ++token;
    if (!a || !b || a === b) { result = null; return; }
    loading = true;
    const [af, bf] = await Promise.all([loadFields(a), loadFields(b)]);
    if (t !== token) return; // a newer request superseded this one
    const am = new Map(af.map((f) => [f.name_en, f]));
    const bm = new Map(bf.map((f) => [f.name_en, f]));
    const added = [], removed = [], changed = [];
    for (const [k, f] of bm) if (k && !am.has(k)) added.push(f);
    for (const [k, f] of am) if (k && !bm.has(k)) removed.push(f);
    for (const [k, f] of am) {
      if (!k || !bm.has(k)) continue;
      const g = bm.get(k), ch = {};
      if ((f.type || '') !== (g.type || '')) ch.type = { from: f.type, to: g.type };
      if ((f.length ?? '') !== (g.length ?? '')) ch.length = { from: f.length, to: g.length };
      if ((f.description_zh || '') !== (g.description_zh || '')) ch.description = { from: f.description_zh, to: g.description_zh };
      if (Object.keys(ch).length) changed.push({ key: k, name_zh: g.name_zh, changes: ch });
    }
    result = { added, removed, changed, afc: af.length, bfc: bf.length };
    loading = false;
  }
  $effect(() => { compute(fromId, toId); });

  function swap() { const t = fromId; fromId = toId; toId = t; }

  const ATTR = { type: 'Type', length: 'Length', description: 'Description' };
  function short(s, n = 160) { s = String(s || ''); return s.length > n ? s.slice(0, n) + '…' : s; }
  const match = (f) => {
    const s = q.trim().toLowerCase();
    if (!s) return true;
    return (f.name_en || '').toLowerCase().includes(s) || (f.name_zh || '').includes(q.trim()) || (f.key || '').toLowerCase().includes(s);
  };
</script>

<svelte:head><title>{file.code} — compare versions — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <nav class="text-sm flex items-center gap-1 flex-wrap">
    <a href="{base}/" class="text-brand-700 hover:underline">Catalogue</a>
    <span class="text-slate-400">/</span>
    <a href="{base}/file/{file.code}/" class="text-brand-700 hover:underline">{file.code}</a>
    <span class="text-slate-400">/</span>
    <span class="text-slate-700">Compare versions</span>
  </nav>

  <header>
    <h1 class="text-3xl font-extrabold text-slate-900">版本沿革 <span class="text-brand-700">· compare versions</span></h1>
    <p class="text-sm text-slate-600 mt-1"><span class="mono font-semibold">{file.code}</span> · {file.name_zh}</p>
  </header>

  {#if versions.length < 2}
    <div class="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-slate-600">
      This file has a single version with fields, so there's nothing to compare.
    </div>
  {:else}
    <!-- Interactive query bar: pick any two versions + filter fields -->
    <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] gap-3 items-end">
        <label class="block">
          <span class="text-xs uppercase tracking-wide text-slate-500 font-semibold">From</span>
          <select bind:value={fromId}
            class="mt-1 w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-400">
            {#each versions as v}<option value={v.version_id}>{vLabel(v)} — {v.field_count} fields</option>{/each}
          </select>
        </label>
        <button onclick={swap} title="Swap"
          class="h-10 px-3 rounded-lg border border-slate-300 text-slate-500 hover:text-brand-700 hover:border-brand-400 transition self-end">⇄</button>
        <label class="block">
          <span class="text-xs uppercase tracking-wide text-slate-500 font-semibold">To</span>
          <select bind:value={toId}
            class="mt-1 w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-400">
            {#each versions as v}<option value={v.version_id}>{vLabel(v)} — {v.field_count} fields</option>{/each}
          </select>
        </label>
      </div>
      <input bind:value={q} placeholder="Filter fields by name (English or 中文)…"
        class="mt-3 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-400" />
    </section>

    {#if fromId === toId}
      <p class="text-slate-500 text-sm">Pick two different versions to compare.</p>
    {:else if loading && !result}
      <p class="text-slate-400 text-sm">Comparing…</p>
    {:else if result}
      {@const A = result.added.filter(match)}
      {@const R = result.removed.filter(match)}
      {@const C = result.changed.filter(match)}
      <p class="text-slate-700 text-sm">
        {#if result.added.length + result.removed.length + result.changed.length === 0}
          These two versions have the same fields.
        {:else}
          <span class="font-bold text-emerald-700">{result.added.length}</span> added ·
          <span class="font-bold text-rose-700">{result.removed.length}</span> removed ·
          <span class="font-bold text-amber-700">{result.changed.length}</span> changed
          {#if q.trim()}<span class="text-slate-400"> · showing matches for “{q.trim()}”</span>{/if}
        {/if}
      </p>

      <section class="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
        <div class="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-4">
          <h3 class="text-sm font-bold text-emerald-800 mb-3 flex items-center gap-2">
            <span class="inline-grid place-items-center w-5 h-5 rounded bg-emerald-600 text-white text-xs">+</span> New in “{vLabel(byId(toId))}”
            <span class="text-xs bg-white text-emerald-700 rounded-full px-2 py-0.5 ring-1 ring-emerald-200">{A.length}</span>
          </h3>
          {#if !A.length}<p class="text-xs text-slate-400">none</p>{/if}
          {#each A as f}
            <div class="text-sm mb-2 rounded-lg bg-white p-2.5 ring-1 ring-emerald-100">
              <a href="{base}/file/{file.code}/field/{f.name_en}/?v={toId}" class="mono font-semibold text-emerald-800 hover:underline">{f.name_en}</a>
              <div class="text-slate-800">{f.name_zh}</div>
            </div>
          {/each}
        </div>
        <div class="rounded-2xl border border-amber-200 bg-amber-50/40 p-4">
          <h3 class="text-sm font-bold text-amber-800 mb-3 flex items-center gap-2">
            <span class="inline-grid place-items-center w-5 h-5 rounded bg-amber-500 text-white text-xs">~</span> Changed
            <span class="text-xs bg-white text-amber-700 rounded-full px-2 py-0.5 ring-1 ring-amber-200">{C.length}</span>
          </h3>
          {#if !C.length}<p class="text-xs text-slate-400">none</p>{/if}
          {#each C as m}
            <div class="text-sm mb-2 rounded-lg bg-white p-2.5 ring-1 ring-amber-100">
              <a href="{base}/file/{file.code}/field/{m.key}/?v={toId}" class="mono font-semibold text-amber-800 hover:underline">{m.key}</a>
              {#each Object.entries(m.changes) as [attr, ch]}
                <div class="mt-1.5">
                  <div class="text-[11px] uppercase tracking-wide text-slate-500 font-semibold">{ATTR[attr] || attr}</div>
                  <div class="text-rose-700 bg-rose-50 rounded px-1.5 py-0.5 mt-0.5">{short(ch.from) || '∅'}</div>
                  <div class="text-emerald-800 bg-emerald-50 rounded px-1.5 py-0.5 mt-0.5">{short(ch.to) || '∅'}</div>
                </div>
              {/each}
            </div>
          {/each}
        </div>
        <div class="rounded-2xl border border-rose-200 bg-rose-50/40 p-4">
          <h3 class="text-sm font-bold text-rose-800 mb-3 flex items-center gap-2">
            <span class="inline-grid place-items-center w-5 h-5 rounded bg-rose-600 text-white text-xs">−</span> Gone from “{vLabel(byId(fromId))}”
            <span class="text-xs bg-white text-rose-700 rounded-full px-2 py-0.5 ring-1 ring-rose-200">{R.length}</span>
          </h3>
          {#if !R.length}<p class="text-xs text-slate-400">none</p>{/if}
          {#each R as f}
            <div class="text-sm mb-2 rounded-lg bg-white p-2.5 ring-1 ring-rose-100">
              <div class="mono font-semibold text-rose-800 line-through">{f.name_en}</div>
              <div class="text-slate-600">{f.name_zh}</div>
            </div>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
</div>
