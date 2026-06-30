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
      fields: ['name_zh', 'name_en', 'description_zh', 'code'],
      storeFields: ['code', 'version_id', 'seq', 'name_zh', 'name_en', 'type', 'length', 'description_zh'],
      searchOptions: { boost: { name_en: 3, name_zh: 2 }, prefix: true, fuzzy: 0.1 }
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

<div class="space-y-4">
  <h1 class="text-2xl font-bold">Search across all fields</h1>
  <input type="search" bind:value={q} placeholder="e.g. ID, FEE_YM, 就醫日期, 住院"
         class="w-full px-3 py-2 border border-slate-300 rounded" />

  {#if !ready}
    <p class="text-slate-500 text-sm">Loading index…</p>
  {:else if q.length < 2}
    <p class="text-slate-500 text-sm">Type at least 2 characters to search field names and descriptions.</p>
  {:else}
    <p class="text-slate-500 text-xs">{results.length} match{results.length === 1 ? '' : 'es'}</p>
    <div class="overflow-x-auto rounded border border-slate-200">
      <table class="tbl w-full bg-white text-left">
        <thead>
          <tr><th>File</th><th>Version</th><th>#</th><th>中文</th><th>英文</th><th>Type</th><th>Description</th></tr>
        </thead>
        <tbody>
          {#each results as r}
            <tr>
              <td class="mono"><a href="{base}/file/{r.code}/?v={r.version_id}" class="text-blue-700 hover:underline">{r.code}</a></td>
              <td class="text-xs text-slate-500">{r.version_id}</td>
              <td class="text-right text-slate-500">{r.seq}</td>
              <td>{r.name_zh}</td>
              <td class="mono">
                <a href="{base}/file/{r.code}/field/{r.name_en}/?v={r.version_id}" class="text-blue-700 hover:underline">{r.name_en}</a>
              </td>
              <td class="text-xs">{r.type} {r.length ?? ''}</td>
              <td class="text-xs text-slate-700 max-w-md">{r.description_zh}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
