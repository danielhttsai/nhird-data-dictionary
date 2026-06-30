<script>
  import { base } from '$app/paths';
  import { page } from '$app/state';

  let { data } = $props();
  const file = data.file;

  // version selection — from ?v= or default to latest extracted
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

  let lang = $state('zh'); // 'zh' or 'en'
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

  function copyText(t) {
    navigator.clipboard?.writeText(t);
  }
</script>

<svelte:head><title>{file.code} — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <nav class="text-sm">
    <a href="{base}/" class="text-blue-700 hover:underline">← All files</a>
  </nav>

  <header class="space-y-1">
    <h1 class="text-2xl font-bold flex items-center gap-3 flex-wrap">
      <span class="mono">{file.code}</span>
      <span class="pill pill-{file.category}">{file.category}</span>
      <span class="text-slate-700 font-normal">{file.name_zh}</span>
    </h1>
    {#if file.name_en}<p class="text-slate-600 text-sm">{file.name_en}</p>{/if}
  </header>

  <!-- Version selector -->
  <section class="bg-white border border-slate-200 rounded p-3">
    <div class="flex flex-wrap gap-2 items-center">
      <span class="text-sm font-medium text-slate-700">Version:</span>
      {#each file.versions as v}
        <button
          class="text-xs px-3 py-1 rounded border
            {v.version_id === selectedId
              ? 'bg-blue-600 text-white border-blue-600'
              : v.extracted ? 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
                            : 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed'}"
          disabled={!v.extracted}
          onclick={() => selectedId = v.version_id}
        >{v.version_id}{!v.extracted ? ' (zip)' : ''}</button>
      {/each}
      {#if file.diffs?.length}
        <a class="ml-auto text-sm text-blue-700 hover:underline" href="{base}/file/{file.code}/diff/">
          Compare versions →
        </a>
      {/if}
    </div>
  </section>

  {#if !ext}
    <p class="text-slate-600 text-sm">No extracted JSON for this version (likely a ZIP bundle of multiple per-wave codebooks; download the ZIP from MOHW to view).</p>
    {#if selected?.pdf_url}<p><a href={selected.pdf_url} class="text-blue-700 hover:underline">Original file</a></p>{/if}
  {:else}

    <!-- Metadata block -->
    <section class="bg-white border border-slate-200 rounded p-4 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-sm">
      <div><span class="text-slate-500">File code:</span> <span class="mono">{ext.code_short}</span></div>
      <div><span class="text-slate-500">Field count:</span> {ext.field_count_declared ?? fields.length} <span class="text-xs text-slate-400">(parsed {fields.length})</span></div>
      <div><span class="text-slate-500">Records:</span> {ext.record_count_raw || '—'}</div>
      <div><span class="text-slate-500">File size:</span> {ext.file_size_raw || '—'}</div>
      <div><span class="text-slate-500">Frequency:</span> {ext.frequency || '—'}</div>
      <div><span class="text-slate-500">Attribute:</span> {ext.attribute || '—'}</div>
      <div><span class="text-slate-500">First published:</span> {selected.doc_first_published || '—'}</div>
      <div><span class="text-slate-500">Last updated:</span> {selected.doc_last_updated || '—'}</div>
      {#if ext.update_history?.length}
        <div class="md:col-span-2">
          <span class="text-slate-500">Codebook history:</span>
          {#each ext.update_history as h}
            <span class="ml-2 mono text-xs">{h.date} {h.note}</span>
          {/each}
        </div>
      {/if}
      {#if ext.data_description_zh}
        <div class="md:col-span-2 mt-1">
          <div class="text-slate-500 text-xs uppercase tracking-wide">Description</div>
          <p class="whitespace-pre-line">{ext.data_description_zh}</p>
        </div>
      {/if}
      {#if ext.notes_zh}
        <div class="md:col-span-2">
          <div class="text-slate-500 text-xs uppercase tracking-wide">Notes</div>
          <p class="whitespace-pre-line">{ext.notes_zh}</p>
        </div>
      {/if}
      {#if ext.primary_keys_raw}
        <div class="md:col-span-2">
          <div class="text-slate-500 text-xs uppercase tracking-wide">Primary keys / linkage</div>
          <p class="whitespace-pre-line">{ext.primary_keys_raw}</p>
        </div>
      {/if}
      {#if selected.pdf_url}
        <div class="md:col-span-2 text-xs">
          <a href={selected.pdf_url} target="_blank" rel="noreferrer" class="text-blue-700 hover:underline">
            Original MOHW PDF ({selected.version_label})
          </a>
        </div>
      {/if}
    </section>

    <!-- Field-table controls -->
    <section>
      <div class="flex flex-wrap gap-3 items-end mb-2">
        <div>
          <label class="text-xs text-slate-500 block">Filter</label>
          <input type="search" placeholder="filter fields…" bind:value={q}
            class="px-3 py-1 border border-slate-300 rounded text-sm w-64" />
        </div>
        <div>
          <label class="text-xs text-slate-500 block">Type</label>
          <select bind:value={typeFilter}
            class="px-2 py-1 border border-slate-300 rounded text-sm">
            <option value="">all</option>
            {#each types as t}<option value={t}>{t}</option>{/each}
          </select>
        </div>
        <div class="ml-auto text-xs text-slate-500 self-end">
          showing {filtered.length} / {fields.length}
        </div>
      </div>

      <div class="overflow-x-auto rounded border border-slate-200 max-h-[70vh] overflow-y-auto">
        <table class="tbl w-full bg-white text-left">
          <thead>
            <tr>
              <th class="w-12 text-right">#</th>
              <th>中文欄位</th>
              <th>英文 (code)</th>
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
                <td class="text-right tabular-nums text-slate-500">{f.seq}</td>
                <td>{f.name_zh}</td>
                <td class="mono group">
                  <a href="{base}/file/{file.code}/field/{f.name_en}/?v={selectedId}"
                     class="text-blue-700 hover:underline">{f.name_en}</a>
                  {#if f.name_en}
                    <button onclick={() => copyText(f.name_en)}
                            class="ml-1 opacity-0 group-hover:opacity-60 hover:opacity-100 text-xs"
                            title="Copy">⎘</button>
                  {/if}
                </td>
                <td class="text-slate-700">{f.type}</td>
                <td class="text-right tabular-nums">{f.length ?? ''}</td>
                <td class="text-xs text-slate-700 max-w-md whitespace-pre-line">{f.description_zh}</td>
                <td>
                  {#if ext.codebooks?.[f.name_en]}
                    <span class="text-xs text-blue-700">{ext.codebooks[f.name_en].entries?.length || 0} codes</span>
                  {/if}
                </td>
                <td class="text-xs">
                  {#each f.available_notes || [] as n}
                    <span class="block">{n.ad_year}{n.marker || ''}</span>
                  {/each}
                </td>
              </tr>
            {/each}
            {#if filtered.length === 0}
              <tr><td colspan="8" class="text-center text-slate-400 py-4">no matches</td></tr>
            {/if}
          </tbody>
        </table>
      </div>
    </section>
  {/if}
</div>
