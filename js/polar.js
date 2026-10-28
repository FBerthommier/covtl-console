// SPDX-FileCopyrightText: 2026 Frédéric Berthommier
// SPDX-License-Identifier: GPL-3.0-or-later
/* polar.js — the CONTINUOUS polar (ρ, θ) display (design brief ch. 6).
 *
 * The display consumes the engine's own granularity and nothing coarser:
 * the utterance is the anchor list returned by syltraj and the segments
 * that run from one anchor to the next. The drawing head advances block
 * by block; stepping, scrubbing and speed control all respect the anchor
 * boundaries. It never invents syllable boundaries, never guesses timing,
 * and never re-synthesizes chunks.
 *
 * Clock model (brief §6.2–6.3):
 *   • polar-only mode — the trajectory is ready but the WAV is still
 *     rendering: the stage runs on its own monotonic clock at the
 *     selected speed (default 1×).
 *   • synced mode — an audio element is attached; its currentTime is the
 *     master clock, the visual loop only reads it. Handoff happens at a
 *     block boundary: when audio appears, the stage finishes the current
 *     block, then re-anchors on the audio clock (no mid-block dilation).
 *
 * θ convention: 0° at top, clockwise (payload arrives pre-converted);
 * ρ is normalized 0..1 over the job's radius range (ρ_max in the payload).
 *
 * COVTL Console v3 — GPL-3.0-or-later (matches the engine license).
 */

const COL = {
  bg: '#0d1117',
  grid: 'rgba(140,155,185,0.14)',
  gridLabel: 'rgba(140,155,185,0.5)',
  ring: 'rgba(160,175,205,0.32)',
  v: '#E0524A',           // vocalic branch — brief token branch.v
  c: '#5A8FD8',           // consonantal branch — brief token branch.c
  head: '#E7EBF0',        // ink.high
  anchorReached: 'rgba(231,235,240,0.9)',
  anchorNext: 'rgba(232,163,61,0.85)',
};
const TRAIL_S = 0.30;      // fading trail length (s) — brief §6.4

export class PolarStage {
  /* container: element that receives the canvases + badge bar.
   * opts.onTick({t, block, blockCount, playing, mode, rhoV, thetaV, rhoC, thetaC})
   * opts.onBlockChange(k) — fired when the head crosses into block k
   * opts.onTogglePlay()   — plane click */
  constructor(container, { onTick, onBlockChange, onTogglePlay } = {}) {
    this.container = container;
    this.onTick = onTick;
    this.onBlockChange = onBlockChange;
    this.onTogglePlay = onTogglePlay;

    this.wrap = document.createElement('div');
    this.wrap.className = 'polar-wrap';
    this.gridCv = document.createElement('canvas');   // static layer (cached)
    this.gridCv.className = 'polar-cv polar-grid';
    this.dynCv = document.createElement('canvas');    // dynamic layer (per tick)
    this.dynCv.className = 'polar-cv polar-dyn';
    this.wrap.append(this.gridCv, this.dynCv);
    container.append(this.wrap);

    this.payload = null;         // normalized segment payload
    this.playing = false;
    this.speed = 1;
    this.loopBlock = false;
    this.mode = 'idle';          // idle | polar-only | synced
    this.t = 0;
    this._clockBase = 0;         // performance.now() anchor for own clock
    this._tBase = 0;
    this._audio = null;          // HTMLAudioElement once synced
    this._pendingAudioSync = false;
    this._block = -1;
    this._raf = null;
    this._lastDom = 0;
    this._crossedBoundary = false;
    this.dpr = Math.min(2, window.devicePixelRatio || 1);

    this.dynCv.addEventListener('pointerdown', () => this.onTogglePlay?.());
    this._loop = this._loop.bind(this);
    this._resizeObserver = new ResizeObserver(() => this._layout());
    this._resizeObserver.observe(container);
  }

  /* ── data ─────────────────────────────────────────────────────── */
  setPayload(payload) {
    this.payload = payload;
    this.t = 0;
    this._block = -1;
    this._pendingAudioSync = false;
    if (this.mode !== 'synced' || !this._audio) this.mode = payload ? 'polar-only' : 'idle';
    this._layout();
    if (this.playing) this._reanchor();
    else this._drawFrame();
  }

  hasData() { return !!(this.payload && this.payload.segments.length); }

  /* ── audio sync ───────────────────────────────────────────────── */
  attachAudio(audioEl, { autoplay = false } = {}) {
    this._audio = audioEl;
    this._pendingAudioSync = true;      // handoff at the next block boundary
    this.mode = 'synced';
    if (!this._audioBound) {
      this._audioBound = true;
      audioEl.addEventListener('play', () => {
        if (this.playing) this._audioSyncNow();
        this._ensureRaf();
      });
      audioEl.addEventListener('ended', () => this.pause());
      audioEl.addEventListener('pause', () => { this._reanchor(); this._drawFrame(); });
    }
    if (autoplay) this._audioSyncNow();
    else this._drawFrame();
  }

  detachAudio() {
    this._audio = null;
    if (this.payload) this.mode = 'polar-only';
    this._reanchor();
  }

  _audioSyncNow() {
    // re-anchor on the audio clock (used when playback starts or at the
    // block-boundary handoff)
    this._pendingAudioSync = false;
    if (this._audio) {
      this.t = this._clamp(this._audio.currentTime);
      this.mode = 'synced';
    }
    this._reanchor();
  }

  /* ── transport ────────────────────────────────────────────────── */
  play() {
    if (!this.hasData()) return;
    if (this._audio && this.mode === 'synced') {
      // replay from the start when the audio already ran to its end
      if (this._audio.ended || this._audio.currentTime >= this._duration() - 0.05) {
        try { this._audio.currentTime = 0; } catch { /* noop */ }
      }
      this._audioSyncNow();
      this._audio.play().catch(() => { /* autoplay refused — own clock keeps the display alive */ });
    }
    this.playing = true;
    this._reanchor();
    this._ensureRaf();
  }

  pause() {
    this.playing = false;
    if (this._audio && this.mode === 'synced') this._audio.pause();
    this._reanchor();
    this._drawFrame();
  }

  toggle() { if (this.playing) this.pause(); else this.play(); }

  stop() {
    this.playing = false;
    if (this._audio) { try { this._audio.pause(); this._audio.currentTime = 0; } catch { /* noop */ } }
    this.t = 0;
    this._block = -1;
    this._reanchor();
    this._drawFrame();
  }

  setSpeed(s) {
    this.speed = s;
    if (this._audio && this.mode === 'synced') this._audio.playbackRate = s;
    this._reanchor();
  }

  setLoop(on) { this.loopBlock = !!on; }

  seek(t) {
    this.t = this._clamp(t);
    if (this._audio && this.mode === 'synced') {
      try { this._audio.currentTime = this.t; } catch { /* noop */ }
    }
    this._reanchor();
    this._drawFrame();
  }

  anchorTimes() { return (this.payload?.anchors || []).map((a) => a.t); }

  seekAnchor(k) {                    // 0-based anchor index
    const ts = this.anchorTimes();
    if (!ts.length) return -1;
    if (k < 0) k = 0;
    if (k >= ts.length) k = ts.length - 1;
    this.seek(ts[k]);
    return k;
  }

  prevAnchor() {
    const ts = this.anchorTimes();
    let k = 0;
    for (let i = 0; i < ts.length; i += 1) {
      if (ts[i] < this.t - 1e-6) k = i;
      else break;
    }
    return this.seekAnchor(k);
  }

  nextAnchor() {
    const ts = this.anchorTimes();
    const k = ts.findIndex((t) => t > this.t + 1e-6);
    return this.seekAnchor(k === -1 ? ts.length - 1 : k);
  }

  currentBlock() {
    const segs = this.payload?.segments || [];
    for (let i = segs.length - 1; i >= 0; i -= 1) {
      if (this.t >= segs[i].t0 - 1e-9) return i;
    }
    return 0;
  }

  blockCount() { return this.payload?.segments.length || 0; }

  /* ── clock internals ──────────────────────────────────────────── */
  _clamp(t) { return Math.max(0, Math.min(this._duration(), t)); }

  _duration() { return this.payload?.duration || 0; }

  _reanchor() {
    this._clockBase = performance.now();
    this._tBase = this.t;
  }

  _ensureRaf() {
    if (this._raf == null) this._raf = requestAnimationFrame(this._loop);
    // background tabs freeze requestAnimationFrame — a cheap interval
    // watchdog keeps the clock (and the audio handoff) running when hidden
    if (this._watchdog == null) {
      this._lastRaf = performance.now();
      this._watchdog = setInterval(() => {
        if (this.playing && performance.now() - this._lastRaf > 120) {
          this._loop(performance.now());
        }
      }, 50);
    }
  }

  _loop(now) {
    this._raf = null;
    this._lastRaf = now;
    if (!this.payload) return;
    if (this.playing) {
      // the audio clock is master only while the audio is actually running
      // (autoplay can be refused — then the own clock keeps the display alive)
      const audioActive = this._audio && !this._audio.paused && !this._audio.ended;
      if (this.mode === 'synced' && audioActive && !this._pendingAudioSync) {
        this.t = this._clamp(this._audio.currentTime);
      } else {
        this.t = this._clamp(this._tBase + (now - this._clockBase) / 1000 * this.speed);
      }
      if (this.loopBlock) {
        // wrap inside the current block — the phonetician's inspection loop
        const b = this.payload.segments[this.currentBlock()];
        if (b && b.t1 > b.t0 && this.t >= b.t1 - 1e-9) {
          this.seek(b.t0 + 0.001);
          this._ensureRaf();
          return;
        }
      } else if (this.t >= this._duration() - 1e-9) {
        this.t = this._duration();
        this.playing = false;
        if (this._audio) { try { this._audio.pause(); } catch { /* noop */ } }
        this._reanchor();
      }
      // audio handoff at a block boundary (never mid-block)
      if (this._pendingAudioSync && this._audio && this._crossedBoundary) {
        this._audioSyncNow();
      }
    }
    this._drawFrame();
    if (this.playing) this._ensureRaf();
  }

  /* ── geometry ─────────────────────────────────────────────────── */
  _layout() {
    const w = this.wrap.clientWidth || 520;
    const h = Math.max(320, Math.round(Math.min(w * 0.78, 560)));
    this.W = w; this.H = h;
    this.wrap.style.height = h + 'px';   // canvases are absolutely positioned
    this.cx = w * 0.5; this.cy = h * 0.52;
    this.R = Math.min(w, h) * 0.40;          // ρ = 1.0 (normalized) maps here
    for (const c of [this.gridCv, this.dynCv]) {
      c.width = w * this.dpr; c.height = h * this.dpr;
      c.style.width = w + 'px'; c.style.height = h + 'px';
    }
    this.gridCv.getContext('2d').setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.dynCv.getContext('2d').setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this._drawGrid();
    this._drawFrame();
  }

  /* display degrees (0 top, clockwise) → canvas xy; ρ already 0..1 */
  _xy(rho, thetaDeg) {
    const rad = thetaDeg * Math.PI / 180;
    return [this.cx + rho * this.R * Math.sin(rad),
            this.cy - rho * this.R * Math.cos(rad)];
  }

  _drawGrid() {
    const ctx = this.gridCv.getContext('2d');
    ctx.clearRect(0, 0, this.W, this.H);
    ctx.fillStyle = COL.bg;
    ctx.fillRect(0, 0, this.W, this.H);
    // spokes every 45°, labels every 90° (brief §6.4: eight spokes)
    ctx.strokeStyle = COL.grid;
    ctx.lineWidth = 1;
    for (let a = 0; a < 360; a += 45) {
      const [x1, y1] = this._xy(0, a), [x2, y2] = this._xy(1.12, a);
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
    ctx.fillStyle = COL.gridLabel;
    ctx.font = '10px ui-monospace, Menlo, Consolas, monospace';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (let a = 0; a < 360; a += 90) {
      const [lx, ly] = this._xy(1.2, a);
      ctx.fillText(a + '°', lx, ly);
    }
    // ρ rings — outermost dashed; labels along the lower-left diagonal
    for (const rho of [0.25, 0.5, 0.75, 1.0]) {
      ctx.strokeStyle = COL.ring;
      ctx.setLineDash(rho === 1.0 ? [4, 5] : []);
      ctx.beginPath(); ctx.arc(this.cx, this.cy, rho * this.R, 0, Math.PI * 2); ctx.stroke();
      ctx.setLineDash([]);
      const [lx, ly] = this._xy(rho, 225);
      ctx.fillText(rho.toFixed(2), lx, ly);
    }
    if (!this.hasData()) {
      ctx.fillStyle = 'rgba(154,165,177,0.85)';
      ctx.font = '13px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('The continuous display starts as soon as the engine produces a trajectory.',
        this.cx, this.H - 22);
      ctx.font = '11px ui-monospace, Menlo, Consolas, monospace';
      ctx.fillText('ρ 0 (center) → 1 (outer ring) · θ 0° top, clockwise',
        this.cx, this.H - 5);
    }
  }

  /* index of the sample at/before t inside a segment (binary search) */
  _segIndexAt(seg, t) {
    const { t: ts, n } = seg;
    if (n === 0) return -1;
    let lo = 0, hi = n - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (ts[mid] <= t) lo = mid; else hi = mid - 1;
    }
    return lo;
  }

  _branchAt(seg, i) {
    const out = { rhoV: seg.rv[i], thetaV: seg.tv[i], rhoC: null, thetaC: null };
    if (seg.rc && Number.isFinite(seg.rc[i])) {
      out.rhoC = seg.rc[i]; out.thetaC = seg.tc[i];
    }
    return out;
  }

  _drawFrame() {
    const ctx = this.dynCv.getContext('2d');
    ctx.clearRect(0, 0, this.W, this.H);
    if (!this.hasData()) { this._emitTick(null); return; }
    const segs = this.payload.segments;
    const t = this.t;

    const blk = this.currentBlock();
    if (blk !== this._block) {
      if (this._block >= 0) this._crossedBoundary = true;
      this._block = blk;
      this.onBlockChange?.(blk);
    }

    const tFrom = Math.max(0, t - TRAIL_S);

    /* branch drawing: current segment at full opacity, previous ones
     * inside the trail window with a fading alpha ramp (brief §6.4) */
    const drawBranch = (rhoKey, thetaKey, color) => {
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      for (let s = 0; s < segs.length; s += 1) {
        const seg = segs[s];
        if (seg.t1 <= tFrom || seg.t0 > t) continue;
        const iEnd = this._segIndexAt(seg, t);
        if (iEnd < 0) continue;
        const live = seg.t0 <= t && t < seg.t1;
        if (live) {
          ctx.globalAlpha = 1;
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          this._strokeBranch(ctx, seg, 0, iEnd, rhoKey, thetaKey);
        }
        const i0 = Math.max(0, this._segIndexAt(seg, tFrom));
        if (iEnd > i0) {
          const nWant = Math.max(2, Math.round((seg.t[iEnd] - Math.max(tFrom, seg.t0)) * 100));
          const stride = Math.max(1, Math.floor((iEnd - i0) / nWant * 2));
          ctx.strokeStyle = color;
          ctx.lineWidth = live ? 2 : 1.6;
          for (let i = i0; i < iEnd; i += stride) {
            const j = Math.min(iEnd, i + stride);
            const frac = Math.max(0.05, Math.min(1, (seg.t[i] - tFrom) / TRAIL_S));
            ctx.globalAlpha = 0.32 * frac;
            this._strokeBranch(ctx, seg, i, j, rhoKey, thetaKey);
          }
        }
      }
      ctx.globalAlpha = 1;
    };
    drawBranch('rv', 'tv', COL.v);
    drawBranch('rc', 'tc', COL.c);

    // anchor markers: reached = filled dot, next = dashed circle
    const anchors = this.payload.anchors;
    anchors.forEach((a, i) => {
      if (a.t > t + 1e-9) {
        if (i === blk + 1) {
          const seg = segs[Math.min(blk, segs.length - 1)];
          const idx = this._segIndexAt(seg, Math.min(t, seg.t1));
          if (idx >= 0) {
            const p = this._branchAt(seg, idx);
            const tgt = p.rhoC !== null ? [p.rhoC, p.thetaC] : [p.rhoV, p.thetaV];
            const [x, y] = this._xy(tgt[0], tgt[1]);
            ctx.strokeStyle = COL.anchorNext;
            ctx.setLineDash([3, 3]);
            ctx.lineWidth = 1.4;
            ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.stroke();
            ctx.setLineDash([]);
          }
        }
        return;
      }
      const segIdx = Math.max(0, i - 1);
      const seg = segs[Math.min(segIdx, segs.length - 1)];
      const idx = this._segIndexAt(seg, a.t);
      if (idx >= 0 && idx < seg.n) {
        const p = this._branchAt(seg, idx);
        const tgt = p.rhoC !== null ? [p.rhoC, p.thetaC] : [p.rhoV, p.thetaV];
        const [x, y] = this._xy(tgt[0], tgt[1]);
        ctx.fillStyle = COL.anchorReached;
        ctx.beginPath(); ctx.arc(x, y, 2.6, 0, Math.PI * 2); ctx.fill();
      }
    });

    // phonetic labels at target positions, for every ACTIVATED syllabic
    // block: reached blocks render faded, the block under the head at full
    // strength. Target positions come from the trajectory itself — the
    // plateau sample for the vowel, each consonant's mid-sub-arc sample
    // (where the arc peaks on the node target) — nothing is invented.
    {
      const labels = new Map();     // dedupe key → {x, y, text, active, count}
      for (const seg of segs) {
        if (seg.t0 > t + 1e-9) continue;           // not yet activated
        const active = t < seg.t1 - 1e-9;
        for (const b of seg.blocks || []) {
          if (b.t1 === undefined) continue;
          if (b.kind === 'plateau' && b.vowel_key) {
            const tm = Math.min(t, (b.t0 + b.t1) / 2);
            const idx = this._segIndexAt(seg, Math.max(seg.t0, Math.min(seg.t1, tm)));
            if (idx >= 0) {
              const p = this._branchAt(seg, idx);
              const key = 'V:' + b.vowel_key + ':' + p.rhoV.toFixed(2) + ':' + p.thetaV.toFixed(0);
              const hit = labels.get(key);
              if (hit) hit.count += 1;            // shared target — count, not hide
              else labels.set(key, { text: b.vowel_key, cat: 'V', active, count: 1, rho: p.rhoV, theta: p.thetaV });
            }
          } else if (b.kind === 'cluster' && b.cons_keys && b.cons_keys.length) {
            const m = b.cons_keys.length;
            b.cons_keys.forEach((ck, k) => {
              const tmid = b.t0 + (k + 0.5) * (b.t1 - b.t0) / m;
              if (tmid > t + 1e-9) return;         // sub-arc not reached yet
              const idx = this._segIndexAt(seg, Math.max(seg.t0, Math.min(seg.t1, tmid)));
              if (idx >= 0) {
                const p = this._branchAt(seg, idx);
                if (p.rhoC === null) return;
                const key = 'C:' + ck + ':' + p.rhoC.toFixed(2) + ':' + p.thetaC.toFixed(0);
                const hit = labels.get(key);
                if (hit) hit.count += 1;
                else labels.set(key, { text: ck, cat: 'C', active, count: 1, rho: p.rhoC, theta: p.thetaC });
              }
            });
          }
        }
      }
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      for (const l of labels.values()) {
        const [x, y] = this._xy(l.rho, l.theta);
        const text = l.count > 1 ? `${l.text}·${l.count}` : l.text;
        ctx.globalAlpha = l.active ? 0.95 : 0.4;
        ctx.font = '600 12px ui-monospace, Menlo, Consolas, monospace';
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(10,13,18,0.85)';
        ctx.strokeText(text, x, y - 12);
        ctx.fillStyle = l.cat === 'V' ? COL.v : COL.c;
        ctx.fillText(text, x, y - 12);
      }
      ctx.globalAlpha = 1;
    }

    // head marker + halo (the only saturated elements besides the branches)
    const cur = segs[blk];
    let tickData = null;
    if (cur) {
      const idx = this._segIndexAt(cur, t);
      if (idx >= 0) {
        const p = this._branchAt(cur, idx);
        tickData = p;
        if (p.rhoC !== null) {
          const [x, y] = this._xy(p.rhoC, p.thetaC);
          ctx.fillStyle = COL.c;
          ctx.globalAlpha = 0.9;
          ctx.beginPath(); ctx.arc(x, y, 3.4, 0, Math.PI * 2); ctx.fill();
          ctx.globalAlpha = 1;
        }
        const [x, y] = this._xy(p.rhoV, p.thetaV);
        const grad = ctx.createRadialGradient(x, y, 0, x, y, 12);
        grad.addColorStop(0, 'rgba(231,235,240,0.35)');
        grad.addColorStop(1, 'rgba(231,235,240,0)');
        ctx.fillStyle = grad;
        ctx.beginPath(); ctx.arc(x, y, 12, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = COL.head;
        ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
      }
    }

    this._emitTick(tickData);
  }

  _strokeBranch(ctx, seg, i0, i1, rhoKey, thetaKey) {
    const rs = seg[rhoKey], th = seg[thetaKey];
    if (!rs) return;
    // collect the finite run, then stroke it as a quadratic midpoint curve
    const pts = [];
    for (let i = i0; i <= i1; i += 1) {
      const r = rs[i];
      if (!Number.isFinite(r)) { if (pts.length > 1) this._strokePts(ctx, pts); pts.length = 0; continue; }
      pts.push(this._xy(r, th[i]));
    }
    if (pts.length > 1) this._strokePts(ctx, pts);
  }

  _strokePts(ctx, pts) {
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    if (pts.length === 2) {
      ctx.lineTo(pts[1][0], pts[1][1]);
    } else {
      for (let i = 1; i < pts.length - 1; i += 1) {
        const mx = (pts[i][0] + pts[i + 1][0]) / 2;
        const my = (pts[i][1] + pts[i + 1][1]) / 2;
        ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
      }
      ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
    }
    ctx.stroke();
  }

  _emitTick(p) {
    const now = performance.now();
    if (this.playing && this._lastDom && now - this._lastDom < 100) return;
    this._lastDom = now;
    this.onTick?.({
      t: this.t,
      block: this._block < 0 ? 0 : this._block,
      blockCount: this.blockCount(),
      playing: this.playing,
      mode: this.mode,
      speed: this.speed,
      loop: this.loopBlock,
      duration: this._duration(),
      ...(p || {}),
    });
  }

  destroy() {
    this._resizeObserver.disconnect();
    if (this._raf != null) cancelAnimationFrame(this._raf);
    if (this._watchdog != null) clearInterval(this._watchdog);
    this.wrap.remove();
  }
}
