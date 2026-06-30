<script>
  import { base } from '$app/paths';
  import { onMount } from 'svelte';
  import MiniSearch from 'minisearch';

  let q = $state('');
  let ready = $state(false);
  let mini;

  let results = $state([]);

  onMount(async () => {
    const r = await fetch(`${base}/data/search-fields.json`);
    const fields = await r.json();
    mini = new MiniSearch({
      fields: ['name_zh', 'name_zh_en', 'name_en', 'description_zh', 'description_en', 'code'],
      storeFields: ['code', 'version_id', 'seq', 'name_zh', 'name_zh_en', 'name_en', 'type', 'length', 'description_zh', 'description_en'],
      searchOptions: { boost: { name_en: 3, name_zh: 2, name_zh_en: 2 }, prefix: true, fuzzy: 0.1 }
    });
    mini.addAll(fields);
    ready = true;
  });

  function search() {
    if (!mini) return;
    results = mini.search(q).slice(0, 200);
  }
  $effect(() => { if (q.length >= 2) search(); else results = []; });
</script>

<svelte:head><title>Search — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <header>
    <h1 class="text-3xl font-extrabold text-slate-900">Search</h1>
    <p class="text-slate-600 mt-1">Across every field name and description in the catalogue.</p>
  </header>

  <input type="search" bind:value={q} placeholder="e.g. ID, FEE_YM, 就醫日期, 住院"
         class="w-full px-4 py-3 border border-slate-300 rounded-xl text-base shadow-sm
                focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-brand-400" />

  {#if !ready}
    <p class="text-slate-500 text-sm">Loading index…</p>
  {:else if q.length < 2}
    <p class="text-slate-500 text-sm">Type at least 2 characters to search.</p>
  {:else}
    <p class="text-slate-500 text-xs">{results.length} match{results.length === 1 ? '' : 'es'}</p>
    <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div class="overflow-x-auto">
        <table class="tbl w-full text-left">
          <thead>
            <tr><th>File</th><th>Version</th><th>#</th><th>中文</th><th>English</th><th>Type</th><th>Description</th></tr>
          </thead>
          <tbody>
            {#each results as r}
              <tr>
                <td class="mono">
                  <a href="{base}/file/{r.code}/?v={r.version_id}" class="text-brand-700 hover:underline font-semibold">{r.code}</a>
                </td>
                <td class="text-xs text-slate-500">{r.version_id}</td>
                <td class="text-right text-slate-400">{r.seq}</td>
                <td>
                  <div class="text-slate-800">{r.name_zh}</div>
                  {#if r.name_zh_en}<div class="text-xs italic text-slate-500">{r.name_zh_en}</div>{/if}
                </td>
                <td class="mono">
                  <a href="{base}/file/{r.code}/field/{r.name_en}/?v={r.version_id}"
                     class="text-brand-700 hover:underline font-semibold">{r.name_en}</a>
                </td>
                <td class="text-xs text-slate-600">{r.type} {r.length ?? ''}</td>
                <td class="text-xs text-slate-700 max-w-md">
                  <div>{r.description_zh}</div>
                  {#if r.description_en}<div class="italic text-slate-500 mt-0.5">{r.description_en}</div>{/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}
</div>
