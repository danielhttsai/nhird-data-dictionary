<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const items = data.catalogue.items;

  const groups = $derived.by(() => {
    const g = new Map();
    for (const it of items) {
      if (!g.has(it.category)) g.set(it.category, []);
      g.get(it.category).push(it);
    }
    return g;
  });

  const totals = $derived({
    files: items.length,
    pdfs: items.reduce((n, it) => n + it.versions.filter(v => v.file_type === 'pdf').length, 0),
    zips: items.reduce((n, it) => n + it.versions.filter(v => v.file_type === 'zip').length, 0)
  });
</script>

<div class="space-y-6">
  <section>
    <h1 class="text-2xl font-bold">HWDC Database Catalogue</h1>
    <p class="text-sm text-slate-600 mt-1">
      {totals.files} files · {totals.pdfs} PDF specs · {totals.zips} multi-file (ZIP) bundles ·
      generated {data.catalogue.generated_at?.slice(0, 10) || ''}
    </p>
  </section>

  {#each [...groups] as [category, list]}
    <section>
      <h2 class="text-lg font-semibold mb-2">
        <span class="pill pill-{category}">{category}</span>
        <span class="text-slate-500 font-normal text-sm ml-2">{list.length} files</span>
      </h2>
      <div class="overflow-x-auto rounded border border-slate-200">
        <table class="tbl w-full bg-white text-left">
          <thead>
            <tr>
              <th>Code</th>
              <th>中文檔名</th>
              <th>English name</th>
              <th class="text-right">Fields</th>
              <th>Freq.</th>
              <th>Versions</th>
            </tr>
          </thead>
          <tbody>
            {#each list as it}
              <tr>
                <td class="mono">
                  <a href="{base}/file/{it.code}/" class="text-blue-700 hover:underline">{it.code}</a>
                  {#if it.code_short}<div class="text-xs text-slate-500 mt-0.5">{it.code_short}</div>{/if}
                </td>
                <td>{it.name_zh}</td>
                <td class="text-slate-600 text-xs">{it.name_en || ''}</td>
                <td class="text-right tabular-nums">{it.field_count ?? '—'}</td>
                <td class="text-slate-600">{it.frequency || ''}</td>
                <td class="space-x-1">
                  {#each it.versions as v}
                    <a href="{base}/file/{it.code}/?v={v.version_id}"
                       class="inline-block px-2 py-0.5 rounded text-xs
                              {v.file_type === 'zip' ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'}
                              hover:opacity-80"
                       title="{v.version_label}{v.file_type === 'zip' ? ' (multi-file bundle)' : ''}">{v.version_id}</a>
                  {/each}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {/each}
</div>
