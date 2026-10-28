// SPDX-FileCopyrightText: 2026 Frédéric Berthommier
// SPDX-License-Identifier: GPL-3.0-or-later
/* api.js — single communication layer between the UI and the engine.
 *
 * LIVE mode: talks to the local FastAPI bridge (server.py v3), which wraps
 *   vtl_synth.Pipeline — the Python backend stays the source of truth
 *   for G2P, the SAMPA guard, syltraj timing, the anchor/block structure
 *   and VocalTractLab synthesis.
 * DEMO mode: no backend detected → the browser-side demo engine simulates
 *   the same stages (clearly labeled everywhere), including an approximate
 *   syllable compiler and polar segments so the whole v3 UI is exercisable.
 *
 * v3:
 *   • api.health() — brief §10.4 status probe (ok | degraded | offline).
 *   • api.compile() — the syllable block compiler (structural half only).
 *   • api.synthesize() polls the v3 job payload; the NEW onPolarReady
 *     callback fires the moment polar_ready flips (before the WAV) and
 *     carries the full anchor→anchor segment payload, so the continuous
 *     polar display starts on its own clock while audio renders.
 *   • structured errors {class, message, hint, symbols} everywhere.
 *   • caches: preview responses + synthesis results (AudioBuffer + polar
 *     payload inside); keys mirror the server (engine version included).
 */

import * as demo from './demo-engine.js';
import { tokenizeSampa, unknownSymbols, enrichRejected } from './data.js';

/* When the console is opened via file:// (double-click), route API calls
 * to the local bridge's default port. Served normally, same-origin wins. */
const BASE = location.protocol === 'file:' ? 'http://127.0.0.1:8421' : '';
/* generous default: embedded/embedded-browser stacks can add seconds of
 * constant per-request latency on loopback (observed ~6 s in the in-app
 * browser while curl answers in 17 ms) — short timeouts misreport a live
 * backend as offline */
const TIMEOUT = 30000;

/* ── caches ─────────────────────────────────────────────────────────── */
const previewCache = new Map();   // key → preview payload
const synthCache = new Map();     // key → synthesis result (AudioBuffer inside)
const compileCache = new Map();   // key → compile payload
const PREVIEW_CACHE_MAX = 64;
const SYNTH_CACHE_MAX = 6;        // decoded AudioBuffers are heavy — keep few
const COMPILE_CACHE_MAX = 32;
const cacheStats = { previewHits: 0, synthHits: 0, compileHits: 0 };

function cacheSet(map, key, value, max) {
  map.set(key, value);
  if (map.size > max) map.delete(map.keys().next().value);   // FIFO eviction
}

export function synthCacheKey(p) {
  /* mirrors the server-side key: everything that changes the audio,
     guard policy deliberately excluded (see header comment). */
  return JSON.stringify([
    p.text, p.mode, p.lang, p.speaker, p.f0,
    [p.timings.tcons, p.timings.tvoy, p.timings.tpause, p.timings.tpauseLong],
    p.expressive, p.engine, p.ortho, p.outputMode, p.exports ?? true, p.label ?? null, p.outputDir ?? 'out',
  ]);
}

export function cacheInfo() {
  return { previewEntries: previewCache.size, previewHits: cacheStats.previewHits,
           compileEntries: compileCache.size, compileHits: cacheStats.compileHits,
           synthEntries: synthCache.size, synthHits: cacheStats.synthHits };
}

/* demo-mode results must never shadow live ones after an upgrade */
export function clearDemoCaches() {
  previewCache.clear();
  compileCache.clear();
  synthCache.clear();       // a demo-rendered WAV must not replay in live mode
}

/* ── in-flight tracker — feeds the header hourglass pill ───────────── */
let inflight = 0;
function busyDelta(d) {
  inflight = Math.max(0, inflight + d);
  const pill = document.getElementById('busy-pill');
  if (pill) {
    if (inflight > 0) {
      pill.style.display = '';
      pill.textContent = `⏳ ${inflight} in flight…`;
    } else {
      pill.style.display = 'none';
    }
  }
}

/* ── fetch helper with structured error parsing ─────────────────────── */
function makeError(status, statusText, body) {
  const e = new Error(body?.error?.message || body?.detail || `${status} ${statusText}`);
  e.status = status;
  e.errorClass = body?.error?.class || (status >= 500 ? 'ServerError' : 'RequestError');
  e.hint = body?.error?.hint || '';
  e.symbols = body?.error?.symbols || [];
  return e;
}

async function jfetch(path, opts = {}, timeout = TIMEOUT) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  busyDelta(1);
  try {
    const r = await fetch(BASE + path, { ...opts, signal: ctl.signal,
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) } });
    if (!r.ok) {
      let body = null;
      try { body = await r.json(); } catch { /* non-JSON */ }
      throw makeError(r.status, r.statusText, body);
    }
    return r.json();
  } catch (err) {
    if (err.name === 'AbortError') {
      const e = new Error(`request timed out: ${path}`);
      e.errorClass = 'Timeout';
      throw e;
    }
    throw err;
  } finally {
    busyDelta(-1);
    clearTimeout(timer);
  }
}

export const api = {
  mode: 'unknown',          // 'live' | 'demo'
  status: null,
  health: null,

  async probe() {
    // several retries — after a bridge restart on the same port, the
    // browser may reuse a dead keep-alive socket for the first fetch(es);
    // a fresh connection succeeds. Gaps grow: 0 / 0.4 s / 2 s.
    const gaps = [0, 400, 2000];
    for (let attempt = 0; attempt < gaps.length; attempt += 1) {
      if (gaps[attempt]) await new Promise((r) => setTimeout(r, gaps[attempt]));
      try {
        this.status = await jfetch('/api/status', {}, 9000);
        this.mode = this.status.backend === 'live' ? 'live' : 'demo';
        break;
      } catch (err) {
        console.warn(`[api] probe attempt ${attempt + 1} failed:`, err);
        this.mode = 'demo';
        this.status = null;
      }
    }
    if (this.mode === 'live') {
      try { this.health = await jfetch('/api/health', {}, 9000); } catch { this.health = null; }
    }
    return this.mode;
  },

  async refreshHealth() {
    if (this.mode !== 'live') return null;
    try { this.health = await jfetch('/api/health', {}, 9000); } catch { this.health = { status: 'offline' }; }
    return this.health;
  },

  /* ── preview stack in ONE call — the cheap half of the pipeline ── */
  async preview({ text, sampa = null, mode = 'ortho', lang, expressive }) {
    const key = JSON.stringify([text ?? '', sampa ?? '', mode, lang, expressive]);
    const hit = previewCache.get(key);
    if (hit) {
      cacheStats.previewHits += 1;
      return { ...hit, cached: true };
    }
    let out;
    if (this.mode === 'live') {
      const r = await jfetch('/api/preview', {
        method: 'POST',
        body: JSON.stringify({ text, sampa, mode, lang, expressive }),
      }, 20000);
      out = {
        g2pString: r.g2p_string,
        enriched: r.enriched_string,
        final: r.final_sampa,
        words: r.words || [],
        groups: r.groups || [],
        warnings: r.warnings || [],
        tokens: r.tokens || [],
        rejected: r.rejected_symbols || [],
        language: r.language || lang,
        lexicon: r.lexicon,
        inventoryDigest: r.inventory_digest || null,
        live: true,
      };
    } else {
      // demo: assemble the same shape from the browser-side engine
      let g2pString = null, enriched, groups = [], warnings = [], words = [];
      if (sampa !== null) {
        enriched = sampa;
        if (expressive) {
          const e = demo.demoEnrich(sampa, { expressive, lang });
          enriched = e.enriched; groups = e.groups;
        }
      } else if (mode === 'phonetic') {
        enriched = (text || '').trim();
      } else {
        const g = demo.demoG2P(text, lang);
        g2pString = g.sampa; warnings = g.warnings; words = g.words;
        const e = demo.demoEnrich(g2pString, { expressive, lang });
        enriched = e.enriched; groups = e.groups;
      }
      const tokens = tokenizeSampa(enriched);
      out = {
        g2pString, enriched, final: enriched,
        words, groups, warnings, tokens,
        rejected: enrichRejected(unknownSymbols(enriched)),
        language: lang, lexicon: null, inventoryDigest: null, live: false,
      };
    }
    cacheSet(previewCache, key, out, PREVIEW_CACHE_MAX);
    return { ...out, cached: false };
  },

  /* ── re-check a hand-edited final SAMPA string ──
     Live mode asks the engine (source of truth); demo re-tokenizes. */
  async checkSampa({ sampa }) {
    if (this.mode === 'live') {
      const r = await jfetch('/api/preview/sampa', {
        method: 'POST', body: JSON.stringify({ sampa }),
      }, 30000);
      return { tokens: r.tokens, rejected: r.rejected, live: true };
    }
    return { tokens: tokenizeSampa(sampa), rejected: enrichRejected(unknownSymbols(sampa)), live: false };
  },

  /* ── syllable block compiler — the structural half, never synthesizes ── */
  async compile({ text, lang = 'en', timings = {}, guardPolicy = 'warn' }) {
    const key = JSON.stringify([text, lang, timings.tcons, timings.tvoy,
                                timings.tpause, timings.tpauseLong]);
    const hit = compileCache.get(key);
    if (hit) {
      cacheStats.compileHits += 1;
      return { ...hit, cached: true };
    }
    let out;
    if (this.mode === 'live') {
      const r = await jfetch('/api/compile', {
        method: 'POST',
        body: JSON.stringify({ text, lang, timings, guard_policy: guardPolicy }),
      }, 20000);
      out = {
        source: r.source, sampa: r.sampa,
        anchors: r.anchors, blocks: r.blocks, nodes: r.nodes,
        metrics: r.metrics, segmentsPreview: r.segments_preview,
        targets: r.targets || {},
        rejected: r.rejected_symbols || [],
        warnings: r.warnings || [],
        rhoMax: 1.45,
        live: true,
      };
    } else {
      out = demo.demoCompile({ text, lang, timings });
    }
    cacheSet(compileCache, key, out, COMPILE_CACHE_MAX);
    return { ...out, cached: false };
  },

  /* ── synthesis: trajectory + VTL → WAV ──
     onPolarReady(payload) fires while the WAV is still rendering (v3). */
  async synthesize(payload, { onStage, onLog, onJob, onPolarReady, cancel } = {}) {
    const key = synthCacheKey(payload);
    const hit = synthCache.get(key);
    if (hit) {
      cacheStats.synthHits += 1;
      onLog?.('client cache hit — identical parameters, no engine work');
      onPolarReady?.(hit.polar);
      return { ...hit, cached: true };
    }
    let result;
    if (this.mode === 'live') result = await this._synthesizeLive(payload, { onStage, onLog, onJob, onPolarReady, cancel });
    else result = await demo.demoSynthesize(payload, { onStage, onLog, onPolarReady, cancel });
    cacheSet(synthCache, key, result, SYNTH_CACHE_MAX);
    return { ...result, cached: false };
  },

  async _synthesizeLive(payload, { onStage, onLog, onJob, onPolarReady, cancel } = {}) {
    const start = await jfetch('/api/synthesize', { method: 'POST', body: JSON.stringify(payload) }, 30000);
    const jobId = start.job_id;
    onJob?.(jobId);
    const echo = start.echo || {};
    onLog?.(`[job ${jobId}] lang=${echo.lang} speaker=${echo.speaker} engine=${echo.engine}` +
      ` ortho=${echo.ortho} expressive=${echo.expressive} guard=${echo.guard}` +
      ` Tcons=${echo.tcons} Tvoy=${echo.tvoy} tpause=${echo.tpause} tpause-long=${echo.tpause_long}`);
    if (start.cached) onLog?.(`server cache hit — job ${jobId} reused (identical parameters)`);
    let polarFetched = false;
    let lastPolar = null;
    for (;;) {
      await new Promise((r) => setTimeout(r, 350));
      if (cancel?.cancelled) {                       // honor Cancel while polling
        fetch(`/api/job/${jobId}/cancel`, { method: 'POST' }).catch(() => {});
        const e = new Error('cancelled');
        e.cancelled = true;
        throw e;
      }
      const job = await jfetch(`/api/job/${jobId}`, {}, 30000);
      onStage?.(job.stage, job.state === 'cancelling' ? 'active' : job.state, job.progress ?? 0);
      if (job.polar_ready && !polarFetched) {
        polarFetched = true;
        try {
          const p = await jfetch(`/api/job/${jobId}/polar`, {}, 30000);
          lastPolar = normalizePolar(p);
          onPolarReady?.(lastPolar);
        } catch (err) {
          onLog?.(`polar payload unavailable: ${err.message}`);
        }
      }
      if (job.state === 'error' || job.state === 'cancelled') {
        const err = new Error(job.error || `synthesis ${job.state}`);
        err.errorClass = job.error_class;
        err.hint = job.error_hint || '';
        err.cancelled = job.state === 'cancelled' || job.error_class === 'Cancelled';
        throw err;
      }
      if (job.state === 'done') {
        const r = job.result;
        // fetch + decode the WAV locally so the spectrogram is computed
        // from the real signal
        busyDelta(1);
        try {
          const wavResp = await fetch(r.wav_url);
          var wavBuf = await wavResp.arrayBuffer();
        } finally { busyDelta(-1); }
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const buffer = await ctx.decodeAudioData(wavBuf.slice(0));
        ctx.close();
        let polar = lastPolar;
        if (!polarFetched && job.polar_ready) {
          try { polar = normalizePolar(await jfetch(`/api/job/${jobId}/polar`, {}, 30000)); }
          catch { polar = null; }
        }
        return {
          sampa: r.sampa, warnings: r.warnings || [], groups: null,
          duration: buffer.duration,
          frames: r.frames, phrases: r.phrases, buffer,
          wavUrl: r.wav_url,
          anchors: job.anchors || null, blockCount: job.block_count ?? null,
          polar, files: r.files, live: true, label: r.label, cached: !!start.cached,
          jobId, echo,
        };
      }
    }
  },
};

/* server segment payload → the shape PolarStage consumes
 * (anchors/segments kept, points packed as parallel arrays) */
export function normalizePolar(p) {
  const segments = (p.segments || []).map((s) => {
    const n = s.points.length;
    const t = new Float32Array(n), rv = new Float32Array(n), tv = new Float32Array(n);
    const hasC = s.points.some((pt) => pt.rho_c !== null && pt.rho_c !== undefined);
    const rc = hasC ? new Float32Array(n) : null, tc = hasC ? new Float32Array(n) : null;
    s.points.forEach((pt, i) => {
      t[i] = pt.t; rv[i] = pt.rho_v ?? 0; tv[i] = pt.theta_v ?? 0;
      if (hasC) { rc[i] = pt.rho_c ?? NaN; tc[i] = pt.theta_c ?? NaN; }
    });
    return {
      index: s.segment_index, t0: s.t0, t1: s.t1,
      anchorFrom: s.anchor_from, anchorTo: s.anchor_to,
      labelFrom: s.label_from, labelTo: s.label_to,
      blocks: s.blocks || [], markers: s.markers || null,
      n, t, rv, tv, rc, tc,
    };
  });
  return {
    jobId: p.job_id, rhoMax: p.rho_max || 1.45,
    duration: p.duration_s || (segments.length ? segments[segments.length - 1].t1 : 0),
    anchors: p.anchors || [], segments,
  };
}
