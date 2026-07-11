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

  // Concise card summary instead of dumping every internal version id.
  function summarize(it) {
    const ev = it.versions.filter(v => v.has_extract && (v.field_count || 0) > 0);
    const years = ev
      .map(v => (v.version_id.match(/AD(\d{4})/) || [])[1])
      .filter(Boolean).map(Number);
    const hasXls = it.versions.some(v => v.file_type === 'xls');
    const parts = [];
    if (it.frequency) parts.push(`每${it.frequency}`);
    if (years.length) {
      const lo = Math.min(...years), hi = Math.max(...years);
      parts.push(lo === hi ? `${lo}` : `${lo}–${hi}`);
    }
    const n = ev.length || it.versions.filter(v => v.has_extract).length;
    parts.push(n === 1 ? '1 version' : `${n} versions`);
    if (hasXls) parts.push('codebooks');
    return parts.join(' · ');
  }
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
    An <strong class="text-brand-700">independent</strong>, bilingual reference to every field in
    every public MOHW database manual — codebooks, availability, and version diffs.
  </p>
  <p class="mt-3 text-sm text-slate-500 max-w-3xl">
    獨立整理的參考工具,非官方產品 · Not affiliated with or endorsed by MOHW / HWDC.
  </p>
  <div class="mt-6 flex flex-wrap gap-3">
    <a href="{base}/search" class="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-6 py-3 rounded-xl transition shadow-sm">
      Hunt down any variable →
    </a>
    <a href="{base}/file/Health01/" class="bg-white border border-slate-300 text-slate-700 hover:border-brand-600 hover:text-brand-700 font-semibold px-6 py-3 rounded-xl transition">
      Start where everyone starts — NHIRD claims →
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
              : category === 'TWCR' ? '台灣癌症登記詳細規格 (TWCR)'
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
          <div class="mt-3 flex items-center justify-between gap-2 text-xs">
            <span class="text-slate-500">{summarize(it)}</span>
            <span class="text-brand-700 font-semibold opacity-0 group-hover:opacity-100 transition">view →</span>
          </div>
        </a>
      {/each}
    </div>
  </section>
{/each}
