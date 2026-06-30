<script>
  import { base } from '$app/paths';
  import { page } from '$app/state';

  let { data } = $props();
  const file = data.file;

  const versions = file.versions.filter(v => v.extracted);
  let selectedId = $state(versions.at(-1)?.version_id || file.versions.at(-1)?.version_id || '');
  $effect(() => {
    const v = page.url.searchParams.get('v');
    if (v && file.versions.some(x => x.version_id === v)) {
      selectedId = v;
    }
  });

  const selected = $derived(file.versions.find(v => v.version_id === selectedId));
  const ext = $derived(selected?.extracted || null);

  let q = $state('');
  let typeFilter = $state('');

  const fields = $derived(ext?.fields || []);
  const filtered = $derived.by(() => {
    const term = q.trim().toLowerCase();
    return fields.filter(f => {
      if (typeFilter && f.type !== typeFilter) return false;
      if (!term) return true;
      return (f.name_zh || '').toLowerCase().includes(term)
        || (f.name_en || '').toLowerCase().includes(term)
        || (f.description_zh || '').toLowerCase().includes(term);
    });
  });

  const types = $derived([...new Set(fields.map(f => f.type).filter(Boolean))].sort());

  function copyText(t) { navigator.clipboard?.writeText(t); }
</script>

<svelte:head><title>{file.code} — {file.name_zh} — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <nav class="text-sm">
    <a href="{base}/" class="text-brand-700 hover:underline">← Catalogue</a>
  </nav>

  <header class="space-y-2">
    <div class="flex items-center gap-3 flex-wrap">
      <span class="mono text-2xl font-extrabold text-brand-700">{file.code}</span>
      <span class="pill pill-{file.category}">{file.category}</span>
      {#if ext?.code_short}<span class="mono text-xs text-slate-500">{ext.code_short}</span>{/if}
    </div>
    <h1 class="text-3xl font-extrabold text-slate-900 leading-tight">{file.name_zh}</h1>
    {#if file.name_en}<p class="text-slate-500 text-sm">{file.name_en}</p>{/if}
  </header>

  <!-- Version selector -->
  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="flex flex-wrap gap-2 items-center">
      <span class="text-xs uppercase tracking-wide text-slate-500 font-semibold mr-2">Version</span>
      {#each file.versions as v}
        <button
          class="text-xs px-3 py-1.5 rounded-lg border font-semibold transition
            {v.version_id === selectedId
              ? 'bg-brand-600 text-white border-brand-600'
              : v.extracted ? 'bg-white text-slate-700 border-slate-300 hover:bg-brand-50 hover:border-brand-400 hover:text-brand-700'
                            : 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed'}"
          disabled={!v.extracted}
          onclick={() => selectedId = v.version_id}
        >{v.version_id}{!v.extracted ? ' (zip)' : ''}</button>
      {/each}
      {#if file.diffs?.length}
        <a class="ml-auto text-sm font-semibold text-brand-700 hover:underline"
           href="{base}/file/{file.code}/diff/">Compare versions →</a>
      {/if}
    </div>
  </section>

  {#if !ext}
    <div class="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
      No extracted JSON for this version — likely a ZIP bundle of multiple per-wave codebooks.
      {#if selected?.pdf_url}
        <a href={selected.pdf_url} class="ml-1 text-brand-700 hover:underline font-semibold">Download from MOHW →</a>
      {/if}
    </div>
  {:else}

    <!-- Metadata cards -->
    <section class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <div class="rounded-xl border border-slate-200 bg-white p-3">
        <div class="text-xs uppercase tracking-wide text-slate-500">Fields</div>
        <div class="text-xl font-extrabold text-brand-700">{ext.field_count_declared ?? fields.length}</div>
        {#if ext.field_count_declared && ext.field_count_declared !== fields.length}
          <div class="text-[10px] text-amber-700">parsed {fields.length}</div>
        {/if}
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3">
        <div class="text-xs uppercase tracking-wide text-slate-500">Frequency</div>
        <div class="text-base font-bold text-slate-900">{ext.frequency || '—'}</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3">
        <div class="text-xs uppercase tracking-wide text-slate-500">Attribute</div>
        <div class="text-base font-bold text-slate-900">{ext.attribute || '—'}</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 col-span-2">
        <div class="text-xs uppercase tracking-wide text-slate-500">Records</div>
        <div class="text-sm text-slate-800">{ext.record_count_raw || '—'}</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3">
        <div class="text-xs uppercase tracking-wide text-slate-500">Last updated</div>
        <div class="text-sm font-bold text-slate-900">{selected.doc_last_updated || '—'}</div>
      </div>
    </section>

    <!-- Descriptive blocks (bilingual where translation available) -->
    <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
      {#if ext.data_description_zh}
        <div>
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Data description</div>
          <p class="text-sm whitespace-pre-line leading-relaxed text-slate-700">{ext.data_description_zh}</p>
          {#if ext.data_description_en}
            <p class="text-xs italic whitespace-pre-line leading-relaxed text-slate-500 mt-1">{ext.data_description_en}</p>
          {/if}
        </div>
      {/if}
      {#if ext.notes_zh}
        <div>
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Notes</div>
          <p class="text-sm whitespace-pre-line leading-relaxed text-slate-700">{ext.notes_zh}</p>
          {#if ext.notes_en}
            <p class="text-xs italic whitespace-pre-line leading-relaxed text-slate-500 mt-1">{ext.notes_en}</p>
          {/if}
        </div>
      {/if}
      {#if ext.primary_keys_raw}
        <div>
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Primary keys / linkage</div>
          <p class="text-sm whitespace-pre-line leading-relaxed text-slate-700">{ext.primary_keys_raw}</p>
          {#if ext.primary_keys_en}
            <p class="text-xs italic whitespace-pre-line leading-relaxed text-slate-500 mt-1">{ext.primary_keys_en}</p>
          {/if}
        </div>
      {/if}
      {#if ext.update_history?.length}
        <div>
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Codebook history</div>
          <ul class="flex flex-wrap gap-x-3 gap-y-1 text-xs mono text-slate-600">
            {#each ext.update_history as h}<li>{h.date} {h.note}</li>{/each}
          </ul>
        </div>
      {/if}
      {#if selected.pdf_url}
        <p class="text-xs pt-1 border-t border-slate-100">
          <a href={selected.pdf_url} target="_blank" rel="noreferrer" class="text-brand-700 hover:underline font-semibold">
            ↗ Original MOHW PDF ({selected.version_label})
          </a>
        </p>
      {/if}
    </section>

    <!-- Field-table controls -->
    <section>
      <div class="flex flex-wrap gap-3 items-end mb-3">
        <div class="flex-1 min-w-64">
          <label class="text-xs uppercase tracking-wide text-slate-500 font-semibold block mb-1">Filter</label>
          <input type="search" placeholder="filter by name, code, or description…" bind:value={q}
            class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-brand-400" />
        </div>
        <div>
          <label class="text-xs uppercase tracking-wide text-slate-500 font-semibold block mb-1">Type</label>
          <select bind:value={typeFilter}
            class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-400">
            <option value="">All</option>
            {#each types as t}<option value={t}>{t}</option>{/each}
          </select>
        </div>
        <div class="ml-auto text-xs text-slate-500 self-end pb-2">
          Showing {filtered.length} / {fields.length}
        </div>
      </div>

      <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="overflow-x-auto max-h-[70vh] overflow-y-auto">
          <table class="tbl w-full text-left">
            <thead>
              <tr>
                <th class="w-12 text-right">#</th>
                <th>中文欄位</th>
                <th>English (code)</th>
                <th>型態</th>
                <th class="text-right">長</th>
                <th>資料描述</th>
                <th>譯碼</th>
                <th>可用</th>
              </tr>
            </thead>
            <tbody>
              {#each filtered as f}
                <tr>
                  <td class="text-right tabular-nums text-slate-400">{f.seq}</td>
                  <td>
                    <div class="font-medium text-slate-800">{f.name_zh}</div>
                    {#if f.name_zh_en}
                      <div class="text-xs italic text-slate-500 mt-0.5">{f.name_zh_en}</div>
                    {/if}
                  </td>
                  <td class="mono group">
                    {#if f.name_en}
                      <a href="{base}/file/{file.code}/field/{encodeURIComponent(f.name_en)}/?v={selectedId}"
                         class="text-brand-700 hover:underline font-semibold">{f.name_en}</a>
                      <button onclick={() => copyText(f.name_en)}
                              class="ml-1 opacity-0 group-hover:opacity-60 hover:opacity-100 text-xs"
                              title="Copy">⎘</button>
                    {:else}
                      <span class="text-slate-300">—</span>
                    {/if}
                  </td>
                  <td class="text-slate-700 text-xs">{f.type}</td>
                  <td class="text-right tabular-nums text-slate-600">{f.length ?? ''}</td>
                  <td class="text-xs text-slate-700 max-w-md whitespace-pre-line leading-relaxed">
                    <div>{f.description_zh}</div>
                    {#if f.description_en}
                      <div class="italic text-slate-500 mt-1">{f.description_en}</div>
                    {/if}
                    {#if f.section}
                      <div class="text-[10px] text-slate-400 mt-1">§ {f.section}</div>
                    {/if}
                  </td>
                  <td class="text-xs text-slate-600 max-w-xs whitespace-pre-line">
                    {#if ext.codebooks?.[f.name_en]}
                      <span class="text-[11px] font-semibold text-brand-700 bg-brand-50 rounded-full px-2 py-0.5">
                        {ext.codebooks[f.name_en].entries?.length || 0} codes
                      </span>
                    {/if}
                    {#if f.value_labels}
                      <div class="leading-snug">{f.value_labels}</div>
                    {/if}
                  </td>
                  <td class="text-[11px] text-slate-600">
                    {#each f.available_notes || [] as n}
                      <span class="block">{n.ad_year}{n.marker || ''}</span>
                    {/each}
                  </td>
                </tr>
              {/each}
              {#if filtered.length === 0}
                <tr><td colspan="8" class="text-center text-slate-400 py-6">no matches</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  {/if}
</div>
