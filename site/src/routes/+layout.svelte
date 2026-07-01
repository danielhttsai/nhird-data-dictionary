<script>
  import '../app.css';
  import { base } from '$app/paths';
  import { page } from '$app/state';
  let { children } = $props();

  // Main-site chrome so this app reads as part of danielhttsai.github.io.
  const SITE = 'https://danielhttsai.github.io';
  const mainNav = [
    { href: SITE + '/', label: 'Home' },
    { href: SITE + '/about', label: 'About' },
    { href: SITE + '/publications', label: 'Publications' },
    { href: SITE + '/writing', label: 'Writing' },
    { href: SITE + '/talks', label: 'Talks' },
    { href: SITE + '/tools', label: 'RWE Tools', active: true },
    { href: SITE + '/networks', label: 'Networks' }
  ];
  const navItems = [
    { href: '/', label: 'Catalogue' },
    { href: '/search', label: 'Search' },
    { href: '/codebook', label: 'Codebooks' }
  ];
  function isActive(href) {
    const p = page.url.pathname.replace(/\/$/, '') || '/';
    const h = (base + href).replace(/\/$/, '') || '/';
    return p === h;
  }
</script>

<a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 bg-brand-600 text-white px-3 py-2 rounded">Skip to content</a>

<div class="page-tint text-slate-800 antialiased">
  <!-- Main-site header (mirrors danielhttsai.github.io) -->
  <header class="sticky top-0 z-40 bg-white/85 backdrop-blur border-b border-slate-200">
    <nav class="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
      <a href="{SITE}/" class="flex items-center gap-2 font-extrabold text-slate-900 tracking-tight">
        <span class="inline-grid place-items-center w-8 h-8 rounded-lg bg-brand-600 text-white text-sm">DT</span>
        <span>Daniel Tsai</span>
      </a>
      <div class="hidden md:flex items-center gap-1 lg:gap-2 text-sm font-semibold">
        {#each mainNav as item}
          <a href={item.href}
             class="px-3 py-2 rounded-lg transition
                    {item.active
                      ? 'text-brand-700 bg-brand-50'
                      : 'text-slate-600 hover:text-brand-700 hover:bg-slate-50'}">
            {item.label}
          </a>
        {/each}
      </div>
      <a href="{SITE}/tools" class="md:hidden text-sm font-semibold text-brand-700 hover:underline">← RWE Tools</a>
    </nav>
  </header>

  <!-- Dictionary sub-nav -->
  <div class="border-b border-slate-200 bg-white/70">
    <nav class="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 min-h-12 py-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
      <a href="{base}/" class="flex items-center gap-2 text-sm font-bold text-slate-700">
        <span class="inline-grid place-items-center w-6 h-6 rounded bg-brand-100 text-brand-700 text-[10px] font-extrabold">DD</span>
        NHIRD / HWDC <span class="text-slate-400 font-normal hidden sm:inline">data dictionary</span>
      </a>
      <div class="flex items-center gap-1 text-sm font-semibold">
        {#each navItems as item}
          <a href="{base}{item.href}"
             class="px-2.5 py-1.5 rounded-lg transition
                    {isActive(item.href)
                      ? 'text-brand-700 bg-brand-50'
                      : 'text-slate-600 hover:text-brand-700 hover:bg-slate-50'}">
            {item.label}
          </a>
        {/each}
      </div>
    </nav>
  </div>

  <main id="main" class="min-h-[60vh]">
    <div class="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-8">
      {@render children?.()}
    </div>
  </main>

  <footer class="border-t border-slate-200 bg-slate-50 mt-12">
    <div class="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <p class="font-extrabold text-slate-900">NHIRD / HWDC data dictionary</p>
        <p class="text-sm text-slate-600 mt-1">
          Sourced from
          <a class="text-brand-700 hover:underline" target="_blank" rel="noreferrer"
             href="https://dep.mohw.gov.tw/DOS/lp-2503-113-xCat-DOS_dc002-1-20.html">MOHW Department of Statistics</a>.
          Field-level metadata only.
        </p>
      </div>
      <ul class="flex flex-wrap gap-x-5 gap-y-2 text-sm font-semibold">
        <li><a href="{base}/" class="text-brand-700 hover:underline">Catalogue</a></li>
        <li><a href="{base}/search" class="text-brand-700 hover:underline">Search</a></li>
        <li><a href="{base}/codebook" class="text-brand-700 hover:underline">Codebooks</a></li>
        <li><a href="https://github.com/danielhttsai/nhird-data-dictionary" target="_blank" rel="noreferrer" class="text-brand-700 hover:underline">GitHub</a></li>
      </ul>
    </div>
    <div class="border-t border-slate-200">
      <div class="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-4 text-xs text-slate-500">
        Built and maintained by <a class="hover:underline text-brand-700" target="_blank" rel="noreferrer" href="https://danielhttsai.github.io/">Daniel Tsai</a>.
      </div>
    </div>
  </footer>
</div>
