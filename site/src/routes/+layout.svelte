<script>
  import '../app.css';
  import { base } from '$app/paths';
  let { children } = $props();
</script>

<header class="border-b border-slate-200 bg-white">
  <div class="mx-auto max-w-7xl px-4 py-4 flex items-center gap-6">
    <a href="{base}/" class="font-bold text-lg text-slate-900">
      NHIRD <span class="text-slate-500 font-normal">/ HWDC data dictionary</span>
    </a>
    <nav class="flex gap-4 text-sm text-slate-700">
      <a href="{base}/" class="hover:text-blue-700">Catalogue</a>
      <a href="{base}/search" class="hover:text-blue-700">Search</a>
      <a href="{base}/codebook" class="hover:text-blue-700">Codebooks</a>
    </nav>
    <div class="flex-1"></div>
    <a href="https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-1-20.html"
       target="_blank" rel="noreferrer"
       class="text-xs text-slate-500 hover:text-slate-700">
      Source: MOHW
    </a>
  </div>
</header>

<main class="mx-auto max-w-7xl px-4 py-6">
  {@render children?.()}
</main>

<footer class="border-t border-slate-200 mt-12 py-6 text-center text-xs text-slate-500">
  Sourced from MOHW Department of Statistics. Field-level metadata only — no individual data.
  <br />
  Generated from official PDFs at <a class="underline" target="_blank"
    href="https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-1-20.html"
    rel="noreferrer">dep.mohw.gov.tw/DOS</a>.
</footer>
