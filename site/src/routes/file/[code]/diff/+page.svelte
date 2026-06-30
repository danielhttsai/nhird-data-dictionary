<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const file = data.file;

  let selectedDiff = $state(file.diffs?.[0]?.file || '');
  const current = $derived(file.diffs?.find(d => d.file === selectedDiff)?.data || null);
</script>

<svelte:head><title>{file.code} diff — NHIRD data dictionary</title></svelte:head>

<div class="space-y-4">
  <nav class="text-sm">
    <a href="{base}/" class="text-blue-700 hover:underline">All files</a>
    <span class="mx-1 text-slate-400">/</span>
    <a href="{base}/file/{file.code}/" class="text-blue-700 hover:underline">{file.code}</a>
    <span class="mx-1 text-slate-400">/</span>
    <span class="text-slate-700">Diff</span>
  </nav>

  <header>
    <h1 class="text-xl font-bold mono">{file.code} version diff</h1>
    <p class="text-sm text-slate-600">{file.name_zh}</p>
  </header>

  {#if !file.diffs?.length}
    <p class="text-slate-600">No version diffs for this file.</p>
  {:else}
    <section>
      <label class="text-sm">Comparison:&nbsp;
        <select bind:value={selectedDiff} class="border border-slate-300 rounded text-sm px-2 py-1">
          {#each file.diffs as d}
            <option value={d.file}>{d.data.earlier_version_id} → {d.data.later_version_id}
              (+{d.data.added.length} −{d.data.removed.length} ~{d.data.modified.length})</option>
          {/each}
        </select>
      </label>
    </section>

    {#if current}
      <section class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- Added -->
        <div class="bg-white border border-slate-200 rounded p-3">
          <h2 class="text-sm font-semibold text-green-700 mb-1">+ Added ({current.added.length})</h2>
          {#if !current.added.length}<p class="text-xs text-slate-400">none</p>{/if}
          {#each current.added as f}
            <div class="text-xs mb-2">
              <div class="mono text-green-800">{f.name_en}</div>
              <div class="text-slate-700">{f.name_zh}</div>
              <div class="text-slate-500">{f.type} · {f.length}</div>
              <div class="text-slate-600">{(f.description_zh || '').slice(0, 100)}</div>
            </div>
          {/each}
        </div>
        <!-- Removed -->
        <div class="bg-white border border-slate-200 rounded p-3">
          <h2 class="text-sm font-semibold text-red-700 mb-1">− Removed ({current.removed.length})</h2>
          {#if !current.removed.length}<p class="text-xs text-slate-400">none</p>{/if}
          {#each current.removed as f}
            <div class="text-xs mb-2">
              <div class="mono text-red-800 line-through">{f.name_en}</div>
              <div class="text-slate-700">{f.name_zh}</div>
              <div class="text-slate-500">{f.type} · {f.length}</div>
            </div>
          {/each}
        </div>
        <!-- Modified -->
        <div class="bg-white border border-slate-200 rounded p-3">
          <h2 class="text-sm font-semibold text-amber-700 mb-1">~ Modified ({current.modified.length})</h2>
          {#if !current.modified.length}<p class="text-xs text-slate-400">none</p>{/if}
          {#each current.modified as m}
            <div class="text-xs mb-2 border-b border-slate-100 pb-2">
              <div class="mono text-amber-800">{m.key}</div>
              {#each Object.entries(m.changes) as [attr, ch]}
                <div class="ml-2">
                  <span class="text-slate-500">{attr}:</span>
                  <span class="text-red-700 line-through">{ch.from}</span>
                  &nbsp;→&nbsp;
                  <span class="text-green-700">{ch.to}</span>
                </div>
              {/each}
            </div>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
</div>
