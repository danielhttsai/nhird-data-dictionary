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

</script>

<svelte:head>
  <title>NHIRD / HWDC data dictionary</title>
  <meta name="description" content="Browse every field in every public MOHW Health and Welfare Data Center database manual. 117 files, 4000+ fields, version-controlled and diffable." />
</svelte:head>

<!-- Hero -->
<section class="py-10 sm:py-14">
  <p class="uppercase tracking-widest text-xs text-brand-600 font-semibold mb-3">
    Real-world data · Taiwan HWDC
  </p>
  <h1 class="text-4xl md:text-5xl font-extrabold text-slate-900 leading-tight">
    NHIRD / HWDC <span class="text-brand-700">data dictionary</span>
  </h1>
  <p class="mt-5 text-lg text-slate-700 max-w-3xl leading-relaxed">
    Every field in every public MOHW database manual — bilingual names, codebooks,
    period of availability, and version diffs. Sourced directly from MOHW Department of Statistics
    and refreshed weekly.
  </p>
  <div class="mt-6 flex flex-wrap gap-3">
    <a href="{base}/search" class="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-6 py-3 rounded-xl transition shadow-sm">
      Search across all fields →
    </a>
    <a href="{base}/file/Health01/" class="bg-white border border-slate-300 text-slate-700 hover:border-brand-600 hover:text-brand-700 font-semibold px-6 py-3 rounded-xl transition">
      Open Health01 (NHIRD claims)
    </a>
  </div>
</section>

<!-- Catalogue by category -->
{#each [...groups] as [category, list]}
  <section class="py-8">
    <div class="flex items-baseline justify-between mb-4 gap-3">
      <h2 class="text-2xl font-bold text-slate-900 flex items-center gap-3">
        <span class="pill pill-{category}">{category}</span>
        <span>{category === 'Health' ? '健康保險與醫療登錄'
              : category === 'Society' ? '社會調查'
              : category === 'Welfare' ? '社會福利與通報'
              : '主題式加值資料庫'}</span>
      </h2>
      <span class="text-sm text-slate-500">{list.length} files</span>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      {#each list as it}
        <a href="{base}/file/{it.code}/"
           class="group flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm
                  hover:shadow-md hover:border-brand-400 transition">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="mono text-sm font-bold text-brand-700">{it.code}</span>
                {#if it.code_short}<span class="mono text-xs text-slate-400">{it.code_short}</span>{/if}
              </div>
              <h3 class="font-bold text-slate-900 leading-snug group-hover:text-brand-700">
                {it.name_zh}
              </h3>
              {#if it.name_en}
                <p class="text-xs text-slate-500 mt-1 line-clamp-2">{it.name_en}</p>
              {/if}
            </div>
            {#if it.field_count}
              <div class="text-right shrink-0">
                <div class="text-2xl font-extrabold text-brand-700 leading-none">{it.field_count}</div>
                <div class="text-[10px] uppercase tracking-wide text-slate-500">fields</div>
              </div>
            {/if}
          </div>
          <div class="mt-3 flex flex-wrap gap-1.5 items-center text-xs">
            {#if it.frequency}
              <span class="text-slate-500">每{it.frequency} ·</span>
            {/if}
            {#each it.versions as v}
              <span class="px-2 py-0.5 rounded text-[11px] font-medium
                           {v.file_type === 'zip'
                             ? 'bg-amber-50 text-amber-800 border border-amber-200'
                             : 'bg-brand-50 text-brand-700 border border-brand-100'}"
                    title={v.version_label}>{v.version_id}{v.file_type === 'zip' ? ' (zip)' : ''}</span>
            {/each}
          </div>
        </a>
      {/each}
    </div>
  </section>
{/each}
