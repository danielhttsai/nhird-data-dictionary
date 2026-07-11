<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const file = data.file;
  const diffs = file.diffs || [];

  // Resolve an internal version_id to the same human, date-based label the
  // file page uses — so the diff never shows "legacy" / "post-20250624" jargon.
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

  let idx = $state(0);
  const current = $derived(diffs[idx]?.data || null);
  const total = $derived(current ? current.added.length + current.removed.length + current.modified.length : 0);

  const ATTR = { type: 'Type', length: 'Length', name_zh: 'Chinese name', description_zh: 'Description' };
  function short(s, n = 160) {
    s = String(s || '');
    return s.length > n ? s.slice(0, n) + '…' : s;
  }
</script>

<svelte:head><title>{file.code} — what changed between versions — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <nav class="text-sm flex items-center gap-1 flex-wrap">
    <a href="{base}/" class="text-brand-700 hover:underline">Catalogue</a>
    <span class="text-slate-400">/</span>
    <a href="{base}/file/{file.code}/" class="text-brand-700 hover:underline">{file.code}</a>
    <span class="text-slate-400">/</span>
    <span class="text-slate-700">Changes</span>
  </nav>

  <header>
    <h1 class="text-3xl font-extrabold text-slate-900">
      What changed <span class="text-brand-700">between versions</span>
    </h1>
    <p class="text-sm text-slate-600 mt-1"><span class="mono font-semibold">{file.code}</span> · {file.name_zh}</p>
  </header>

  {#if !diffs.length}
    <div class="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-slate-600">
      This file has a single version, so there's nothing to compare.
      <a href="{base}/file/{file.code}/" class="text-brand-700 hover:underline font-semibold">Back to {file.code} →</a>
    </div>
  {:else}
    <!-- Comparison picker: readable pills, not a cryptic dropdown -->
    {#if diffs.length > 1}
      <div class="flex flex-wrap gap-2">
        {#each diffs as d, i}
          <button onclick={() => (idx = i)}
            class="text-sm rounded-xl border px-3 py-2 transition text-left
                   {idx === i ? 'border-brand-500 bg-brand-50 text-brand-800 ring-1 ring-brand-300'
                              : 'border-slate-200 bg-white text-slate-600 hover:border-brand-300'}">
            <span class="font-semibold">{vLabel(d.data.earlier_version_id)}</span>
            <span class="text-slate-400 mx-1">→</span>
            <span class="font-semibold">{vLabel(d.data.later_version_id)}</span>
          </button>
        {/each}
      </div>
    {/if}

    {#if current}
      <!-- Prominent summary banner -->
      <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex items-center gap-3 flex-wrap text-sm">
          <span class="rounded-lg bg-slate-100 px-3 py-1.5 font-semibold text-slate-700">{vLabel(current.earlier_version_id)}</span>
          <span class="text-brand-600 text-lg">→</span>
          <span class="rounded-lg bg-brand-50 px-3 py-1.5 font-semibold text-brand-800">{vLabel(current.later_version_id)}</span>
        </div>
        <p class="mt-3 text-slate-700">
          {#if total === 0}
            No field-level changes between these two versions.
          {:else}
            <span class="font-bold text-emerald-700">{current.added.length}</span> field{current.added.length === 1 ? '' : 's'} added ·
            <span class="font-bold text-rose-700">{current.removed.length}</span> removed ·
            <span class="font-bold text-amber-700">{current.modified.length}</span> changed
          {/if}
        </p>
      </section>

      {#if total > 0}
        <section class="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
          <!-- Added -->
          <div class="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-4">
            <h2 class="text-sm font-bold text-emerald-800 mb-3 flex items-center gap-2">
              <span class="inline-grid place-items-center w-5 h-5 rounded bg-emerald-600 text-white text-xs">+</span>
              New fields
              <span class="text-xs font-semibold bg-white text-emerald-700 rounded-full px-2 py-0.5 ring-1 ring-emerald-200">{current.added.length}</span>
            </h2>
            {#if !current.added.length}<p class="text-xs text-slate-400">none</p>{/if}
            {#each current.added as f}
              <div class="text-sm mb-2 rounded-lg bg-white p-2.5 ring-1 ring-emerald-100">
                <div class="mono font-semibold text-emerald-800">{f.name_en}</div>
                <div class="text-slate-800">{f.name_zh}</div>
                <div class="text-slate-400 mono text-xs mt-0.5">{f.type}{f.length ? ` · ${f.length}` : ''}</div>
              </div>
            {/each}
          </div>
          <!-- Removed -->
          <div class="rounded-2xl border border-rose-200 bg-rose-50/40 p-4">
            <h2 class="text-sm font-bold text-rose-800 mb-3 flex items-center gap-2">
              <span class="inline-grid place-items-center w-5 h-5 rounded bg-rose-600 text-white text-xs">−</span>
              Removed fields
              <span class="text-xs font-semibold bg-white text-rose-700 rounded-full px-2 py-0.5 ring-1 ring-rose-200">{current.removed.length}</span>
            </h2>
            {#if !current.removed.length}<p class="text-xs text-slate-400">none</p>{/if}
            {#each current.removed as f}
              <div class="text-sm mb-2 rounded-lg bg-white p-2.5 ring-1 ring-rose-100">
                <div class="mono font-semibold text-rose-800 line-through">{f.name_en}</div>
                <div class="text-slate-600">{f.name_zh}</div>
              </div>
            {/each}
          </div>
          <!-- Modified -->
          <div class="rounded-2xl border border-amber-200 bg-amber-50/40 p-4">
            <h2 class="text-sm font-bold text-amber-800 mb-3 flex items-center gap-2">
              <span class="inline-grid place-items-center w-5 h-5 rounded bg-amber-500 text-white text-xs">~</span>
              Changed fields
              <span class="text-xs font-semibold bg-white text-amber-700 rounded-full px-2 py-0.5 ring-1 ring-amber-200">{current.modified.length}</span>
            </h2>
            {#if !current.modified.length}<p class="text-xs text-slate-400">none</p>{/if}
            {#each current.modified as m}
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
        </section>
      {/if}
    {/if}
  {/if}
</div>
