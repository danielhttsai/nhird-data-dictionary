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
    const a = t.added.length, r = t.removed.length, m = t.modified.length;
    return { i, data: t, a, r, m, total: a + r + m };
  });
  const maxTotal = Math.max(1, ...rows.map((x) => x.total));

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
    <!-- GRAPHIC OVERVIEW: one proportional bar per comparison; bar length ∝ total change -->
    <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-bold text-slate-900">Each comparison, by amount changed</h2>
        <div class="hidden sm:flex items-center gap-3 text-[11px] font-semibold">
          <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-emerald-500"></span>added</span>
          <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-rose-500"></span>removed</span>
          <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-amber-400"></span>changed</span>
        </div>
      </div>
      <div class="space-y-1.5">
        {#each rows as x}
          <button onclick={() => (idx = x.i)}
            class="w-full text-left rounded-xl px-3 py-2 transition border
                   {idx === x.i ? 'border-brand-400 bg-brand-50/50 ring-1 ring-brand-200' : 'border-transparent hover:bg-slate-50'}">
            <div class="flex items-center justify-between gap-3 text-xs mb-1">
              <span class="font-semibold text-slate-800 truncate">
                {vLabel(x.data.earlier_version_id)} <span class="text-slate-400">→</span> {vLabel(x.data.later_version_id)}
              </span>
              <span class="shrink-0 tabular-nums text-slate-500">
                {#if x.total === 0}no change{:else}<span class="text-emerald-700 font-semibold">+{x.a}</span> <span class="text-rose-700 font-semibold">−{x.r}</span> <span class="text-amber-700 font-semibold">~{x.m}</span>{/if}
              </span>
            </div>
            <div class="h-2.5 rounded-full bg-slate-100 overflow-hidden">
              <div class="h-full flex" style="width:{(x.total / maxTotal) * 100}%">
                {#if x.a}<div class="bg-emerald-500 h-full" style="width:{(x.a / x.total) * 100}%"></div>{/if}
                {#if x.r}<div class="bg-rose-500 h-full" style="width:{(x.r / x.total) * 100}%"></div>{/if}
                {#if x.m}<div class="bg-amber-400 h-full" style="width:{(x.m / x.total) * 100}%"></div>{/if}
              </div>
            </div>
          </button>
        {/each}
      </div>
    </section>

    {#if cur}
      {@const ef = fc(cur.data.earlier_version_id)}
      {@const lf = fc(cur.data.later_version_id)}
      <!-- SELECTED COMPARISON: field-count change + big proportional bar -->
      <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex items-center gap-3 flex-wrap text-sm mb-4">
          <span class="rounded-lg bg-slate-100 px-3 py-1.5 font-semibold text-slate-700">{vLabel(cur.data.earlier_version_id)}</span>
          <span class="text-brand-600 text-lg">→</span>
          <span class="rounded-lg bg-brand-50 px-3 py-1.5 font-semibold text-brand-800">{vLabel(cur.data.later_version_id)}</span>
        </div>

        {#if ef != null && lf != null}
          <div class="flex items-end gap-4 mb-4">
            <div class="text-center">
              <div class="text-3xl font-extrabold text-slate-400 leading-none tabular-nums">{ef}</div>
              <div class="text-[10px] uppercase tracking-wide text-slate-400 mt-1">fields before</div>
            </div>
            <div class="text-brand-500 text-2xl pb-3">→</div>
            <div class="text-center">
              <div class="text-3xl font-extrabold text-brand-700 leading-none tabular-nums">{lf}</div>
              <div class="text-[10px] uppercase tracking-wide text-slate-500 mt-1">fields after</div>
            </div>
            <div class="pb-2 text-sm font-semibold {lf - ef > 0 ? 'text-emerald-700' : lf - ef < 0 ? 'text-rose-700' : 'text-slate-400'}">
              {lf - ef > 0 ? '+' : ''}{lf - ef} net
            </div>
          </div>
        {/if}

        {#if cur.total === 0}
          <p class="text-slate-500 text-sm">No field-level changes between these two versions.</p>
        {:else}
          <div class="h-5 rounded-lg overflow-hidden flex text-[10px] font-bold text-white">
            {#if cur.a}<div class="bg-emerald-500 grid place-items-center" style="width:{(cur.a / cur.total) * 100}%" title="added">{cur.a >= 3 ? cur.a : ''}</div>{/if}
            {#if cur.m}<div class="bg-amber-400 grid place-items-center" style="width:{(cur.m / cur.total) * 100}%" title="changed">{cur.m >= 3 ? cur.m : ''}</div>{/if}
            {#if cur.r}<div class="bg-rose-500 grid place-items-center" style="width:{(cur.r / cur.total) * 100}%" title="removed">{cur.r >= 3 ? cur.r : ''}</div>{/if}
          </div>
          <div class="mt-2 flex gap-4 text-xs font-semibold">
            <span class="text-emerald-700">+{cur.a} added</span>
            <span class="text-amber-700">~{cur.m} changed</span>
            <span class="text-rose-700">−{cur.r} removed</span>
          </div>
        {/if}
      </section>

      {#if cur.total > 0}
        <!-- Field detail, secondary to the chart -->
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
