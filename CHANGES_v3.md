<!-- SPDX-FileCopyrightText: 2026 Frédéric Berthommier -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# COVTL Console v3 — Change Record

Scope: implement the COVTL Lab Console design brief (October 2026, 40 pp.)
on the v2 codebase, plus the syllable block compiler inspired by
nasqret.github.io/eml-formalization ("compile blocks — here, syllables").
The engine wins wherever brief and engine disagree (brief §1 preamble);
this record lists both the implementation and the honest divergences.

Deliverables:

1. Continuous polar display (brief ch. 6) — data model, playback engine,
   start-early, transport, rendering.
2. Syllable block compiler (eml-inspired) — endpoint + panel.
3. Brief API surface — health/languages/speakers, job payloads, segments.
4. Layout + design system (brief ch. 4, 9) — header chips, 6-group control
   column, stage zones, dark instrument tokens.
5. State machine + shortcuts (brief ch. 11, §12.9).
6. v2 surface preserved; docs; standalone build; packaging.

---

## A. Engine ground truth established first (brief ch. 2)

- `.polar` format v4 verified live: JSON, 100 Hz, `trajectory.vocalic /
  consonantal {rho, theta}` (trigonometric radians), `phonemes[]` with
  t0/t1 spans, `inventory[]`. v2's parser read a pre-v4 layout and always
  returned None in live mode — replaced by the segment pipeline below.
- `syltraj.build_phrase_pval(phrase, t_cons, t_voy, pause_*)` returns
  `(Pval, blocks, nodes, anchors)`; `SylBlock` kinds observed:
  initial, cluster, plateau, background, pause, decay, attack, terminal.
- Worked example `Dis.iz.i.zi.fOR.@s` (Tcons 100/Tvoy 80): **11 anchors,
  16 blocks, 6 syllable plateaus, 238 steps (2.38 s)**. The brief's
  "7 anchors / 6 blocks" was an idealization; the engine's own anchor
  list (incl. ▸ start, word-end, pause, ◂ end anchors) is what the
  display consumes, per the brief's own acceptance rule ("block
  boundaries shown = anchor list returned by the engine").

## B. Anchor timestamps — instrumented replay, not reimplementation

- `build_global_pval` iterates over consecutive anchor pairs; every block
  append constructs a `SylBlock`, and every iteration calls
  `_collect_consonants` exactly once (after the possible departure
  plateau). server.py hooks BOTH (same idiom as
  `polar_video._recorded_build_pval`), producing anchor k's step position
  as: cumulative block steps at iteration k, minus that iteration's
  departure plateau (plateaus are never emitted after the hook —
  verified against the walk source).
- Hard drift checks: recorded block count == engine blocks, iteration
  count == len(anchors)−1; failures raise `StructureDrift` instead of
  guessing. Verified on the worked example, `ba da ga | iowa a g`
  (22 anchors), breath-pause input, and multi-phrase jobs.
- Live verification (jd3, en, audio-only): `polar_ready` observed True
  BEFORE `wav_ready` on a fresh job; anchors 0.00/0.20/0.40/…/2.38;
  WAV duration 2.3746 s vs structure 2.38 s (audio quantization).

## C. Bridge v3 (server.py)

- New: `POST /api/compile` — anchors/blocks/nodes/metrics/segments_preview/
  polar targets, guard-aware, LRU(64). Mirrors the synthesis walk exactly
  (same `structure_compile` helper).
- New: `GET /api/job/{id}/polar` — segment payload per brief annex A.4:
  anchors[], segments[{t0,t1,anchor_from/to,labels,blocks,markers,points}],
  points at 100 Hz with null channels, **θ pre-converted to display
  degrees (0° top, clockwise: deg = (90 − deg_trig) mod 360)** and
  **ρ normalized 0..1** (rho_max carried in the payload).
- New: `/api/health`, `/api/languages`, `/api/speakers?lang=` (brief §10.3).
- Worker v3: stage 1 builds structure + writes the `.polar` (engine's own
  `build_polar`/`write_polar`, same params → byte-identical content) and
  flips `polar_ready` BEFORE the VTL runs; stage 2 = `Pipeline.run(...,
  polar=(video-polar mode))`. On VTL failure the trajectory stays
  available (brief §6.2). Legacy engine → no continuous display (noted).
- Job payload: v2 fields + `polar_ready`, `wav_ready`, `anchors`,
  `block_count`, `duration_s`, `echo` (also on cache hits — v3 fix).
- Synthesis cache key now includes the engine version (brief §11.1).
- v2 endpoints unchanged (`/api/status` extended with compile-cache stats
  and inventory digest).

## D. Continuous polar display (js/polar.js — rewritten)

- Layered canvases: static grid (rings 0.25/0.5/0.75/1.0 dashed outer,
  8 spokes, ρ labels on the 225° diagonal) cached; dynamic layer redrawn
  per tick: trail (fading ~300 ms), current segment full opacity, anchor
  dots (reached) / dashed ring (next), consonantal target dot, white head
  + halo, progress arc on the outer ring.
- Dual clock: own monotonic clock in polar-only mode; audio element is
  master once attached (`audio.currentTime` read-only in the loop);
  block-boundary handoff via `_pendingAudioSync`; if autoplay is refused
  the own clock keeps the display alive (audio takes over on its `play`
  event). Replay from 0 when the audio ran to its end.
- Background-tab robustness: rAF freezes in hidden tabs — a 50 ms interval
  watchdog advances the loop when rAF stalls (>120 ms), so start-early
  works even when the console tab is hidden.
- Transport wiring (app.js): play/pause/stop, A−/A+ (`[` `]`), scrub bar
  with anchor ticks (click a tick = snap to that anchor; amber band =
  current block), speeds 0.25/0.5/1/2 (also `playbackRate`), loop-block,
  downloads menu, time + ρ/θ readout (both branches) + Block k/n +
  A_k→A_k+1 badges, polar-only/synced badge.
- Spectrogram (v2 renderer kept): `setSource` gains an `anchors` argument →
  amber anchor vlines; cursor follows the tick.

## E. Syllable block compiler (js/compiler.js + /api/compile)

Inspired by the eml-formalization dashboard layout:
input + Compile → **metric tiles** (syllables · anchors · blocks · C/V ·
duration) → **block sequence** chips (the RPN-string analogue, one chip per
anchor→anchor segment) → **block cards** (the clickable-tree analogue):
click to expand onset cluster consonants with (ρ, θ) targets (normalized +
display degrees), nucleus plateau, block kinds, then "seek polar display →"
jumps to that segment; "Use in phonetic input →" routes the string to the
stage (mode phonetic, preview). Presets + inventory palette chips.
Demo mode: arithmetic mirror (cluster (m+1)·Tcons, plateau Tvoy, pauses),
labeled "demo arithmetic — approximate" everywhere.

## F. Layout, design system, state machine

- index.html rebuilt per brief §4: 56 px header (wordmark, state chip,
  language/speaker/backend chips with health drawer), 400 px control
  column with the 6 ordered groups, stage zones (preview stack with
  aligned 178 px label grid → action bar + progress strip → compiler →
  polar panel → transport → spectrogram → log).
- css/app.css rewritten on the brief ch. 9 tokens (bg #101418/#171B21/
  #1D232B, amber #E8A33D, cyan #57B8D8, branch V #E0524A / C #5A8FD8,
  4 px spacing ladder, 1 px drawn structure, amber drift edges).
- Timings = steppers (±10 ms) with amber custom edge + "Reset to language
  profile"; f0 pre-filled from the registry (60–350 clamp); unverified
  speaker+lang banner (brief §5.1 copy).
- Guard: warn default per brief §2.5 (v2 defaulted to error); red-reject
  UX per ch. 7 verified live: red strikethrough + dotted underline,
  count badge, banner with `→ suggestions`, policy error blocks with the
  exact button labels, warn relabels to "Synthesize anyway (N dropped)".
- State machine per Table 11.1; late preview responses can no longer
  downgrade a running job's state (v3 fix).
- Keyboard per §12.9 (plain keys outside editors; `C` added for the
  compiler; `?` overlay with a "New in v3" section).

## G. Divergences from the brief (engine / continuity wins)

| Brief says | v3 does | Why |
|---|---|---|
| one subprocess per job (§10.2) | in-process `Pipeline` per job on a thread (v2 model) | the v2 bridge has run in-process against this engine all along (speaker/lang passed per job); a subprocess hop adds failure modes without changing outputs here |
| 7 anchors / 6 blocks for the worked example (§2.9) | 11 anchors / 10 segments (engine's own list) | the engine's anchor list includes start/word-end/pause/end anchors; the brief's own acceptance test binds the display to the engine's answer |
| `GET /api/jobs/{id}/...` plural paths (§10.3) | `/api/job/{id}/...` (v2 paths) | v2 client compatibility; new fields added to the same payloads |
| polar-ready during synthesis implies engine order (§6.6) | bridge builds the trajectory stage first | `Pipeline.run` writes .polar after the WAV; the bridge reorders stages using the engine's own `build_polar` (identical bytes, verified), which is the honest way to satisfy start-early with this engine |
| `error` guard default (v2 console) | `warn` default (brief §2.5) | brief follows the engine CLI default |

## H. Test log (2026-10-27, local engine v1.1.0)

- Direct bridge tests (real engine): structure_compile on the worked
  example / multi-phrase / breath inputs; fresh synthesis job with
  `polar_ready` observed before `wav_ready`; segment payload θ/ρ checks.
- Browser (live bridge on 8421): probe→live; preview stack; compile
  (22 anchors / 28 blocks / 4.04 s on `ba da ga | iowa a g`); synthesis
  cached + fresh; polar-only clock advancing (Block 1→7 while VTL runs);
  audio sync + replay-from-end fix; anchor stepping 0.20/0.40/back 0.20;
  loop toggle; downloads (wav/tract/polar/txt); guard error→warn flow
  (`B`/`c` red, suggestions, blocked/unblocked button labels); compiler
  card click → seek to 0.69 s (segment t0); screenshot review.
- Demo mode (static server): banner, demo compile labeled, demo synthesis
  with polar segments.
- Standalone: single-file build boots and synthesizes in demo mode
  (export-name fix for `$`/`$$` in the bundler); rebuild verified.
- Known acceptable behaviors: hidden tabs throttle rAF (watchdog covers
  the clock; rendering resumes on focus); demo compiler is arithmetic
  (labeled), the real walk needs the bridge.
