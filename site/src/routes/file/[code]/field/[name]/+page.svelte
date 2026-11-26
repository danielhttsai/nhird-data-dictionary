<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const { code, name_zh: fileNameZh, fieldName, occurrences } = data;
  const latest = $derived(occurrences.at(-1) || null);
  // Fields that hold NHI drug codes (or their ATC code) link to the drug code lookup.
  const DRUG_FIELDS = { Health04: ['DRUG_NO', 'ORDER_CODE'], Health05: ['ORDER_CODE'], Health06: ['DRUG_NO', 'ORDER_CODE'], Health17: ['DRUG_NO', 'DRUG_ATC7_CODE'], Health37: ['ORDER_CODE'] };
  const isDrugField = (DRUG_FIELDS[code] || []).includes(fieldName);
  // A field of a multi-table manual is addressed <table>.<column>; show the column.
  const colName = $derived(latest?.field?.name_en || fieldName);
  const tbl = $derived(latest?.table || null);
</script>

<svelte:head><title>{colName} — {code} — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <nav class="text-sm flex items-center gap-1 flex-wrap">
    <a href="{base}/" class="text-brand-700 hover:underline">Catalogue</a>
    <span class="text-slate-400">/</span>
    <a href="{base}/file/{code}/" class="text-brand-700 hover:underline">{code}</a>
    <span class="text-slate-400">/</span>
    {#if tbl}
      <a href="{base}/file/{code}/?t={tbl.code_short}" class="text-brand-700 hover:underline mono">{tbl.code_short}</a>
      <span class="text-slate-400">/</span>
    {/if}
    <span class="text-slate-700 mono">{colName}</span>
  </nav>

  <header>
    <div class="flex items-baseline gap-3 flex-wrap">
      <span class="mono text-2xl font-extrabold text-brand-700">{colName}</span>
      {#if latest}<span class="text-slate-700 font-semibold">— {latest.field.name_zh_en || latest.field.name_zh}</span>{/if}
    </div>
    {#if latest?.field.name_zh_en && latest?.field.name_zh}
      <p class="text-sm text-slate-500 mt-0.5">{latest.field.name_zh}</p>
    {/if}
    <p class="text-sm text-slate-600 mt-1">
      in <a class="text-brand-700 hover:underline font-semibold" href="{base}/file/{code}/">{code}</a> {fileNameZh}
      {#if tbl}
        · table <a class="mono text-brand-700 hover:underline font-semibold" href="{base}/file/{code}/?t={tbl.code_short}">{tbl.code_short}</a>
        {tbl.name_zh_en || ''} <span class="text-slate-500">{tbl.name_zh || ''}</span>
      {/if}
    </p>
  </header>

  {#if isDrugField}
    <a href="{base}/drugs/" class="flex items-center justify-between gap-3 rounded-2xl border border-brand-200 bg-brand-50 px-5 py-3 text-sm hover:border-brand-400 transition">
      <span class="text-slate-700"><strong class="text-brand-700">Drug code lookup</strong> — map the NHI drug codes in this field to ingredient and ATC, or list every code for an ATC class. <span class="text-slate-500">健保藥品代碼查詢</span></span>
      <span class="text-brand-700 font-semibold whitespace-nowrap">Open →</span>
    </a>
  {/if}

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
        <p class="whitespace-pre-line leading-relaxed text-slate-700">{latest.field.description_en || latest.field.description_zh}</p>
        {#if latest.field.description_en && latest.field.description_zh}
          <p class="whitespace-pre-line leading-relaxed text-slate-500 text-sm mt-2">{latest.field.description_zh}</p>
        {/if}
      </div>
      {#if latest.field.purpose_zh}
        <div class="col-span-2">
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Purpose <span class="normal-case font-normal">收錄目的</span></div>
          {#if latest.field.purpose_en}<p class="whitespace-pre-line leading-relaxed text-slate-700">{latest.field.purpose_en}</p>{/if}
          <p class="whitespace-pre-line leading-relaxed {latest.field.purpose_en ? 'text-slate-500 text-sm mt-1' : 'text-slate-700'}">{latest.field.purpose_zh}</p>
        </div>
      {/if}
      {#if latest.field.guide_zh}
        <!-- TWCR manuals: the item's coding guide (編碼指引), as the registry manual gives it -->
        <div class="col-span-2">
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Coding guide <span class="normal-case font-normal">編碼指引</span></div>
          {#if latest.field.guide_en}<p class="whitespace-pre-line leading-relaxed text-slate-700">{latest.field.guide_en}</p>{/if}
          <p class="whitespace-pre-line leading-relaxed {latest.field.guide_en ? 'text-slate-500 text-sm mt-1' : 'text-slate-700'}">{latest.field.guide_zh}</p>
        </div>
      {/if}
      {#if latest.field.available_notes?.length}
        <div class="col-span-2">
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Period</div>
          {#each latest.field.available_notes as n}
            <div class="text-xs text-slate-600">since AD {n.ad_year} (ROC {n.roc_year}) {n.marker || ''}</div>
          {/each}
        </div>
      {/if}
      {#if latest.field.refs?.length}
        <div class="col-span-2">
          <div class="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Reference documents</div>
          {#each latest.field.refs as r}
            <a href={r.url} target="_blank" rel="noreferrer"
               class="block text-sm text-brand-700 hover:underline">📄 {r.label}</a>
          {/each}
        </div>
      {/if}
    </section>

    {#if latest.codebook?.text}
      <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 class="text-sm font-bold text-slate-900 mb-1">Coding rules <span class="text-xs font-normal text-slate-500">譯碼說明 · {latest.codebook.field_zh}</span></h2>
        {#if latest.codebook.text_en}<p class="text-sm whitespace-pre-line leading-relaxed text-slate-700">{latest.codebook.text_en}</p>{/if}
        <p class="whitespace-pre-line leading-relaxed {latest.codebook.text_en ? 'text-xs text-slate-500 mt-2' : 'text-sm text-slate-700'}">{latest.codebook.text}</p>
      </section>
    {/if}

    {#if latest.codebook?.grid?.rows?.length}
      <!-- a code table that is a grid (a column per period, several lists side by side):
           shown cell by cell as the manual prints it -->
      <section>
        <h2 class="text-sm font-bold text-slate-900 mb-1 flex items-center gap-2 flex-wrap">
          Code table as printed <span class="text-xs font-normal text-slate-500">手冊原表 · {latest.codebook.field_zh}</span>
          <span class="text-[11px] font-semibold text-brand-700 bg-brand-50 rounded-full px-2 py-0.5">{latest.codebook.grid.rows.length} rows</span>
        </h2>
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div class="overflow-x-auto max-h-96 overflow-y-auto">
            <table class="tbl w-full text-left text-xs">
              {#if latest.codebook.grid.header?.length}
                <thead><tr>{#each latest.codebook.grid.header as h}<th>{h}</th>{/each}</tr></thead>
              {/if}
              <tbody>
                {#each latest.codebook.grid.rows as r}
                  <tr>{#each r as c}<td class="text-slate-700 whitespace-pre-line">{c}</td>{/each}</tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    {/if}

    {#if latest.codebook && latest.codebook.entries?.length}
      <section>
        <h2 class="text-sm font-bold text-slate-900 mb-1 flex items-center gap-2 flex-wrap">
          Codebook — {latest.codebook.field_en || latest.codebook.field_zh}
          {#if latest.codebook.field_en && latest.codebook.field_zh}
            <span class="text-xs font-normal text-slate-500">{latest.codebook.field_zh}</span>
          {/if}
          <span class="text-[11px] font-semibold text-brand-700 bg-brand-50 rounded-full px-2 py-0.5">
            {latest.codebook.entries.length} entries
          </span>
        </h2>
        {#if latest.codebook.source}
          <p class="text-xs text-slate-500 mb-2">
            來源 Source: {latest.codebook.source}
            {#if latest.codebook.source_url}
              · <a href={latest.codebook.source_url} target="_blank" rel="noreferrer" class="text-brand-700 hover:underline">下載原始表 ↗</a>
            {/if}
          </p>
        {/if}
        {#if latest.codebook.note}
          <p class="text-xs text-amber-700 bg-amber-50/60 border border-amber-100 rounded-lg px-2.5 py-1.5 mb-2">ⓘ {latest.codebook.note}</p>
        {/if}
        {#if latest.codebook.revisions?.length}
          <details class="mb-3 rounded-xl border border-slate-200 bg-slate-50/60">
            <summary class="cursor-pointer select-none px-3 py-2 text-xs font-bold text-slate-700">
              版本沿革 Revision history · {latest.codebook.revisions.length}
            </summary>
            <ol class="px-3 pb-3 pt-2 space-y-2 border-t border-slate-200">
              {#each latest.codebook.revisions as r}
                <li class="text-xs flex gap-2">
                  <span class="mt-1 shrink-0 w-1.5 h-1.5 rounded-full bg-brand-400"></span>
                  <div>
                    <div class="font-semibold text-brand-800">{r.ver}</div>
                    {#if r.note_en}<div class="text-slate-700 leading-relaxed">{r.note_en}</div>{/if}
                    {#if r.note_zh}<div class="text-slate-500 leading-relaxed">{r.note_zh}</div>{/if}
                  </div>
                </li>
              {/each}
            </ol>
          </details>
        {/if}
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div class="overflow-x-auto max-h-96 overflow-y-auto">
            <table class="tbl w-full text-left">
              <thead><tr><th class="w-24">Code</th><th>English <span class="font-normal text-slate-400">名稱</span></th></tr></thead>
              <tbody>
                {#each latest.codebook.entries as e, i}
                  {#if e.section && e.section !== latest.codebook.entries[i - 1]?.section}
                    <tr><td colspan="2" class="bg-slate-50 text-xs font-semibold text-slate-600">{e.section}</td></tr>
                  {/if}
                  <tr>
                    <td class="mono font-semibold text-brand-700">{e.code}</td>
                    <td>
                      <div class="text-slate-800">{e.label_en || e.label_zh}</div>
                      {#if e.label_en && e.label_zh}<div class="text-xs text-slate-500">{e.label_zh}</div>{/if}
                      {#if e.icd || e.validity}
                        <div class="text-[11px] text-slate-500 mt-0.5">
                          {#if e.icd}<span class="mono">ICD-10-CM {e.icd}</span>{/if}
                          {#if e.icd && e.validity} · {/if}
                          {#if e.validity}Certificate valid 證明有效期限: {e.validity}{/if}
                        </div>
                      {/if}
                    </td>
                  </tr>
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
                  <td class="text-xs text-slate-700">{(o.field.description_en || o.field.description_zh || '').slice(0, 200)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    {/if}
  {/if}
</div>
