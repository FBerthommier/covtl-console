// SPDX-FileCopyrightText: 2026 Frédéric Berthommier
// SPDX-License-Identifier: GPL-3.0-or-later
/* spectrogram.js — spectrogram, phonetic segmentation overlay, time cursor.
 * The spectrogram is computed in the browser (radix-2 FFT, Hann window)
 * from the audio returned by the backend (or by the demo renderer), so the
 * picture always shows the actual signal. In LIVE mode the server can also
 * supply a precomputed PNG; this renderer is the offline fallback. */

const FFT_SIZE = 1024;
const HOP = 256;
const FMAX = 8000;

/* magma-like ramp tuned for the dark lab theme */
const RAMP = [
  [0.00, 8, 10, 16], [0.18, 40, 24, 74], [0.38, 120, 40, 105],
  [0.58, 194, 68, 96], [0.75, 227, 115, 52], [0.90, 248, 178, 60],
  [1.00, 255, 236, 180],
];
function rampColor(u) {
  let i = 0;
  while (i < RAMP.length - 2 && u > RAMP[i + 1][0]) i += 1;
  const a = RAMP[i], b = RAMP[i + 1];
  const t = (u - a[0]) / (b[0] - a[0] || 1);
  return [a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t];
}

/* iterative radix-2 FFT (in-place, real input → magnitude spectrum) */
function fftMagnitudes(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i += 1) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -2 * Math.PI / len;
    for (let i = 0; i < n; i += len) {
      for (let k = 0; k < len / 2; k += 1) {
        const c = Math.cos(ang * k), s = Math.sin(ang * k);
        const xr = re[i + k + len / 2] * c - im[i + k + len / 2] * s;
        const xi = re[i + k + len / 2] * s + im[i + k + len / 2] * c;
        re[i + k + len / 2] = re[i + k] - xr; im[i + k + len / 2] = im[i + k] - xi;
        re[i + k] += xr; im[i + k] += xi;
      }
    }
  }
  const m = new Float32Array(n / 2);
  for (let i = 0; i < n / 2; i += 1) m[i] = Math.hypot(re[i], im[i]);
  return m;
}

export class SpectrogramView {
  constructor(container, { onSeek } = {}) {
    this.container = container;
    this.onSeek = onSeek;
    this.spec = document.createElement('canvas');
    this.overlay = document.createElement('canvas');
    container.append(this.spec, this.overlay);
    this.spec.className = 'spec-canvas';
    this.overlay.className = 'spec-overlay';
    this.duration = 0;
    this.segments = [];
    this.f0Curve = null;
    this.cursorT = -1;
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    this._bind();
    this._raf = null;
  }

  /* ── data ── */
  setSource(buffer, segments, f0Curve, anchors) {
    this.duration = buffer.duration;
    this.segments = segments || [];
    this.f0Curve = f0Curve || null;
    this.anchors = anchors || [];      // v3: amber anchor lines (brief §8.1)
    const data = buffer.getChannelData(0);
    const sr = buffer.sampleRate;
    const win = new Float32Array(FFT_SIZE);
    for (let i = 0; i < FFT_SIZE; i += 1) win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (FFT_SIZE - 1));
    const frames = Math.max(1, Math.floor((data.length - FFT_SIZE) / HOP));
    this.frames = frames;
    this.mag = new Float32Array(frames * (FFT_SIZE / 2));
    const re = new Float32Array(FFT_SIZE), im = new Float32Array(FFT_SIZE);
    let peak = 1e-9;
    for (let f = 0; f < frames; f += 1) {
      const off = f * HOP;
      for (let i = 0; i < FFT_SIZE; i += 1) { re[i] = (data[off + i] || 0) * win[i]; im[i] = 0; }
      const m = fftMagnitudes(re, im);
      for (let b = 0; b < FFT_SIZE / 2; b += 1) {
        const v = Math.log10(1 + 40 * m[b]);
        this.mag[f * (FFT_SIZE / 2) + b] = v;
        if (v > peak) peak = v;
      }
    }
    this.peak = peak;
    this.render();
  }

  setPng(pngUrl, duration, segments) {
    const img = new Image();
    img.onload = () => { this.pngImg = img; this.duration = duration; this.segments = segments || []; this.render(); };
    img.src = pngUrl;
  }

  /* ── layout ── */
  _layout() {
    const w = this.container.clientWidth || 900;
    const h = Math.round(Math.min(340, Math.max(240, w * 0.36)));
    this.W = w; this.H = h; this.segH = 24;
    for (const c of [this.spec, this.overlay]) {
      c.width = w * this.dpr; c.height = h * this.dpr;
      c.style.width = w + 'px'; c.style.height = h + 'px';
    }
    this.spec.getContext('2d').setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.overlay.getContext('2d').setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  render() {
    this._layout();
    this._drawSpec();
    this._drawOverlay();
  }

  _drawSpec() {
    const ctx = this.spec.getContext('2d');
    ctx.fillStyle = '#07090d';
    ctx.fillRect(0, 0, this.W, this.H);
    if (this.pngImg) {
      ctx.drawImage(this.pngImg, 0, 0, this.W, this.H - this.segH);
      return;
    }
    if (!this.mag) return;
    const bins = FFT_SIZE / 2;
    const binMax = Math.min(bins - 1, Math.round(FMAX / (44100 / FFT_SIZE)));
    // putImageData bypasses the DPR transform — raster into an offscreen
    // canvas at native pixel size, then draw scaled into CSS space
    const imgH = this.H - this.segH;
    const tmp = this._specTmp || (this._specTmp = document.createElement('canvas'));
    if (tmp.width !== this.W || tmp.height !== imgH) { tmp.width = this.W; tmp.height = imgH; }
    const tctx = tmp.getContext('2d');
    const img = tctx.createImageData(this.W, imgH);
    for (let x = 0; x < this.W; x += 1) {
      const f = Math.min(this.frames - 1, Math.round(x / this.W * (this.frames - 1)));
      for (let y = 0; y < imgH; y += 1) {
        const b = Math.round((1 - y / (imgH - 1)) * binMax);
        const v = this.mag[f * bins + b] / this.peak;
        const [r, g, bl] = rampColor(Math.pow(v, 1.35));
        const o = (y * this.W + x) * 4;
        img.data[o] = r; img.data[o + 1] = g; img.data[o + 2] = bl; img.data[o + 3] = 255;
      }
    }
    tctx.putImageData(img, 0, 0);
    ctx.drawImage(tmp, 0, 0, this.W, imgH);
    // frequency gridlines
    ctx.strokeStyle = 'rgba(255,255,255,0.07)';
    ctx.fillStyle = 'rgba(200,210,228,0.55)';
    ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
    ctx.lineWidth = 1;
    for (const khz of [1, 2, 3, 4, 5, 6, 7]) {
      const y = (1 - (khz * 1000) / FMAX) * (this.H - this.segH);
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(this.W, y); ctx.stroke();
      ctx.fillText(khz + 'k', 4, y - 3);
    }
  }

  _drawOverlay() {
    const ctx = this.overlay.getContext('2d');
    ctx.clearRect(0, 0, this.W, this.H);
    if (!this.duration) return;
    const x = (t) => t / this.duration * this.W;
    // v3 — anchor overlay: the same ticks as the scrub bar (brief §8.1).
    // Anchors arrive as {t, label, kind}: synthetic anchors (▸ start /
    // ◂ end, kind 'synth') draw dashed cyan with their glyph; regular
    // anchors draw solid amber with their phonetic label when there is
    // room before the next anchor.
    const anchorList = (this.anchors || []).map((a) => (typeof a === 'number' ? { t: a } : a));
    if (anchorList.length) {
      ctx.lineWidth = 1;
      ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
      ctx.textBaseline = 'top';
      anchorList.forEach((a, i) => {
        const synth = a.kind === 'synth';
        const ax = Math.round(x(a.t)) + 0.5;
        ctx.strokeStyle = synth ? 'rgba(87,184,216,0.6)' : 'rgba(232,163,61,0.75)';
        if (synth) ctx.setLineDash([4, 3]);
        ctx.beginPath(); ctx.moveTo(ax, 0); ctx.lineTo(ax, this.H - this.segH); ctx.stroke();
        ctx.setLineDash([]);
        // label — room check against the next anchor (≥ 14 px)
        const lbl = a.label || (synth ? (i === 0 ? '▸' : '◂') : '');
        const nextT = anchorList[i + 1] ? (anchorList[i + 1].t ?? anchorList[i + 1]) : this.duration;
        const room = x(nextT) - x(a.t);
        if (lbl && (synth || room >= 14)) {
          ctx.fillStyle = synth ? 'rgba(87,184,216,0.9)' : 'rgba(232,163,61,0.95)';
          const tx = Math.min(this.W - 10, ax + 3);
          ctx.fillText(lbl, tx, 2);
        }
      });
    }
    // segmentation band — phonetic units between anchors
    const y0 = this.H - this.segH;
    ctx.fillStyle = 'rgba(12,15,22,0.92)';
    ctx.fillRect(0, y0, this.W, this.segH);
    let alt = 0;
    for (const s of this.segments) {
      if (s.type === 'rejected' || s.end <= s.start) continue;
      const sx = x(s.start), sw = Math.max(1, x(s.end) - x(s.start));
      const isPause = s.type.startsWith('pause');
      const isSkip = s.type === 'skip';
      ctx.fillStyle = isSkip ? 'rgba(90,100,120,0.04)'
        : isPause ? 'rgba(90,100,120,0.14)'
        : (alt % 2 ? 'rgba(76,195,255,0.10)' : 'rgba(76,195,255,0.04)');
      ctx.fillRect(sx, y0, sw, this.segH);
      if (!isSkip) {
        ctx.fillStyle = isPause ? '#8a94a8' : '#c3d4ea';
        ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
        const label = s.sym;
        if (sw > 7 && sw > ctx.measureText(label).width + 2) {
          ctx.fillText(label, sx + sw / 2 - ctx.measureText(label).width / 2, y0 + 7);
        }
      }
      ctx.strokeStyle = 'rgba(255,255,255,0.10)';
      ctx.beginPath(); ctx.moveTo(sx, y0); ctx.lineTo(sx, this.H); ctx.stroke();
      if (!isPause && !isSkip) alt += 1;
    }
    // f0 overlay
    if (this.f0Curve && this.showF0) {
      ctx.strokeStyle = 'rgba(76,195,255,0.9)';
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      let started = false;
      for (let t = 0; t <= this.duration; t += 0.008) {
        const f = this.f0Curve(t);
        if (f == null) { started = false; continue; }
        const px = x(t), py = (1 - f / FMAX) * (this.H - this.segH);
        if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
      }
      ctx.stroke();
    }
    // cursor
    if (this.cursorT >= 0) {
      const cx = x(this.cursorT);
      ctx.strokeStyle = '#4cc3ff';
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, this.H); ctx.stroke();
      const label = this.cursorT.toFixed(2) + ' s';
      ctx.font = '10px ui-monospace, Menlo, Consolas, monospace';
      const tw = ctx.measureText(label).width + 10;
      const bx = Math.min(this.W - tw - 2, Math.max(2, cx + 4));
      ctx.fillStyle = 'rgba(10,13,20,0.9)';
      ctx.fillRect(bx, 2, tw, 16);
      ctx.fillStyle = '#4cc3ff';
      ctx.fillText(label, bx + 5, 13);
    }
  }

  cursor(t) { this.cursorT = t; this._drawOverlay(); }
  toggleF0(on) { this.showF0 = on; this._drawOverlay(); }

  _bind() {
    this.overlay.style.cursor = 'crosshair';
    this.overlay.addEventListener('pointerdown', (e) => {
      if (!this.duration) return;
      const r = this.overlay.getBoundingClientRect();
      this.onSeek?.((e.clientX - r.left) / r.width * this.duration);
    });
  }

  exportPng() {
    const c = document.createElement('canvas');
    c.width = this.W * this.dpr; c.height = this.H * this.dpr;
    const ctx = c.getContext('2d');
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.drawImage(this.spec, 0, 0, this.W, this.H);
    ctx.drawImage(this.overlay, 0, 0, this.W, this.H);
    return new Promise((res) => c.toBlob(res, 'image/png'));
  }
}
