// SPDX-FileCopyrightText: 2026 Frédéric Berthommier
// SPDX-License-Identifier: GPL-3.0-or-later
/* compiler.js — the syllable BLOCK COMPILER panel (v3).
 *
 * Inspired by the stripped-down compiler dashboard of
 * nasqret.github.io/eml-formalization: an expression is *compiled* into
 * primitive blocks, the result is shown as metric tiles + a canonical
 * string + a clickable block tree. Here the blocks are SYLLABLES and the
 * compiler is the engine itself: syltraj's anchor walk over the SAMPA
 * phrase. Compilation never synthesizes — it is the cheap structural
 * half (design brief P4: preview/compile cheap, synthesis explicit).
 *
 * Layout of the panel (mirroring the eml dashboard):
 *   • source row      — mono input + Compile button + palette chips
 *   • metric tiles    — syllables · anchors · blocks · C/V · duration
 *   • block string    — the compiled segment sequence as labeled chips
 *                       (the analogue of the RPN/post-order string)
 *   • block canvas    — one card per anchor→anchor segment; click a card
 *                       to expand its internal structure (onset cluster
 *                       consonants with their (ρ, θ) targets, vowel
 *                       plateau, pause/breath flags) and — when a job is
 *                       loaded — to seek the continuous polar display to
 *                       exactly that segment.
 *
 * COVTL Console v3 — GPL-3.0-or-later (matches the engine license).
 */
import { el } from './render.js';
import { VOWELS, CONSONANTS, tokenizeSampa, isVowel } from './data.js';

const PALETTE_MARKERS = [
  { sym: '.', tip: 'syllable link (coarticulation, no pause)' },
  { sym: ' ', tip: 'short pause (tpause)' },
  { sym: '|', tip: 'long pause (tpause-long)' },
  { sym: '%', tip: 'expressive breath pause (~130 ms)' },
];
const PRESETS = [
  { label: 'ba da ga | iowa a g', text: 'ba da ga | iowa a g' },
  { label: 'Dis.iz.i.zi.fOR.@s', text: 'Dis.iz.i.zi.fOR.@s' },
  { label: 'pta.kli.pra', text: 'pta.kli.pra' },
  { label: 'kAtS dZiN tSwE', text: 'kAtS dZiN tSwE' },
];

const KIND_TIP = {
  initial: 'utterance-initial arc — neutral → first anchor',
  cluster: 'consonant cluster: onset sub-arcs toward each closure target',
  plateau: 'vowel plateau — stationary hold at the vowel target',
  background: 'vocalic background arc between vowel anchors',
  pause: 'pause arc between phrases/words',
  decay: 'amplitude decay into a pause',
  attack: 'amplitude attack out of a pause',
  terminal: 'phrase-terminal arc → neutral',
};

/* chronological phoneme string of an anchor→anchor stretch: clusters and
 * plateaus in engine order, '‿' marking a consonant group that follows a
 * vowel inside the same stretch (coda of the previous syllable fused with
 * the next onset — that is the engine's coarticulation, not a syllable) */
export function stretchLabel(blocks) {
  let out = '';
  let sawVowel = false;
  for (const b of blocks || []) {
    if (b.kind === 'plateau') { out += (b.vowel_key || '@'); sawVowel = true; }
    else if (b.kind === 'cluster' && b.cons_keys && b.cons_keys.length) {
      out += (sawVowel ? '‿' : '') + b.cons_keys.join('');
    }
    else if (b.breath) out += '%';
    else if (b.kind === 'pause') out += (b.long ? '|' : '␣');
    else if (b.kind === 'decay' || b.kind === 'attack') out += '·';
    else if (b.kind === 'initial' && !out) out += '▸';
    else if (b.kind === 'terminal') out += '◂';
  }
  return out || '·';
}

const degDisplay = (rad) => ((90 - rad * 180 / Math.PI) % 360 + 360) % 360;

export class SyllableCompiler {
  /* opts: { api, getTimings(), getGuardPolicy(), getLang(),
   *          onSendToInput(sampa), onSeekSegment(index), onLog() } */
  constructor(root, opts) {
    this.opts = opts;
    this.result = null;
    this.selected = -1;
    this.loading = false;
    this.userEdited = false;      // user typed their own blocks
    this._lastAuto = null;        // last string auto-filled from the pipeline
    this._autoTimer = null;
    root.append(this._build());
  }

  _build() {
    this.rootEl = el('section', { class: 'zone zone-compiler', id: 'zone-compiler' });
    const head = el('header', { class: 'zone-head' },
      el('h2', { text: 'Syllable compiler' }),
      el('span', { class: 'zone-sub', text: 'the engine’s articulation plan — auto-compiles the preview’s final SAMPA · type your own blocks to explore · no audio' }),
      el('span', { class: 'head-gap' }),
      el('span', { class: 'compiler-src-note mono', id: 'compiler-src-note' }),
      el('button', { class: 'btn btn-primary', id: 'btn-compile',
        'data-tip': 'Answers: HOW will the engine articulate it? Decomposes the SAMPA string into the real articulation plan — anchors, blocks, gesture durations, (ρ, θ) targets — as tiles, chips and clickable cards. No sound, no job. Step 2 of 3: Preview (what string) → Compile (what plan) → Synthesize (what sound).',
        title: 'Decompose into the engine’s anchor/block structure (no synthesis)',
        onclick: () => this.compile() }, 'Compile structure', el('kbd', { class: 'mini inverse', text: 'C' })));

    const palette = el('div', { class: 'palette' },
      el('span', { class: 'palette-group', text: 'vowels' }),
      VOWELS.map((v) => this._palChip(v, 'vowel')),
      el('span', { class: 'palette-group', text: 'consonants' }),
      CONSONANTS.map((c) => this._palChip(c, 'consonant')),
      el('span', { class: 'palette-group', text: 'markers' }),
      PALETTE_MARKERS.map((m) => this._palChip(m.sym === ' ' ? '␣' : m.sym, 'marker', m.sym)),
    );

    this.input = el('textarea', {
      class: 'mono compiler-input', rows: 2, spellcheck: 'false', id: 'compiler-input',
      placeholder: 'Compose syllable blocks, e.g. ba da ga | iowa a g  ·  pta.kli.pra',
    });
    this.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.compile(); }
      e.stopPropagation();      // plain-key shortcuts must not fire while typing
    });
    // typing one's own blocks detaches the panel from the auto pipeline
    // and invalidates any in-flight compile response
    this.input.addEventListener('input', () => {
      this._seq = (this._seq || 0) + 1;      // stale responses must not land
      this.userEdited = this.input.value !== this._lastAuto;
    });

    const presets = el('div', { class: 'chips-row compiler-presets' },
      el('span', { class: 'dim', text: 'presets:' }),
      PRESETS.map((p) => el('button', {
        class: 'chip chip-btn mono', text: p.label,
        onclick: () => { this.input.value = p.text; this.compile(); },
      })));

    const explainer = el('p', { class: 'hint compiler-explainer' },
      el('strong', { text: 'What “Compile structure” does: ' }),
      'the engine reads your syllable string and answers with its real articulation plan — the anchor list, the blocks between consecutive anchors (clusters, vowel plateaus, pauses), each phoneme’s (ρ, θ) target and the resulting duration. ',
      el('strong', { text: 'It never synthesizes: ' }),
      'no audio, no job. Use it to inspect or debug a string first; then send it to the phonetic input or press Synthesize to hear it.',
      el('br'),
      el('span', { class: 'dim', text: 'Cards are anchor→anchor COARTICULATION stretches, not dictionary syllables: a stretch may fuse the previous syllable’s coda with the next onset (shown as ‿) — that is exactly how the engine groups gestures.' }));

    this.tiles = el('div', { class: 'tiles', id: 'compiler-tiles' });
    this.resultNote = el('div', { class: 'compiler-result-note', id: 'compiler-result-note', style: 'display:none' });
    this.blockString = el('div', { class: 'block-string', id: 'compiler-blockstring' },
      el('span', { class: 'dim', text: 'compile to see the block sequence' }));
    this.canvas = el('div', { class: 'block-canvas', id: 'compiler-canvas' },
      el('div', { class: 'dim compiler-empty', id: 'compiler-empty' },
        'No compiled structure yet — type syllable blocks (or take a preset) and press Compile. ',
        el('br'), 'The engine answers with its real anchors, blocks and per-phoneme polar targets.'));
    this.errorBox = el('div', { class: 'compiler-error', id: 'compiler-error', style: 'display:none' });

    this.rootEl.append(
      head,
      el('div', { class: 'zone-body' },
        presets,
        this.input,
        palette,
        explainer,
        this.errorBox,
        this.resultNote,
        this.tiles,
        el('div', { class: 'block-string-wrap' },
          el('div', { class: 'block-string-title' }, 'block sequence', el('span', { class: 'dim', text: ' — one chip per anchor→anchor segment, in time order' })),
          this.blockString),
        el('div', { class: 'block-canvas-title' }, 'block cards', el('span', { class: 'dim', text: ' — click a card to inspect its structure; click again to collapse' })),
        this.canvas,
        el('div', { class: 'compiler-actions' },
          el('button', { class: 'btn btn-sm', id: 'btn-compiler-send', text: 'Use in phonetic input →',
            'data-tip': 'Send the compiled string to the phonetic source and preview it', onclick: () => this._send() }),
          el('span', { class: 'dim', id: 'compiler-link-note' })),
      ));
    return this.rootEl;
  }

  _palChip(sym, kind, raw) {
    return el('button', {
      class: `pal-chip pal-${kind} mono`, text: sym,
      'data-tip': raw === '.' ? 'syllable link' : raw === ' ' ? 'short pause'
        : raw === '|' ? 'long pause' : raw === '%' ? 'breath pause' : `insert ${sym}`,
      onclick: () => this._insert(raw ?? sym),
    });
  }

  _insert(sym) {
    const t = this.input;
    const s = sym === '␣' ? ' ' : sym;
    const pos = t.selectionStart ?? t.value.length;
    t.value = t.value.slice(0, pos) + s + t.value.slice(t.selectionEnd ?? pos);
    t.focus();
    t.setSelectionRange(pos + s.length, pos + s.length);
  }

  setInput(text) {
    if (document.activeElement !== this.input) this.input.value = text;
  }

  /* back to the pristine panel — used by the input reset (key R): clears
   * the field, the tiles, the block sequence, the cards and every note,
   * and invalidates any in-flight compile response */
  reset() {
    clearTimeout(this._autoTimer);
    this._seq = (this._seq || 0) + 1;        // stale responses must not land
    this.result = null;
    this.selected = -1;
    this.userEdited = false;
    this._lastAuto = null;
    this.input.value = '';
    this.tiles.innerHTML = '';
    this.blockString.innerHTML = '';
    this.blockString.append(el('span', { class: 'dim', text: 'compile to see the block sequence' }));
    this.canvas.innerHTML = '';
    this.canvas.append(el('div', { class: 'dim compiler-empty', id: 'compiler-empty' },
      'No compiled structure yet — type syllable blocks (or take a preset) and press Compile. ',
      el('br'), 'The engine answers with its real anchors, blocks and per-phoneme polar targets.'));
    this._error(null);
    this.resultNote.style.display = 'none';
    this.resultNote.innerHTML = '';
    const link = document.getElementById('compiler-link-note');
    if (link) link.textContent = '';
  }

  /* step 2 follows step 1: compile the pipeline's final SAMPA (debounced,
   * cached). A string typed by hand is respected — we only note that the
   * panel has detached from the preview. */
  maybeAutoCompile(sampa) {
    clearTimeout(this._autoTimer);
    this._autoTimer = setTimeout(() => {
      if (this.userEdited && this.input.value !== sampa) {
        const noteEl = document.getElementById('compiler-link-note');
        if (noteEl) {
          noteEl.textContent = 'manual blocks kept (differ from the preview SAMPA) — ' +
            'clear the field to re-link, or press Compile to recompile them';
        }
        return;
      }
      this.userEdited = false;
      this._lastAuto = sampa;
      if (document.activeElement !== this.input) this.input.value = sampa;
      this.compile(sampa).catch(() => {});
    }, 120);
  }

  async compile(text) {
    const src = (text ?? this.input.value).trim();
    if (!src) { this._error('Nothing to compile — the source is empty.'); return; }
    this._error(null);
    // seq guard: under slow links, an older compile response must never
    // overwrite a newer one (the "blocks from an inadequate string" bug)
    this._seq = (this._seq || 0) + 1;
    const seq = this._seq;
    this.loading = true;
    const btn = document.getElementById('btn-compile');
    btn.disabled = true; btn.textContent = '⏳ compiling…';
    try {
      const r = await this.opts.api.compile({
        text: src, lang: this.opts.getLang(),
        timings: this.opts.getTimings(),
        guardPolicy: this.opts.getGuardPolicy(),
      });
      if (seq !== this._seq) return;            // a newer compile superseded this one
      if (text !== undefined) this.input.value = src;
      this.result = r;
      this.selected = -1;
      this.userEdited = src !== this._lastAuto;   // explicit Compile of a manual string stays manual
      this._render();
      const m = r.metrics;
      const note = document.getElementById('compiler-result-note');
      note.style.display = '';
      note.className = `compiler-result-note ok`;
      note.innerHTML = '';
      note.append(el('span', { class: 'ok-mark', text: '✓ plan compiled — ' }),
        el('span', { text: `${m.anchors} anchors · ${m.blocks} blocks · ${m.duration_s.toFixed(2)} s of planned gestures. ` }),
        el('span', { class: 'dim', text: 'Inspection only — nothing was synthesized. ' }),
        el('span', { text: 'Click a card below to inspect a segment, or press Synthesize to hear this string.' }));
      this.opts.onLog?.(`compiled ${m.syllables} syllable(s) · ${m.blocks} blocks · ${m.anchors} anchors · ${m.duration_s.toFixed(2)} s${r.cached ? ' (cache hit)' : ''}`);
    } catch (err) {
      this.result = null;
      const note = document.getElementById('compiler-result-note');
      note.style.display = 'none';
      this._error(`${err.errorClass || 'Error'}: ${err.message}${err.hint ? ' — ' + err.hint : ''}`);
      if (err.symbols?.length) this._errorRejected(err.symbols);
    } finally {
      this.loading = false;
      if (seq === this._seq) {
        btn.disabled = false;
        btn.textContent = 'Compile structure';
      }
    }
  }

  _errorRejected(symbols) {
    const box = document.getElementById('compiler-error');
    box.append(el('div', { class: 'compiler-rej mono' },
      'rejected: ', symbols.map((s) => el('span', {
        class: 'tok tok-rejected mono', text: s.symbol,
        'data-tip': (s.suggestions || []).length ? `→ ${s.suggestions.join(' / ')}` : s.reason,
      }))));
  }

  _error(msg) {
    const box = document.getElementById('compiler-error');
    box.style.display = msg ? '' : 'none';
    box.innerHTML = '';
    if (msg) box.append(el('div', { class: 'guard-banner guard-error', text: msg }));
  }

  _render() {
    const r = this.result;
    if (!r) return;
    this._renderTiles(r);
    this._renderBlockString(r);
    this._renderCanvas(r);
    const note = document.getElementById('compiler-src-note');
    note.textContent = r.live ? 'engine: syltraj (live)' : 'demo arithmetic (approximate — labeled)';
    note.className = `compiler-src-note mono ${r.live ? 'ok' : 'warn'}`;
  }

  _renderTiles(r) {
    const m = r.metrics;
    const tile = (label, value, tip) => el('div', { class: 'tile', 'data-tip': tip || '' },
      el('div', { class: 'tile-value mono', text: String(value) }),
      el('div', { class: 'tile-label', text: label }));
    this.tiles.innerHTML = '';
    this.tiles.append(
      tile('syllables', m.syllables, 'vowel plateaus — one per syllable nucleus'),
      tile('anchors', m.anchors, 'syltraj anchor list (▸ start, vowels, pauses, ◂ end)'),
      tile('blocks', m.blocks, 'engine blocks between consecutive anchors'),
      tile('C / V', `${m.consonants} / ${m.vowels}`, 'consonant closures / vowel nodes'),
      tile('duration', m.duration_s.toFixed(2) + ' s', `block steps: ${m.steps} @ 100 Hz`),
    );
  }

  _renderBlockString(r) {
    this.blockString.innerHTML = '';
    for (const s of r.segmentsPreview) {
      const isPause = s.kinds.includes('pause') || s.kinds.includes('terminal') || s.kinds.includes('initial');
      const chip = el('button', {
        class: `bstr-chip mono ${isPause ? 'bstr-pause' : ''} ${s.segment_index === this.selected ? 'sel' : ''}`,
        'data-tip': `segment ${s.segment_index}: ${s.t0.toFixed(2)}–${s.t1.toFixed(2)} s · ${s.n_steps} steps · ${s.kinds.join('+')}`,
        onclick: () => this.selectSegment(s.segment_index),
      }, s.stretch || s.label || '·');
      this.blockString.append(chip);
    }
  }

  _renderCanvas(r) {
    this.canvas.innerHTML = '';
    const empty = document.getElementById('compiler-empty');
    if (empty) empty.remove();
    for (const s of r.segmentsPreview) {
      const card = this._card(r, s);
      this.canvas.append(card);
    }
  }

  _card(r, s) {
    const expanded = s.segment_index === this.selected;
    const kinds = [...new Set(s.kinds)];
    const isPause = kinds.some((k) => ['pause', 'initial', 'terminal'].includes(k));
    const card = el('div', {
      class: `block-card ${isPause ? 'card-pause' : ''} ${expanded ? 'expanded' : ''}`,
      role: 'button', tabindex: '0',
      onclick: () => this.selectSegment(s.segment_index),
      onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.selectSegment(s.segment_index); } },
    });
    const stretch = s.stretch || stretchLabel(s.blocks) || s.label;
    card.append(
      el('div', { class: 'card-head' },
        el('span', { class: 'card-idx mono', text: `S${s.segment_index}` }),
        el('span', { class: 'card-label mono', text: stretch, 'data-tip': 'chronological phoneme string — ‿ marks consonants fusing with the previous vowel (coarticulation, not a syllable boundary)' }),
        el('span', { class: 'card-kind', text: kinds.join('+') })),
      el('div', { class: 'card-time mono', text: `${s.t0.toFixed(2)}–${s.t1.toFixed(2)} s · ${s.n_steps} st` }),
    );
    if (expanded) {
      const body = el('div', { class: 'card-body' });
      // onset consonant cluster with polar targets
      if (s.cons.length) {
        body.append(el('div', { class: 'card-row-title', text: 'onset / cluster' }));
        const consRow = el('div', { class: 'card-cons' });
        for (const c of s.cons) {
          const tgt = r.targets[c];
          const rho = tgt ? (tgt.rho / (r.rhoMax || 1.45)).toFixed(2) : '·';
          const deg = tgt ? degDisplay(tgt.theta).toFixed(0) : '·';
          consRow.append(el('span', {
            class: 'cons-chip mono', text: c,
            'data-tip': tgt ? `target ρ ${tgt.rho.toFixed(2)} cm (n. ${rho}) · θ ${deg}° (display)` : 'target unavailable',
          }, c, el('sub', { text: tgt ? `${rho}·${deg}°` : '' })));
        }
        body.append(consRow);
      }
      if (s.vowel) {
        const vt = r.targets[s.vowel];
        const rho = vt ? (vt.rho / (r.rhoMax || 1.45)).toFixed(2) : '·';
        const deg = vt ? degDisplay(vt.theta).toFixed(0) : '·';
        body.append(el('div', { class: 'card-row-title', text: 'nucleus' }));
        body.append(el('div', { class: 'card-cons' },
          el('span', { class: 'cons-chip cons-vowel mono', 'data-tip': vt ? `plateau target ρ ${vt.rho.toFixed(2)} cm · θ ${deg}°` : '' },
            s.vowel, el('sub', { text: vt ? `${rho}·${deg}°` : '' }))));
      }
      const kindsRow = el('div', { class: 'card-kinds' });
      for (const k of kinds) {
        kindsRow.append(el('span', { class: `kind-badge kind-${k}`, 'data-tip': KIND_TIP[k] || k, text: k }));
      }
      body.append(kindsRow);
      body.append(el('div', { class: 'card-actions' },
        el('button', {
          class: 'btn btn-xs', text: 'seek polar display →',
          onclick: (e) => { e.stopPropagation(); this.opts.onSeekSegment?.(s.segment_index); },
        })));
      card.append(body);
    }
    return card;
  }

  selectSegment(index) {
    this.selected = this.selected === index ? -1 : index;
    if (this.result) {
      this._renderBlockString(this.result);
      this._renderCanvas(this.result);
    }
    if (this.selected >= 0) this.opts.onSeekSegment?.(index, { fromCard: true });
  }

  markPlayingSegment(index) {
    // highlight the chip matching the polar display's current block
    if (!this.result) return;
    this.blockString.querySelectorAll('.bstr-chip').forEach((c, i) => {
      c.classList.toggle('playing', i === index);
    });
  }

  _send() {
    const src = (this.input.value || '').trim();
    if (src) this.opts.onSendToInput?.(src);
  }
}

/* helper reused by app.js for the stage's own compile chip */
export function segmentLabel(seg) {
  if (!seg) return '·';
  const cons = (seg.blocks || []).flatMap((b) => b.cons_keys || []);
  const vowel = (seg.blocks || []).find((b) => b.kind === 'plateau')?.vowel_key || '';
  return cons.join('') + vowel || seg.labelFrom || '·';
}
