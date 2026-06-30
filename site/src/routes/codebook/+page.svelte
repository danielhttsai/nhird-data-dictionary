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

<div class="space-y-4">
  <h1 class="text-2xl font-bold">Codebooks</h1>
  <p class="text-sm text-slate-600">
    Every codebook (譯碼說明) across the catalogue, indexed by the English field code.
    The same code (e.g. <span class="mono">CASE_TYPE</span>) often appears in multiple files; entry lists may differ between files.
  </p>
  <input type="search" bind:value={q} placeholder="filter by name (CASE_TYPE, 案件分類, …)"
    class="w-full px-3 py-2 border border-slate-300 rounded" />

  {#if !index}
    <p class="text-slate-500">Loading…</p>
  {:else}
    <p class="text-slate-500 text-xs">{filtered.length} / {index.count} codebooks</p>
    <div class="overflow-x-auto rounded border border-slate-200">
      <table class="tbl w-full bg-white text-left">
        <thead><tr><th>Code</th><th>Appears in</th></tr></thead>
        <tbody>
          {#each filtered as [name, items]}
            <tr>
              <td class="mono align-top">{name}</td>
              <td class="text-xs">
                {#each items as it, i}
                  {#if i > 0}, {/if}
                  <a class="text-blue-700 hover:underline"
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
  {/if}
</div>
