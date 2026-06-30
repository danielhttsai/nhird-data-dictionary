<script>
  import { page } from '$app/state';
  import { base } from '$app/paths';
</script>

<svelte:head><title>{page.status} — NHIRD data dictionary</title></svelte:head>

<div class="py-16 max-w-2xl mx-auto text-center">
  <p class="text-7xl font-extrabold text-brand-700 mb-3">{page.status}</p>
  <h1 class="text-xl font-bold text-slate-900 mb-3">
    {page.status === 404 ? 'Page not found' : 'Something went wrong'}
  </h1>
  <p class="text-slate-600 mb-6">
    {page.error?.message || 'The page you asked for is not on this site.'}
  </p>
  <a href="{base}/" class="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-6 py-3 rounded-xl transition">
    Back to catalogue
  </a>
</div>
