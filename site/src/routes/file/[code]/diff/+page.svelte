<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const file = data.file;
  const diffs = file.diffs || [];

  function fmtDate(s) {
    const m = String(s || '').match(/(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[1]}/${m[2]}/${m[3]}` : s;
  }
  function vLabel(id) {
    const v = (file.versions || []).find((x) => x.version_id === id);
    if (!v) return id;
    if (v.file_type === 'xls') return (v.version_label || '').replace(/^Excel codebook · /, '');
    if (id.includes('__wave_')) return (v.version_label || '').replace(/^legacy · /, '').replace(/^post-20250624 · /, '');
    if (id.includes('post-20250624')) {
      const p = (v.version_label || '').match(/(2010 年以前|2011-2017 年|2018 年以後)/);
      return (p ? p[1] + ' · ' : '') + '2025/06/24 起適用';
    }
    const p = (v.version_label || '').match(/(2010 年以前|2011-2017 年|2018 年以後)/);
    if (p) return p[1];
    if (v.doc_first_published) return `${fmtDate(v.doc_first_published)} 起`;
    return v.version_label || id;
  }
  function fc(id) {
    const v = (file.versions || []).find((x) => x.version_id === id);
    return v?.field_count ?? null;
  }

  const rows = diffs.map((d, i) => {
    const t = d.data;
    return { i, data: t, a: t.added.length, r: t.removed.length, m: t.modified.length };
  });

  let idx = $state(0);
  const cur = $derived(rows[idx] || null);

  const ATTR = { type: 'Type', length: 'Length', name_zh: 'Chinese name', description_zh: 'Description' };
  function short(s, n = 160) { s = String(s || ''); return s.length > n ? s.slice(0, n) + '…' : s; }
</script>

<svelte:head><title>{file.code} — version changes — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <nav class="text-sm flex items-center gap-1 flex-wrap">
    <a href="{base}/" class="text-brand-700 hover:underline">Catalogue</a>
    <span class="text-slate-400">/</span>
    <a href="{base}/file/{file.code}/" class="text-brand-700 hover:underline">{file.code}</a>
    <span class="text-slate-400">/</span>
    <span class="text-slate-700">Version changes</span>
  </nav>

  <header>
    <h1 class="text-3xl font-extrabold text-slate-900">版本沿革 <span class="text-brand-700">· version changes</span></h1>
    <p class="text-sm text-slate-600 mt-1"><span class="mono font-semibold">{file.code}</span> · {file.name_zh}</p>
  </header>

  {#if !diffs.length}
    <div class="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-slate-600">
      This file has a single version, so there's nothing to compare.
    </div>
  {:else}
    <!-- Clean comparison list: pick one to see the detail -->
    <section class="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-100 text-xs uppercase tracking-wide text-slate-500 font-semibold">
        Pick two versions to compare
      </div>
      <ul class="divide-y divide-slate-100">
        {#each rows as x}
          <li>
            <button onclick={() => (idx = x.i)}
              class="w-full text-left flex items-center justify-between gap-4 px-4 py-3 transition
                     {idx === x.i ? 'bg-brand-50/60' : 'hover:bg-slate-50'}">
              <span class="text-sm min-w-0 flex items-center gap-2">
                {#if idx === x.i}<span class="w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0"></span>{/if}
                <span class="truncate {idx === x.i ? 'font-semibold text-brand-900' : 'text-slate-700'}">
                  {vLabel(x.data.earlier_version_id)} <span class="text-slate-400 mx-0.5">→</span> {vLabel(x.data.later_version_id)}
                </span>
              </span>
              <span class="shrink-0 flex items-center gap-2 text-xs tabular-nums font-semibold">
                {#if x.a + x.r + x.m === 0}
                  <span class="text-slate-400">no change</span>
                {:else}
                  <span class="text-emerald-700">+{x.a}</span>
                  <span class="text-rose-700">−{x.r}</span>
                  <span class="text-amber-700">~{x.m}</span>
                {/if}
              </span>
            </button>
          </li>
        {/each}
      </ul>
    </section>

    {#if cur}
      {@const ef = fc(cur.data.earlier_version_id)}
      {@const lf = fc(cur.data.later_version_id)}
      <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex items-center gap-3 flex-wrap text-sm">
          <span class="rounded-lg bg-slate-100 px-3 py-1.5 font-semibold text-slate-700">{vLabel(cur.data.earlier_version_id)}</span>
          <span class="text-brand-600 text-lg">→</span>
          <span class="rounded-lg bg-brand-50 px-3 py-1.5 font-semibold text-brand-800">{vLabel(cur.data.later_version_id)}</span>
          {#if ef != null && lf != null}
            <span class="ml-auto text-sm text-slate-500">
              <span class="tabular-nums font-semibold text-slate-600">{ef}</span>
              <span class="mx-1 text-brand-500">→</span>
              <span class="tabular-nums font-semibold text-brand-700">{lf}</span> fields
              <span class="ml-1 font-semibold {lf - ef > 0 ? 'text-emerald-700' : lf - ef < 0 ? 'text-rose-700' : 'text-slate-400'}">({lf - ef > 0 ? '+' : ''}{lf - ef})</span>
            </span>
          {/if}
        </div>
        <p class="mt-3 text-slate-700 text-sm">
          {#if cur.a + cur.r + cur.m === 0}
            No field-level changes between these two versions.
          {:else}
            <span class="font-bold text-emerald-700">{cur.a}</span> added ·
            <span class="font-bold text-rose-700">{cur.r}</span> removed ·
            <span class="font-bold text-amber-700">{cur.m}</span> changed
          {/if}
        </p>
      </section>

      {#if cur.a + cur.r + cur.m > 0}
        <section class="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
          <div class="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-4">
            <h3 class="text-sm font-bold text-emerald-800 mb-3 flex items-center gap-2">
              <span class="inline-grid place-items-center w-5 h-5 rounded bg-emerald-600 text-white text-xs">+</span> New fields
              <span class="text-xs bg-white text-emerald-700 rounded-full px-2 py-0.5 ring-1 ring-emerald-200">{cur.a}</span>
            </h3>
            {#if !cur.a}<p class="text-xs text-slate-400">none</p>{/if}
            {#each cur.data.added as f}
              <div class="text-sm mb-2 rounded-lg bg-white p-2.5 ring-1 ring-emerald-100">
                <div class="mono font-semibold text-emerald-800">{f.name_en}</div>
                <div class="text-slate-800">{f.name_zh}</div>
              </div>
            {/each}
          </div>
          <div class="rounded-2xl border border-amber-200 bg-amber-50/40 p-4">
            <h3 class="text-sm font-bold text-amber-800 mb-3 flex items-center gap-2">
              <span class="inline-grid place-items-center w-5 h-5 rounded bg-amber-500 text-white text-xs">~</span> Changed fields
              <span class="text-xs bg-white text-amber-700 rounded-full px-2 py-0.5 ring-1 ring-amber-200">{cur.m}</span>
            </h3>
            {#if !cur.m}<p class="text-xs text-slate-400">none</p>{/if}
            {#each cur.data.modified as m}
              <div class="text-sm mb-2 rounded-lg bg-white p-2.5 ring-1 ring-amber-100">
                <div class="mono font-semibold text-amber-800">{m.key}</div>
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
              <span class="inline-grid place-items-center w-5 h-5 rounded bg-rose-600 text-white text-xs">−</span> Removed fields
              <span class="text-xs bg-white text-rose-700 rounded-full px-2 py-0.5 ring-1 ring-rose-200">{cur.r}</span>
            </h3>
            {#if !cur.r}<p class="text-xs text-slate-400">none</p>{/if}
            {#each cur.data.removed as f}
              <div class="text-sm mb-2 rounded-lg bg-white p-2.5 ring-1 ring-rose-100">
                <div class="mono font-semibold text-rose-800 line-through">{f.name_en}</div>
                <div class="text-slate-600">{f.name_zh}</div>
              </div>
            {/each}
          </div>
        </section>
      {/if}
    {/if}
  {/if}
</div>
