<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const { code, category, name_zh: fileNameZh, fieldName, occurrences } = data;
  const latest = $derived(occurrences.at(-1) || null);
</script>

<svelte:head><title>{fieldName} — {code} — NHIRD data dictionary</title></svelte:head>

<div class="space-y-4">
  <nav class="text-sm">
    <a href="{base}/" class="text-blue-700 hover:underline">All files</a>
    <span class="mx-1 text-slate-400">/</span>
    <a href="{base}/file/{code}/" class="text-blue-700 hover:underline">{code}</a>
    <span class="mx-1 text-slate-400">/</span>
    <span class="text-slate-700 mono">{fieldName}</span>
  </nav>

  <header>
    <h1 class="text-xl font-bold flex items-center gap-2">
      <span class="mono">{fieldName}</span>
      {#if latest}<span class="text-slate-700 font-normal">— {latest.field.name_zh}</span>{/if}
    </h1>
    <p class="text-sm text-slate-600">in <a class="text-blue-700 hover:underline" href="{base}/file/{code}/">{code}</a> {fileNameZh}</p>
  </header>

  {#if !latest}
    <p class="text-slate-600">Field not found in this file.</p>
  {:else}
    <section class="bg-white border border-slate-200 rounded p-4 grid grid-cols-2 gap-3 text-sm">
      <div><span class="text-slate-500">Type:</span> {latest.field.type}</div>
      <div><span class="text-slate-500">Length:</span> {latest.field.length ?? ''}</div>
      <div class="col-span-2">
        <div class="text-slate-500 text-xs uppercase tracking-wide">Description</div>
        <p class="whitespace-pre-line">{latest.field.description_zh}</p>
      </div>
      {#if latest.field.available_notes?.length}
        <div class="col-span-2">
          <div class="text-slate-500 text-xs uppercase tracking-wide">Period notes</div>
          {#each latest.field.available_notes as n}
            <div class="text-xs">since AD {n.ad_year} (ROC {n.roc_year}) — {n.marker || ''}</div>
          {/each}
        </div>
      {/if}
    </section>

    {#if latest.codebook && latest.codebook.entries?.length}
      <section>
        <h2 class="text-sm font-semibold mb-1">Codebook · {latest.codebook.field_zh} ({latest.codebook.entries.length})</h2>
        <div class="overflow-x-auto rounded border border-slate-200 max-h-96 overflow-y-auto">
          <table class="tbl w-full bg-white text-left">
            <thead><tr><th class="w-20">Code</th><th>名稱</th></tr></thead>
            <tbody>
              {#each latest.codebook.entries as e}
                <tr><td class="mono">{e.code}</td><td>{e.label_zh}</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    {/if}

    {#if occurrences.length > 1}
      <section>
        <h2 class="text-sm font-semibold mb-1">Across versions</h2>
        <table class="tbl w-full bg-white text-left rounded border border-slate-200">
          <thead><tr><th>Version</th><th>Type</th><th>Length</th><th>Description (truncated)</th></tr></thead>
          <tbody>
            {#each occurrences as o}
              <tr>
                <td class="mono text-xs">{o.version_id}</td>
                <td>{o.field.type}</td>
                <td>{o.field.length ?? ''}</td>
                <td class="text-xs text-slate-700">{(o.field.description_zh || '').slice(0, 200)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {/if}
  {/if}
</div>
