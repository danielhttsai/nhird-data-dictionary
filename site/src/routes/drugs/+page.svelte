<script>
  import { base } from '$app/paths';
  import { onMount } from 'svelte';

  // Payload columns (see scripts/build_drug_codes.py):
  // 0 code · 1 name · 2 ingredient# · 3 strength# · 4 form# · 5 mfr# · 6 cls# · 7 atc# · 8 compound · 9 first · 10 last_priced
  let db = $state(null);
  let failed = $state(false);
  let q = $state('');
  let onlyPriced = $state(false);
  let open = $state(null);        // code of the expanded row
  let copied = $state('');
  let hay = [];                   // lower-cased search text per row
  const SHOW = 200;

  onMount(async () => {
    try {
      const r = await fetch(`${base}/data/drug-codes.json`);
      if (!r.ok) throw new Error(String(r.status));
      const d = await r.json();
      hay = d.rows.map(r =>
        `${r[0]} ${r[1]} ${d.ingredient[r[2]]} ${d.atc[r[7]]} ${d.mfr[r[5]]} ${d.form[r[4]]}`.toLowerCase());
      db = d;
      const p = new URLSearchParams(location.search).get('q');
      if (p) q = p;
    } catch (e) {
      failed = true;
    }
  });

  // An ATC-looking query (A10, A10BA, A10BA02) matches the ATC code by prefix,
  // so "C10" lists lipid-modifying agents and not every code containing c10.
  // It also matches an ingredient that has it as a whole word ("VITAMIN B12").
  const ATC_RE = /^[a-z]\d{2}([a-z]{1,2}(\d{2})?)?$/i;

  const matches = $derived.by(() => {
    if (!db) return [];
    const terms = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length || terms.join('').length < 2) return [];
    const atcTerms = terms.filter(t => ATC_RE.test(t)).map(t => t.toUpperCase());
    const atcWord = atcTerms.map(t => new RegExp(`(^|[^A-Z0-9])${t}([^A-Z0-9]|$)`));
    const textTerms = terms.filter(t => !ATC_RE.test(t));
    const out = [];
    const rows = db.rows;
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      if (onlyPriced && r[10] !== 'open') continue;
      if (atcTerms.length && !atcTerms.every((t, k) => db.atc[r[7]].startsWith(t) || atcWord[k].test(db.ingredient[r[2]]))) continue;
      const h = hay[i];
      if (textTerms.length && !textTerms.every(t => h.includes(t))) continue;
      out.push(r);
    }
    // Codes that are still priced first; the payload is already in code order.
    out.sort((a, b) => (b[10] === 'open') - (a[10] === 'open'));
    return out;
  });

  const summary = $derived.by(() => {
    const ing = new Set(), atc = new Set();
    for (const r of matches) { if (db.ingredient[r[2]]) ing.add(r[2]); atc.add(r[7]); }
    return { ing: ing.size, atc: atc.size };
  });

  function atcName(code) {
    if (!db) return '';
    const l2 = db.atc_names[code.slice(0, 3)], l1 = db.atc_names[code.slice(0, 1)];
    return [l1?.[0], l2?.[0]].filter(Boolean).join(' › ');
  }
  function status(r) {
    if (r[10] === 'open') return { label: 'Priced', zh: '給付中', cls: 'bg-emerald-50 text-emerald-800' };
    if (r[10] === '') return { label: 'No price on record', zh: '無支付價', cls: 'bg-slate-100 text-slate-600' };
    return { label: `Priced until ${r[10]}`, zh: '已停止給付', cls: 'bg-amber-50 text-amber-800' };
  }

  async function copyCodes(fmt) {
    const codes = matches.map(r => r[0]);
    const text = fmt === 'sas' ? codes.map(c => `'${c}'`).join(', ') : codes.join('\n');
    try {
      await navigator.clipboard.writeText(text);
      copied = `${codes.length.toLocaleString()} codes copied`;
    } catch (e) {
      copied = 'Copy was blocked by the browser; use Download CSV instead';
    }
    setTimeout(() => (copied = ''), 3500);
  }

  function downloadCsv() {
    const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const head = ['nhi_drug_code', 'product_name', 'ingredient', 'strength', 'dosage_form', 'manufacturer',
                  'classification', 'atc_code', 'compound', 'first_listed', 'priced_until'];
    const lines = [head.join(',')];
    for (const r of matches) {
      lines.push([r[0], r[1], db.ingredient[r[2]], db.strength[r[3]], db.form[r[4]], db.mfr[r[5]], db.cls[r[6]],
                  db.atc[r[7]], r[8] ? 'compound' : 'single', r[9], r[10] === 'open' ? 'current' : r[10]].map(esc).join(','));
    }
    const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `nhi-drug-codes_${q.trim().replace(/[^\w-]+/g, '_').slice(0, 40) || 'all'}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  const examples = ['metformin', 'A10BA02', 'C10AA', 'empagliflozin 10', 'BC25352100'];
  const FIELDS = [
    { file: 'Health04', field: 'ORDER_CODE', note: 'Ambulatory care orders 門急診醫令 (named DRUG_NO before 2025-06-24)' },
    { file: 'Health05', field: 'ORDER_CODE', note: 'Inpatient orders 住院醫令' },
    { file: 'Health06', field: 'ORDER_CODE', note: 'Pharmacy orders 藥局醫令 (named DRUG_NO before 2025-06-24)' },
    { file: 'Health17', field: 'DRUG_NO', note: 'Drug master file 藥品主檔' }
  ];
</script>

<svelte:head>
  <title>Drug code lookup — NHIRD data dictionary</title>
  <meta name="description" content="Look up Taiwan NHI drug codes and map between drug code, ingredient and ATC. 45,000 codes from the public NHI drug item query." />
</svelte:head>

<div class="space-y-6">
  <header>
    <h1 class="text-3xl font-extrabold text-slate-900">Drug code lookup <span class="text-lg font-semibold text-slate-400">健保藥品代碼查詢</span></h1>
    <p class="text-slate-600 mt-1 max-w-3xl">
      Map between the 10-character NHI drug code, the ingredient, and the ATC code. Type a code, a product or
      ingredient name, or an ATC code; an ATC code matches by prefix, so <span class="mono">C10AA</span> lists every statin.
    </p>
  </header>

  <input type="search" bind:value={q} placeholder="e.g. metformin, A10BA02, BC25352100, 永信"
         aria-label="Search drug codes"
         class="w-full px-4 py-3 border border-slate-300 rounded-xl text-base shadow-sm
                focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-brand-400" />

  <div class="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
    <label class="inline-flex items-center gap-2 text-slate-700">
      <input type="checkbox" bind:checked={onlyPriced} class="rounded border-slate-300" />
      Only codes with a current price <span class="text-slate-400">僅顯示給付中</span>
    </label>
    <span class="text-slate-400">Try:</span>
    {#each examples as ex}
      <button type="button" class="mono text-brand-700 hover:underline" onclick={() => (q = ex)}>{ex}</button>
    {/each}
  </div>

  {#if failed}
    <p class="text-red-700 text-sm">The drug code list could not be loaded. Reload the page to try again.</p>
  {:else if !db}
    <p class="text-slate-500 text-sm">Loading 45,000 drug codes…</p>
  {:else if q.trim().length < 2}
    <p class="text-slate-500 text-sm">
      {db.meta.n_codes.toLocaleString()} drug codes, {db.meta.n_priced.toLocaleString()} with a current price.
      Type at least 2 characters to search.
    </p>
  {:else}
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-slate-600 text-sm">
        <strong class="text-slate-900">{matches.length.toLocaleString()}</strong> code{matches.length === 1 ? '' : 's'}
        · {summary.ing.toLocaleString()} ingredient{summary.ing === 1 ? '' : 's'}
        · {summary.atc.toLocaleString()} ATC code{summary.atc === 1 ? '' : 's'}
        {#if matches.length > SHOW}<span class="text-slate-400">(showing the first {SHOW}; copy and download include all)</span>{/if}
      </p>
      {#if matches.length}
        <div class="flex flex-wrap items-center gap-2 text-sm font-semibold">
          {#if copied}<span class="text-emerald-700 font-normal" role="status">{copied}</span>{/if}
          <button type="button" onclick={() => copyCodes('lines')} class="px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:border-brand-600 hover:text-brand-700">Copy codes</button>
          <button type="button" onclick={() => copyCodes('sas')} class="px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:border-brand-600 hover:text-brand-700" title="Quoted and comma-separated, ready for an IN (...) list">Copy as 'A','B',…</button>
          <button type="button" onclick={downloadCsv} class="px-3 py-1.5 rounded-lg bg-brand-600 text-white hover:bg-brand-700">Download CSV</button>
        </div>
      {/if}
    </div>

    {#if matches.length}
      <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="overflow-x-auto">
          <table class="tbl w-full text-left">
            <thead>
              <tr><th>NHI code</th><th>Product</th><th>Ingredient · strength</th><th>Form</th><th>ATC</th><th>Status</th></tr>
            </thead>
            <tbody>
              {#each matches.slice(0, SHOW) as r (r[0])}
                {@const st = status(r)}
                {@const atc = db.atc[r[7]]}
                <tr class="cursor-pointer" onclick={() => (open = open === r[0] ? null : r[0])}>
                  <td class="mono font-semibold text-brand-700 whitespace-nowrap">
                    <button type="button" class="hover:underline" aria-expanded={open === r[0]}>{r[0]}</button>
                  </td>
                  <td class="text-slate-800">{r[1]}</td>
                  <td>
                    {#if db.ingredient[r[2]]}
                      <div class="text-slate-800">{db.ingredient[r[2]]}</div>
                    {:else}
                      <div class="text-slate-400 italic">not given by NHI 健保未列成分</div>
                    {/if}
                    <div class="text-xs text-slate-500">{db.strength[r[3]]}{r[8] ? ' · compound 複方' : ''}</div>
                  </td>
                  <td class="text-xs text-slate-600 whitespace-nowrap">{db.form[r[4]]}</td>
                  <td class="mono whitespace-nowrap">{atc}</td>
                  <td><span class="inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap {st.cls}">{st.label}</span></td>
                </tr>
                {#if open === r[0]}
                  <tr class="bg-slate-50">
                    <td colspan="6">
                      <div class="grid gap-4 md:grid-cols-2 py-2 text-sm">
                        <dl class="space-y-1.5">
                          <div><dt class="inline text-slate-500">Manufacturer 藥商：</dt><dd class="inline text-slate-800">{db.mfr[r[5]] || '—'}</dd></div>
                          <div><dt class="inline text-slate-500">Classification 分類：</dt><dd class="inline text-slate-800">{db.cls[r[6]] || '—'}</dd></div>
                          <div><dt class="inline text-slate-500">First listed 首次收載：</dt><dd class="inline text-slate-800">{r[9] || '—'}</dd></div>
                          <div><dt class="inline text-slate-500">Status 狀態：</dt><dd class="inline text-slate-800">{st.label} · {st.zh}</dd></div>
                          <div><dt class="inline text-slate-500">ATC：</dt><dd class="inline text-slate-800"><span class="mono">{atc}</span>{atcName(atc) ? ` · ${atcName(atc)}` : ''}</dd></div>
                        </dl>
                        <div class="space-y-1.5">
                          <p class="text-slate-500">Map onwards 延伸對照</p>
                          <ul class="space-y-1">
                            {#if db.ingredient[r[2]]}
                              <li><button type="button" class="text-brand-700 font-semibold hover:underline" onclick={(e) => { e.stopPropagation(); q = db.ingredient[r[2]]; open = null; }}>All codes with this ingredient →</button></li>
                            {/if}
                            <li><button type="button" class="text-brand-700 font-semibold hover:underline" onclick={(e) => { e.stopPropagation(); q = atc; open = null; }}>All codes under ATC {atc} →</button></li>
                            {#if atc.length === 7}
                              <li><a class="text-brand-700 font-semibold hover:underline" target="_blank" rel="noreferrer" onclick={(e) => e.stopPropagation()}
                                     href="https://atcddd.fhi.no/atc_ddd_index/?code={atc}">Defined daily dose (DDD) on the WHO ATC/DDD index ↗</a></li>
                            {/if}
                            <li><a class="text-brand-700 font-semibold hover:underline" target="_blank" rel="noreferrer" onclick={(e) => e.stopPropagation()}
                                   href="https://info.nhi.gov.tw/INAE3000/INAE3000S01">Current price on the official NHI query 健保用藥品項查詢 ↗</a></li>
                          </ul>
                        </div>
                      </div>
                    </td>
                  </tr>
                {/if}
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {:else}
      <p class="text-slate-500 text-sm">No drug code matches. Check the spelling, or search by the first letters of the ATC code.</p>
    {/if}
  {/if}

  <section class="grid gap-4 md:grid-cols-2 pt-2">
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 class="font-bold text-slate-900">Where these codes appear in NHIRD <span class="font-normal text-slate-400 text-sm">代碼出現在哪些欄位</span></h2>
      <ul class="mt-3 space-y-2 text-sm">
        {#each FIELDS as f}
          <li>
            <a class="mono font-semibold text-brand-700 hover:underline" href="{base}/file/{f.file}/field/{f.field}/">{f.file} · {f.field}</a>
            <span class="text-slate-600"> — {f.note}</span>
          </li>
        {/each}
        <li>
          <a class="mono font-semibold text-brand-700 hover:underline" href="{base}/file/Health17/field/DRUG_ATC7_CODE/">Health17 · DRUG_ATC7_CODE</a>
          <span class="text-slate-600"> — the ATC code as stored in the drug master file</span>
        </li>
      </ul>
      <p class="mt-3 text-xs text-slate-500">Order fields also carry procedure and device codes; only drug codes are listed here.</p>
    </div>
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 class="font-bold text-slate-900">Source and limits <span class="font-normal text-slate-400 text-sm">資料來源與限制</span></h2>
      <ul class="mt-3 space-y-2 text-sm text-slate-700 list-disc pl-5">
        <li>
          Compiled from the public
          <a class="text-brand-700 hover:underline" target="_blank" rel="noreferrer" href="https://info.nhi.gov.tw/INAE3000/INAE3000S01">NHI drug item query 健保用藥品項查詢</a>{#if db}, snapshot of {db.meta.snapshot}{/if}.
          Codes added after that date are missing.
        </li>
        <li>
          Ingredient names follow NHI's group label, tidied to one spelling per ingredient: upper case, Chinese qualifiers
          put into English, and spacing made regular. Compound products carry their components and doses in the name.
          {#if db?.meta.n_no_ingredient}{db.meta.n_no_ingredient.toLocaleString()} old compound products have no ingredient label at NHI; they still map to an ATC code.{/if}
        </li>
        <li>The ATC code is the one NHI records for the item. Some are shorter than 7 characters, and a few are NHI-specific and not in the WHO index.</li>
        <li>Status is read from the price history: an item counts as priced when its current price is above zero. Use the official query before relying on it.</li>
        <li>Prices and DDD values are not stored here. Follow the links on each row to the official sources.</li>
      </ul>
    </div>
  </section>
</div>
