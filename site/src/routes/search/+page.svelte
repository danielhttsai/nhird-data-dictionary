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
    const raw = await r.json();
    // Index uses compact keys: c=code v=version_id s=seq zh=name_zh
    // ze=name_zh_en en=name_en d=description_zh. Add a numeric id.
    const docs = raw.map((f, i) => ({ id: i, ...f }));
    mini = new MiniSearch({
      fields: ['zh', 'ze', 'en', 'd', 'c'],
      storeFields: ['c', 'v', 's', 'zh', 'ze', 'en', 'd'],
      searchOptions: { boost: { en: 3, zh: 2, ze: 2 }, prefix: true, fuzzy: 0.1 }
    });
    mini.addAll(docs);
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
    <p class="text-slate-500 text-xs">{results.length} match{results.length === 1 ? '' : 'es'}{results.length === 200 ? '+ (showing first 200)' : ''}</p>
    <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div class="overflow-x-auto">
        <table class="tbl w-full text-left">
          <thead>
            <tr><th>File</th><th>Version</th><th>#</th><th>中文</th><th>English</th><th>Description</th></tr>
          </thead>
          <tbody>
            {#each results as r}
              <tr>
                <td class="mono">
                  <a href="{base}/file/{r.c}/?v={r.v}" class="text-brand-700 hover:underline font-semibold">{r.c}</a>
                </td>
                <td class="text-xs text-slate-500">{r.v}</td>
                <td class="text-right text-slate-400">{r.s}</td>
                <td>
                  <div class="text-slate-800">{r.zh}</div>
                  {#if r.ze}<div class="text-xs italic text-slate-500">{r.ze}</div>{/if}
                </td>
                <td class="mono">
                  {#if r.en}
                    <a href="{base}/file/{r.c}/field/{encodeURIComponent(r.en)}/?v={r.v}"
                       class="text-brand-700 hover:underline font-semibold">{r.en}</a>
                  {:else}<span class="text-slate-300">—</span>{/if}
                </td>
                <td class="text-xs text-slate-700 max-w-md">{r.d}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}
</div>
