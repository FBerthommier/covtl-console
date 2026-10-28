// SPDX-FileCopyrightText: 2026 Frédéric Berthommier
// SPDX-License-Identifier: GPL-3.0-or-later
/* demo-engine.js — OFFLINE SIMULATION of the covtl-pipeline stages.
 * This module powers DEMO mode only (no Python backend detected).
 * It deliberately mirrors the ENGINE's semantics — marker rules, guard
 * tokenizer, timing model, F0 declination — but it does NOT reimplement
 * VocalTractLab: demo audio is a formant approximation, clearly labeled.
 * In LIVE mode every function here is bypassed in favor of the local
 * Python server (server.py → vtl_synth.Pipeline), which stays the single
 * source of truth for G2P, the guard and synthesis.
 */
import {
  LANGUAGES, DEMO_LEXICON_EN, DEMO_LEXICON_FR, FUNCTION_WORDS, ACOUSTICS,
  POLAR_TARGETS, tokenizeSampa, isSampaToken, VOWELS, ENGINE,
} from './data.js';

/* ══════════════════════ G2P (grapheme → phoneme) ══════════════════════
 * Mirrors utils/g2p.py + per-language gateways:
 *  - sentence punctuation  . ! ? ; :  → phrase break  ' | '  (long pause)
 *  - comma / en-dash       , – —      → ' '  (short inter-word pause)
 *  - adjacent words inside a part are joined with '.'  (coarticulation)
 *  - unknown word → kept verbatim + warning (engine: "word not in CMUdict
 *    (kept verbatim)"); words already valid SAMPA pass through silently. */
export function demoG2P(text, lang) {
  const warnings = [];
  const profile = LANGUAGES[lang] || LANGUAGES.en;
  const lex = lang === 'fr' ? DEMO_LEXICON_FR : DEMO_LEXICON_EN;
  if (lang !== 'en' && lang !== 'fr') {
    warnings.push(`Demo lexicon covers English and French only — start the Python backend for real ${profile.display} G2P (Wikipron lexicon + rules).`);
  }
  // notation gateway: per-language character aliases (setlang notation_alias)
  let norm = text;
  for (const [ch, sampa] of Object.entries(profile.alias || {})) norm = norm.split(ch).join(sampa);

  const sentences = norm.split(/[.!?;:]+[\s]*/).map((s) => s.trim()).filter(Boolean);
  const outPhrases = [];
  const wordInfos = [];
  let pIdx = 0;
  for (const sentence of sentences) {
    const parts = sentence.split(/\s*[,–—]\s*/).map((p) => p.trim()).filter(Boolean);
    const sampaParts = [];
    let cIdx = 0;
    for (const part of parts) {
      const words = part.match(/[A-Za-zÀ-ɏ'’]+/g) || [];
      if (!words.length) continue;
      const tokens = words.map((w) => {
        const key = w.toLowerCase();
        if (lex[key]) { wordInfos.push({ word: w, sampa: lex[key], known: true, phraseIdx: pIdx, partIdx: cIdx }); return lex[key]; }
        if (isSampaToken(key)) { wordInfos.push({ word: w, sampa: key, known: true, passthrough: true, phraseIdx: pIdx, partIdx: cIdx }); return key; }
        warnings.push(`word not in ${lang === 'en' ? 'CMUdict' : 'the lexicon'} (kept verbatim): '${w}'`);
        wordInfos.push({ word: w, sampa: key, known: false, phraseIdx: pIdx, partIdx: cIdx });
        return key;
      });
      sampaParts.push(tokens.join('.'));
      cIdx += 1;
    }
    if (sampaParts.length) outPhrases.push(sampaParts.join(' '));
    pIdx += 1;
  }
  return { sampa: outPhrases.join(' | '), warnings, words: wordInfos, language: lang };
}

/* ══════════════════ Breath-group chunker (expressive) ═════════════════
 * Mirrors utils/chunking.py in spirit: function-word dictionaries,
 * hard 5-word balance, '%' breath markers between groups. */
export function demoChunk(sampa, lang) {
  const fw = new Set(FUNCTION_WORDS[lang === 'fr' ? 'fr' : 'en']);
  const outPhrases = [];
  for (const phrase of sampa.split(' | ')) {
    const partOuts = [];
    for (const part of phrase.split(' ')) {
      const words = part.split('.');
      const groups = [];
      let group = [];
      const flush = () => { if (group.length) { groups.push(group.join('.')); group = []; } };
      for (const w of words) {
        group.push(w);
        const isFunc = fw.has(w.toLowerCase()) || w.length <= 2;
        if (!isFunc && group.length >= 3) flush();          // content-word balance
        if (group.length >= 5) flush();                     // hard 5-word max
      }
      flush();
      partOuts.push(groups.join(' % '));
    }
    outPhrases.push(partOuts.join(' '));
  }
  return outPhrases.join(' | ');
}

export function demoEnrich(sampa, { expressive, lang }) {
  const enriched = expressive ? demoChunk(sampa, lang) : sampa;
  // breath groups for visualization: phrases → groups split on '%'
  const groups = [];
  for (const phrase of enriched.split(' | ')) {
    for (const g of phrase.split(/\s*%\s*/)) {
      if (g.trim()) groups.push({ sampa: g.trim(), words: g.split(/[. ]/).filter(Boolean).length });
    }
  }
  return { enriched, groups };
}

/* ══════════════════════ Segment timeline (syltraj) ════════════════════
 * Approximate block schedule: consonant gesture = Tcons, vowel gesture =
 * Tvoy, ' ' = Tpause, '|' = Tpause-long, '%' = 130 ms. (The real syltraj
 * builds typed blocks with cluster sub-arcs; the server recomputes exact
 * timing when the .polar intermediate is produced.) */
export function demoTimeline(sampaText, timings) {
  const tokens = tokenizeSampa(sampaText);
  const segments = [];
  let t = 0.05;                                    // 50 ms leading edge
  const add = (sym, type, ms) => { const d = ms / 1000; segments.push({ sym, type, start: t, end: t + d }); t += d; };
  for (const tok of tokens) {
    switch (tok.sym) {
      case ' ':  add('␣', 'pause-short', timings.tpause); break;
      case '|':  add('|', 'pause-long', timings.tpauseLong); break;
      case '%':  add('%', 'pause-breath', ENGINE.breathPauseMs); break;
      case ',':  add(',', 'pause-short', timings.tpause); break;
      case '.': case '-': case '~': break;          // zero-duration markers
      default:
        if (tok.kind === 'vowel') add(tok.sym, 'vowel', timings.tvoy);
        else if (tok.kind === 'consonant') add(tok.sym, 'consonant', timings.tcons);
        else add(tok.sym, 'rejected', 0);           // dropped by the parser
    }
  }
  t += 0.12;                                       // release + trailing decay
  return { segments, duration: t };
}

/* ══════════════════════════ F0 contour ════════════════════════════════
 * Mirrors pipeline.apply_f0_declination (onset gain → final gain, 25 ms
 * attack ramp, per-phrase) + expressive plan: per-group re-attacks, pitch
 * accents (+10 % gaussian on group-initial vowels), stronger nuclear fall. */
export function demoF0(timeline, { f0Base, onset, final, expressive, groups }) {
  const { segments, duration } = timeline;
  const vowels = segments.filter((s) => s.type === 'vowel');
  const phrases = [];
  let cur = [];
  for (const s of segments) {
    if (s.type === 'pause-long') { if (cur.length) phrases.push(cur); cur = []; }
    else cur.push(s);
  }
  if (cur.length) phrases.push(cur);

  const groupStarts = [];
  if (expressive && groups) {
    // group-initial vowels = accent targets; group-final vowels = falls
    let tCursor = 0;
    for (const g of groups) {
      const gv = vowels.filter((v) => v.sym && g.sampa.includes(v.sym) && v.start >= tCursor);
      if (gv.length) { groupStarts.push({ first: gv[0], last: gv[gv.length - 1] }); tCursor = gv[0].start + 0.01; }
    }
  }
  const f0At = (t) => {
    const phrase = phrases.find((p) => t >= p[0].start && t <= p[p.length - 1].end);
    if (!phrase || !vowels.length) return f0Base;
    const p0 = phrase[0].start, p1 = phrase[phrase.length - 1].end;
    const prog = Math.min(1, Math.max(0, (t - p0) / Math.max(1e-6, p1 - p0)));
    let g = onset + (final - onset) * prog;
    const attack = Math.min(1, (t - p0) / 0.025);
    g = 1.0 + (g - 1.0) * attack;
    if (expressive) {
      for (const gs of groupStarts) {
        if (gs.first) {
          const d = Math.abs(t - (gs.first.start + gs.first.end) / 2) / 0.06;
          if (d < 3) g += 0.10 * Math.exp(-0.5 * d * d);      // pitch accent
        }
      }
      const lastV = vowels[vowels.length - 1];
      if (lastV && t > lastV.start - 0.02 && t < lastV.end + 0.05) g -= 0.06; // nuclear fall
    }
    return f0Base * g;
  };
  return { f0At, duration };
}

/* ════════════════════ Formant synthesis (demo audio) ══════════════════
 * Source–filter sketch: glottal periodic wave (−12 dB/oct rolloff) through
 * three automated band-passes + nasal resonator; frication noise through a
 * moving band-pass; stop bursts as short noise pulses at place frequencies. */
const CONTROL_RATE = 4410;

function buildControlEvents(timeline, f0) {
  const { segments } = timeline;
  const events = [];   // {t, f1,f2,f3, voiced, noise, noiseHz, nasal}
  const push = (t, a) => events.push({ t, ...a });
  for (const s of segments) {
    const a = ACOUSTICS[s.sym];
    const mid = (s.start + s.end) / 2;
    if (s.type === 'vowel' || (a && (a.glide || a.nasal)) && s.type === 'consonant') {
      const f = a.f || a.glide;
      push(s.start + 0.004, { f1: f[0], f2: f[1], f3: f[2], voiced: 0.95, noise: 0, noiseHz: 2000, nasal: a.nasal ? 1 : 0 });
      push(mid, { f1: f[0], f2: f[1], f3: f[2], voiced: 0.95, noise: 0, noiseHz: 2000, nasal: a.nasal ? 1 : 0 });
    } else if (a && a.stop) {
      const locus = { labial: [350, 800, 2200], alveolar: [350, 1700, 2600], velar: [350, 1300, 2300] }[a.place];
      push(s.start + 0.002, { f1: 250, f2: locus[1], f3: locus[2], voiced: a.voiced ? 0.30 : 0, noise: 0, noiseHz: 1500, nasal: 0 });
      const burstT = s.start + (s.end - s.start) * 0.7;
      push(burstT, { f1: 250, f2: locus[1], f3: locus[2], voiced: a.voiced ? 0.2 : 0, noise: 0.9, noiseHz: a.burst[0], nasal: 0 });
      push(burstT + 0.018, { f1: 250, f2: locus[1], f3: locus[2], voiced: 0.1, noise: 0.15, noiseHz: a.burst[1], nasal: 0 });
    } else if (a && (a.fric || a.affr)) {
      const band = a.fric || a.affr;
      push(s.start + 0.003, { f1: 350, f2: 1200, f3: 2400, voiced: a.voiced ? 0.22 : 0, noise: 0.75, noiseHz: (band[0] + band[1]) / 2, nasal: 0 });
      push(s.end - 0.003, { f1: 350, f2: 1200, f3: 2400, voiced: a.voiced ? 0.22 : 0, noise: 0.75, noiseHz: (band[0] + band[1]) / 2, nasal: 0 });
    } else if (a && a.f) {   // l, R, m, n, J
      push(s.start + 0.004, { f1: a.f[0], f2: a.f[1], f3: a.f[2], voiced: 0.7, noise: 0, noiseHz: 2000, nasal: a.nasal ? 1 : 0 });
      push(s.end - 0.004, { f1: a.f[0], f2: a.f[1], f3: a.f[2], voiced: 0.7, noise: 0, noiseHz: 2000, nasal: a.nasal ? 1 : 0 });
    }
  }
  events.sort((x, y) => x.t - y.t);
  return events;
}

const smooth = (x) => x * x * (3 - 2 * x);
function sampleCurve(events, t, key) {
  if (!events.length) return 0;
  if (t <= events[0].t) return events[0][key];
  if (t >= events[events.length - 1].t) return events[events.length - 1][key];
  let i = 0;
  while (i < events.length - 1 && events[i + 1].t < t) i += 1;
  const a = events[i], b = events[i + 1];
  const span = Math.max(1e-6, b.t - a.t);
  const u = smooth(Math.min(1, Math.max(0, (t - a.t) / span)));
  return a[key] + (b[key] - a[key]) * u;
}

export async function demoAudio(timeline, f0) {
  const { duration } = timeline;
  const n = Math.ceil(duration * ENGINE.audioRateHz);
  const OfflineCtx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const ctx = new OfflineCtx(1, n, ENGINE.audioRateHz);
  const master = ctx.createGain();
  master.gain.value = 0.9;
  master.connect(ctx.destination);

  // ── voiced branch ──
  const osc = ctx.createOscillator();
  const harmonics = new Float32Array(24).map((_, k) => 1 / Math.pow(k + 1, 1.4));
  harmonics[0] = 0; // remove DC
  const wave = ctx.createPeriodicWave(harmonics, new Float32Array(24));
  osc.setPeriodicWave(wave);
  const voicedBus = ctx.createGain();
  const bps = [8, 10, 12].map((q) => { const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.Q.value = q; return f; });
  const gBps = bps.map(() => ctx.createGain());
  bps.forEach((f, i) => { osc.connect(f); f.connect(gBps[i]); gBps[i].connect(voicedBus); });
  gBps.forEach((g, i) => { g.gain.value = [1, 0.7, 0.35][i]; });
  const voicedGain = ctx.createGain();
  voicedBus.connect(voicedGain); voicedGain.connect(master);
  // nasal resonator
  const nasalFilter = ctx.createBiquadFilter();
  nasalFilter.type = 'bandpass'; nasalFilter.frequency.value = 250; nasalFilter.Q.value = 1.5;
  const nasalGain = ctx.createGain();
  osc.connect(nasalFilter); nasalFilter.connect(nasalGain); nasalGain.connect(master);

  // ── noise branch ──
  const noiseBuf = ctx.createBuffer(1, ENGINE.audioRateHz * 2, ENGINE.audioRateHz);
  const nd = noiseBuf.getChannelData(0);
  for (let i = 0; i < nd.length; i += 1) nd[i] = Math.random() * 2 - 1;
  const noise = ctx.createBufferSource();
  noise.buffer = noiseBuf; noise.loop = true;
  const noiseFilter = ctx.createBiquadFilter();
  noiseFilter.type = 'bandpass'; noiseFilter.Q.value = 1.2;
  const noiseGain = ctx.createGain(); noiseGain.gain.value = 0;
  noise.connect(noiseFilter); noiseFilter.connect(noiseGain); noiseGain.connect(master);

  // ── control curves ──
  const events = buildControlEvents(timeline, f0);
  const nCtrl = Math.ceil(duration * CONTROL_RATE);
  const curve = (fn) => { const a = new Float32Array(nCtrl); for (let i = 0; i < nCtrl; i += 1) a[i] = fn(i / CONTROL_RATE); return a; };
  const t0 = ctx.currentTime;
  osc.frequency.setValueCurveAtTime(curve((t) => f0.f0At(t)), t0, nCtrl / CONTROL_RATE);
  bps[0].frequency.setValueCurveAtTime(curve((t) => sampleCurve(events, t, 'f1')), t0, nCtrl / CONTROL_RATE);
  bps[1].frequency.setValueCurveAtTime(curve((t) => sampleCurve(events, t, 'f2')), t0, nCtrl / CONTROL_RATE);
  bps[2].frequency.setValueCurveAtTime(curve((t) => sampleCurve(events, t, 'f3')), t0, nCtrl / CONTROL_RATE);
  voicedGain.gain.setValueCurveAtTime(curve((t) => sampleCurve(events, t, 'voiced')), t0, nCtrl / CONTROL_RATE);
  nasalGain.gain.setValueCurveAtTime(curve((t) => 0.5 * sampleCurve(events, t, 'nasal')), t0, nCtrl / CONTROL_RATE);
  noiseFilter.frequency.setValueCurveAtTime(curve((t) => sampleCurve(events, t, 'noiseHz')), t0, nCtrl / CONTROL_RATE);
  noiseGain.gain.setValueCurveAtTime(curve((t) => sampleCurve(events, t, 'noise')), t0, nCtrl / CONTROL_RATE);
  osc.start(t0); noise.start(t0);
  osc.stop(t0 + duration); noise.stop(t0 + duration);
  return ctx.startRendering();
}

/* ═══════════════════ Polar trajectories (demo geometry) ═══════════════
 * Vocalic branch: continuous background arc through the vowel anchors;
 * consonantal branch: excursion to the closure target (ρ > 1) during the
 * consonant only — the two branches are dissociated, as in the .polar
 * format v4 / dual-panel video. */
export function demoPolar(timeline) {
  const { segments, duration } = timeline;
  const vowels = segments.filter((s) => s.type === 'vowel' && POLAR_TARGETS[s.sym]);
  const consonants = segments.filter((s) => s.type === 'consonant' && POLAR_TARGETS[s.sym]);
  const center = (s) => (s.start + s.end) / 2;
  const polarAt = (t, list) => {
    if (!list.length) return null;
    const lastIdx = list.length - 1;
    if (t <= center(list[0])) return POLAR_TARGETS[list[0].sym];
    if (t >= center(list[lastIdx])) return POLAR_TARGETS[list[lastIdx].sym];
    let i = 0;
    while (i < lastIdx - 1 && center(list[i + 1]) < t) i += 1;
    const a = list[i], b = list[i + 1];
    const ta = center(a), tb = center(b);
    return lerpTarget(POLAR_TARGETS[a.sym], POLAR_TARGETS[b.sym], smooth(Math.min(1, Math.max(0, (t - ta) / Math.max(1e-6, tb - ta)))));
  };
  const consonantAt = (t) => {
    const c = consonants.find((s) => t >= s.start && t <= s.end);
    if (!c) return null;
    const target = POLAR_TARGETS[c.sym];
    const u = (t - c.start) / (c.end - c.start);
    const env = Math.sin(Math.PI * Math.min(1, Math.max(0, u))) ** 0.7;   // excursion envelope
    return { rho: 1 + (target.rho - 1) * env, theta: target.theta };
  };
  return { duration, at: (t) => ({ vocalic: polarAt(t, vowels), consonantal: consonantAt(t) }) };
}
function lerpTarget(a, b, u) {
  let d = b.theta - a.theta;
  while (d > 180) d -= 360;
  while (d < -180) d += 360;
  return { rho: a.rho + (b.rho - a.rho) * u, theta: a.theta + d * u };
}

/* ════════════════════════ Syllable block compiler (v3) ══════════════════
 * DEMO approximation of the engine's syltraj anchor walk. The real
 * structure always comes from the Python backend (POST /api/compile);
 * this arithmetic mirror (cluster (m+1)·Tcons, plateau Tvoy, pause arcs,
 * initial/terminal) keeps the compiler panel and the continuous display
 * exercisable offline. Labeled "approximate" everywhere it is shown. */
export function demoCompile({ text, lang = 'en', timings = {} }) {
  const prof = LANGUAGES[lang] || LANGUAGES.en;
  const t = { ...prof.timings, ...timings };
  const Tcons = Math.max(1, Math.round((t.tcons ?? 100) / 10));
  const Tvoy = Math.max(1, Math.round((t.tvoy ?? 80) / 10));
  const Tpause = Math.max(1, Math.round((t.tpause ?? 200) / 10));
  const TpauseLong = Math.max(1, Math.round((t.tpauseLong ?? 320) / 10));

  const src = (text || '').trim();
  const phrases = src.split('|').map((p) => p.trim()).filter(Boolean);
  const anchors = [];
  const blocks = [];
  const nodes = [];
  let cursor = 0;   // steps

  const anchor = (kind, label, extra = {}) => {
    anchors.push({ i: anchors.length, t: Math.round(cursor) / 100, kind, label, ...extra });
  };
  const block = (kind, nSteps, extra = {}) => {
    blocks.push({ kind, n_steps: nSteps, t0: cursor / 100, t1: (cursor + nSteps) / 100, ...extra });
    cursor += nSteps;
  };

  phrases.forEach((phrase, pi) => {
    anchor('synth', '▸');
    block('initial', Tpause);
    // walk syllable-like units: consonant run + vowel, '.' splits inside words
    const toks = tokenizeSampa(phrase);
    let consRun = [];
    const flushVowel = (v) => {
      const m = consRun.length;
      if (m > 0) block('cluster', (m + 1) * Tcons, { n_cons: m, cons_keys: consRun, vowel_key: '' });
      anchor('V', consRun.join('') + v);
      block('plateau', Tvoy, { vowel_key: v, n_cons: 0, cons_keys: [] });
      nodes.push({ kind: 'V', key: v, rho: (POLAR_TARGETS[v] || { rho: 0.7 }).rho, theta: (POLAR_TARGETS[v] || { theta: 180 }).theta, in_cluster: false });
      consRun = [];
    };
    for (const tok of toks) {
      if (tok.kind === 'consonant') consRun.push(tok.sym);
      else if (tok.kind === 'vowel') flushVowel(tok.sym);
      else if (tok.kind === 'pause-short' || tok.kind === 'pause-breath') {
        if (consRun.length) { flushVowel('@'); }
        block('pause', tok.kind === 'pause-breath' ? 13 : Tpause, { breath: tok.kind === 'pause-breath' });
        anchor('pause', tok.kind === 'pause-breath' ? '%' : '␣', { breath: tok.kind === 'pause-breath' });
      }
      // links ('.') coarticulate — no block, the cluster spans them
    }
    if (consRun.length) flushVowel('@');       // trailing consonants → schwa
    block('decay', Tcons);
    anchor('V', '', { word_end: true });
    block('terminal', pi < phrases.length - 1 ? TpauseLong : Tpause);
    anchor('synth', '◂');
  });

  const syllables = blocks.filter((b) => b.kind === 'plateau').length;
  const clusters = blocks.filter((b) => b.kind === 'cluster');
  const metrics = {
    anchors: anchors.length,
    segments: Math.max(0, anchors.length - 1),
    blocks: blocks.length,
    syllables,
    clusters: clusters.length,
    consonants: clusters.reduce((n, b) => n + (b.n_cons || 0), 0),
    vowels: nodes.filter((n) => n.kind === 'V').length,
    steps: cursor,
    duration_s: cursor / 100,
  };
  // segments preview (same shape as /api/compile)
  const segmentsPreview = [];
  for (let k = 0; k < anchors.length - 1; k += 1) {
    const a0 = anchors[k], a1 = anchors[k + 1];
    if (a1.t <= a0.t) continue;
    const span = blocks.filter((b) => b.t0 < a1.t - 1e-9 && b.t1 > a0.t + 1e-9);
    const cons = span.flatMap((b) => b.cons_keys || []);
    const vowel = (span.find((b) => b.kind === 'plateau') || {}).vowel_key || '';
    segmentsPreview.push({
      segment_index: segmentsPreview.length, t0: a0.t, t1: a1.t,
      label: cons.join('') + vowel || a0.label || a1.label || '-',
      cons, vowel, kinds: span.map((b) => b.kind),
      n_steps: Math.round((a1.t - a0.t) * 100),
    });
  }
  // polar targets: POLAR_TARGETS are trig degrees → store radians like the engine
  const targets = {};
  for (const [k, tgt] of Object.entries(POLAR_TARGETS)) {
    targets[k] = { rho: tgt.rho, theta: (tgt.theta * Math.PI) / 180 };
  }
  return {
    source: src, sampa: src, anchors, blocks, nodes, metrics,
    segmentsPreview, targets, rejected: [],
    warnings: ['demo arithmetic — approximate structure (start the bridge for the real syltraj walk)'],
    rhoMax: 1.45, live: false,
  };
}

/* demo polar segment payload in the normalized PolarStage shape */
export function demoSegmentPayload(compileResult) {
  const rhoMax = compileResult.rhoMax || 1.45;
  const anchors = compileResult.anchors;
  const segs = [];
  for (let k = 0; k < anchors.length - 1; k += 1) {
    const a0 = anchors[k], a1 = anchors[k + 1];
    if (a1.t <= a0.t + 1e-9) continue;
    const n = Math.max(1, Math.round((a1.t - a0.t) * 100));
    const t = new Float32Array(n), rv = new Float32Array(n), tv = new Float32Array(n);
    let hasC = false;
    const rc = [], tc = [];
    for (let i = 0; i < n; i += 1) {
      const ti = a0.t + i / 100;
      // positional interpolation between the anchor vowels' polar targets
      const from = POLAR_TARGETS[_vowelOf(a0.label)] || POLAR_TARGETS['@'];
      const to = POLAR_TARGETS[_vowelOf(a1.label)] || POLAR_TARGETS['@'];
      const u = Math.min(1, Math.max(0, (ti - a0.t) / (a1.t - a0.t)));
      const smooth = u * u * (3 - 2 * u);
      let dth = to.theta - from.theta;
      while (dth > 180) dth -= 360;
      while (dth < -180) dth += 360;
      t[i] = ti;
      rv[i] = (from.rho + (to.rho - from.rho) * smooth) / rhoMax;
      tv[i] = ((90 - (from.theta + dth * smooth)) % 360 + 360) % 360;
      // consonantal excursion inside cluster spans
      const span = compileResult.blocks.find((b) => ti >= b.t0 && ti < b.t1 && b.kind === 'cluster');
      if (span && span.cons_keys && span.cons_keys.length) {
        const ckey = span.cons_keys[Math.min(span.cons_keys.length - 1,
          Math.floor((ti - span.t0) / Math.max(1e-9, (span.t1 - span.t0) / span.cons_keys.length)))];
        const ctgt = POLAR_TARGETS[ckey];
        if (ctgt) {
          const env = Math.pow(Math.sin(Math.PI * Math.min(1, Math.max(0, u))), 0.7);
          hasC = true;
          rc.push((1 + (ctgt.rho - 1) * env) / rhoMax);
          tc.push(((90 - ctgt.theta) % 360 + 360) % 360);
          continue;
        }
      }
      rc.push(NaN); tc.push(NaN);
    }
    segs.push({
      index: segs.length, t0: a0.t, t1: a1.t,
      anchorFrom: a0.i, anchorTo: a1.i, labelFrom: a0.label, labelTo: a1.label,
      blocks: compileResult.blocks
        .filter((b) => b.t0 < a1.t - 1e-9 && b.t1 > a0.t + 1e-9)
        .map((b) => ({ kind: b.kind, n_steps: b.n_steps, cons_keys: b.cons_keys || [],
                       vowel_key: b.vowel_key || '', long: !!b.long, breath: !!b.breath,
                       t0: b.t0, t1: b.t1 })),
      markers: null, n, t, rv, tv,
      rc: hasC ? Float32Array.from(rc) : null,
      tc: hasC ? Float32Array.from(tc) : null,
    });
  }
  return {
    jobId: 'demo', rhoMax,
    duration: compileResult.metrics.duration_s,
    anchors, segments: segs,
  };
}

function _vowelOf(label) {
  const ch = (label || '').slice(-1);
  return POLAR_TARGETS[ch] ? ch : null;
}

/* ════════════════════════ Synthesis orchestration ═════════════════════
 * Staged like the real pipeline: g2p → trajectory → vtl → wav (+ video).
 * Each stage reports progress; the VTL stage is the long one.
 * v3: onPolarReady fires right after the trajectory stage with the demo
 * segment payload, so the continuous display starts before the audio. */
export async function demoSynthesize(payload, { onStage, onLog, onPolarReady, cancel } = {}) {
  const { text, mode, lang, speaker, timings, expressive, f0, outputMode } = payload;
  const profile = LANGUAGES[lang] || LANGUAGES.en;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const checkCancel = () => { if (cancel && cancel.cancelled) { const e = new Error('cancelled'); e.cancelled = true; throw e; } };
  const stage = async (name, ms, fn) => {
    checkCancel();
    onStage?.(name, 'active');
    onLog?.(`[${name}] running…`);
    if (fn) await fn();
    await wait(ms);
    checkCancel();
    onStage?.(name, 'done');
  };

  let sampa, warnings = [], groups = null;
  await stage('g2p', 140, async () => {
    if (mode === 'ortho') {
      const g = demoG2P(text, lang);
      sampa = g.sampa; warnings = g.warnings;
      const e = demoEnrich(sampa, { expressive, lang });
      sampa = e.enriched; groups = e.groups;
    } else {
      sampa = text.trim();
      if (expressive) warnings.push('expressive mode ignored: phonetic input (use_g2p=False) has no syntactic structure');
    }
    if (!sampa.trim()) throw new Error(`ValueError — no phonetic content in: '${text.slice(0, 40)}'`);
  });

  const timeline = demoTimeline(sampa, timings);
  await stage('trajectory', 420);

  // v3 — continuous display data ready before the audio (start-early)
  let demoStruct = null;
  try {
    demoStruct = demoCompile({ text: sampa, lang, timings });
    onPolarReady?.(demoSegmentPayload(demoStruct));
    onLog?.(`[trajectory] ${demoStruct.metrics.blocks} blocks · ${demoStruct.metrics.anchors} anchors (demo arithmetic)`);
  } catch (err) {
    onLog?.(`[trajectory] demo structure unavailable: ${err.message}`);
  }

  const f0c = demoF0(timeline, { f0Base: f0, onset: profile.f0.onset, final: profile.f0.final, expressive, groups });
  let buffer = null;
  await stage('vtl', 1250, async () => {
    onLog?.('[vtl] demo formant renderer (VocalTractLab not available offline)');
    buffer = await demoAudio(timeline, f0c);
  });

  const wav = encodeWav(buffer);
  await stage('wav', 260, async () => {
    onLog?.(`[wav] ${buffer.duration.toFixed(2)} s, 44.1 kHz mono, ${(wav.byteLength / 1024).toFixed(0)} KiB`);
  });

  if (outputMode !== 'audio') {
    await stage('video', 500, async () => {
      onLog?.('[video] MP4 rendering requires the Python backend (demo mode: skipped)');
    });
  }

  const frames = Math.round(timeline.duration * ENGINE.tractRateHz);
  return {
    sampa, warnings, groups, timeline, buffer, wav,
    f0Curve: f0c.f0At,
    duration: buffer.duration,
    frames,
    phrases: sampa.split(' | ').length,
    polar: demoStruct ? demoSegmentPayload(demoStruct) : demoPolar(timeline),
    anchors: demoStruct ? demoStruct.anchors : null,
    blockCount: demoStruct ? demoStruct.metrics.segments : null,
    files: [
      { name: 'demo.wav', kind: 'wav', blob: new Blob([wav], { type: 'audio/wav' }), available: true },
      { name: 'demo_sampa.txt', kind: 'txt', blob: new Blob([sampa + '\n'], { type: 'text/plain' }), available: true },
      { name: 'demo.tract', kind: 'tract', available: false },
      { name: 'demo.mp4', kind: 'mp4', available: false },
    ],
  };
}

/* ── WAV encoder (16-bit PCM mono — same format class as the engine) ── */
export function encodeWav(buffer) {
  const ch = buffer.getChannelData(0);
  const n = ch.length;
  const out = new ArrayBuffer(44 + n * 2);
  const v = new DataView(out);
  const w = (o, s) => { for (let i = 0; i < s.length; i += 1) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVE');
  w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, buffer.sampleRate, true); v.setUint32(28, buffer.sampleRate * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, 'data'); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i += 1) {
    const s = Math.max(-1, Math.min(1, ch[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return out;
}
