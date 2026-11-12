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


## Correction round — N1/N2/N3 (2026-11-07)

External audit findings N1 (speaker parameter without effect), N2
(server freeze during long syntheses) and N3 (file written outside
out/ via label). Fixes span the console AND the engine (covtl-pipeline
branch `fix/n1-n3-speaker-label`: `resolve_speaker`/`sanitize_label`
in `vtl_synth/core/pipeline.py`).

### Verified code-level facts

- N1 — `POST /api/synthesize` validates `speaker` against the engine
  registry: unknown name → **422 `UnknownSpeaker`**, no job
  (`validate_synth_request` in `covtl_console/server.py`). The engine
  resolves a registered name per request (`Pipeline.__init__` →
  `resolve_speaker`): the orthogonal branch reads the registered
  `.speaker` file (`speaker_file` forwarded to `build_phrase_tract`)
  and `f0_hz=None` follows the REQUESTED speaker's registry
  `f0_default`. Requesting the active speaker is byte-identical to the
  previous output (same file, same f0); 5 speakers now produce 5
  distinct WAVs (were: 5× identical jd3 bytes, SHA256 411c3daa…).
- N1 honesty — `/api/speakers` publishes `speaker_layers`
  (per_request: orthogonal branch + f0; process_global:
  geometry/constants + audio anatomy; full_swap:
  install_speaker.py + restart) and `in_registry` per entry; the job
  `echo` canonicalizes the name and carries `speaker_note` when it
  differs from the installed speaker.
- N2 — stage 2 (tract + wav [+ mp4]) executes in a
  `ProcessPoolExecutor(max_workers=1)` worker process
  (`covtl_console/_synthproc.py::run_synthesis`; payload/result are
  picklable dicts; engine exceptions cross the boundary unchanged).
  Measured: `/api/health` max 0.01 s over 1 400 probes while a ~140 s
  synthesis ran (before: unresponsive ≥ 30 s at 570 chars, ~13 min at
  4 900). In-process fallback (same function) latches on
  `BrokenProcessPool`/pool-creation failure with an explicit job note.
  Pool terminated on app shutdown so Ctrl+C is not held hostage
  (`_shutdown_synth_pool`; `_processes` dict→list across py3.11/3.12
  normalized).
- N2 — server-side text bound: **422 `TextTooLong` above
  `MAX_SYNTH_CHARS` = 2000** (equals the UI's `MAX_CHARS`, asserted by
  test), message tells the user to split into sentences.
- N3 — `label` pre-flight: separators `/ \ :`, control characters,
  Windows reserved device names, > 64 chars → **422 `InvalidLabel`**,
  no job; surviving characters sanitized like the engine's
  `sanitize_label` (`[^A-Za-z0-9_.-]` → `_`, glob metacharacters
  neutralized, dots kept — finding F1 semantics preserved); the worker
  and the engine receive the SANITIZED label (engine re-guard is
  idempotent). `outputDir` sanitization unchanged.
- Tests: `tests/test_fixes_n1_n2_n3.py` (19: 422 contracts, distinct
  audio per speaker, health-responsiveness during synthesis, label
  sanitization on disk; 1 slow-marked). Engine:
  `tests/test_speaker_resolution.py` (23: resolution, per-request
  ortho layer, distinct tracts/WAVs, label guards). Console suite:
  78 passed (60 before + 18 new non-slow), engine suite 211 passed +
  23 new = 234, the 3 pre-existing environment failures
  (registry hash + 2 syltraj byte baselines, numpy/line-ending
  sensitive) unchanged.

### Interpretive points

- The per-request speaker is a LAYERED switch, honestly partial: s1/s2
  speaker files share jd3's orthogonal columns (verified: identical
  tract for 'p a p a' at equal f0), so their audible difference rides
  on f0; m01/w02 differ in the tract as well. The geometry and the
  audio anatomy stay with the installed speaker — that boundary is the
  wheel's (no hot reload), stated in `/api/speakers`, the echo note
  and the README.
- N2's `max_workers=1` serializes synthesis jobs deliberately: the
  engine is CPU-bound on one core and the registry's process-global
  state stays consistent; a queue of requests degrades gracefully
  (jobs run back-to-back).

### Out of scope (listed, not fixed)

- CORS `allow_origins=["*"]` on a 127.0.0.1 bind remains by design
  (local tool, UI may run from `file://`); N3 removed the write
  primitive a rogue page could use, arbitrary READ was never possible
  (files endpoint serves registered paths only — audit-tested 404).


## Notation refactor — FROM·CONSONANTS·TO (2026-11-04)

### Verified code-level facts

- Tile notation is now defined ONCE, server-side
  (`segment_notation(a0, a1, span_blocks)` in `covtl_console/server.py`),
  exported by `/api/compile` (`segments_preview[].notation`) and
  `/api/job/{id}/polar` (`segments[].notation`); `compiler.js` and
  `app.js` consume it (`stretchLabel` deleted, the duplicated `out_s`
  loop in `compile_blocks` deleted — the two definitions had already
  diverged: VV arcs read "-" in tiles and "‿a" in the spectrogram).
- Tile grammar: `FROM·CONSONANTS·TO` per anchor→anchor segment
  ("·" is a field separator, not an anchor); muted anchors
  (`is_vowel_onset`, `is_word_end`) carry the key of the vowel their
  point derives from + "*" (new `_mute_label`, theta-match + nearest
  node index; anchors export `mute` / `syl_onset` flags). "‿" and the
  decay/attack "·" tokens are gone.
- Anchors are now contiguous in the notation: every tile's FROM equals
  the previous tile's TO (tested).
- Tests: `tests/test_notation.py` (7 tests — expected strings
  hand-traced and verified against the engine: iba, ib.bi, i.bi, ia;
  compile/polar notation equality; chain contiguity; no "‿").
  `test_api.py` stretch assertions rewritten to the notation (the
  Dis.iz… tile list is asserted verbatim). Suite: 61 passed.
- Synthesis untouched: syltraj, build_polar, the audio path, timings
  and caches are not modified by this refactor.

### Interpretive points

- "*" reads as "weighted by COEFCEN" — a muted anchor is a timing
  joint, not a string vowel; the earlier label (neighboring consonant
  key, or empty) was ambiguous.
- Nasal hiatus tiles keep ORAL bases ("a·a"): the "~" is re-injected
  in the audio VO gate, not in the plan notation; the hiatus label
  itself stays on the background block.

### Out of scope (listed, not fixed)

- The engine's "pause" block kind is unreachable from the console.
- The `syllables` metric ignores VV nuclei (background arcs).
- Per-phoneme polar targets are computed with `theta_ctx=π`.
- Compile-cache entries are not keyed on the guard policy.
- `rhoMax` is hardcoded at 1.45 client-side.

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

---

## I. Addendum (2026-11-03) — V1V2 hiatus labeling completed + covtl-sandhi integration

Engine side: `304f04c` (nasal_preproc V1V2 layer) + the covtl-sandhi
Branch-A hook (`82694bc`, default off) landed in covtl-pipeline; the
console tracks both.

- **Hiatus labeling completed.** `nasal_hiatus_intervals` MERGES adjacent
  nasal slots into one velar-open interval keyed on the oral bases —
  the merged `V~.V~` case (`ta~.a~ta`) labeled the background arc with
  the raw merged key (`a+a`) instead of the run's nasal notation. The
  label is now re-derived from the plan runs: `a~.a`, `a.a~`,
  `a~.a~`. The segment payload carries the per-block `hiatus` label,
  and a pure background journey (no plateau, no cluster) figures the
  arrival vowel above the green target anchor on the polar disc —
  such journeys drew no phonetic label at all before.
- **Compile plan == synth plan** re-verified empirically on the four
  V1V2 phrases (`kOma~.a.le.vu`, `ta~.ata`, `ta.a~ta`, `ta~.a~ta`):
  the console's instrumented mirror walk matches the engine's real
  synthesis block ledger 1:1 (kinds, steps, vowel keys, flags).
- **covtl-sandhi end-to-end.** Capability probe (None until Branch B is
  present — never a crash), exposed on `/api/status` + `/api/health`;
  `/api/preview` and the early polar stage (`_resolve_sampa`) apply the
  exact `Pipeline.run` gateways (g2p oracle / post / pre, expressive
  path included); `/api/synthesize` passes the level signature-guarded
  and echoes it with a degradation note; all cache keys include the
  level; `/api/compile` documents the no-op (SAMPA has no orthography).
  UI: Prosody level/mode selects + live capability hint. There is NO
  per-stretch `link_level` in the engine plan — an inserted liaison
  consonant shows up like any onset cluster (single source of truth,
  no UI reinterpretation).

---

## J. Addendum (2026-11-03, later) — covtl-sandhi installed, `standard` default

- **The rule package is now part of the recommended install.** The
  console UI preselects the `standard` sandhi level on fresh profiles
  (state default + `<option selected>`); the engine/API default stays
  `off`. Installation docs (README per-system blocks, INSTALL.md,
  user manual §Installing) gained the step
  `pip install git+https://github.com/FBerthommier/covtl-sandhi.git`
  (or `pip install covtl-sandhi`); the Prosody hint states the default
  and the install command. With the package present, liaison really
  fires: fr `faut il → fo.til`, `mon ami → mO~.na.mi`, `les amis →
  le.za.mi`, and `comment allez-vous` → `kOma~.ta.le.vu` (the liaison
  [t] carries the transition — the V~.V hiatus becomes a plain
  cluster, which the compiled plan shows honestly).

---

## K. Addendum (2026-11-03, latest) — flash install (pip package + bootstrap)

- **The console is a pip package** (`covtl-console` 3.1.0,
  `pyproject.toml`): `pip install
  git+https://github.com/FBerthommier/covtl-console.git` resolves the
  whole chain — `vtl-synth` from GitHub (VocalTractLab binaries are in
  its wheel), `covtl-sandhi` (liaison rules), `fastapi`/`uvicorn` —
  and installs the `covtl-console` command (`--host`/`--port`).
  Already-installed distributions satisfy the git-URL requirements, so
  development checkouts (editable engine) are never clobbered.
- **Packaging restructure**: bridge implementation moved to
  `covtl_console/server.py` with the UI assets inside the package
  (`covtl_console/ui/`, served by the bridge from site-packages);
  artifacts land in `out/` under the current working directory; the
  repo-root `server.py` is a shim that aliases `covtl_console.server`
  in `sys.modules` so `python server.py`, `import server` and the
  suite's monkeypatching keep working unchanged (verified: 49 fast
  tests green).
- **Bootstrap installer (option A)**: `install_flash.py` — creates a
  venv, installs engine + rules + bridge + console, writes
  `run_console.bat`/`run_console.sh`; options `--python`, `--venv`,
  `--engine` (git URL or local checkout), `--no-sandhi`, `--run`.
- **Flash install e2e-verified**: fresh venv, `pip install .` resolved
  engine 1.1.0 + covtl-sandhi 0.1.0 + console 3.1.0 from GitHub,
  `covtl-console --port 8422` came up LIVE (fr active, sandhi
  available, six languages, UI served from site-packages).

## L. Addendum (2026-11-04) — flash-install validation campaign

- **`tests/flash_e2e.py`** — the one-command flash install, proven end
  to end as a user gets it: wheel built from the checkout
  (`python -m build`), installed into a bare scratch venv (git deps
  resolve from the wheel metadata), entry point `covtl-console`
  started as a subprocess on a free port, and the real chain replayed
  over HTTP against the installed server: health (live engine, sandhi
  available, six rule languages), fr preview `bonjour, comment
  allez-vous` @ standard → `bO~ZuR kOma~.ta.le.vu` (liaison `t`),
  compile 14 anchors / 20 blocks / 3.96 s ± 1 step (the liaison
  variant; the no-sandhi string is 18 blocks / 3.68 s), synthesis with
  polar_ready observed BEFORE wav_ready and WAV duration = structure
  ± 40 ms, the three hiatus pairs `ta~.ata` / `ta.a~ta` / `ta~.a~ta`
  as pairwise-distinct WAVs with the velum opening measured inside the
  engine's `nasal_hiatus_intervals` windows (tract column 7: max ≥ 0.4,
  middle-half mean ≥ 0.3 — the 0.5 target ramps to −0.1 at the edges
  and the 20 ms velar timer rounds the plateau; oral control `ta.ata`
  ≤ 0.2), liaison `faut il` → `fo.til`, then clean `pip uninstall` and
  scratch-venv deletion. Helper `tests/_flash_vo_probe.py` runs in the
  scratch interpreter (where the engine lives) and recomputes the
  intervals with the engine's own walk; the .tract file runs at 400 Hz,
  so step windows are mapped onto rows by `n_rows / n_steps`.
- **CI job `flash`** (ubuntu + windows, py3.12) runs the script on the
  pushed commit and uploads `flash_e2e.log` — the same path a user's
  `pip install` takes, exercised on both OSes on every push.
- Evidence and divergences: `docs/flash-validation-report.md`.
