/* Colometrics — single-page frontend (vanilla JS). */
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };

  let BOOKS = [];
  let booksFlat = []; // [{bookIndex, chapter}] for reader navigation

  // ---------------- routing ----------------
  function parseHash() {
    const h = location.hash.replace(/^#/, '') || '/';
    const [pathPart, queryPart] = h.split('?');
    const segs = pathPart.split('/').filter(Boolean);
    const q = new URLSearchParams(queryPart || '');
    return { view: segs[0] || 'analyzer', segs, q };
  }

  function route() {
    const { view, segs, q } = parseHash();
    const v = ['analyzer', 'reader', 'about'].includes(view) ? view : 'analyzer';
    document.querySelectorAll('.view').forEach((s) => { s.hidden = s.id !== `view-${v}`; });
    document.querySelectorAll('#site-nav a').forEach((a) => {
      a.classList.toggle('active', a.dataset.nav === v);
    });
    if (v === 'analyzer') {
      if (segs[1] && BOOKS.some((b) => b.id === segs[1])) {
        selectVerse(segs[1], parseInt(segs[2], 10) || 1, parseInt(segs[3], 10) || 1, q.get('mode'));
      } else if (!analyzerLoaded) {
        loadInitialVerse(q);
      }
    } else if (v === 'reader') {
      const book = segs[1] && BOOKS.some((b) => b.id === segs[1]) ? segs[1] : null;
      gotoReader(book ? BOOKS.findIndex((b) => b.id === book) : null,
        parseInt(segs[2], 10) || 1, q.get('mode') || readMode());
    }
  }

  // ---------------- analyzer ----------------
  let analyzerLoaded = false;
  const MODE_KEY = 'colometricsMode';
  let verseMode = localStorage.getItem(MODE_KEY) || 'none';
  let current = { book: null, chapter: null, verse: null };
  let colaData = null;

  async function initAnalyzer() {
    const res = await fetch('/api/index');
    BOOKS = await res.json();
    booksFlat = [];
    BOOKS.forEach((b, bi) => {
      for (let c = 1; c <= b.chapters.length; c++) booksFlat.push({ bookIndex: bi, chapter: c });
      const opt = document.createElement('option');
      opt.value = b.id; opt.textContent = b.name;
      $('sv-book').appendChild(opt.cloneNode(true));
      $('read-book').appendChild(opt);
    });
    analyzerLoaded = true;

    $('sv-book').addEventListener('change', () => { populateChapters('sv'); });
    $('sv-chapter').addEventListener('change', () => { populateVerses(); });
    $('sv-verse').addEventListener('change', () => { updateOk(); });
    $('sv-ok').addEventListener('click', () => { commitVerse(); });
    [$('sv-book'), $('sv-chapter'), $('sv-verse')].forEach((sel) => {
      sel.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); commitVerse(); } });
    });
    $('sv-prev').addEventListener('click', () => stepVerse(-1));
    $('sv-next').addEventListener('click', () => stepVerse(1));
    $('sv-en-toggle').addEventListener('change', () => renderEnglish());

    document.querySelectorAll('input[name="sv-mode"]').forEach((r) => {
      r.addEventListener('change', async () => {
        verseMode = r.value;
        localStorage.setItem(MODE_KEY, verseMode);
        if (current.verse) await loadVerse();
      });
    });
    const saved = document.querySelector(`input[name="sv-mode"][value="${verseMode}"]`);
    if (saved) saved.checked = true;
  }

  function bookById(id) { return BOOKS.find((b) => b.id === id); }

  function populateChapters(which) {
    const bookSel = $(which === 'sv' ? 'sv-book' : 'read-book');
    const chSel = $(which === 'sv' ? 'sv-chapter' : 'read-chapter');
    const book = bookById(bookSel.value);
    chSel.innerHTML = '<option value="">Chapter…</option>';
    if (!book) { chSel.disabled = true; return; }
    book.chapters.forEach((_, i) => {
      const o = document.createElement('option');
      o.value = String(i + 1); o.textContent = String(i + 1);
      chSel.appendChild(o);
    });
    chSel.disabled = false;
    chSel.value = '1';
    if (which === 'sv') populateVerses();
  }

  function populateVerses() {
    const book = bookById($('sv-book').value);
    const ch = parseInt($('sv-chapter').value, 10);
    const vSel = $('sv-verse');
    vSel.innerHTML = '<option value="">Verse…</option>';
    if (!book || !ch) { vSel.disabled = true; updateOk(); return; }
    const count = book.chapters[ch - 1];
    for (let i = 1; i <= count; i++) {
      const o = document.createElement('option');
      o.value = String(i); o.textContent = String(i);
      vSel.appendChild(o);
    }
    vSel.disabled = false;
    vSel.value = '1';
    updateOk();
  }

  function updateOk() { $('sv-ok').disabled = !$('sv-verse').value; }

  async function loadInitialVerse(q) {
    // pleasant default: Psalm 1:1 in prose mode? Respect stored mode.
    const book = q.get('book') && bookById(q.get('book')) ? q.get('book') : 'Ps';
    const chapter = parseInt(q.get('chapter'), 10) || 1;
    const verse = parseInt(q.get('verse'), 10) || 1;
    selectVerse(book, chapter, verse, q.get('mode'));
  }

  function selectVerse(bookId, chapter, verse, mode) {
    if (mode && ['none', 'poetry', 'prose'].includes(mode)) {
      verseMode = mode;
      localStorage.setItem(MODE_KEY, mode);
      const r = document.querySelector(`input[name="sv-mode"][value="${mode}"]`);
      if (r) r.checked = true;
    }
    $('sv-book').value = bookId;
    populateChapters('sv');
    $('sv-chapter').value = String(chapter);
    $('sv-chapter').dispatchEvent(new Event('change'));
    $('sv-verse').value = String(verse);
    updateOk();
    commitVerse();
  }

  function commitVerse() {
    const book = $('sv-book').value;
    const chapter = parseInt($('sv-chapter').value, 10);
    const verse = parseInt($('sv-verse').value, 10);
    if (!book || !chapter || !verse) return;
    current = { book, chapter, verse };
    const q0 = parseHash().q;
    const keep = ['word', 'mi', 'full', 'selftest', 'en'].filter((k) => q0.get(k) !== null).map((k) => `&${k}=${q0.get(k)}`).join('');
    const newHash = `#/analyzer/${book}/${chapter}/${verse}?mode=${verseMode}${keep}`;
    if (location.hash !== newHash) history.replaceState(null, '', newHash);
    loadVerse();
  }

  async function loadVerse() {
    const { book, chapter, verse } = current;
    if (!book) return;
    const box = $('sv-verse-text');
    box.innerHTML = '<div class="placeholder">Loading…</div>';
    $('sv-word-panel').innerHTML = '';
    let data;
    try {
      const res = await fetch(`/api/colometry/${book}/${chapter}/${verse}?mode=${verseMode}`);
      if (!res.ok) throw new Error(`${res.status}`);
      data = await res.json();
    } catch (e) {
      box.innerHTML = `<div class="wp-error">Could not load this verse (${esc(e.message)}).</div>`;
      return;
    }
    colaData = data;
    if (parseHash().q.get('en') === '1') $('sv-en-toggle').checked = true;
    renderVerse(data);
    renderEnglish();
    const b = bookById(book);
    $('sv-ref').textContent = `${b.name} ${chapter}:${verse}`;
    $('sv-badge').hidden = !data.poetic_book;
    $('sv-verse-placeholder')?.classList.add('hidden');
    $('sv-prev').disabled = false;
    $('sv-next').disabled = false;
    const wordParam = parseHash().q.get('word');
    if (wordParam !== null) {
      const miParam = parseHash().q.get('mi');
      const sel = miParam !== null
        ? box.querySelector(`.m[data-tok="${wordParam}"][data-mi="${miParam}"]`)
        : null;
      const target = sel || box.querySelector(`.w[data-idx="${wordParam}"]`);
      if (target) target.click();
    }
    if (parseHash().q.get('selftest') === '1') {
      setTimeout(() => {
        box.scrollIntoView();
        const bad = [];
        box.querySelectorAll('.w, .m').forEach((el) => {
          const r = el.getBoundingClientRect();
          const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          if (!hit || (hit !== el && !el.contains(hit) && !(hit.contains && hit.contains(el)))) {
            bad.push((el.className || '') + '|' + (el.textContent || '').slice(0, 10) + '|hit=' + (hit ? hit.className || hit.tagName : 'null'));
          }
        });
        document.title = 'SELFTEST bad=' + bad.length + ' :: ' + bad.slice(0, 8).join(' ;; ');
      }, 800);
    }
  }

  function renderVerse(data) {
    const box = $('sv-verse-text');
    box.innerHTML = '';
    box.classList.toggle('no-colon', data.mode === 'none');
    tokenEls = {};
    data.cola.forEach((colon, ci) => {
      const line = document.createElement('span');
      line.className = 'colon';
      colon.forEach((w) => {
        const span = document.createElement('span');
        span.className = 'w' + (w.cl ? ' closes' : '');
        span.dataset.idx = w.i;
        if (w.m && w.m.length > 1) {
          w.m.forEach((m, mi) => {
            const mspan = document.createElement('span');
            mspan.className = 'm k-' + m.k;
            mspan.dataset.tok = w.i;
            mspan.dataset.mi = mi;
            mspan.textContent = m.t;
            mspan.title = m.l || m.s || '';
            mspan.addEventListener('click', (ev) => { ev.stopPropagation(); selectMorpheme(w.i, mi, mspan); });
            span.appendChild(mspan);
          });
          // clicking the word itself (not a part) selects the whole word
          span.addEventListener('click', () => selectWord(w.i, span));
          tokenEls[w.i] = span;
        } else {
          span.className = 'w plain' + (w.cl ? ' closes' : '');
          span.textContent = w.t;
          span.addEventListener('click', () => selectWord(w.i, span));
          tokenEls[w.i] = span;
        }
        const tail = document.createTextNode(w.tr || ' ');
        line.appendChild(span);
        line.appendChild(tail);
      });
      box.appendChild(line);
    });
    fitLines(box, data.mode !== 'none');
  }
  let tokenEls = {};

  // a morpheme of a segmented word was clicked: every part — including the
  // core — gets its own focused panel; the panel links back to the whole word
  function selectMorpheme(tokIdx, mi, el) {
    document.querySelectorAll('#sv-verse-text .m.selected').forEach((x) => x.classList.remove('selected'));
    document.querySelectorAll('#sv-verse-text .w.selected').forEach((x) => x.classList.remove('selected'));
    el.classList.add('selected');
    const w = findWord(tokIdx);
    const m = w && w.m ? w.m[mi] : null;
    if (!m) {
      selectWord(tokIdx, tokenEls[tokIdx]);
      return;
    }
    renderMorphemePanel(tokIdx, mi, m);
  }

  function findWord(tokIdx) {
    if (!colaData) return null;
    for (const colon of colaData.cola) {
      for (const w of colon) if (w.i === tokIdx) return w;
    }
    return null;
  }

  async function renderMorphemePanel(tokIdx, mi, m) {
    const panel = $('sv-word-panel');
    const w = findWord(tokIdx);
    const partLabel = m.k === 'suffix' ? 'pronominal suffix' : m.k === 'prefix' ? 'prefix' : '';
    panel.innerHTML = `<div class="wp-card">
      <span class="wp-heb" dir="rtl" lang="he">${esc(m.t)}</span>
      ${partLabel ? `<span class="wp-part">${partLabel}</span>` : ''}
      <span class="wp-translit">${esc(translitLite(m.t))}</span>
      ${m.s ? `<div class="wp-tags"><span class="tag sign">${esc(m.s)}</span></div>` : ''}
      ${m.l ? `<p class="wp-note">${esc(m.l)}</p>` : ''}
      ${m.g ? `<p class="wp-note"><b>${esc(m.g)}</b></p>` : ''}
      ${m.g ? '' : '<div id="wp-part-lex">Loading…</div>'}
      <button type="button" class="btn btn-link" id="wp-whole">whole word <span dir="rtl" lang="he">${esc(w.t)}</span> ▸</button>
    </div>`;
    $('wp-whole').addEventListener('click', () => selectWord(tokIdx, tokenEls[tokIdx]));
    if (m.g) {
      // clitics and suffixes are fully described by their gloss — no lexicon call
      return;
    }
    try {
      const res = await fetch(`/api/lexicon/${encodeURIComponent(m.t)}`);
      const data = await res.json();
      renderPartLexicon($('wp-part-lex'), m.t, data);
    } catch (e) {
      $('wp-part-lex').innerHTML = `<p class="wp-error">${esc(e.message)}</p>`;
    }
  }

  // compact abridged BDB + "Full BDB entry" toggle, shared by part panels
  function renderPartLexicon(box, form, data) {
    const abridged = (data.entries || []).find((e) => /BDB Augmented/.test(e.lexicon));
    const full = (data.entries || []).find((e) => e.lexicon === 'BDB Dictionary');
    if (!abridged && !full) {
      box.innerHTML = '<p class="wp-note">No lexicon entry for this part.</p>';
      return;
    }
    let html = '<div class="wp-bdb">';
    if (abridged) {
      const flat = flattenSenses(abridged.senses).slice(0, 8);
      html += `<h3><span class="headword" dir="rtl" lang="he">${esc(abridged.headword)}</span>
        <span class="bdb-meta">${esc(abridged.transliteration || '')}${abridged.strong ? ' · Strong ' + esc(abridged.strong) : ''}${abridged.morphology ? ' · ' + esc(abridged.morphology) : ''}</span></h3>`;
      if (flat.length) html += `<p class="bdb-abridged">${flat.map((s, i) => `<b>${i + 1}.</b> ${esc(s)}`).join(' &nbsp; ')}</p>`;
    }
    html += '</div>';
    if (full) {
      html += `<button type="button" class="btn btn-link bdb-full-toggle" id="part-bdb-toggle">Full BDB entry ▸</button>
        <div class="bdb-full" id="part-bdb-full" hidden></div>`;
    }
    box.innerHTML = html;
    if (full) {
      const toggle = box.querySelector('#part-bdb-toggle');
      const boxFull = box.querySelector('#part-bdb-full');
      let loaded = false;
      toggle.addEventListener('click', () => {
        const show = boxFull.hidden;
        boxFull.hidden = !show;
        toggle.textContent = show ? 'Full BDB entry ▾' : 'Full BDB entry ▸';
        if (show && !loaded) {
          boxFull.appendChild(renderFullSenses(full.senses));
          loaded = true;
        }
      });
    }
  }

  // rough one-word transliteration for part panels (the API only transliterates
  // whole tokens); good enough as a reading aid next to the Hebrew
  function translitLite(s) {
    const map = {
      א: 'ʾ', ב: 'b', ג: 'g', ד: 'd', ה: 'h', ו: 'w', ז: 'z', ח: 'ḥ', ט: 'ṭ', י: 'y',
      כ: 'k', ל: 'l', מ: 'm', נ: 'n', ס: 's', ע: 'ʿ', פ: 'p', צ: 'ṣ', ק: 'q', ר: 'r',
      ש: 'š', ת: 't', ך: 'k', ם: 'm', ן: 'n', ף: 'p', ץ: 'ṣ',
      '\u05B0': 'ə', '\u05B1': 'ă', '\u05B2': 'a', '\u05B3': 'o', '\u05B4': 'i',
      '\u05B5': 'ē', '\u05B6': 'e', '\u05B7': 'a', '\u05B8': 'ā', '\u05B9': 'ō',
      '\u05BB': 'u', '\u05BC': '', '\u05BD': '', '\u05BE': '-', '\u05BF': '', '\u05C0': ' ',
    };
    let out = '';
    for (const ch of s) {
      if (map[ch] !== undefined) out += map[ch];
      else if (/[\u0591-\u05A9\u05A6\u05AC-\u05AF\u05BF\u05C0-\u05C3]/.test(ch)) out += '';
    }
    return out;
  }

  // shrink-to-fit so each colon occupies one visual row (never below 1rem;
  // below that, wrapping with a hanging indent beats illegibility)
  function fitLines(container, wrap) {
    if (!container) return;
    const lines = container.querySelectorAll('.colon');
    if (!wrap || !lines.length) {
      container.style.fontSize = '';
      container.classList.remove('wrap-colon');
      return;
    }
    const avail = container.clientWidth - 8;
    const maxPx = 1.6 * 16;
    const minPx = 1.0 * 16;
    const widestAt = (px) => {
      container.style.fontSize = px + 'px';
      let widest = 0;
      for (const l of lines) {
        // inline-block + nowrap shrink-wraps so scrollWidth is the true text width
        // (a block's scrollWidth never drops below its clientWidth, even when empty)
        l.style.whiteSpace = 'nowrap';
        l.style.display = 'inline-block';
        widest = Math.max(widest, l.scrollWidth);
        l.style.whiteSpace = '';
        l.style.display = '';
      }
      return widest;
    };
    if (widestAt(maxPx) <= avail) {
      container.style.fontSize = maxPx + 'px';
      container.classList.remove('wrap-colon');
      return;
    }
    let lo = minPx, hi = maxPx, best = minPx;
    while (hi - lo > 0.5) {
      const mid = (lo + hi) / 2;
      if (widestAt(mid) <= avail) { best = mid; lo = mid; } else { hi = mid; }
    }
    container.style.fontSize = best + 'px';
    container.classList.toggle('wrap-colon', widestAt(best) > avail);
  }
  let resizeTimer = null;
  function refitLoadedVerse() {
    const box = $('sv-verse-text');
    if (box && box.querySelectorAll('.colon').length) fitLines(box, verseMode !== 'none');
  }
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(refitLoadedVerse, 150);
  });
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => setTimeout(refitLoadedVerse, 50));
  }

  async function selectWord(idx, span) {
    document.querySelectorAll('#sv-verse-text .w.selected').forEach((el) => el.classList.remove('selected'));
    document.querySelectorAll('#sv-verse-text .m.selected').forEach((el) => el.classList.remove('selected'));
    span.classList.add('selected');
    const panel = $('sv-word-panel');
    panel.innerHTML = '<div class="wp-card">Loading…</div>';
    let info;
    try {
      const res = await fetch(`/api/word/${current.book}/${current.chapter}/${current.verse}/${idx}`);
      if (!res.ok) throw new Error(`${res.status}`);
      info = await res.json();
    } catch (e) {
      panel.innerHTML = `<div class="wp-card wp-error">Error: ${esc(e.message)}</div>`;
      return;
    }
    renderWordPanel(info);
  }

  function renderWordPanel(info) {
    const panel = $('sv-word-panel');
    const tags = [];
    if (info.sign && info.sign !== 'silluq') {
      tags.push(`<span class="tag sign">${esc(info.sign_title || info.sign)}</span>`);
    }
    info.accents.forEach((a) => {
      const cls = a.role === 'disjunctive' ? 'disj' : 'conj';
      tags.push(`<span class="tag ${cls}">${esc(a.title)} — ${a.role}</span>`);
    });
    if (info.paseq) tags.push('<span class="tag">paseq</span>');
    if (info.is_verse_final && info.accents.some((a) => a.name === 'silluq')) {
      tags.push('<span class="tag disj">end of verse (sof pasuq)</span>');
    }
    let html = `<div class="wp-card">
      <span class="wp-heb" dir="rtl" lang="he">${esc(info.token)}</span>
      <span class="wp-translit">${esc(info.transliteration)}</span>
      <div class="wp-tags">${tags.join('')}</div>`;
    if (info.sign === 'legarmeh') {
      html += `<p class="wp-note">Compound sign: an accent + paseq (U+05C0); it functions as a disjunctive.</p>`;
    } else if (info.sign === 'revia_mugrash') {
      html += `<p class="wp-note">Compound sign: geresh muqdam + revia = reviʿa mugrash (one sign).</p>`;
    } else if (info.sign === 'ole') {
      html += `<p class="wp-note">Compound sign: ʿole we-yored — the ʿole closes a colon together with the following yored.</p>`;
    }

    // morphemes with real parsing (OSHB morphology)
    if (info.morphemes && info.morphemes.length) {
      html += '<div class="morphemes" id="wp-morphemes">';
      info.morphemes.forEach((m, i) => {
        const sep = i < info.morphemes.length - 1 ? '<span class="morph-sep">+</span>' : '';
        const label = m.short ? `<span class="morph-label">${esc(m.short)}</span>` : '';
        const tip = esc(m.long || m.morph || '');
        html += `<button type="button" class="morph" data-i="${i}" title="${tip}">
            <span class="morph-text" dir="rtl" lang="he">${esc(m.t)}</span>${label}</button>${sep}`;
      });
      html += '</div><div id="wp-morph-lookup"></div>';
    }

    // compact abridged BDB + full entry on demand
    if (info.bdb) {
      const b = info.bdb;
      const flat = flattenSenses(b.senses).slice(0, 8);
      html += `<div class="wp-bdb">
        <h3><span class="headword" dir="rtl" lang="he">${esc(b.headword)}</span>
          <span class="bdb-meta">${esc(b.transliteration || '')}${b.strong ? ' · Strong ' + esc(b.strong) : ''}${b.morphology ? ' · ' + esc(b.morphology) : ''}${b.pronunciation ? ' · ' + esc(b.pronunciation) : ''}</span></h3>`;
      if (flat.length) {
        html += `<p class="bdb-abridged">${flat.map((s, i) => `<b>${i + 1}.</b> ${esc(s)}`).join(' &nbsp; ')}</p>`;
      }
      html += '</div>';
      if (info.bdb_full) {
        html += `<button type="button" class="btn btn-link bdb-full-toggle" id="bdb-toggle">Full BDB entry ▸</button>
        <div class="bdb-full" id="bdb-full" hidden></div>`;
      }
    } else if (info.lexicon_entries && info.lexicon_entries.length) {
      const e0 = info.lexicon_entries[0];
      html += `<div class="wp-bdb"><h3><span class="headword" dir="rtl" lang="he">${esc(e0.headword)}</span>
        <span class="bdb-meta">${esc(e0.lexicon)}</span></h3>${renderSenses(e0.senses)}</div>`;
    } else {
      html += `<p class="wp-note">No lexicon entry found for this form.</p>`;
    }
    html += '</div>';
    panel.innerHTML = html;

    if (info.morphemes && info.morphemes.length) {
      const lookupBox = $('wp-morph-lookup');
      let openIdx = null;
      panel.querySelectorAll('.morph').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const i = Number(btn.dataset.i);
          if (openIdx === i) { lookupBox.innerHTML = ''; openIdx = null; return; }
          openIdx = i;
          panel.querySelectorAll('.morph').forEach((b) => b.classList.remove('on'));
          btn.classList.add('on');
          const m = info.morphemes[i];
          lookupBox.innerHTML = '<div class="morph-lookup loading">Loading…</div>';
          try {
            const res = await fetch(`/api/lexicon/${encodeURIComponent(m.t)}`);
            const data = await res.json();
            renderMorphLookup(lookupBox, m, data);
          } catch (e) {
            lookupBox.innerHTML = `<div class="morph-lookup wp-error">${esc(e.message)}</div>`;
          }
        });
      });
    }
    if (info.bdb && info.bdb_full) {
      const toggle = $('bdb-toggle');
      const full = $('bdb-full');
      let loaded = false;
      const doToggle = () => {
        const show = full.hidden;
        full.hidden = !show;
        toggle.textContent = show ? 'Full BDB entry ▾' : 'Full BDB entry ▸';
        if (show && !loaded) {
          full.appendChild(renderFullSenses(info.bdb_full.senses));
          loaded = true;
        }
      };
      toggle.addEventListener('click', doToggle);
      if (parseHash().q.get('full') === '1') doToggle();
    }
  }

  function flattenSenses(senses, depth) {
    depth = depth || 0;
    let out = [];
    (senses || []).forEach((s) => {
      if (s.definition) out.push(s.definition.trim());
      if (depth < 1 && s.senses) out = out.concat(flattenSenses(s.senses, depth + 1));
    });
    return out;
  }

  function renderMorphLookup(box, morph, data) {
    let html = `<div class="morph-lookup">
      <span class="morph-text" dir="rtl" lang="he">${esc(morph.t)}</span>
      ${morph.long ? `<span class="morph-long">${esc(morph.long)}</span>` : ''}
      ${morph.lemma && /^\d/.test(morph.lemma) ? `<span class="bdb-meta"> · Strong ${esc(morph.lemma.replace(/ .*/, ''))}</span>` : ''}`;
    if (morph.clitic) {
      html += ` — <b>${esc(morph.clitic)}</b></div>`;
      box.innerHTML = html;
      return;
    }
    const bdb = (data.entries || []).find((e) => /BDB Augmented/.test(e.lexicon));
    if (bdb) {
      const flat = flattenSenses(bdb.senses).slice(0, 8);
      html += ` — <b>${esc(bdb.headword)}</b>${flat.length ? ': ' + flat.map((s, i) => `${i + 1}. ${esc(s)}`).join(' · ') : ''}`;
    } else {
      html += ' — no lexicon entry for this part';
    }
    html += '</div>';
    box.innerHTML = html;
  }

  // The unabridged BDB entry arrives as HTML with strong/em/sup/span/a(data-ref).
  // Keep a small allow-list; scripture references become links into the analyzer.
  const REF_BOOK_MAP = { '1 Samuel': '1Sam', '2 Samuel': '2Sam', '1 Kings': '1Kgs', '2 Kings': '2Kgs',
    '1 Chronicles': '1Chr', '2 Chronicles': '2Chr', 'Song of Songs': 'Song' };
  function bookIdFromName(name) {
    if (REF_BOOK_MAP[name]) return REF_BOOK_MAP[name];
    const b = BOOKS.find((x) => x.name === name);
    return b ? b.id : null;
  }
  function sanitizeBdbHtml(html) {
    const allowed = { STRONG: [], EM: [], I: ['EM'], U: [], B: ['STRONG'], SUP: [], SUB: [], BR: [] };
    const doc = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html');
    const walk = (node) => {
      const out = document.createDocumentFragment();
      node.childNodes.forEach((child) => {
        if (child.nodeType === Node.TEXT_NODE) {
          out.appendChild(document.createTextNode(child.textContent));
          return;
        }
        if (child.nodeType !== Node.ELEMENT_NODE) return;
        const tag = child.tagName;
        if (tag === 'SPAN') {
          const el = document.createElement('span');
          if (child.getAttribute('dir') === 'rtl') {
            el.setAttribute('dir', 'rtl');
            el.setAttribute('lang', 'he');
          }
          el.appendChild(walk(child));
          out.appendChild(el);
          return;
        }
        if (tag === 'A') {
          const ref = child.getAttribute('data-ref') || '';
          const m = ref.match(/^(.+?)\s+(\d+):(\d+)$/);
          const bid = m ? bookIdFromName(m[1]) : null;
          if (bid) {
            const a = document.createElement('a');
            a.href = `#/analyzer/${bid}/${m[2]}/${m[3]}`;
            a.textContent = child.textContent;
            out.appendChild(a);
          } else {
            out.appendChild(document.createTextNode(child.textContent));
          }
          return;
        }
        if (allowed[tag]) {
          const el = document.createElement(tag.toLowerCase());
          el.appendChild(walk(child));
          out.appendChild(el);
          return;
        }
        out.appendChild(walk(child));
      });
      return out;
    };
    return walk(doc.body.firstChild);
  }
  function renderFullSenses(senses) {
    if (!senses || !senses.length) return document.createDocumentFragment();
    const ol = document.createElement('ol');
    ol.className = 'senses full-senses';
    senses.forEach((s) => {
      const li = document.createElement('li');
      li.appendChild(sanitizeBdbHtml(s.definition || ''));
      if (s.senses && s.senses.length) li.appendChild(renderFullSenses(s.senses));
      ol.appendChild(li);
    });
    return ol;
  }

  function renderSenses(senses) {
    if (!senses || !senses.length) return '';
    const items = senses.map((s) => {
      let inner = esc(s.definition || '');
      if (s.senses && s.senses.length) inner += renderSenses(s.senses);
      return `<li>${inner}</li>`;
    });
    return `<ol class="senses">${items.join('')}</ol>`;
  }

  function renderEnglish() {
    const el = $('sv-english');
    if (!$('sv-en-toggle').checked || !colaData) { el.hidden = true; return; }
    el.hidden = false;
    el.textContent = colaData.english || '';
  }

  async function stepVerse(delta) {
    const { book, chapter, verse } = current;
    if (!book) return;
    const b = bookById(book);
    const chCount = b.chapters.length;
    const vCount = b.chapters[chapter - 1];
    let nb = book, nc = chapter, nv = verse + delta;
    if (nv < 1) {
      if (chapter > 1) { nc = chapter - 1; nv = b.chapters[nc - 1]; }
      else {
        const bi = BOOKS.findIndex((x) => x.id === book);
        if (bi <= 0) return;
        nb = BOOKS[bi - 1].id; nc = BOOKS[bi - 1].chapters.length; nv = BOOKS[bi - 1].chapters[nc - 1];
      }
    } else if (nv > vCount) {
      if (chapter < chCount) { nc = chapter + 1; nv = 1; }
      else {
        const bi = BOOKS.findIndex((x) => x.id === book);
        if (bi >= BOOKS.length - 1) return;
        nb = BOOKS[bi + 1].id; nc = 1; nv = 1;
      }
    }
    history.replaceState(null, '', `#/analyzer/${nb}/${nc}/${nv}?mode=${verseMode}`);
    selectVerse(nb, nc, nv);
  }

  // ---------------- reader ----------------
  let readModeCurrent = 'accented';

  function readMode() { return $('read-mode').value; }

  function gotoReader(bookIndex, chapter, mode) {
    if (bookIndex === null || bookIndex === undefined || bookIndex < 0 || isNaN(bookIndex)) {
      bookIndex = readBookIndex();
      if (bookIndex < 0) bookIndex = 0;
    }
    readModeCurrent = mode || readModeCurrent;
    $('read-mode').value = readModeCurrent;
    $('read-book').value = BOOKS[bookIndex].id;
    populateChapters('read');
    $('read-chapter').value = String(chapter);
    updateReaderNav();
    loadChapter(bookIndex, chapter);
    const labels = { accented: 'Accented text', unaccented: 'Unaccented text', consonantal: 'Consonantal text', translit: 'Transliterated text' };
    $('read-crumb').textContent = labels[readModeCurrent];
    $('read-title').textContent = labels[readModeCurrent];
    const id = BOOKS[bookIndex] && BOOKS[bookIndex].id;
    if (id) history.replaceState(null, '', `#/reader/${id}/${chapter}?mode=${readModeCurrent}`);
  }

  function readBookIndex() {
    return BOOKS.findIndex((b) => b.id === $('read-book').value);
  }

  function initReader() {
    $('read-book').addEventListener('change', () => {
      gotoReader(readBookIndex(), 1, readModeCurrent);
    });
    $('read-chapter').addEventListener('change', () => {
      gotoReader(readBookIndex(), parseInt($('read-chapter').value, 10), readModeCurrent);
    });
    $('read-mode').addEventListener('change', () => {
      readModeCurrent = readMode();
      gotoReader(readBookIndex(), parseInt($('read-chapter').value, 10), readModeCurrent);
    });
    $('read-prev').addEventListener('click', () => stepChapter(-1));
    $('read-next').addEventListener('click', () => stepChapter(1));
    $('read-en-toggle').addEventListener('change', renderReaderEnglish);
  }

  function updateReaderNav() {
    const idx = booksFlat.findIndex((f) => f.bookIndex === readBookIndex()
      && f.chapter === parseInt($('read-chapter').value, 10));
    $('read-prev').disabled = idx <= 0;
    $('read-next').disabled = idx >= booksFlat.length - 1 || idx === -1;
  }

  function stepChapter(delta) {
    const idx = booksFlat.findIndex((f) => f.bookIndex === readBookIndex()
      && f.chapter === parseInt($('read-chapter').value, 10));
    const next = idx + delta;
    if (next < 0 || next >= booksFlat.length) return;
    gotoReader(booksFlat[next].bookIndex, booksFlat[next].chapter, readModeCurrent);
  }

  let chapterCache = null;

  async function loadChapter(bookIndex, chapter) {
    const id = BOOKS[bookIndex].id;
    const mode = readModeCurrent;
    const heb = $('read-text');
    const en = $('read-english');
    heb.innerHTML = '<div class="placeholder">Loading…</div>';
    en.innerHTML = '';
    let data;
    try {
      const res = await fetch(`/api/chapter/${id}/${chapter}?mode=${mode}`);
      if (!res.ok) throw new Error(`${res.status}`);
      data = await res.json();
    } catch (e) {
      heb.innerHTML = `<div class="wp-error">Could not load this chapter (${esc(e.message)}).</div>`;
      return;
    }
    chapterCache = data;
    heb.dir = data.rtl ? 'rtl' : 'ltr';
    heb.lang = data.rtl ? 'he' : 'en';
    heb.innerHTML = '';
    const verses = Object.entries(data.verses);
    verses.sort((a, b) => parseInt(a[0], 10) - parseInt(b[0], 10));
    for (const [num, v] of verses) {
      const p = document.createElement('p');
      const ns = document.createElement('span');
      ns.className = 'verse-num';
      ns.textContent = num;
      p.appendChild(ns);
      p.appendChild(document.createTextNode(v.he + ' '));
      heb.appendChild(p);
    }
    renderReaderEnglish();
  }

  function renderReaderEnglish() {
    const en = $('read-english');
    if (!$('read-en-toggle').checked || !chapterCache) { en.hidden = true; return; }
    en.hidden = false;
    en.innerHTML = '';
    const verses = Object.entries(chapterCache.verses);
    verses.sort((a, b) => parseInt(a[0], 10) - parseInt(b[0], 10));
    for (const [num, v] of verses) {
      const p = document.createElement('p');
      const ns = document.createElement('span');
      ns.className = 'verse-num';
      ns.textContent = num;
      p.appendChild(ns);
      p.appendChild(document.createTextNode(v.en + ' '));
      en.appendChild(p);
    }
  }

  // ---------------- boot ----------------
  document.addEventListener('DOMContentLoaded', async () => {
    await initAnalyzer();
    initReader();
    route();
  });
  window.addEventListener('hashchange', route);
})();
