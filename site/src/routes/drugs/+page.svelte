<script>
  import { base } from '$app/paths';
  import { onMount } from 'svelte';

  // Payload columns (see scripts/build_drug_codes.py):
  // 0 code · 1 name · 2 ingredient# · 3 strength# · 4 form# · 5 mfr# · 6 cls# · 7 atc# · 8 compound · 9 first · 10 last_priced
  // 11 set# (what the product contains) · 12 flags (1 short label, 2 compound with unnamed parts, 4 ATC from the licence)
  // 13 Chinese product name · 14 current NHI price (0 when not priced)
  let db = $state(null);
  let failed = $state(false);
  let q = $state('');
  let onlyPriced = $state(false);
  let mix = $state('all');        // all | single | compound
  let open = $state(null);        // code of the expanded row
  let copied = $state('');
  let loose = $state('');         // the query the reader asked to match as plain text instead of as a component
  let prices = $state(null);      // code -> price periods; loaded when a row is first opened
  let pricesFailed = $state(false);
  let hay = [];                   // lower-cased search text per row
  let compIndex = new Map();      // component name or any of its other names -> index
  let compCount = [];             // codes per component
  const SHOW = 200;

  // What a product contains is worked out when the data is built: from its TFDA
  // licence formula where there is one, and from the NHI label otherwise.
  //   yes   components it contains
  //   maybe components the label allows but nothing confirms
  //   also  other names of the same substance, kept so a search still finds it
  const parts = r => { const [yes, maybe, also] = db.sets[r[11]]; return { yes, maybe, also }; };
  const labelOf = (d, r) => (r[12] & 1 ? d.single_label[r[2]] : d.ingredient[r[2]]) ?? '';
  const namesOf = (d, list) => list.map(c => d.component[c]);
  // One ingredient, nothing else possible, and no unnamed parts.
  const isSingle = r => { const p = parts(r); return p.yes.length === 1 && !p.maybe.length && !(r[12] & 2); };

  onMount(async () => {
    try {
      const r = await fetch(`${base}/data/drug-codes.json`);
      if (!r.ok) throw new Error(String(r.status));
      const d = await r.json();
      compIndex = new Map([...d.component.map((c, i) => [c, i]), ...Object.entries(d.alias)]);
      hay = d.rows.map(r =>
        `${r[0]} ${r[1]} ${r[13]} ${labelOf(d, r)} ${namesOf(d, d.sets[r[11]].flat()).join(' ')} ${d.strength[r[3]]} ${d.atc[r[7]]} ${d.mfr[r[5]]} ${d.form[r[4]]}`.toLowerCase());
      compCount = new Array(d.component.length).fill(0);
      for (const r of d.rows) for (const c of d.sets[r[11]][0]) compCount[c]++;
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

  // The query is read for the reader; nobody has to know a syntax.
  //   - A run of words that is exactly a component name ("metformin", "clavulanic acid",
  //     "losartan potassium", "paracetamol") means products that contain that component, alone
  //     or in a compound. Salt forms and synonyms count as the same component. So "estradiol"
  //     does not return ETHINYLESTRADIOL, and "metformin" does not return a product that only
  //     shares a price group with a metformin combination.
  //   - An ATC-looking word matches the ATC code by prefix.
  //   - Every other word (a code, a strength, a brand, a manufacturer, Chinese) matches as text.
  // The page says how it read the query and offers the wider text match with one click.
  // A name in double quotes is still taken as a component name, for a name the reader wants exact.
  const reading = $derived.by(() => {
    const quoted = [];
    const rest = q.replace(/["“”]([^"“”]*)["“”]/g, (_, name) => {
      const n = name.trim().toUpperCase().replace(/\s+/g, ' ');
      if (n) quoted.push(n);
      return ' ';
    }).replace(/["“”]/g, ' ');
    let words = rest.trim().split(/\s+/).filter(Boolean);
    const comps = [], named = [], terms = [];
    if (db && loose !== q) {
      // "amoxicillin/clavulanic acid", "a + b", "a, b": separators between names are not part of them
      words = words.flatMap(w => (compIndex.has(w.toUpperCase()) ? [w] : w.split(/[,;+&/]+/).filter(Boolean)));
      let i = 0;
      while (i < words.length) {
        let n = Math.min(words.length - i, 12), name = '';
        for (; n >= 1; n--) {
          name = words.slice(i, i + n).join(' ').toUpperCase();
          if (compIndex.has(name) && (n > 1 || (name.length >= 3 && !/^[\d.]+$/.test(name) && !ATC_RE.test(name)))) break;
        }
        if (n) {
          const c = compIndex.get(name);
          if (!comps.includes(c)) { comps.push(c); named.push(name); }
          i += n;
        } else terms.push(words[i++].toLowerCase());
      }
    } else {
      for (const w of words) terms.push(w.toLowerCase());
    }
    const link = new Set(['and', 'with', '&']);  // "amoxicillin and clavulanic acid"
    return { quoted, comps, named, terms: comps.length ? terms.filter(t => !link.has(t)) : terms };
  });
  const unknown = $derived(db ? reading.quoted.filter(n => !compIndex.has(n)) : []);

  function search(want, terms) {
    const atcTerms = terms.filter(t => ATC_RE.test(t)).map(t => t.toUpperCase());
    const atcWord = atcTerms.map(t => new RegExp(`(^|[^A-Z0-9])${t}([^A-Z0-9]|$)`));
    const textTerms = terms.filter(t => !ATC_RE.test(t));
    const out = [];
    const rows = db.rows;
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      if (onlyPriced && r[10] !== 'open') continue;
      if (mix !== 'all' && isSingle(r) !== (mix === 'single')) continue;
      const p = parts(r);
      if (want.length && !want.every(c => p.yes.includes(c) || p.maybe.includes(c) || p.also.includes(c))) continue;
      if (atcTerms.length && !atcTerms.every((t, k) => db.atc[r[7]].startsWith(t) || atcWord[k].test(labelOf(db, r)))) continue;
      const h = hay[i];
      if (textTerms.length && !textTerms.every(t => h.includes(t))) continue;
      out.push(r);
    }
    // Codes that are still priced first; the payload is already in code order.
    out.sort((a, b) => (b[10] === 'open') - (a[10] === 'open'));
    return out;
  }

  const active = $derived(reading.quoted.length > 0 || reading.comps.length > 0 || reading.terms.join('').length >= 2);
  const matches = $derived.by(() => {
    if (!db || !active || unknown.length) return [];
    return search([...reading.quoted.map(n => compIndex.get(n)), ...reading.comps], reading.terms);
  });

  // How the query was read, and what the other reading would add.
  const readAs = $derived.by(() => {
    if (!db || !active || unknown.length) return null;
    const comps = [...reading.quoted.map(n => compIndex.get(n)), ...reading.comps];
    const atc = reading.terms.filter(t => ATC_RE.test(t)).map(t => t.toUpperCase());
    const text = reading.terms.filter(t => !ATC_RE.test(t));
    let wider = 0, related = [];
    if (reading.comps.length) {
      // the same words as plain text: codes that only mention the name somewhere
      const got = new Set(matches.map(r => r[0]));
      const words = q.replace(/["“”]/g, ' ').trim().toLowerCase().split(/\s+/).filter(Boolean);
      wider = search(reading.quoted.map(n => compIndex.get(n)), words).filter(r => !got.has(r[0])).length;
      if (reading.comps.length === 1 && !reading.quoted.length) {
        // other components whose name has this one as a whole word: INSULIN -> INSULIN GLARGINE, ...
        const word = new RegExp(`(^|[^A-Z0-9])${reading.named[0].replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^A-Z0-9]|$)`);
        related = db.component.map((name, i) => ({ name, i, n: compCount[i] }))
          .filter(c => c.i !== reading.comps[0] && c.n && word.test(c.name))
          .sort((a, b) => b.n - a.n).slice(0, 8);
      }
    }
    return { comps, atc, text, wider, related, loose: loose === q && q.trim() !== '' };
  });

  const summary = $derived.by(() => {
    const ing = new Set(), atc = new Set();
    let single = 0;
    for (const r of matches) {
      const label = labelOf(db, r);
      if (label) ing.add(label);
      atc.add(r[7]);
      if (isSingle(r)) single++;
    }
    return { ing: ing.size, atc: atc.size, single, compound: matches.length - single };
  });

  function atcName(code) {
    if (!db) return '';
    const l1 = db.atc_names[code.slice(0, 1)], l2 = db.atc_names[code.slice(0, 3)];
    const own = code.length > 3 ? db.atc_names[code] : null;
    return [l1?.[0], l2?.[0], own?.[0]].filter(Boolean).join(' › ');
  }

  // Price periods are a separate file, fetched the first time a row is opened.
  let pricesLoading = false;
  async function toggle(code) {
    open = open === code ? null : code;
    if (open && !prices && !pricesLoading) {
      pricesLoading = true;
      try {
        const r = await fetch(`${base}/data/drug-prices.json`);
        if (!r.ok) throw new Error(String(r.status));
        prices = await r.json();
      } catch (e) {
        pricesFailed = true;
      }
      pricesLoading = false;
    }
  }
  const dayText = n => (n ? `${String(n).slice(0, 4)}-${String(n).slice(4, 6)}-${String(n).slice(6, 8)}` : '');
  function periodsOf(code) {
    const p = prices?.[code] ?? [], out = [];
    for (let i = 0; i < p.length; i += 3) out.push({ from: dayText(p[i]), to: dayText(p[i + 1]), price: p[i + 2] });
    return out.reverse();  // newest first
  }
  const money = v => v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  // Defined daily doses exactly as the WHO index shows them: dose, unit, route, note.
  const dddOf = atc => db?.ddd?.[atc] ?? [];
  const dddText = d => `${d[0]} ${d[1]}${d[2] ? ` ${d[2]}` : ''}${d[3] ? ` (${d[3]})` : ''}`;
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
    const head = ['nhi_drug_code', 'product_name', 'product_name_zh', 'ingredient', 'components', 'n_components',
                  'possible_components', 'other_names', 'strength', 'dosage_form', 'manufacturer', 'classification',
                  'atc_code', 'atc_name', 'atc_source', 'single_or_compound', 'nhi_mark', 'first_listed', 'priced_until',
                  'current_price_ntd', 'who_ddd', 'nhi_group_label', 'data_checked'];
    const names = list => namesOf(db, list).join('; ');
    const lines = [head.join(',')];
    for (const r of matches) {
      const p = parts(r);
      const atc = db.atc[r[7]];
      lines.push([r[0], r[1], r[13], labelOf(db, r), names(p.yes), p.yes.length, names(p.maybe), names(p.also),
                  db.strength[r[3]], db.form[r[4]], db.mfr[r[5]], db.cls[r[6]], atc,
                  atc.length > 3 ? db.atc_names[atc]?.[0] ?? '' : '', atc ? (r[12] & 4 ? 'TFDA licence' : 'NHI') : '',
                  isSingle(r) ? 'single' : 'compound', r[8] ? 'compound' : 'single', r[9],
                  r[10] === 'open' ? 'current' : r[10], r[14] || '', dddOf(atc).map(dddText).join('; '), db.ingredient[r[2]], db.meta.checked].map(esc).join(','));
    }
    const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `nhi-drug-codes_${q.trim().replace(/[^\w-]+/g, '_').slice(0, 40) || 'all'}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  const FIELDS = [
    { file: 'Health04', field: 'ORDER_CODE', note: 'Ambulatory care orders 門急診醫令 (named DRUG_NO before 2025-06-24)' },
    { file: 'Health05', field: 'ORDER_CODE', note: 'Inpatient orders 住院醫令' },
    { file: 'Health06', field: 'ORDER_CODE', note: 'Pharmacy orders 藥局醫令 (named DRUG_NO before 2025-06-24)' },
    { file: 'Health17', field: 'DRUG_NO', note: 'Drug master file 藥品主檔' }
  ];
</script>

<svelte:head>
  <title>Drug code lookup — NHIRD data dictionary</title>
  <meta name="description" content="Look up Taiwan NHI drug codes and map between drug code, ingredient, component and ATC. 45,000 codes from the public NHI drug item query and TFDA licence data, refreshed every week." />
</svelte:head>

<div class="space-y-6">
  <header>
    <h1 class="text-3xl font-extrabold text-slate-900">Drug code lookup <span class="text-lg font-semibold text-slate-400">健保藥品代碼查詢</span></h1>
    <p class="text-slate-600 mt-1 max-w-3xl">
      Map between the 10-character NHI drug code, the ingredient, and the ATC code. Type anything: a code, an
      ingredient, a brand in English or Chinese, or an ATC code. The page works out what you typed. An ingredient
      name finds every product that contains it, alone or in a compound, whatever salt or synonym the product uses;
      an ATC code matches by prefix, so <span class="mono">C10AA</span> lists every statin.
    </p>
  </header>

  <input type="search" bind:value={q} placeholder="e.g. metformin, A10BA02, BC25352100, 脈優, 永信"
         aria-label="Search drug codes"
         class="w-full px-4 py-3 border border-slate-300 rounded-xl text-base shadow-sm
                focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-brand-400" />

  <div class="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
    <label class="inline-flex items-center gap-2 text-slate-700">
      <input type="checkbox" bind:checked={onlyPriced} class="rounded border-slate-300" />
      Only codes with a current price <span class="text-slate-400">僅顯示給付中</span>
    </label>
    <label class="inline-flex items-center gap-2 text-slate-700">
      <span class="sr-only">Single or compound</span>
      <select bind:value={mix} class="rounded-lg border border-slate-300 bg-white py-1 pl-2 pr-7 text-sm">
        <option value="all">Single and compound 單複方皆顯示</option>
        <option value="single">Single ingredient only 僅單方</option>
        <option value="compound">Compound only 僅複方</option>
      </select>
    </label>
  </div>

  {#if failed}
    <p class="text-red-700 text-sm">The drug code list could not be loaded. Reload the page to try again.</p>
  {:else if !db}
    <p class="text-slate-500 text-sm">Loading 45,000 drug codes…</p>
  {:else if unknown.length}
    <p class="text-slate-600 text-sm">
      No component is named exactly <span class="mono">{unknown.join(', ')}</span>.
      <button type="button" class="text-brand-700 font-semibold hover:underline" onclick={() => (q = q.replace(/["“”]/g, ''))}>Search for it as text →</button>
    </p>
  {:else if !active}
    <p class="text-slate-500 text-sm">
      {db.meta.n_codes.toLocaleString()} drug codes, {db.meta.n_priced.toLocaleString()} with a current price.
      Checked against the official sources on {db.meta.checked}. Type at least 2 characters to search.
    </p>
  {:else}
    {#if readAs && (readAs.comps.length || readAs.atc.length || readAs.loose)}
      <div class="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 space-y-1.5">
        <p class="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span class="text-slate-500">Read as 判讀為</span>
          {#each readAs.comps as c}
            <span class="rounded-full bg-brand-50 border border-brand-200 px-2 py-0.5 text-xs font-semibold text-brand-700">contains 含成分 {db.component[c]}</span>
          {/each}
          {#each readAs.atc as t}
            <span class="rounded-full bg-slate-100 border border-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-700">ATC {t}{t.length < 7 ? '…' : ''}</span>
          {/each}
          {#each readAs.text as t}
            <span class="rounded-full bg-slate-100 border border-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-700">text 文字 “{t}”</span>
          {/each}
          {#if readAs.loose}
            <button type="button" class="text-brand-700 font-semibold hover:underline" onclick={() => (loose = '')}>Read ingredient names as components again →</button>
          {/if}
        </p>
        {#if readAs.comps.length && summary.single + summary.compound > 0}
          <p>
            <button type="button" class="hover:underline {mix === 'single' ? 'font-semibold text-brand-700' : ''}" onclick={() => (mix = mix === 'single' ? 'all' : 'single')}>{summary.single.toLocaleString()} as the only ingredient 單方</button>
            · <button type="button" class="hover:underline {mix === 'compound' ? 'font-semibold text-brand-700' : ''}" onclick={() => (mix = mix === 'compound' ? 'all' : 'compound')}>{summary.compound.toLocaleString()} in a compound 複方</button>
            {#if mix !== 'all'}· <button type="button" class="text-brand-700 hover:underline" onclick={() => (mix = 'all')}>show both</button>{/if}
          </p>
        {/if}
        {#if readAs.related.length}
          <p class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span class="text-slate-500">Different substances with a similar name 名稱相近的其他成分</span>
            {#each readAs.related as c}
              <button type="button" class="rounded-full border border-slate-300 bg-white px-2 py-0.5 text-xs text-slate-700 hover:border-brand-600 hover:text-brand-700"
                      onclick={() => (q = c.name.toLowerCase())}>{c.name} <span class="text-slate-400">{c.n.toLocaleString()}</span></button>
            {/each}
          </p>
        {/if}
        {#if readAs.wider}
          <p>
            {readAs.wider.toLocaleString()} more code{readAs.wider === 1 ? '' : 's'} mention the words in a name without containing the component.
            <button type="button" class="text-brand-700 font-semibold hover:underline" onclick={() => (loose = q)}>Show those too →</button>
          </p>
        {/if}
      </div>
    {/if}
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-slate-600 text-sm">
        <strong class="text-slate-900">{matches.length.toLocaleString()}</strong> code{matches.length === 1 ? '' : 's'}
        {#if summary.single && summary.compound && !readAs?.comps.length}({summary.single.toLocaleString()} single 單方, {summary.compound.toLocaleString()} compound 複方){/if}
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
              <tr><th>NHI code</th><th>Product</th><th>Ingredient · strength</th><th>Form</th><th>ATC</th><th class="text-right">Price 支付價</th><th>Status</th></tr>
            </thead>
            <tbody>
              {#each matches.slice(0, SHOW) as r (r[0])}
                {@const st = status(r)}
                {@const atc = db.atc[r[7]]}
                {@const p = parts(r)}
                {@const label = labelOf(db, r)}
                <tr class="cursor-pointer" onclick={() => toggle(r[0])}>
                  <td class="mono font-semibold text-brand-700 whitespace-nowrap">
                    <button type="button" class="hover:underline" aria-expanded={open === r[0]}>{r[0]}</button>
                  </td>
                  <td class="text-slate-800">{r[1]}{#if r[13]}<div class="text-xs text-slate-500">{r[13]}</div>{/if}</td>
                  <td>
                    {#if label}
                      <div class="text-slate-800">{label}</div>
                    {:else if p.yes.length}
                      <div class="text-slate-800">{namesOf(db, p.yes).join(' + ')}</div>
                      <div class="text-xs text-slate-400 italic">from the licence; no NHI label 依許可證處方，健保未列成分</div>
                    {:else}
                      <div class="text-slate-400 italic">not given by NHI 健保未列成分</div>
                    {/if}
                    <div class="text-xs text-slate-500">{db.strength[r[3]]}{isSingle(r) ? '' : `${db.strength[r[3]] ? ' · ' : ''}compound 複方${p.yes.length > 1 ? ` (${p.yes.length})` : ''}`}</div>
                  </td>
                  <td class="text-xs text-slate-600 whitespace-nowrap">{db.form[r[4]]}</td>
                  <td class="mono whitespace-nowrap">{atc}</td>
                  <td class="text-right whitespace-nowrap text-slate-800">{r[14] ? money(r[14]) : '—'}</td>
                  <td><span class="inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap {st.cls}">{st.label}</span></td>
                </tr>
                {#if open === r[0]}
                  <tr class="bg-slate-50">
                    <td colspan="7">
                      <div class="grid gap-4 md:grid-cols-2 py-2 text-sm">
                        <dl class="space-y-1.5">
                          <div><dt class="inline text-slate-500">Manufacturer 藥商：</dt><dd class="inline text-slate-800">{db.mfr[r[5]] || '—'}</dd></div>
                          <div><dt class="inline text-slate-500">Classification 分類：</dt><dd class="inline text-slate-800">{db.cls[r[6]] || '—'}</dd></div>
                          <div><dt class="inline text-slate-500">First listed 首次收載：</dt><dd class="inline text-slate-800">{r[9] || '—'}</dd></div>
                          <div><dt class="inline text-slate-500">Status 狀態：</dt><dd class="inline text-slate-800">{st.label} · {st.zh}</dd></div>
                          <div><dt class="inline text-slate-500">ATC：</dt><dd class="inline text-slate-800"><span class="mono">{atc || '—'}</span>{atcName(atc) ? ` · ${atcName(atc)}` : ''}{#if r[12] & 4}<span class="text-xs text-slate-500"> (from the TFDA licence; NHI gives no full code 依許可證補齊)</span>{/if}</dd></div>
                          {#if dddOf(atc).length}
                            <div><dt class="inline text-slate-500" title="Defined daily dose, with unit and route of administration (O oral, P parenteral, R rectal, N nasal, V vaginal, SL sublingual, TD transdermal, Inhal inhalation)">DDD (WHO)：</dt><dd class="inline text-slate-800">{dddOf(atc).map(dddText).join(' · ')}</dd></div>
                          {/if}
                          <div><dt class="inline text-slate-500">NHI price 支付價：</dt><dd class="inline text-slate-800">{r[14] ? `NT$ ${money(r[14])}` : 'none at present 目前無支付價'}</dd></div>
                          {#if p.yes.length || p.maybe.length}
                            <div>
                              <dt class="inline text-slate-500">Components 個別成分：</dt>
                              <dd class="inline">
                                {#each p.yes as c}
                                  <button type="button" title="Every code that contains {db.component[c]}"
                                          class="mr-1.5 mb-1 inline-block rounded-full border border-brand-200 bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700 hover:border-brand-600"
                                          onclick={(e) => { e.stopPropagation(); q = db.component[c].toLowerCase(); open = null; }}>{db.component[c]}</button>
                                {/each}
                                {#each p.maybe as c}
                                  <button type="button" title="The NHI label allows this component; this product may or may not contain it"
                                          class="mr-1.5 mb-1 inline-block rounded-full border border-dashed border-slate-400 bg-white px-2 py-0.5 text-xs font-semibold text-slate-600 hover:border-brand-600"
                                          onclick={(e) => { e.stopPropagation(); q = db.component[c].toLowerCase(); open = null; }}>{db.component[c]} ?</button>
                                {/each}
                                {#if p.maybe.length}<span class="text-xs text-slate-500">? = may contain 可能含有</span>{/if}
                                {#if r[12] & 2}<span class="text-xs text-slate-500">NHI marks this product as compound but names only this component, and no licence formula was found 健保註記為複方，僅列此成分</span>{/if}
                              </dd>
                            </div>
                          {/if}
                          {#if p.also.length}
                            <div><dt class="inline text-slate-500">Also named 另名：</dt><dd class="inline text-slate-800">{namesOf(db, p.also).join(', ')}</dd></div>
                          {/if}
                          {#if label !== db.ingredient[r[2]]}
                            <div><dt class="inline text-slate-500">NHI price group 核價分組：</dt><dd class="inline text-slate-800">{db.ingredient[r[2]]}. The group also covers combinations; this product has none of the added components.</dd></div>
                          {/if}
                        </dl>
                        <div class="space-y-3">
                          <div class="space-y-1.5">
                            <p class="text-slate-500">Map onwards 延伸對照</p>
                            <ul class="space-y-1">
                              {#each p.yes as c}
                                <li><button type="button" class="text-brand-700 font-semibold hover:underline" onclick={(e) => { e.stopPropagation(); q = db.component[c].toLowerCase(); open = null; }}>All codes that contain {db.component[c]} →</button></li>
                              {/each}
                              {#if atc}
                                <li><button type="button" class="text-brand-700 font-semibold hover:underline" onclick={(e) => { e.stopPropagation(); q = atc; open = null; }}>All codes under ATC {atc} →</button></li>
                              {/if}
                              {#if atc.length === 7}
                                <li><a class="text-brand-700 font-semibold hover:underline" target="_blank" rel="noreferrer" onclick={(e) => e.stopPropagation()}
                                       href="https://atcddd.fhi.no/atc_ddd_index/?code={atc}">This code on the WHO ATC/DDD index ↗</a></li>
                              {/if}
                              <li><a class="text-brand-700 font-semibold hover:underline" target="_blank" rel="noreferrer" onclick={(e) => e.stopPropagation()}
                                     href="https://info.nhi.gov.tw/INAE3000/INAE3000S01">The official NHI query 健保用藥品項查詢 ↗</a></li>
                            </ul>
                          </div>
                          <div>
                            <p class="text-slate-500">NHI price history 歷次支付價 <span class="text-xs">(NT$)</span></p>
                            {#if prices}
                              <div class="mt-1 max-h-44 overflow-y-auto rounded-lg border border-slate-200 bg-white">
                                <table class="w-full text-xs">
                                  <tbody>
                                    {#each periodsOf(r[0]) as pp}
                                      <tr class="border-b border-slate-100 last:border-0">
                                        <td class="px-2 py-1 mono text-slate-600 whitespace-nowrap">{pp.from} → {pp.to || 'now 迄今'}</td>
                                        <td class="px-2 py-1 text-right {pp.price ? 'text-slate-800 font-semibold' : 'text-slate-400'}">{pp.price ? money(pp.price) : 'no price 無支付價'}</td>
                                      </tr>
                                    {/each}
                                  </tbody>
                                </table>
                              </div>
                            {:else if pricesFailed}
                              <p class="text-xs text-red-700">The price history could not be loaded.</p>
                            {:else}
                              <p class="text-xs text-slate-400">Loading…</p>
                            {/if}
                          </div>
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
      <h2 class="font-bold text-slate-900">Sources <span class="font-normal text-slate-400 text-sm">資料來源</span></h2>
      <ul class="mt-3 space-y-2 text-sm text-slate-700 list-disc pl-5">
        <li>
          Codes, names, prices and status:
          <a class="text-brand-700 hover:underline" target="_blank" rel="noreferrer" href="https://info.nhi.gov.tw/INAE3000/INAE3000S01">NHI drug item query 健保用藥品項查詢</a>.
        </li>
        <li>
          Components and missing ATC codes: licence formulas and licence ATC codes from
          <a class="text-brand-700 hover:underline" target="_blank" rel="noreferrer" href="https://data.fda.gov.tw">TFDA open data 食藥署開放資料</a>
          (Open Government Data License).
        </li>
        {#if db?.meta.ddd_source}
          <li>
            ATC names and defined daily doses: WHO Collaborating Centre for Drug Statistics Methodology,
            <a class="text-brand-700 hover:underline" target="_blank" rel="noreferrer" href="https://atcddd.fhi.no/atc_ddd_index/">ATC/DDD Index</a>,
            shown unchanged.
          </li>
        {/if}
        <li>
          All of it is downloaded again every Monday and the list is rebuilt automatically{#if db}.
          Last checked {db.meta.checked}; last change found {db.meta.snapshot}{/if}.
        </li>
      </ul>
    </div>
  </section>
</div>
