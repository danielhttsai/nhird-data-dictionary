<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const file = data.file;

  let selectedDiff = $state(file.diffs?.[0]?.file || '');
  const current = $derived(file.diffs?.find(d => d.file === selectedDiff)?.data || null);
</script>

<svelte:head><title>{file.code} diff — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <nav class="text-sm flex items-center gap-1 flex-wrap">
    <a href="{base}/" class="text-brand-700 hover:underline">Catalogue</a>
    <span class="text-slate-400">/</span>
    <a href="{base}/file/{file.code}/" class="text-brand-700 hover:underline">{file.code}</a>
    <span class="text-slate-400">/</span>
    <span class="text-slate-700">Diff</span>
  </nav>

  <header>
    <h1 class="text-3xl font-extrabold text-slate-900">
      <span class="mono text-brand-700">{file.code}</span> · version diff
    </h1>
    <p class="text-sm text-slate-600 mt-1">{file.name_zh}</p>
  </header>

  {#if !file.diffs?.length}
    <p class="text-slate-600">No version diffs for this file.</p>
  {:else}
    <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <label class="text-sm flex items-center gap-3 flex-wrap">
        <span class="text-xs uppercase tracking-wide text-slate-500 font-semibold">Comparison</span>
        <select bind:value={selectedDiff}
          class="border border-slate-300 rounded-lg text-sm px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-400">
          {#each file.diffs as d}
            <option value={d.file}>
              {d.data.earlier_version_id} → {d.data.later_version_id}
              (+{d.data.added.length} −{d.data.removed.length} ~{d.data.modified.length})
            </option>
          {/each}
        </select>
      </label>
    </section>

    {#if current}
      <section class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- Added -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 class="text-sm font-bold text-emerald-700 mb-3 flex items-center gap-2">
            <span class="text-base">+</span> Added
            <span class="text-xs font-semibold bg-emerald-50 text-emerald-700 rounded-full px-2 py-0.5">{current.added.length}</span>
          </h2>
          {#if !current.added.length}<p class="text-xs text-slate-400">none</p>{/if}
          {#each current.added as f}
            <div class="text-xs mb-3 pb-2 border-b border-slate-100 last:border-0">
              <div class="mono font-semibold text-emerald-700">{f.name_en}</div>
              <div class="text-slate-800">{f.name_zh}</div>
              <div class="text-slate-500 mono">{f.type} · {f.length}</div>
              <div class="text-slate-600 mt-1 line-clamp-3">{(f.description_zh || '').slice(0, 120)}</div>
            </div>
          {/each}
        </div>
        <!-- Removed -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 class="text-sm font-bold text-rose-700 mb-3 flex items-center gap-2">
            <span class="text-base">−</span> Removed
            <span class="text-xs font-semibold bg-rose-50 text-rose-700 rounded-full px-2 py-0.5">{current.removed.length}</span>
          </h2>
          {#if !current.removed.length}<p class="text-xs text-slate-400">none</p>{/if}
          {#each current.removed as f}
            <div class="text-xs mb-3 pb-2 border-b border-slate-100 last:border-0">
              <div class="mono font-semibold text-rose-700 line-through">{f.name_en}</div>
              <div class="text-slate-700">{f.name_zh}</div>
              <div class="text-slate-500 mono">{f.type} · {f.length}</div>
            </div>
          {/each}
        </div>
        <!-- Modified -->
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 class="text-sm font-bold text-amber-700 mb-3 flex items-center gap-2">
            <span class="text-base">~</span> Modified
            <span class="text-xs font-semibold bg-amber-50 text-amber-700 rounded-full px-2 py-0.5">{current.modified.length}</span>
          </h2>
          {#if !current.modified.length}<p class="text-xs text-slate-400">none</p>{/if}
          {#each current.modified as m}
            <div class="text-xs mb-3 pb-2 border-b border-slate-100 last:border-0">
              <div class="mono font-semibold text-amber-700">{m.key}</div>
              {#each Object.entries(m.changes) as [attr, ch]}
                <div class="ml-2 mt-1">
                  <span class="text-slate-500">{attr}:</span>
                  <span class="text-rose-600 line-through">{ch.from}</span>
                  <span class="text-slate-400 mx-1">→</span>
                  <span class="text-emerald-700">{ch.to}</span>
                </div>
              {/each}
            </div>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
</div>
