// SPDX-FileCopyrightText: 2026 Frédéric Berthommier
// SPDX-License-Identifier: GPL-3.0-or-later
/* app.js — COVTL Lab Console v3 controller.
 *
 * Implements the design brief's state machine (ch. 11) over the v3
 * machinery: language-first preview loop, live red-reject guard, explicit
 * synthesis with the two readiness flags (polar_ready → the continuous
 * display starts on its own clock; wav_ready → clean handoff to the audio
 * clock at the next block boundary), anchor-stepping transport, and the
 * syllable block compiler panel.
 *
 * The Python engine (through server.py) stays the single source of truth;
 * this file only owns presentation, transport and shortcuts.
 */
import { api, cacheInfo, clearDemoCaches } from './api.js';
import * as R from './render.js';
import {
  LANGUAGES, SPEAKERS, VOWELS, CONSONANTS, EXAMPLES,
} from './data.js';
import { PolarStage } from './polar.js';
import { SpectrogramView } from './spectrogram.js';
import { SyllableCompiler, stretchLabel } from './compiler.js';

const SETTINGS_KEY = 'covtl.settings.v3';
const HISTORY_KEY = 'covtl.history.v1';      // preserved from v2
const MAX_CHARS = 2000;

const state = {
  appState: 'empty',          // brief table 11.1
  mode: 'ortho',              // ortho | phonetic
  lang: 'en',
  speaker: 'jd3',
  f0: null, f0Edited: false,
  timings: { ...LANGUAGES.en.timings },
  customTimings: false,
  expressive: false,
  engine: 'syl',
  ortho: true,
  guardPolicy: 'warn',        // brief §2.5 default
  outputMode: 'audio',
  displayPolar: true,
  displaySpec: true,
  exports: false,
  outDir: 'out',
  outLabel: '',
  sources: { ortho: 'this is easy for us', phonetic: 'ba da ga | iowa a g' },
  lastPreviewed: null,        // input the current preview stack represents
  preview: null,
  editedSampa: null,
  sampaTokens: [],
  sampaRejected: [],
  job: { id: null, running: false, cancel: null },
  result: null,
  polar: null,
  history: [],
};

let polarStage, spec, compiler;
let previewSeq = 0;
let convertTimer = null;
const $ = R.$, $$ = R.$$;

/* ═══════════════════════ init ═══════════════════════ */
async function init() {
  loadSettings();
  buildStatic();
  bindControls();
  bindTransport();
  bindShortcuts();
  polarStage = new PolarStage($('#polar-container'), {
    onTick: onPolarTick,
    onTogglePlay: () => togglePlay(),
  });
  window.__polar = polarStage;      // debug handle (console inspection)
  spec = new SpectrogramView($('#spec-container'), { onSeek: (t) => seekTime(t) });
  compiler = new SyllableCompiler($('#compiler-root'), {
    api,
    getTimings: () => state.timings,
    getGuardPolicy: () => state.guardPolicy,
    getLang: () => state.lang,
    onSendToInput: (sampa) => useInPhoneticInput(sampa),
    onSeekSegment: (idx) => seekSegment(idx),
    onLog: (m) => R.log(m),
  });
  const mode = await api.probe();
  setBackendChip();
  if (mode === 'demo') $('#demo-banner').style.display = '';
  applyStateToControls();
  updateDerived();
  await convert();
  // step 2 auto-follows step 1 (maybeAutoCompile in convert) — no fixed
  // initial compile string here
  // the very first tab load after a bridge restart can race the server's
  // first-response warm-up — re-probe in the background and upgrade to
  // live (re-running the flows) without requiring the user to hit Retry
  if (mode === 'demo' && location.protocol !== 'file:') {
    for (const delay of [2000, 6000, 15000]) {
      setTimeout(async () => {
        if (api.mode !== 'demo') return;
        await api.probe();
        if (api.mode === 'live') {
          setBackendChip();
          previewCacheBust();
          await convert();
          R.log('backend came online — live engine engaged (auto-retry)');
        }
      }, delay);
    }
  }
  setInterval(refreshBackend, 15000);
}

function previewCacheBust() {
  // demo-mode previews must not shadow live ones
  clearDemoCaches();
}

/* ═══════════════════════ static UI ═══════════════════════ */
function buildStatic() {
  const langSel = $('#sel-lang');
  for (const [code, l] of Object.entries(LANGUAGES)) {
    langSel.append(new Option(`${code} — ${l.display}`, code));
  }
  const spkSel = $('#sel-speaker');
  for (const s of SPEAKERS) {
    spkSel.append(new Option(`${s.id} — ${s.name} · f0 ${s.f0.toFixed(1)} Hz`, s.id));
  }
  R.renderExamples(EXAMPLES, (ex) => pickExample(ex));
  const guardSeg = $('#guard-seg');
  guardSeg.querySelectorAll('button').forEach((b) => {
    b.classList.toggle('active', b.dataset.policy === state.guardPolicy);
  });
  const modeSeg = $('#mode-toggle');
  modeSeg.querySelectorAll('button').forEach((b) => {
    b.classList.toggle('active', b.dataset.mode === state.mode);
  });
  buildHelp();
}

function buildHelp() {
  const body = $('#help-body');
  body.innerHTML = '';
  const row = (k, v) => R.el('tr', {}, R.el('kbd', { class: 'mono', text: k }), R.el('td', { text: v }));
  body.append(
    R.el('h3', { text: 'Keyboard map' }),
    R.el('table', { class: 'keys-table' },
      row('Space / K', 'Play or pause'),
      row('Shift + S', 'Stop (back to start)'),
      row('[ / ]', 'Previous / next anchor'),
      row('L', 'Loop the current block'),
      row('0 / 1 / 2 / 3', 'Speed 0.25× / 0.5× / 1× / 2×'),
      row('P', 'Preview the engine\'s input (G2P + enrichment + guard — never makes sound)'),
      row('S', 'Synthesize from the current source'),
      row('E', 'Synthesize from the edited SAMPA'),
      row('C', 'Focus the syllable compiler (Enter compiles)'),
      row('D', 'Downloads menu'),
      row('R', 'Reset the input — clears both panes and the whole preview chain (drafts, preview, edited SAMPA, guard results)'),
      row('Esc', 'Cancel a running synthesis / stop playback'),
      row('?', 'This overlay')),
    R.el('h3', { text: 'New in v3' }),
    R.el('ul', { class: 'help-list' },
      R.el('li', { text: 'Continuous polar display — the drawing head advances anchor by anchor through the real syltraj trajectory; it starts on its own clock while the WAV renders, then re-syncs to the audio clock at the next block boundary.' }),
      R.el('li', { text: 'Syllable compiler — “Compile structure” asks the engine to decompose a syllable string into its real anchor→anchor plan (anchors, blocks, (ρ, θ) targets, durations). It never synthesizes; after inspecting, send the string to the phonetic input or press Synthesize to hear it.' }),
      R.el('li', { text: 'Anchor overlay on the spectrogram — the same ticks as the scrub bar, straight from the engine.' }),
      R.el('li', { text: 'Brief endpoints: /api/health, /api/languages, /api/speakers, /api/compile, /api/job/{id}/polar.' })),
  );
}

/* ═══════════════════════ settings ═══════════════════════ */
function saveSettings() {
  const s = {
    mode: state.mode, lang: state.lang, speaker: state.speaker,
    f0: state.f0Edited ? state.f0 : null,
    timings: state.customTimings ? state.timings : null,
    expressive: state.expressive, engine: state.engine, ortho: state.ortho,
    guardPolicy: state.guardPolicy, outputMode: state.outputMode,
    displayPolar: state.displayPolar, displaySpec: state.displaySpec,
    exports: state.exports, outDir: state.outDir, outLabel: state.outLabel,
    sources: state.sources,
  };
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
}

function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
    if (s.mode) state.mode = s.mode;
    if (s.lang && LANGUAGES[s.lang]) { state.lang = s.lang; state.timings = { ...LANGUAGES[s.lang].timings }; }
    if (s.speaker) state.speaker = s.speaker;
    if (s.f0) { state.f0 = s.f0; state.f0Edited = true; }
    if (s.timings) { state.timings = s.timings; state.customTimings = true; }
    for (const k of ['expressive', 'engine', 'ortho', 'outputMode', 'displayPolar', 'displaySpec', 'exports', 'outDir', 'outLabel']) {
      if (s[k] !== undefined && s[k] !== null) state[k] = s[k];
    }
    if (s.guardPolicy) state.guardPolicy = s.guardPolicy;
    if (s.sources) state.sources = { ...state.sources, ...s.sources };
  } catch { /* fresh start */ }
  try { state.history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch { state.history = []; }
  R.renderHistory(state.history, restoreHistory);
}

function pushHistory(payload, result, source) {
  state.history.unshift({
    time: new Date().toLocaleTimeString('en-US', { hour12: false }),
    text: payload.text.slice(0, 60), sampa: result.sampa, lang: payload.lang,
    speaker: payload.speaker, expressive: payload.expressive,
    duration: result.duration, source, cached: !!result.cached,
  });
  state.history = state.history.slice(0, 30);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history));
  R.renderHistory(state.history, restoreHistory);
}

function restoreHistory(h) {
  if (state.mode === 'ortho') { state.sources.ortho = h.text; $('#text-input').value = h.text; }
  else { state.sources.phonetic = h.sampa; $('#phonetic-input').value = h.sampa; }
  convert();
}

/* ═══════════════════════ controls binding ═══════════════════════ */
function bindControls() {
  $('#sel-lang').addEventListener('change', (e) => {
    state.lang = e.target.value;
    if (!state.customTimings) state.timings = { ...LANGUAGES[state.lang].timings };
    updateDerived();
    saveSettings();
    debouncedConvert();
  });
  $('#sel-speaker').addEventListener('change', (e) => {
    state.speaker = e.target.value;
    if (!state.f0Edited) state.f0 = null;
    updateDerived();
    saveSettings();
    debouncedConvert();
  });
  $('#num-f0').addEventListener('change', (e) => {
    const v = parseFloat(e.target.value);
    if (Number.isFinite(v)) {
      state.f0 = Math.max(60, Math.min(350, v));
      state.f0Edited = true;
    }
    updateDerived();
    saveSettings();
  });
  $('#btn-f0-reset').addEventListener('click', () => {
    state.f0 = null; state.f0Edited = false;
    updateDerived();
    saveSettings();
  });

  // input mode
  $('#mode-toggle').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-mode]');
    if (!b) return;
    state.mode = b.dataset.mode;
    $$('#mode-toggle button').forEach((x) => x.classList.toggle('active', x === b));
    updateInputVisibility();
    saveSettings();
    convert();
  });
  $('#text-input').addEventListener('input', () => onSourceInput());
  $('#phonetic-input').addEventListener('input', () => onSourceInput());
  for (const id of ['#text-input', '#phonetic-input']) {
    $(id).addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); convert(); }
      e.stopPropagation();
    });
  }

  // timings sliders
  for (const key of ['tcons', 'tvoy', 'tpause', 'tpauseLong']) {
    const range = $(`#st-${key}`);
    const val = $(`#st-${key}-val`);
    range.addEventListener('input', () => {
      state.timings[key] = parseInt(range.value, 10);
      state.customTimings = true;
      val.textContent = range.value;
      range.classList.add('custom');
      $('#timings-profile').style.display = '';
      saveSettings();
    });
    range.addEventListener('change', () => {
      saveSettings();
      // live recompile of the compiler panel when its string matches
      if (compiler?.result?.sampa && compiler.input.value === compiler.result.sampa) {
        compiler.compile().catch(() => {});
      }
    });
  }
  $('#btn-timings-reset').addEventListener('click', () => {
    state.timings = { ...LANGUAGES[state.lang].timings };
    state.customTimings = false;
    updateDerived();
    saveSettings();
  });
  $('#btn-reset-input').addEventListener('click', resetInputs);

  $('#chk-expressive').addEventListener('change', (e) => {
    state.expressive = e.target.checked;
    $('#breath-ms').textContent = state.expressive ? '≈130 ms' : '— (expressive off)';
    saveSettings();
    convert();
  });
  $('#sel-engine').addEventListener('change', (e) => {
    state.engine = e.target.value;
    $('#legacy-note').style.display = state.engine === 'legacy' ? '' : 'none';
    saveSettings();
  });
  $('#chk-ortho').addEventListener('change', (e) => { state.ortho = e.target.checked; saveSettings(); });
  $('#chk-polar-display').addEventListener('change', (e) => {
    state.displayPolar = e.target.checked;
    $('#zone-polar').style.display = state.displayPolar ? '' : 'none';
    saveSettings();
  });
  $('#chk-spec').addEventListener('change', (e) => {
    state.displaySpec = e.target.checked;
    $('#zone-spec').style.display = state.displaySpec ? '' : 'none';
    saveSettings();
  });
  $('#chk-exports').addEventListener('change', (e) => { state.exports = e.target.checked; saveSettings(); });
  $$('input[name="outmode"]').forEach((r) => r.addEventListener('change', (e) => {
    state.outputMode = e.target.value;
    saveSettings();
  }));
  $('#out-dir').addEventListener('input', (e) => { state.outDir = e.target.value || 'out'; updateOutResolved(); saveSettings(); });
  $('#out-label').addEventListener('change', (e) => { state.outLabel = e.target.value; saveSettings(); });

  // guard policy
  $('#guard-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-policy]');
    if (!b) return;
    state.guardPolicy = b.dataset.policy;
    $$('#guard-seg button').forEach((x) => x.classList.toggle('active', x === b));
    applyGuard();
    saveSettings();
  });

  // header chips
  $('#chip-lang').addEventListener('click', () => { $('#sel-lang').focus(); });
  $('#chip-speaker').addEventListener('click', () => { $('#sel-speaker').focus(); });
  $('#chip-backend').addEventListener('click', toggleHealthDrawer);
  $('#btn-help').addEventListener('click', () => { $('#help-overlay').style.display = ''; });
  $('#btn-help-close').addEventListener('click', () => { $('#help-overlay').style.display = 'none'; });
  $('#help-overlay').addEventListener('click', (e) => {
    if (e.target.id === 'help-overlay') $('#help-overlay').style.display = 'none';
  });
  $('#btn-retry').addEventListener('click', async () => {
    await api.probe();
    setBackendChip();
    clearDemoCaches();
    convert();
  });
  $('#btn-inventory').addEventListener('click', () => {
    const pop = $('#inventory-pop');
    R.renderInventory(null, VOWELS, CONSONANTS);
    pop.style.display = pop.style.display === 'none' ? '' : 'none';
  });

  // preview editing of the final SAMPA
  $('#btn-sampa-edit').addEventListener('click', openSampaEditor);
  $('#btn-sampa-apply').addEventListener('click', applySampaEdit);
  $('#btn-sampa-cancel').addEventListener('click', closeSampaEditor);
  $('#btn-sampa-revert').addEventListener('click', () => {
    state.editedSampa = null;
    closeSampaEditor();
    if (state.preview) state.sampaTokens = state.preview.tokens;
    if (state.preview) state.sampaRejected = state.preview.rejected;
    renderPreviewStack();
  });
  $('#sampa-edit').addEventListener('input', debouncedGuardCheck);
  $('#sampa-edit').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); applySampaEdit(); }
    e.stopPropagation();
  });

  // action bar
  $('#btn-preview').addEventListener('click', () => convert());
  $('#btn-synth').addEventListener('click', () => synthesize('auto'));
  $('#btn-synth-edit').addEventListener('click', () => synthesize('edited'));
  $('#btn-cancel').addEventListener('click', cancelSynthesis);

  // spectrogram toolbar
  $('#btn-f0').addEventListener('click', () => {
    const on = !spec.showF0;
    spec.toggleF0(on);
    $('#btn-f0').classList.toggle('on', on);
  });
  $('#btn-spec-png').addEventListener('click', async () => {
    const blob = await spec.exportPng();
    downloadBlob(blob, 'covtl-spectrogram.png');
  });
  $('#btn-history-clear').addEventListener('click', () => {
    state.history = [];
    localStorage.setItem(HISTORY_KEY, '[]');
    R.renderHistory(state.history, restoreHistory);
  });
}

function bindTransport() {
  $('#btn-play').addEventListener('click', () => togglePlay());
  $('#btn-stop').addEventListener('click', () => stopPlayback());
  $('#btn-prev-anchor').addEventListener('click', () => polarStage?.prevAnchor());
  $('#btn-next-anchor').addEventListener('click', () => polarStage?.nextAnchor());
  $('#btn-loop').addEventListener('click', () => {
    const on = !(polarStage?.loopBlock);
    polarStage?.setLoop(on);
    $('#btn-loop').classList.toggle('on', on);
  });
  $$('#speed-seg button').forEach((b) => b.addEventListener('click', () => setSpeed(b.dataset.speed)));
  $('#btn-downloads').addEventListener('click', () => {
    const menu = $('#dl-menu');
    menu.style.display = menu.style.display === 'none' ? '' : 'none';
  });
  // scrub bar
  const track = $('#scrub-track');
  let scrubbing = false;
  const scrubTo = (e) => {
    if (!polarStage?.hasData()) return;
    const r = track.getBoundingClientRect();
    const u = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    seekTime(u * polarStage._duration());
  };
  track.addEventListener('pointerdown', (e) => { scrubbing = true; track.setPointerCapture(e.pointerId); scrubTo(e); });
  track.addEventListener('pointermove', (e) => { if (scrubbing) scrubTo(e); });
  track.addEventListener('pointerup', () => { scrubbing = false; });
}

/* ═══════════════════════ derived UI ═══════════════════════ */
function applyStateToControls() {
  $('#sel-lang').value = state.lang;
  $('#sel-speaker').value = state.speaker;
  $('#text-input').value = state.sources.ortho;
  $('#phonetic-input').value = state.sources.phonetic;
  $('#chk-expressive').checked = state.expressive;
  $('#sel-engine').value = state.engine;
  $('#chk-ortho').checked = state.ortho;
  $('#chk-polar-display').checked = state.displayPolar;
  $('#chk-spec').checked = state.displaySpec;
  $('#chk-exports').checked = state.exports;
  $(`input[name="outmode"][value="${state.outputMode}"]`).checked = true;
  $('#out-dir').value = state.outDir;
  $('#out-label').value = state.outLabel;
  $$('#guard-seg button').forEach((b) => b.classList.toggle('active', b.dataset.policy === state.guardPolicy));
  $$('#mode-toggle button').forEach((b) => b.classList.toggle('active', b.dataset.mode === state.mode));
  $('#zone-polar').style.display = state.displayPolar ? '' : 'none';
  $('#zone-spec').style.display = state.displaySpec ? '' : 'none';
  updateInputVisibility();
  updateDerived();
  updateCounters();
}

function updateInputVisibility() {
  $('#text-input').style.display = state.mode === 'ortho' ? '' : 'none';
  $('#phonetic-input').style.display = state.mode === 'phonetic' ? '' : 'none';
  $('#draft-note').textContent = state.mode === 'ortho'
    ? 'phonetic draft kept' : 'orthographic draft kept';
}

function updateCounters() {
  const src = state.mode === 'ortho' ? state.sources.ortho : state.sources.phonetic;
  const n = (src || '').length;
  const el = $('#input-count');
  el.textContent = `${n} / ${MAX_CHARS} chars`;
  el.classList.toggle('over', n > MAX_CHARS);
}

function updateDerived() {
  // header chips
  const L = LANGUAGES[state.lang];
  $('#chip-lang').textContent = `${state.lang.toUpperCase()} — ${L.display}`;
  const spk = SPEAKERS.find((s) => s.id === state.speaker) || SPEAKERS[0];
  const f0 = state.f0 ?? spk.f0;
  $('#chip-speaker').textContent = `${spk.id} · f0 ${f0.toFixed(1)} Hz`;
  $('#num-f0').value = f0.toFixed(1);
  $('#speaker-warn').style.display = (state.lang !== 'en' && state.speaker !== 'jd3') ? '' : 'none';
  $('#breath-ms').textContent = state.expressive ? '≈130 ms' : '— (expressive off)';
  // timings sliders
  const d = LANGUAGES[state.lang].timings;
  for (const key of ['tcons', 'tvoy', 'tpause', 'tpauseLong']) {
    const range = $(`#st-${key}`);
    range.value = state.timings[key];
    $(`#st-${key}-val`).textContent = state.timings[key];
    range.classList.toggle('custom', state.timings[key] !== d[key]);
  }
  $('#timings-profile').textContent =
    `profile ${state.lang}: Tcons ${d.tcons} / Tvoy ${d.tvoy} / tpause ${d.tpause} / tpause-long ${d.tpauseLong}`;
  $('#timings-profile').style.display = state.customTimings ? '' : 'none';
  updateOutResolved();
}

/* show where artifacts really land — 'out' is relative to the bridge */
function updateOutResolved() {
  const root = api.status?.out_root;
  const el = $('#out-resolved');
  if (el) el.textContent = `artifacts → ${root ? root + '\\' : '(bridge) '}${state.outDir}\\`;
}

function updateSynthButtons() {
  const rej = state.sampaRejected.length;
  const hasPhonetic = state.sampaTokens.some((t) => t.kind === 'vowel' || t.kind === 'consonant');
  const btn = $('#btn-synth');
  const btnE = $('#btn-synth-edit');
  const editedDiffers = state.editedSampa !== null
    && state.editedSampa !== (state.preview ? state.preview.final : null);
  if (state.job.running) {
    btn.disabled = true;
    btn.textContent = '⏳ Synthesizing…';
    btnE.disabled = true;
  } else if (state.previewBusy) {
    // coordination: a preview in flight must complete before synthesis —
    // the synthesized string is the preview/compile output
    btn.disabled = true;
    btn.textContent = '⏳ Synthesize — preview in flight…';
    btnE.disabled = true;
  } else if (!hasPhonetic) {
    btn.disabled = true;
    btn.textContent = 'Synthesize — no phonetic content';
    btnE.disabled = true;
  } else if (state.guardPolicy === 'error' && rej > 0) {
    btn.disabled = true;
    btn.textContent = `Synthesize — blocked by guard (${rej} red)`;
    btnE.disabled = true;
  } else if (state.guardPolicy === 'warn' && rej > 0) {
    btn.disabled = false;
    btn.textContent = `Synthesize anyway (${rej} symbol${rej > 1 ? 's' : ''} dropped)`;
    btnE.disabled = !editedDiffers;
  } else {
    btn.disabled = false;
    btn.textContent = 'Synthesize from preview';
    btnE.disabled = !editedDiffers;
  }
  btnE.title = editedDiffers ? 'Use the edited final SAMPA (use_g2p=False)' : 'Enabled when the final SAMPA row is edited';
}

const PREVIEW_STATES = new Set(['empty', 'preview-ready', 'guard-warn', 'guard-error', 'backend-offline']);

function setPreviewState(s) {
  // a late preview response must never downgrade a running job's state
  if (PREVIEW_STATES.has(state.appState)) setAppState(s);
}

function finalSampaOf() {
  return state.editedSampa ?? state.preview?.final ?? '';
}

/* ═══════════════════════ input reset ═══════════════════════ */
/* One action clears BOTH input panes (orthographic + phonetic) and every
 * state of the preview chain: drafts, preview stack, edited SAMPA, guard
 * results. Without it, stale state leaks across modes — an edited SAMPA
 * keeps steering synthesis after you switch panes, and an ortho draft
 * blocks a fresh phonetic start (observed: typing "ba da ga" ortho-wise
 * stuck the chain at the G2P's "ba.da" while a previously edited SAMPA
 * silently kept steering). Language, speaker, timings, results, history
 * and the display are untouched. */
function resetInputs() {
  clearTimeout(convertTimer);
  convertTimer = null;
  previewSeq++;                        // any in-flight preview response is dropped
  state.sources = { ortho: '', phonetic: '' };
  state.lastPreviewed = null;
  state.preview = null;
  state.editedSampa = null;
  state.sampaTokens = [];
  state.sampaRejected = [];
  $('#text-input').value = '';
  $('#phonetic-input').value = '';
  $('#sampa-edit-wrap').style.display = 'none';
  $('#g2p-words').innerHTML = '';
  $('#preview-status').textContent = '';
  renderPreviewStack();                // empty → placeholders, state 'empty'
  updateCounters();
  saveSettings();
  R.log('input reset — both panes and the preview chain cleared (R)');
}

/* ═══════════════════════ preview flow ═══════════════════════ */
/* Preview fires on a COMPLETE unit only: a word/syllable boundary in the
 * input (space, punctuation, `.` `|` `%`), or the Preview button (P).
 * It never runs mid-word on every keystroke. */
function onSourceInput() {
  state.sources.ortho = $('#text-input').value;
  state.sources.phonetic = $('#phonetic-input').value;
  updateCounters();
  saveSettings();
  if (!$('#auto-preview').checked) return;
  const src = (state.mode === 'ortho' ? state.sources.ortho : state.sources.phonetic) || '';
  if (endsWithUnitBoundary(src)) debouncedConvert(250);
}

function endsWithUnitBoundary(s) {
  const t = s.replace(/\s+$/, '');
  if (!t) return false;
  // word/syllable end: space, punctuation, or an engine marker
  return /[ .,;:!?|%|\-]$/.test(t) || /\s$/.test(s);
}

function debouncedConvert(delay = 400) { clearTimeout(convertTimer); convertTimer = setTimeout(convert, delay); }

async function convert() {
  const seq = ++previewSeq;
  const src = (state.mode === 'ortho' ? state.sources.ortho : state.sources.phonetic) || '';
  if (!src.trim()) { renderPreviewStack(); return; }
  if (src.length > MAX_CHARS) return;
  // immediate feedback — under slow links the user must see the request
  // is in flight (the "nothing happens, then it lands later" bug)
  const btnP = $('#btn-preview');
  btnP.disabled = true;
  const oldLabel = btnP.textContent;
  btnP.textContent = '⏳ Previewing…';
  $('#preview-status').textContent = '⏳ previewing — G2P + guard in flight…';
  state.previewBusy = true;
  updateSynthButtons();
  try {
    const out = await api.preview({
      text: src, mode: state.mode === 'ortho' ? 'ortho' : 'phonetic',
      lang: state.lang, expressive: state.expressive,
    });
    if (seq !== previewSeq) return;      // stale response guard
    state.preview = out;
    state.lastPreviewed = src;           // what the preview stack represents
    state.sampaTokens = out.tokens;
    state.sampaRejected = out.rejected;
    if (state.editedSampa !== null) {
      await guardRefreshEdited();
    }
    renderPreviewStack();
    // step 2 follows step 1 — the compiler panel tracks the final SAMPA
    compiler?.maybeAutoCompile(finalSampaOf());
    if (out.cached) R.log('preview cache hit');
  } catch (err) {
    if (seq === previewSeq) showError(err, 'Preview failed');
  } finally {
    if (seq === previewSeq) {
      btnP.disabled = false;
      btnP.textContent = oldLabel;
      state.previewBusy = false;
      updateSynthButtons();
    }
  }
}

function renderPreviewStack() {
  const p = state.preview;
  const g2pRow = $('#row-g2p-value');
  const enrRow = $('#row-enriched-value');
  const samRow = $('#row-sampa-value');
  g2pRow.innerHTML = ''; enrRow.innerHTML = ''; samRow.innerHTML = '';
  $('#badge-sampa-edited').style.display = state.editedSampa !== null ? '' : 'none';

  if (!p) {
    g2pRow.append(R.el('span', { class: 'dim', text: '—' }));
    enrRow.append(R.el('span', { class: 'dim', text: '—' }));
    samRow.append(R.el('span', { class: 'dim', text: 'type text or phonetics, then press Preview' }));
    setPreviewState('empty');
    updateSynthButtons();
    return;
  }
  if (state.mode === 'phonetic') {
    g2pRow.append(R.el('span', { class: 'dim', text: 'not applicable — direct phonetic input' }));
  } else if (p.g2pString) {
    g2pRow.append(R.sampaPlain(p.g2pString));
  }
  $('#preview-status').textContent =
    '✓ guard checked — nothing synthesized · press Synthesize to hear this string';
  enrRow.append(R.sampaTokens(p.tokens, []));
  samRow.append(R.sampaTokens(state.sampaTokens, state.sampaRejected));
  // word chips (unknown words) under the G2P row
  const wbox = $('#g2p-words');
  wbox.innerHTML = '';
  if (p.words && p.words.length && state.mode === 'ortho') {
    for (const w of p.words) {
      wbox.append(R.el('span', {
        class: `tok tok-word mono ${w.known ? '' : 'tok-unknown'}`, text: w.sampa,
        'data-tip': w.known ? 'lexicon hit' : 'word not in the lexicon — kept verbatim, symbols checked by the guard',
      }));
    }
  }
  // count badge
  const n = state.sampaRejected.length;
  const badge = $('#sampa-count');
  badge.style.display = n ? '' : 'none';
  badge.textContent = `${n} rejected`;
  renderGuardBanner();
  // warnings
  const wwarn = $('#preview-warnings');
  wwarn.innerHTML = '';
  for (const w of p.warnings || []) wwarn.append(R.el('div', { class: 'warn-line', text: `⚠ ${w}` }));

  setPreviewState(n === 0 ? 'preview-ready' : (state.guardPolicy === 'error' ? 'guard-error' : 'guard-warn'));
  updateSynthButtons();
}

function renderGuardBanner() {
  R.renderGuardBanner(state.sampaRejected, state.guardPolicy, stripRejected, () => {
    state.guardPolicy = 'warn';
    $$('#guard-seg button').forEach((x) => x.classList.toggle('active', x.dataset.policy === 'warn'));
    applyGuard();
    saveSettings();
  });
}

function applyGuard() {
  renderGuardBanner();
  updateSynthButtons();
  setPreviewState(state.sampaRejected.length === 0 ? 'preview-ready'
    : (state.guardPolicy === 'error' ? 'guard-error' : 'guard-warn'));
}

async function guardRefreshEdited() {
  const s = state.editedSampa;
  if (s === null) return;
  try {
    const r = await api.checkSampa({ sampa: s });
    state.sampaTokens = r.tokens;
    state.sampaRejected = r.rejected;
  } catch { /* keep previous */ }
}

function debouncedGuardCheck() {
  clearTimeout(debouncedGuardCheck._t);
  debouncedGuardCheck._t = setTimeout(async () => {
    const v = $('#sampa-edit').value;
    const seq = previewSeq;
    try {
      const r = await api.checkSampa({ sampa: v });
      state.editedSampa = v;
      state.sampaTokens = r.tokens;
      state.sampaRejected = r.rejected;
      if (seq === previewSeq) renderPreviewStack();
    } catch { /* ignore transient */ }
  }, 250);
}

function openSampaEditor() {
  const row = $('#row-sampa-value');
  const ta = $('#sampa-edit');
  ta.value = finalSampaOf();
  row.style.display = 'none';
  $('#sampa-edit-wrap').style.display = '';
  $('#btn-sampa-edit').style.display = 'none';
  ta.focus();
}

function closeSampaEditor() {
  $('#row-sampa-value').style.display = '';
  $('#sampa-edit-wrap').style.display = 'none';
  $('#btn-sampa-edit').style.display = '';
}

async function applySampaEdit() {
  const v = $('#sampa-edit').value;
  state.editedSampa = v;
  closeSampaEditor();
  await guardRefreshEdited();
  renderPreviewStack();
}

function stripRejected() {
  const keep = state.sampaTokens.filter((t) => t.kind !== 'rejected').map((t) => t.sym).join('');
  state.editedSampa = keep;
  guardRefreshEdited().then(() => renderPreviewStack());
  R.log(`stripped ${state.sampaRejected.length} rejected symbol(s) — final SAMPA marked edited`);
}

function pickExample(ex) {
  if (ex.lang && LANGUAGES[ex.lang]) {
    state.lang = ex.lang;
    $('#sel-lang').value = ex.lang;
    if (!state.customTimings) state.timings = { ...LANGUAGES[ex.lang].timings };
    updateDerived();
  }
  if (ex.sampa) {
    state.mode = 'phonetic';
    state.sources.phonetic = ex.sampa;
    $('#phonetic-input').value = ex.sampa;
  } else if (ex.text) {
    state.mode = 'ortho';
    state.sources.ortho = ex.text;
    $('#text-input').value = ex.text;
  } else return;
  $$('#mode-toggle button').forEach((b) => b.classList.toggle('active', b.dataset.mode === state.mode));
  updateInputVisibility();
  saveSettings();
  convert();
  if (ex.sampa) compiler?.maybeAutoCompile(ex.sampa);
}

function useInPhoneticInput(sampa) {
  state.mode = 'phonetic';
  state.sources.phonetic = sampa;
  $('#phonetic-input').value = sampa;
  $$('#mode-toggle button').forEach((b) => b.classList.toggle('active', b.dataset.mode === 'phonetic'));
  updateInputVisibility();
  saveSettings();
  convert();
  R.toast('Sent to the phonetic input — previewing', 'info');
}

/* ═══════════════════════ synthesis flow ═══════════════════════ */
/* Synthesis always consumes the PREVIEW/COMPILE output — WYSIWYG by
 * construction: the string you inspected is the string that is spoken.
 *  • ortho path (text unchanged since its preview): the engine recomputes
 *    the same deterministic G2P → identical SAMPA, and expressive prosody
 *    keeps its syntactic structure;
 *  • phonetic path (edited SAMPA, or text drifted from its preview): the
 *    exact previewed/edited string goes through --phonetic (use_g2p=False).
 * Synthesize is DISABLED until a preview exists — everything is visible
 * before it can run. */
function synthPayload(source) {
  // priority 1 — the COMPILER output when the user edited its field: the
  // brief's contract is that Synthesize speaks the compiled structure
  const compilerText = compiler?.input?.value?.trim() ?? '';
  if (compiler?.userEdited && compilerText) {
    return {
      text: compilerText, mode: 'phonetic', lang: state.lang,
      speaker: state.speaker, expressive: state.expressive, f0: state.f0,
      timings: { ...state.timings }, engine: state.engine, ortho: state.ortho,
      outputMode: state.outputMode, guardPolicy: state.guardPolicy,
      outputDir: state.outDir, label: state.outLabel || null,
      exports: state.exports,
      _via: 'phonetic (compiler-edited blocks — your compiled structure)',
    };
  }
  const orthoText = state.sources.ortho || '';
  const orthoIntact = state.mode === 'ortho' && !state.editedSampa
    && state.preview !== null && state.lastPreviewed === orthoText
    && orthoText.trim().length > 0;
  if (source === 'edited' && state.editedSampa !== null) {
    return {
      text: state.editedSampa, mode: 'phonetic', lang: state.lang,
      speaker: state.speaker, expressive: state.expressive, f0: state.f0,
      timings: { ...state.timings }, engine: state.engine, ortho: state.ortho,
      outputMode: state.outputMode, guardPolicy: state.guardPolicy,
      outputDir: state.outDir, label: state.outLabel || null,
      exports: state.exports,
      _via: 'phonetic (the exact edited SAMPA)',
    };
  }
  return {
    text: orthoIntact ? orthoText : finalSampaOf(),
    mode: orthoIntact ? 'ortho' : 'phonetic',
    lang: state.lang,
    speaker: state.speaker,
    expressive: state.expressive,
    f0: state.f0,
    timings: { ...state.timings },
    engine: state.engine,
    ortho: state.ortho,
    outputMode: state.outputMode,
    guardPolicy: state.guardPolicy,
    outputDir: state.outDir,
    label: state.outLabel || null,
    exports: state.exports,
    _via: orthoIntact ? 'ortho (G2P deterministic — same SAMPA as preview)' : 'phonetic (the exact previewed/edited SAMPA)',
  };
}

async function synthesize(source) {
  if (state.job.running) return;
  const payload = synthPayload(source);
  if (!payload.text.trim()) { R.toast('Nothing to synthesize — preview first (P or word end).', 'warn'); return; }
  if (payload.text.length > MAX_CHARS) { R.toast(`Source too long (${payload.text.length} > ${MAX_CHARS} chars).`, 'warn'); return; }
  R.log(`synthesize uses: ${payload._via}`);
  delete payload._via;
  state.job = { id: null, running: true, cancel: { cancelled: false } };
  $('#job-strip').style.display = '';
  $('#btn-cancel').style.display = '';
  setAppState('synthesizing');
  updateSynthButtons();
  $('#polar-status').textContent = `job starting… ${source === 'edited' ? '(from edited SAMPA)' : ''}`;
  R.log(`synthesize ${source === 'edited' ? 'from edited SAMPA (use_g2p=False)' : 'from current source'} · guard=${state.guardPolicy}`);
  try {
    const result = await api.synthesize(payload, {
      onStage: (stage, st, progress) => R.renderProgress({ stage, state: st, progress, polarReady: polarStage?.hasData(), wavReady: false }),
      onLog: (m) => R.log(m),
      onJob: (id) => { state.job.id = id; },
      onPolarReady: (polar) => {
        state.polar = polar;
        polarStage.setPayload(polar);
        buildScrubTicks();
        setAppState('polar-running');
        polarStage.play();          // start-early: own clock at 1×
        $('#polar-status').textContent = 'polar-only — audio still rendering';
        R.log(`trajectory ready: ${polar.segments.length} blocks / ${polar.anchors.length} anchors — display started (polar-only)`);
      },
      cancel: state.job.cancel,
    });
    state.result = result;
    onSynthesisDone(result, payload, source);
  } catch (err) {
    if (err.cancelled) {
      R.log('synthesis cancelled');
    } else {
      showError(err, 'Synthesis failed');
    }
    // never leave the app stuck in "Synthesizing": fall back to the last
    // coherent state (the trajectory if we have one, else the preview)
    if (polarStage?.hasData()) {
      setAppState('polar-running');
      $('#polar-status').textContent = 'polar-only — synthesis failed, trajectory kept';
    } else {
      setAppState(state.sampaRejected.length
        ? (state.guardPolicy === 'error' ? 'guard-error' : 'guard-warn')
        : 'preview-ready');
      $('#job-strip').style.display = 'none';
    }
  } finally {
    state.job.running = false;
    $('#btn-cancel').style.display = 'none';
    updateSynthButtons();
  }
}

function onSynthesisDone(result, payload, source) {
  R.renderProgress({ stage: 'wav', state: 'done', progress: 1, polarReady: true, wavReady: true });
  // audio element
  const audio = $('#audio-el');
  if (result.wavUrl) audio.src = result.wavUrl;
  else if (result.files?.[0]?.blob) audio.src = URL.createObjectURL(result.files[0].blob);
  audio.load();
  // spectrogram — anchors with their labels/kinds + the phonetic units
  // between them (from the engine's segment payload)
  let specSegments = [];
  let specAnchors = [];
  if (result.polar) {
    specAnchors = result.polar.anchors.map((a) => ({ t: a.t, label: a.label, kind: a.kind }));
    specSegments = result.polar.segments.map((s) => {
      const dur = s.t1 - s.t0;
      const sym = unitLabel(s);
      const blocks = s.blocks || [];
      let type = 'segment';
      if (dur < 0.005) type = 'skip';
      else if (blocks.some((b) => b.breath)) type = 'pause-breath';
      else if (blocks.some((b) => b.kind === 'pause' && b.long)) type = 'pause-long';
      else if (blocks.some((b) => b.kind === 'pause')) type = 'pause-short';
      else if (blocks.length === 0) type = 'pause-short';
      return { start: s.t0, end: s.t1, sym, type };
    });
  }
  spec.setSource(result.buffer, specSegments, result.f0Curve || null, specAnchors);
  $('#seg-badge').style.display = '';
  $('#seg-badge').textContent = 'anchor overlay: engine structure';
  // polar payload (cache-hit path may not have fired onPolarReady yet)
  if (result.polar && result.polar !== state.polar) {
    state.polar = result.polar;
    polarStage.setPayload(result.polar);
    buildScrubTicks();
  }
  const wasPlaying = polarStage.playing;
  polarStage.attachAudio(audio, { autoplay: wasPlaying });
  setAppState('ready');
  $('#polar-status').textContent = 'synced to audio clock';
  R.renderResult({
    duration: result.duration, frames: result.frames, phrases: result.phrases,
    warnings: result.warnings, live: result.live, source: source === 'edited' ? 'sampa' : 'text',
    cached: result.cached, anchors: result.polar ? result.polar.anchors : null,
    blocks: result.blockCount,
  });
  R.renderDownloads($('#dl-menu'), result.files, {
    live: result.live,
    onDownload: (f) => {
      if (f.url) window.open(f.url, '_blank');
      else if (f.blob) downloadBlob(f.blob, f.name);
    },
  });
  if (result.sampa) {
    // keep the compiler cards linked to the actual synthesized string —
    // the auto-follow respects a manually edited compiler field
    compiler?.maybeAutoCompile(result.sampa);
  }
  R.log(`done: ${result.duration.toFixed(2)} s · ${result.polar ? result.polar.segments.length + ' blocks' : 'no polar data'}` +
        `${result.cached ? ' · cache hit' : ''}`);
  pushHistory(payload, result, source);
  if (wasPlaying) audio.play().catch(() => {});
}

function cancelSynthesis() {
  if (state.job.running) {
    state.job.cancel.cancelled = true;
    R.log('cancel requested…');
  } else {
    stopPlayback();
  }
}

/* ═══════════════════════ transport ═══════════════════════ */
function togglePlay() {
  if (!polarStage?.hasData()) return;
  polarStage.toggle();
}

function stopPlayback() {
  polarStage?.stop();
  const audio = $('#audio-el');
  try { audio.pause(); audio.currentTime = 0; } catch { /* noop */ }
  setSpeed('1');
}

function setSpeed(s) {
  polarStage?.setSpeed(parseFloat(s));
  $('#audio-el').playbackRate = parseFloat(s);
  $$('#speed-seg button').forEach((b) => b.classList.toggle('active', b.dataset.speed === s));
}

function seekTime(t) {
  polarStage?.seek(t);
  const audio = $('#audio-el');
  if (audio.src) { try { audio.currentTime = t; } catch { /* noop */ } }
}

function seekSegment(idx) {
  const segs = state.polar?.segments;
  if (!segs || !segs.length) {
    R.toast('No polar payload loaded — synthesize first (cards seek the live trajectory).', 'warn');
    return;
  }
  const seg = segs[idx];
  if (!seg) {
    // card from a compile of a different string than the loaded trajectory
    R.toast(`This card belongs to an older compile (${idx + 1}th card) than the loaded trajectory (${segs.length} blocks) — recompiling the synthesized string…`, 'warn');
    if (state.result?.sampa) {
      compiler.setInput(state.result.sampa);
      compiler.compile(state.result.sampa).catch(() => {});
    }
    return;
  }
  seekTime(seg.t0 + 0.005);
  flashSegment(idx);
}

function flashSegment(idx) {
  const track = $('#scrub-track');
  track.classList.remove('flash');
  void track.offsetWidth;      // restart the animation
  track.classList.add('flash');
  compiler?.markPlayingSegment(idx);
}

/* phonetic unit label of an anchor→anchor segment: chronological stretch
 * (clusters and plateaus in engine order, ‿ = coda fused with next onset) */
function unitLabel(seg) {
  return stretchLabel(seg.blocks || []);
}

function onPolarTick(tick) {
  const bEl = $('#polar-block');
  bEl.textContent = tick.blockCount ? `Block ${tick.block + 1} / ${tick.blockCount}` : '—';
  const seg = state.polar?.segments[tick.block];
  $('#polar-anchor').textContent = seg
    ? `anchor A${seg.anchorFrom + 1} → A${seg.anchorTo + 1} (${seg.labelFrom || '·'} → ${seg.labelTo || '·'})` : '—';
  const fmt = (v) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : v.toFixed(2);
  $('#polar-readout').textContent =
    `ρ/θ V ${fmt(tick.rhoV)} · ${tick.thetaV === undefined ? '—' : tick.thetaV.toFixed(0)}°` +
    (tick.rhoC !== null && tick.rhoC !== undefined ? `   C ${fmt(tick.rhoC)} · ${tick.thetaC.toFixed(0)}°` : '');
  $('#polar-time').textContent = `${tick.t.toFixed(2)} / ${(tick.duration || 0).toFixed(2)} s`;
  const modeEl = $('#polar-mode');
  modeEl.textContent = tick.mode === 'synced' ? 'synced · audio clock' : 'polar-only';
  modeEl.className = `polar-mode-badge ${tick.mode === 'synced' ? 'ok' : 'own'}`;
  $('#btn-play').textContent = tick.playing ? 'Pause' : 'Play';
  if (tick.duration) {
    const u = Math.max(0, Math.min(1, tick.t / tick.duration));
    $('#scrub-head').style.left = (u * 100) + '%';
    if (seg) {
      $('#scrub-band').style.left = (seg.t0 / tick.duration * 100) + '%';
      $('#scrub-band').style.width = (Math.max(0.4, (seg.t1 - seg.t0) / tick.duration * 100)) + '%';
    }
  }
  spec.cursor(tick.t);
  compiler?.markPlayingSegment(tick.block);
}

function buildScrubTicks() {
  const track = $('#scrub-ticks');
  track.innerHTML = '';
  const dur = polarStage?._duration() || 0;
  for (const a of polarStage?.payload?.anchors || []) {
    const tick = R.el('div', {
      class: `scrub-tick ${a.kind === 'pause' ? 'tick-pause' : ''} ${a.long ? 'tick-long' : ''}`,
      'data-tip': `A${a.i + 1} · ${a.label || a.kind} · ${a.t.toFixed(2)} s`,
    });
    tick.style.left = (dur ? a.t / dur * 100 : 0) + '%';
    tick.addEventListener('click', (e) => { e.stopPropagation(); polarStage.seekAnchor(a.i); });
    track.append(tick);
  }
}

/* ═══════════════════════ backend / health ═══════════════════════ */
function setBackendChip() {
  const dot = $('#backend-dot');
  const label = $('#backend-label');
  if (api.mode === 'live') {
    const st = api.health?.status || 'ok';
    dot.className = `dot ${st === 'ok' ? 'ok' : st === 'degraded' ? 'warn' : 'err'}`;
    label.textContent = `backend live · engine v${api.status?.version || '?'}`;
    $('#demo-banner').style.display = 'none';
    if (st !== 'ok') R.log(`health: ${st} — ${JSON.stringify(api.health?.registry_warnings || [])}`);
  } else {
    dot.className = 'dot err';
    label.textContent = 'backend offline — demo mode';
    $('#demo-banner').style.display = '';
  }
}

async function refreshBackend() {
  if (api.mode !== 'live') return;
  await api.refreshHealth();
  setBackendChip();
}

function toggleHealthDrawer() {
  const d = $('#health-drawer');
  if (d.style.display === 'none') {
    d.style.display = '';
    $('#health-json').textContent = JSON.stringify(api.health || { status: 'unknown' }, null, 2);
  } else {
    d.style.display = 'none';
  }
}

/* ═══════════════════════ app state machine (brief table 11.1) ═══════ */
function setAppState(s) {
  state.appState = s;
  const map = {
    empty: 'Empty',
    'preview-ready': 'Preview ready',
    'guard-warn': 'Guard warning',
    'guard-error': 'Guard blocked',
    synthesizing: 'Synthesizing',
    'polar-running': 'Polar-only (live)',
    ready: 'Ready',
    playing: 'Playing',
    'backend-offline': 'Backend offline',
  };
  const chip = $('#state-chip');
  chip.textContent = map[s] || s;
  chip.dataset.state = s;
  $('#zone-polar').classList.toggle('offline', s === 'backend-offline');
}

/* ═══════════════════════ errors ═══════════════════════ */
function showError(err, title) {
  const hint = err.hint || '';
  R.toast(`${title}: ${err.message}`, 'error', 6500);
  R.log(`${title}: ${err.errorClass || 'Error'} — ${err.message}${hint ? ' · ' + hint : ''}`, { level: 'error' });
  if (err.symbols?.length) {
    R.log(`rejected: ${err.symbols.map((x) => x.symbol).join(' ')}`, { level: 'error' });
  }
}

function downloadBlob(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

/* ═══════════════════════ keyboard (brief §12.9) ═══════════════════════ */
function bindShortcuts() {
  document.addEventListener('keydown', (e) => {
    if ($('#help-overlay').style.display !== 'none') {
      if (e.key === 'Escape') $('#help-overlay').style.display = 'none';
      return;
    }
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) {
      return;
    }
    if (e.key === 'Escape') { cancelSynthesis(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) {
      if (e.key === 'Enter') { e.preventDefault(); synthesize('auto'); }
      return;
    }
    switch (e.key) {
      case ' ': case 'k': case 'K': e.preventDefault(); togglePlay(); break;
      case 'S': if (e.shiftKey) { e.preventDefault(); stopPlayback(); } break;
      case 's': e.preventDefault(); synthesize('auto'); break;
      case 'e': case 'E': e.preventDefault(); synthesize('edited'); break;
      case 'p': case 'P': e.preventDefault(); convert(); break;
      case 'c': case 'C': e.preventDefault(); $('#compiler-input')?.focus(); break;
      case 'l': case 'L': $('#btn-loop').click(); break;
      case '[': polarStage?.prevAnchor(); break;
      case ']': polarStage?.nextAnchor(); break;
      case '0': setSpeed('0.25'); break;
      case '1': setSpeed('0.5'); break;
      case '2': setSpeed('1'); break;
      case '3': setSpeed('2'); break;
      case 'd': case 'D': $('#btn-downloads').click(); break;
      case 'r': case 'R': e.preventDefault(); resetInputs(); break;
      case '?': $('#help-overlay').style.display = ''; break;
      default: break;
    }
  });
}

init();
