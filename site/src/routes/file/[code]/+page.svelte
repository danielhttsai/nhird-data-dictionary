<script>
  import { base } from '$app/paths';
  import { page } from '$app/state';

  let { data } = $props();
  const file = data.file;

  // Default to a version that actually has a field table — preferring a main
  // PDF, else the richest (most fields) — so survey files don't land on an
  // empty 0-field wave.
  const withData = file.versions.filter(v => (v.field_count || 0) > 0 && !v.garbled);
  const pdfWf = withData.filter(v => v.file_type !== 'xls');
  const richest = withData.slice().sort((a, b) => (b.field_count || 0) - (a.field_count || 0))[0];
  const defaultV = pdfWf.at(-1) || richest || file.versions.find(v => v.fields_file) || file.versions.at(-1);
  let selectedId = $state(defaultV?.version_id || '');
  $effect(() => {
    const v = page.url.searchParams.get('v');
    if (v && file.versions.some(x => x.version_id === v)) {
      selectedId = v;
    }
  });

  const selected = $derived(file.versions.find(v => v.version_id === selectedId));
  const meta = $derived(selected?.meta || null);

  // A manual that documents several tables (Welfare20: ten, each with its own
  // header block, fields and code tables) lists them in meta.tables; each field
  // carries its table's code. The page shows one table at a time (?t=<code>).
  const tables = $derived(meta?.tables || []);
  let tableId = $state('');
  $effect(() => {
    const t = page.url.searchParams.get('t');
    if (t) tableId = t;
  });
  const table = $derived(tables.length ? (tables.find(t => t.code_short === tableId) || tables[0]) : null);
  // header facts of the table shown (or of the file)
  // (a file listed under a shared header, Health55, has no description of its own:
  // the manual's header facts stand in for what the table does not state)
  const info = $derived(table
    ? { ...meta, ...Object.fromEntries(Object.entries(table).filter(([, v]) => v !== '' && v != null)) }
    : meta);
  const fkey = (f) => (f.table && f.name_en ? `${f.table}.${f.name_en}` : f.name_en);
  // a code table of one table's field, or one the manual's files share (Health55)
  const cbOf = (f) => codebooks?.[fkey(f)] || (f.table ? codebooks?.[f.name_en] : null);
  function pickTable(code) {
    tableId = code;
    const u = new URL(window.location.href);
    u.searchParams.set('t', code);
    history.replaceState(history.state, '', u);
  }

  // Lazy-load each version's field table on demand (keeps the initial page light).
  let fieldsCache = $state({});
  let loadingFields = $state(false);
  $effect(() => {
    const v = selected;
    if (!v || !v.fields_file || fieldsCache[v.version_id]) return;
    loadingFields = true;
    fetch(`${base}/data/fields/${v.fields_file}`)
      .then(r => r.ok ? r.json() : { fields: [], codebooks: {} })
      .then(d => { fieldsCache = { ...fieldsCache, [v.version_id]: d }; })
      .catch(() => { fieldsCache = { ...fieldsCache, [v.version_id]: { fields: [], codebooks: {} } }; })
      .finally(() => { loadingFields = false; });
  });
  const fieldData = $derived(selected ? fieldsCache[selected.version_id] : null);
  const allFields = $derived(fieldData?.fields || []);
  const fields = $derived(table ? allFields.filter(f => f.table === table.code_short) : allFields);
  const codebooks = $derived(fieldData?.codebooks || {});

  let q = $state('');
  let typeFilter = $state('');

  const filtered = $derived.by(() => {
    const term = q.trim().toLowerCase();
    return fields.filter(f => {
      if (typeFilter && f.type !== typeFilter) return false;
      if (!term) return true;
      return (f.name_zh || '').toLowerCase().includes(term)
        || (f.name_en || '').toLowerCase().includes(term)
        || (f.name_zh_en || '').toLowerCase().includes(term)
        || (f.description_zh || '').toLowerCase().includes(term)
        || (f.description_en || '').toLowerCase().includes(term);
    });
  });

  const types = $derived([...new Set(fields.map(f => f.type).filter(Boolean))].sort());

  function copyText(t) { navigator.clipboard?.writeText(t); }

  // Clean, human, DATE-based display label (no internal "legacy" jargon).
  function fmtDate(s) {
    const m = String(s || '').match(/(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[1]}/${m[2]}/${m[3]}` : s;
  }
  function vLabel(v) {
    if (v.file_type === 'xls')
      return (v.version_label || '').replace(/^Excel codebook · /, '');
    if (v.version_id.includes('__wave_'))
      return (v.version_label || '').replace(/^legacy · /, '').replace(/^post-20250624 · /, '');
    // Main versions → date-based.
    if (v.version_id.includes('post-20250624')) {
      const period = (v.version_label || '').match(/(2010 年以前|2011-2017 年|2018 年以後)/);
      return (period ? period[1] + ' · ' : '') + '2025/06/24 起適用';
    }
    const periodOnly = (v.version_label || '').match(/(2010 年以前|2011-2017 年|2018 年以後)/);
    if (periodOnly) return periodOnly[1];
    if (v.doc_first_published) return `${fmtDate(v.doc_first_published)} 起`;
    return v.version_label || v.version_id;
  }
  function vLabelId(id) {
    const v = file.versions.find((x) => x.version_id === id);
    return v ? vLabel(v) : id;
  }
  function names(list, key = 'name_en', n = 10) {
    const arr = list.map((f) => f[key]).filter(Boolean);
    return arr.slice(0, n).join(', ') + (arr.length > n ? ` +${arr.length - n} more` : '');
  }
  const HIST = { '初版': 'first edition', '修訂': 'revised', '新增': 'added', '修正': 'amended', '版': 'ed.' };
  function histNote(n) { n = (n || '').trim(); return HIST[n] ? `${n} · ${HIST[n]}` : n; }
  function vGroup(v) {
    if (v.file_type === 'xls') return 'Codebooks 編碼簿';
    if (v.version_id.includes('__wave_')) return 'Sub-files / waves 附屬檔';
    if (v.version_id.includes('twcr_manual')) return 'Registry manual (TWCR) 癌症登記手冊';
    return 'Main versions 主檔';
  }
  // Build grouped option list — only versions with an actual field table
  // (0-field supplementary docs like 問卷/實施計畫 are reachable via the
  // "Original MOHW PDF" link, not the selector).
  const selectable = $derived(file.versions.filter(v => (v.field_count || 0) > 0 && !v.garbled));
  const groupedVersions = $derived.by(() => {
    const g = new Map();
    for (const v of selectable) {
      const k = vGroup(v);
      if (!g.has(k)) g.set(k, []);
      g.get(k).push(v);
    }
    return [...g];
  });
  const manyVersions = $derived(selectable.length > 8);
</script>

<svelte:head><title>{file.code} — {file.name_en || file.name_zh} — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <nav class="text-sm">
    <a href="{base}/" class="text-brand-700 hover:underline">← Catalogue</a>
  </nav>

  <header class="space-y-2">
    <div class="flex items-center gap-3 flex-wrap">
      <span class="mono text-2xl font-extrabold text-brand-700">{file.code}</span>
      <span class="pill pill-{file.category}">{file.category}</span>
      {#if info?.code_short}<span class="mono text-xs text-slate-500">{info.code_short}</span>{/if}
    </div>
    <h1 class="text-3xl font-extrabold text-slate-900 leading-tight">{file.name_en || file.name_zh}</h1>
    {#if file.name_en && file.name_zh}<p class="text-slate-500 text-sm">{file.name_zh}</p>{/if}
  </header>

  <!-- Version selector -->
  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
    {#if manyVersions}
      <!-- Many sub-files / waves → grouped dropdown -->
      <div class="flex flex-wrap items-center gap-3">
        <label class="text-xs uppercase tracking-wide text-slate-500 font-semibold">
          Version / 檔案
          <span class="ml-1 normal-case text-slate-400 font-normal">
            ({file.versions.filter(v => v.has_extract).length} files & waves)
          </span>
        </label>
        <select bind:value={selectedId}
          class="flex-1 min-w-64 max-w-xl px-3 py-2 border border-slate-300 rounded-lg text-sm
                 focus:outline-none focus:ring-2 focus:ring-brand-400">
          {#each groupedVersions as [group, vs]}
            <optgroup label={group}>
              {#each vs as v}
                <option value={v.version_id}>
                  {vLabel(v)}{v.field_count ? ` — ${v.field_count} fields` : ''}
                </option>
              {/each}
            </optgroup>
          {/each}
        </select>
        {#if selectable.length > 1}
          <a class="text-sm font-semibold text-brand-700 hover:underline"
             href="{base}/file/{file.code}/diff/">Compare →</a>
        {/if}
      </div>
    {:else}
      <!-- Few versions → buttons -->
      <div class="flex flex-wrap gap-2 items-center">
        <span class="text-xs uppercase tracking-wide text-slate-500 font-semibold mr-2">Version</span>
        {#each selectable as v}
          <button
            class="text-xs px-3 py-1.5 rounded-lg border font-semibold transition
              {v.version_id === selectedId
                ? 'bg-brand-600 text-white border-brand-600'
                : 'bg-white text-slate-700 border-slate-300 hover:bg-brand-50 hover:border-brand-400 hover:text-brand-700'}"
            onclick={() => selectedId = v.version_id}
          >{vLabel(v)}</button>
        {/each}
        {#if selectable.length > 1}
          <a class="ml-auto text-sm font-semibold text-brand-700 hover:underline"
             href="{base}/file/{file.code}/diff/">Compare versions →</a>
        {/if}
      </div>
    {/if}
  </section>

  {#if tables.length > 1}
    <!-- One manual, several tables -->
    <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-2">
        Tables <span class="normal-case font-normal text-slate-400">資料表 · this manual documents {tables.length} tables</span>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {#each tables as t}
          {@const n = fieldData ? allFields.filter(f => f.table === t.code_short).length : t.fields_parsed}
          <button onclick={() => pickTable(t.code_short)}
            class="text-left rounded-xl border px-3 py-2 transition
              {t.code_short === table?.code_short
                ? 'border-brand-500 bg-brand-50'
                : 'border-slate-200 hover:border-brand-400 hover:bg-brand-50/40'}">
            <div class="mono text-xs font-semibold text-brand-700 break-all">{t.code_short}</div>
            <div class="text-sm font-semibold text-slate-800 leading-snug">{t.name_zh_en || t.name_zh}</div>
            {#if t.name_zh_en}<div class="text-xs text-slate-500">{t.name_zh}</div>{/if}
            <div class="text-[11px] text-slate-500 mt-0.5">
              {n ?? ''} fields{#if t.field_count_declared != null && n != null && t.field_count_declared !== n}<span class="text-amber-700"> · header says {t.field_count_declared}</span>{/if}
            </div>
          </button>
        {/each}
      </div>
    </section>
  {/if}

  <!-- Version changes live on their own interactive page (kept out of the way here). -->
  {#if selectable.length > 1}
    <a href="{base}/file/{file.code}/diff/"
       class="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm hover:border-brand-400 transition group">
      <span class="text-sm font-semibold text-slate-800">
        Version history <span class="text-slate-400 font-normal text-xs">版本沿革</span>
        <span class="text-slate-300 font-normal mx-1">·</span>
        <span class="text-slate-600 font-normal">compare fields across {selectable.length} versions</span>
      </span>
      <span class="text-sm font-semibold text-brand-700 group-hover:underline whitespace-nowrap shrink-0">Open →</span>
    </a>
  {/if}

  {#if !meta}
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
        {#if table}
          {@const shown = fieldData ? fields.length : table.fields_parsed}
          <div class="text-xl font-extrabold text-brand-700">{table.field_count_declared ?? shown ?? '—'}</div>
          {#if table.field_count_declared != null && shown != null && table.field_count_declared !== shown}
            <div class="text-[10px] text-amber-700">the field table lists {shown}</div>
          {/if}
        {:else}
          <div class="text-xl font-extrabold text-brand-700">{meta.field_count_declared ?? selected.field_count ?? '—'}</div>
          {#if meta.field_count_declared && selected.field_count && meta.field_count_declared !== selected.field_count}
            <div class="text-[10px] text-amber-700">parsed {selected.field_count}</div>
          {/if}
        {/if}
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3">
        <div class="text-xs uppercase tracking-wide text-slate-500">Frequency</div>
        <div class="text-base font-bold text-slate-900">{info.frequency || '—'}</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3">
        <div class="text-xs uppercase tracking-wide text-slate-500">Attribute</div>
        <div class="text-base font-bold text-slate-900">{info.attribute || '—'}</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 col-span-2">
        <div class="text-xs uppercase tracking-wide text-slate-500">Records</div>
        <div class="text-sm text-slate-800">{info.record_count_raw || '—'}</div>
        {#if info.file_size_raw}<div class="text-[11px] text-slate-500 mt-0.5">File size {info.file_size_raw}</div>{/if}
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3">
        <div class="text-xs uppercase tracking-wide text-slate-500">Last updated</div>
        <div class="text-sm font-bold text-slate-900">{selected.doc_last_updated || '—'}</div>
      </div>
    </section>

    <!-- Descriptive blocks (bilingual where translation available) -->
    <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
      {#if table}
        <div>
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Table</div>
          <p class="text-sm text-slate-800"><span class="mono font-semibold">{table.code_short}</span>
            · {table.name_zh_en || table.name_zh}{#if table.name_zh_en} <span class="text-slate-500">{table.name_zh}</span>{/if}
            {#if table.page_start}<span class="text-xs text-slate-400"> · page {table.page_start} of the manual</span>{/if}</p>
        </div>
        {#if table.note || table.note_zh}
          <p class="text-xs text-amber-800 bg-amber-50/70 border border-amber-100 rounded-lg px-3 py-2 leading-relaxed">
            ⓘ {table.note}{#if table.note_zh}<span class="block text-amber-700/80 mt-1">{table.note_zh}</span>{/if}
          </p>
        {/if}
      {/if}
      {#if info.data_description_zh}
        <div>
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Data description</div>
          <p class="text-sm whitespace-pre-line leading-relaxed text-slate-700">{info.data_description_en || info.data_description_zh}</p>
          {#if info.data_description_en}
            <p class="text-xs whitespace-pre-line leading-relaxed text-slate-500 mt-1">{info.data_description_zh}</p>
          {/if}
        </div>
      {/if}
      {#if info.notes_zh}
        <div>
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Notes</div>
          <p class="text-sm whitespace-pre-line leading-relaxed text-slate-700">{info.notes_en || info.notes_zh}</p>
          {#if info.notes_en}
            <p class="text-xs whitespace-pre-line leading-relaxed text-slate-500 mt-1">{info.notes_zh}</p>
          {/if}
        </div>
      {/if}
      {#if info.primary_keys_raw}
        <div>
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Primary keys / linkage</div>
          <p class="text-sm whitespace-pre-line leading-relaxed text-slate-700">{info.primary_keys_en || info.primary_keys_raw}</p>
          {#if info.primary_keys_en}
            <p class="text-xs whitespace-pre-line leading-relaxed text-slate-500 mt-1">{info.primary_keys_raw}</p>
          {/if}
        </div>
      {/if}
      {#if info.update_history?.length}
        <div>
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Codebook history</div>
          <ul class="flex flex-wrap gap-x-3 gap-y-1 text-xs mono text-slate-600">
            {#each info.update_history as h}<li>{h.date} {histNote(h.note)}</li>{/each}
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
          {#if loadingFields && !fieldData}Loading…{:else}Showing {filtered.length} / {fields.length}{/if}
        </div>
      </div>

      {#if loadingFields && !fieldData}
        <div class="rounded-2xl border border-slate-200 bg-white shadow-sm p-10 text-center text-sm text-slate-400">
          Loading {selected.field_count?.toLocaleString?.() || ''} fields…
        </div>
      {:else}
      <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="overflow-x-auto max-h-[70vh] overflow-y-auto">
          <table class="tbl w-full text-left">
            <thead>
              <tr>
                <th class="w-12 text-right">#</th>
                <th>Field name <span class="font-normal text-slate-400">名稱</span></th>
                <th>Code</th>
                <th>Type</th>
                <th class="text-right">Len</th>
                <th>Description <span class="font-normal text-slate-400">描述</span></th>
                <th>Codes</th>
                <th>Since</th>
              </tr>
            </thead>
            <tbody>
              {#each filtered as f}
                <tr>
                  <td class="text-right tabular-nums text-slate-400">{f.seq}</td>
                  <td>
                    <div class="font-medium text-slate-800">{f.name_zh_en || f.name_zh}</div>
                    {#if f.name_zh_en && f.name_zh}
                      <div class="text-xs text-slate-500 mt-0.5">{f.name_zh}</div>
                    {/if}
                  </td>
                  <td class="mono group">
                    {#if f.name_en}
                      <a href="{base}/file/{file.code}/field/{encodeURIComponent(fkey(f))}/?v={selectedId}"
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
                    <div>{f.description_en || f.description_zh}</div>
                    {#if f.description_en && f.description_zh}
                      <div class="text-slate-500 mt-1">{f.description_zh}</div>
                    {/if}
                    {#if f.section}
                      <div class="text-[10px] text-slate-400 mt-1">§ {f.section}</div>
                    {/if}
                    {#if f.refs?.length}
                      <div class="mt-1 flex flex-col gap-0.5">
                        {#each f.refs as r}
                          <a href={r.url} target="_blank" rel="noreferrer"
                             class="text-[11px] text-brand-700 hover:underline">📄 {r.label}</a>
                        {/each}
                      </div>
                    {/if}
                  </td>
                  <td class="text-xs text-slate-600 max-w-xs whitespace-pre-line">
                    {#if cbOf(f)}
                      <a href="{base}/file/{file.code}/field/{encodeURIComponent(fkey(f))}/?v={selectedId}"
                         class="inline-block text-[11px] font-semibold text-brand-700 bg-brand-50 rounded-full px-2 py-0.5 hover:underline">
                        {cbOf(f).entries?.length ? `${cbOf(f).entries.length} codes` : cbOf(f).grid ? `table, ${cbOf(f).grid.rows.length} rows` : 'coding rules'}
                      </a>
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
      {/if}
    </section>
  {/if}
</div>
