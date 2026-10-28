// SPDX-FileCopyrightText: 2026 Frédéric Berthommier
// SPDX-License-Identifier: GPL-3.0-or-later
/* render.js — DOM renderers for the v3 console zones.
 * Pure presentation: no state, no engine calls. app.js owns the state. */

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null) node.append(c);
  return node;
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ── toasts ─────────────────────────────────────────────────────────── */
export function toast(message, type = 'info', timeout = 4200) {
  const box = $('#toasts');
  const t = el('div', { class: `toast toast-${type}`, role: 'status' },
    el('span', { class: 'toast-msg', text: message }));
  box.append(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, timeout);
}

/* ── stage log (single pane at the bottom of the stage — brief §4.3) ── */
export function log(message, { level = 'info' } = {}) {
  const pane = $('#log-pane');
  if (!pane) { console.log(message); return; }
  const time = new Date().toLocaleTimeString('en-US', { hour12: false });
  pane.append(el('div', { class: `log-line log-${level}` },
    el('span', { class: 'log-time', text: time }),
    el('span', { class: 'log-body', text: message })));
  while (pane.children.length > 400) pane.firstChild.remove();
  pane.scrollTop = pane.scrollHeight;
}

/* ── SAMPA token stream (shared by the three preview rows) ─────────── */
export function sampaTokens(tokens, rejected = []) {
  const stream = el('div', { class: 'sampa-words' });
  const rejMap = new Map(rejected.map((r) => [r.position, r]));
  for (const t of tokens) {
    let cls = 'tok';
    let tip = null;
    if (t.kind === 'rejected') {
      cls += ' tok-rejected';
      const r = rejMap.get(t.position) || {};
      const sug = (r.suggestions || []).length ? ` Did you mean: ${(r.suggestions || []).join(', ')}?` : '';
      tip = `“${t.sym}” (position ${t.position + 1}) — ${r.reason || 'not in the engine inventory (ALL_PHONEME_KEYS)'}.${sug}`;
    }
    else if (t.kind === 'pause-short') { cls += ' tok-pause'; tip = 'short pause (tpause)'; }
    else if (t.kind === 'pause-long') { cls += ' tok-pause tok-long'; tip = 'long pause (tpause-long)'; }
    else if (t.kind === 'pause-breath') { cls += ' tok-pause tok-breath'; tip = 'expressive breath pause'; }
    else if (t.kind === 'link') { cls += ' tok-link'; tip = 'syllable link — coarticulated, no pause'; }
    else if (t.kind === 'feature') { cls += ' tok-feature'; tip = 'nasality marker'; }
    else cls += ' tok-word mono';
    const attrs = { class: cls, text: t.sym === ' ' ? '␣' : t.sym };
    if (tip) attrs['data-tip'] = tip;
    stream.append(el('span', attrs));
  }
  return stream;
}

/* plain mono string for rows that are shown verbatim */
export function sampaPlain(value) {
  return el('div', { class: 'sampa-words' },
    el('span', { class: 'tok tok-word mono', text: value || '(empty)' }));
}

/* ── guard banner (the red-reject experience, brief ch. 7) ─────────── */
export function renderGuardBanner(rejected, policy, onStrip, onWarnPolicy) {
  const box = $('#guard-banner');
  box.innerHTML = '';
  if (!rejected.length) { box.style.display = 'none'; box.dataset.policy = ''; return; }
  box.style.display = '';
  const uniq = [...new Map(rejected.map((r) => [r.symbol, r])).values()];
  const entry = (r) => `'${r.symbol}'${(r.suggestions || []).length ? ` → ${r.suggestions.join(' / ')}` : ''}`;
  const list = uniq.map(entry).join(', ');
  if (policy === 'error') {
    box.className = 'guard-banner guard-error';
    box.dataset.policy = 'error';
    box.append(
      el('div', { class: 'guard-title' }, `Synthesis blocked: ${rejected.length} symbol${rejected.length > 1 ? 's' : ''} outside the engine inventory (${list})`),
      el('div', { class: 'guard-hint', text: 'The engine tokenizer (longest match over ALL_PHONEME_KEYS) would silently drop these symbols. Fix the red symbols, strip them, or set the guard policy to “warn”. Arrows (→) suggest engine-SAMPA replacements.' }),
      el('div', { class: 'guard-actions' },
        el('button', { class: 'btn btn-sm', id: 'btn-strip', text: 'Strip rejected symbols' }),
        el('button', { class: 'btn btn-sm', id: 'btn-warn-policy', text: 'Switch policy to warn' })),
    );
    $('#btn-strip').addEventListener('click', onStrip);
    $('#btn-warn-policy').addEventListener('click', onWarnPolicy);
  } else if (policy === 'warn') {
    box.className = 'guard-banner guard-warn';
    box.dataset.policy = 'warn';
    box.append(
      el('div', { class: 'guard-title' }, `SAMPA guard warning: ${rejected.length} symbol${rejected.length > 1 ? 's' : ''} will be dropped (${list})`),
      el('div', { class: 'guard-hint', text: 'Policy is “warn”: synthesis proceeds and the engine drops the red symbols.' }));
  } else {
    box.className = 'guard-banner guard-off';
    box.dataset.policy = 'off';
    box.append(
      el('div', { class: 'guard-title' }, `Guard off — ${rejected.length} unknown symbol${rejected.length > 1 ? 's' : ''} still displayed in red (${list})`),
      el('div', { class: 'guard-hint', text: 'The string is sent to the engine exactly as written — the engine defines what happens to unknown symbols. The console still shows what the tokenizer would drop.' }));
  }
}

/* ── inventory popover ──────────────────────────────────────────────── */
export function renderInventory(digest, vowels, consonants) {
  const pop = $('#inventory-pop');
  pop.innerHTML = '';
  const close = el('button', { class: 'pop-close', text: '×', onclick: () => { pop.style.display = 'none'; } });
  pop.append(el('div', { class: 'pop-title' }, 'Engine inventory — ALL_PHONEME_KEYS', close));
  pop.append(el('div', { class: 'pop-sub', text: `vowels (ρ ≤ 1 in the polar plane)${digest?.count ? ` · ${digest.count} symbols total` : ''}` }),
    el('div', { class: 'inv-row' }, vowels.map((v) => el('span', { class: 'tok tok-word mono', text: v }))));
  pop.append(el('div', { class: 'pop-sub', text: 'consonants (closures at ρ 1.0–1.45)' }),
    el('div', { class: 'inv-row' }, consonants.map((c) => el('span', { class: 'tok tok-word mono', text: c }))));
  pop.append(el('div', { class: 'pop-sub', text: 'markers (engine syntax, never rejected)' }),
    el('div', { class: 'inv-row' }, ['. ␣ | % ~'].map((m) => el('span', { class: 'tok tok-pause mono', text: m }))));
  pop.append(el('div', { class: 'pop-note', text: 'Any other symbol is rejected by the guard and painted red in the final SAMPA. Nasalized vowels (a~, E~, O~, …) are vowel + the “~” nasality marker.' }));
}

/* ── synthesis progress (slim strip under the action bar) ──────────── */
export function renderProgress({ stage, state, progress, polarReady, wavReady }) {
  const bar = $('#job-bar');
  const label = $('#job-label');
  const strip = $('#job-strip');
  if (!bar) return;
  strip.dataset.state = state || 'idle';
  bar.style.width = (state === 'done' ? 100 : Math.round((progress || 0) * 100)) + '%';
  const names = { g2p: 'G2P', trajectory: 'trajectory', vtl: 'VTL', wav: 'WAV', video: 'MP4' };
  const flags = [polarReady ? 'polar✓' : null, wavReady ? 'wav✓' : null].filter(Boolean).join(' ');
  label.textContent = `${names[stage] || stage || ''}${flags ? ' · ' + flags : ''}`;
  strip.querySelectorAll('.job-stage').forEach((s) => {
    const order = ['g2p', 'trajectory', 'vtl', 'wav', 'video'];
    const idx = order.indexOf(s.dataset.stage), act = order.indexOf(stage);
    if (state === 'done' || idx < act) s.dataset.state = 'done';
    else if (s.dataset.stage === stage) s.dataset.state = state === 'active' ? 'active' : state;
    else s.dataset.state = 'idle';
  });
}

/* ── result summary chips ───────────────────────────────────────────── */
export function renderResult({ duration, frames, phrases, warnings, live, source, cached, anchors, blocks }) {
  const box = $('#result-summary');
  if (!box) return;
  box.innerHTML = '';
  const items = [
    duration != null ? el('span', { class: 'res-item' }, el('strong', { text: duration.toFixed(2) + ' s' }), ' audio') : null,
    anchors ? el('span', { class: 'res-item' }, el('strong', { text: String(anchors.length) }), ` anchors · ${blocks} blocks`) : null,
    frames ? el('span', { class: 'res-item' }, el('strong', { text: String(frames) }), ' frames @ 400 Hz') : null,
    phrases ? el('span', { class: 'res-item' }, el('strong', { text: String(phrases) }), ` phrase${phrases > 1 ? 's' : ''}`) : null,
    source ? el('span', { class: 'res-item res-src', text: source === 'sampa' ? 'from edited SAMPA · use_g2p=False' : 'from text · G2P' }) : null,
    cached ? el('span', { class: 'res-item res-cache', 'data-tip': 'Identical parameters — replayed from cache without engine work', text: 'cache hit' }) : null,
    warnings && warnings.length ? el('span', { class: 'res-item res-warn', text: `${warnings.length} warning${warnings.length > 1 ? 's' : ''}` }) : null,
    el('span', { class: `res-item badge-${live ? 'live' : 'demo'}`, text: live ? 'live engine' : 'demo renderer' }),
  ];
  items.filter(Boolean).forEach((i) => box.append(i));
}

/* ── downloads menu (transport) ─────────────────────────────────────── */
export function renderDownloads(box, files, { live, onDownload }) {
  box.innerHTML = '';
  if (!files || !files.length) {
    box.append(el('div', { class: 'dl-empty dim', text: 'No artifacts yet — synthesize first.' }));
    return;
  }
  for (const f of files) {
    box.append(el('button', {
      class: 'dl-item', disabled: f.available === false ? '' : null,
      'data-tip': f.available === false
        ? (live ? 'Not produced for this job (audio-only output).' : 'Produced by the Python backend (vtl-synth run) — start server.py.')
        : `Download ${f.name}`,
      onclick: () => f.available !== false && onDownload(f),
    },
      el('span', { class: 'dl-kind mono', text: f.kind }),
      el('span', { class: 'dl-name mono', text: f.name }),
      f.size ? el('span', { class: 'dl-size', text: f.size }) : null));
  }
}

/* ── examples & history ─────────────────────────────────────────────── */
export function renderExamples(examples, onPick) {
  const box = $('#examples');
  if (!box) return;
  box.innerHTML = '';
  for (const ex of examples) {
    box.append(el('button', { class: 'chip chip-btn', text: ex.label, onclick: () => onPick(ex) }));
  }
}

export function renderHistory(items, onRestore) {
  const box = $('#history-list');
  if (!box) return;
  box.innerHTML = '';
  if (!items.length) { box.append(el('div', { class: 'dim', text: 'No syntheses yet in this session.' })); return; }
  for (const h of items.slice(0, 14)) {
    box.append(el('div', {
      class: 'history-item', 'data-tip': h.sampa.slice(0, 120), onclick: () => onRestore(h),
    },
      el('span', { class: 'hist-time', text: h.time }),
      el('span', { class: 'hist-text', text: h.text.slice(0, 46) }),
      el('span', { class: 'hist-meta', text: `${h.lang}·${h.speaker}${h.expressive ? '·expr' : ''} · ${(h.duration || 0).toFixed(2)} s` })));
  }
}
