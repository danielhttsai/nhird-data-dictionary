<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const { code, name_zh: fileNameZh, fieldName, occurrences } = data;
  const latest = $derived(occurrences.at(-1) || null);
</script>

<svelte:head><title>{fieldName} — {code} — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <nav class="text-sm flex items-center gap-1 flex-wrap">
    <a href="{base}/" class="text-brand-700 hover:underline">Catalogue</a>
    <span class="text-slate-400">/</span>
    <a href="{base}/file/{code}/" class="text-brand-700 hover:underline">{code}</a>
    <span class="text-slate-400">/</span>
    <span class="text-slate-700 mono">{fieldName}</span>
  </nav>

  <header>
    <div class="flex items-baseline gap-3 flex-wrap">
      <span class="mono text-2xl font-extrabold text-brand-700">{fieldName}</span>
      {#if latest}<span class="text-slate-700 font-semibold">— {latest.field.name_zh}</span>{/if}
    </div>
    <p class="text-sm text-slate-600 mt-1">
      in <a class="text-brand-700 hover:underline font-semibold" href="{base}/file/{code}/">{code}</a> {fileNameZh}
    </p>
  </header>

  {#if !latest}
    <p class="text-slate-600">Field not found in this file.</p>
  {:else}
    <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm grid grid-cols-2 gap-4 text-sm">
      <div>
        <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold">Type</div>
        <div class="mono text-base font-bold text-slate-900">{latest.field.type}</div>
      </div>
      <div>
        <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold">Length</div>
        <div class="mono text-base font-bold text-slate-900">{latest.field.length ?? ''}</div>
      </div>
      <div class="col-span-2">
        <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Description</div>
        <p class="whitespace-pre-line leading-relaxed text-slate-700">{latest.field.description_zh}</p>
      </div>
      {#if latest.field.available_notes?.length}
        <div class="col-span-2">
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Period</div>
          {#each latest.field.available_notes as n}
            <div class="text-xs text-slate-600">since AD {n.ad_year} (ROC {n.roc_year}) {n.marker || ''}</div>
          {/each}
        </div>
      {/if}
    </section>

    {#if latest.codebook && latest.codebook.entries?.length}
      <section>
        <h2 class="text-sm font-bold text-slate-900 mb-2 flex items-center gap-2">
          Codebook — {latest.codebook.field_zh}
          <span class="text-[11px] font-semibold text-brand-700 bg-brand-50 rounded-full px-2 py-0.5">
            {latest.codebook.entries.length} entries
          </span>
        </h2>
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div class="overflow-x-auto max-h-96 overflow-y-auto">
            <table class="tbl w-full text-left">
              <thead><tr><th class="w-24">Code</th><th>名稱</th></tr></thead>
              <tbody>
                {#each latest.codebook.entries as e}
                  <tr><td class="mono font-semibold text-brand-700">{e.code}</td><td class="text-slate-800">{e.label_zh}</td></tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    {/if}

    {#if occurrences.length > 1}
      <section>
        <h2 class="text-sm font-bold text-slate-900 mb-2">Across versions</h2>
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table class="tbl w-full text-left">
            <thead><tr><th>Version</th><th>Type</th><th>Length</th><th>Description (truncated)</th></tr></thead>
            <tbody>
              {#each occurrences as o}
                <tr>
                  <td class="mono text-xs font-semibold text-brand-700">{o.version_id}</td>
                  <td>{o.field.type}</td>
                  <td class="tabular-nums">{o.field.length ?? ''}</td>
                  <td class="text-xs text-slate-700">{(o.field.description_zh || '').slice(0, 200)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    {/if}
  {/if}
</div>
