<script>
  import { base } from '$app/paths';
  import { onMount } from 'svelte';

  let index = $state(null);
  let q = $state('');

  onMount(async () => {
    const r = await fetch(`${base}/data/codebooks-index.json`);
    index = await r.json();
  });

  const filtered = $derived.by(() => {
    if (!index) return [];
    const list = Object.entries(index.items || {});
    if (!q.trim()) return list;
    const t = q.trim().toLowerCase();
    return list.filter(([k, items]) =>
      k.toLowerCase().includes(t)
      || items.some(it => (it.field_zh || '').toLowerCase().includes(t))
    );
  });
</script>

<svelte:head><title>Codebooks — NHIRD data dictionary</title></svelte:head>

<div class="space-y-6">
  <header>
    <h1 class="text-3xl font-extrabold text-slate-900">Codebooks</h1>
    <p class="text-slate-600 mt-1 max-w-3xl">
      Every 譯碼說明 across the catalogue, indexed by the English field code. The same
      code (e.g. <span class="mono">CASE_TYPE</span>) often appears in multiple files; entry
      lists may differ between files.
    </p>
  </header>

  <input type="search" bind:value={q} placeholder="filter by name (CASE_TYPE, 案件分類, …)"
    class="w-full px-4 py-3 border border-slate-300 rounded-xl text-base shadow-sm
           focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-brand-400" />

  {#if !index}
    <p class="text-slate-500">Loading…</p>
  {:else}
    <p class="text-slate-500 text-xs">{filtered.length} / {index.count} codebooks</p>
    <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div class="overflow-x-auto">
        <table class="tbl w-full text-left">
          <thead><tr><th class="w-44">Code</th><th>Appears in</th></tr></thead>
          <tbody>
            {#each filtered as [name, items]}
              <tr>
                <td class="mono font-semibold text-brand-700 align-top">{name}</td>
                <td class="text-xs">
                  {#each items as it, i}
                    {#if i > 0}<span class="text-slate-300">·</span> {/if}
                    <a class="text-brand-700 hover:underline font-semibold"
                       href="{base}/file/{it.code}/field/{name}/?v={it.version_id}">
                      {it.code}/{it.version_id}
                    </a>
                    <span class="text-slate-500">({it.field_zh}, {it.n_entries})</span>
                  {/each}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}
</div>
