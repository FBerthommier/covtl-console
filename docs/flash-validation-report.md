<!-- SPDX-FileCopyrightText: 2026 Frédéric Berthommier -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Flash-install validation campaign — report (2026-11-04)

> **Update 2026-11-04 (tile notation refactor):** the stretch labels shown below with the `‿` coarticulation marker have been replaced by the unambiguous tile notation `FROM·CONSONANTS·TO` (muted anchors carry `*`; `·` is a field separator, not an anchor). See `CHANGES_v3.md` in the console repository.

Everything needed to decide the PyPI publication of `covtl-sandhi`,
`vtl-synth` and `covtl-console`. **The publication itself is out of
scope**; TestPyPI dry runs were not exercised either (no account step
performed). Campaign executed per the deferred prompt of 2026-11-03.

- Console under test: `bdec379` + the campaign's own commits
  `85c7f2d` (flash e2e + CI) and `dbbb1a4` (docs) — the user's tree
  was never reverted; the nine functional commits between `49adeb0`
  and `bdec379` (demo-mode removal, single Synthesize button,
  upstream-wins propagation, compile-to-polar) were validated as found.
- Engine: `covtl-pipeline` @ `453d0b7` (GitHub main, unchanged during
  the campaign); `covtl-sandhi` 0.1.0 from GitHub.
- Baselines re-measured first: console fast suite **49 passed / 1
  deselected**; engine suite **213 passed / 1 failed**
  (`test_hashes_match_registry`, the only tolerated failure). Local
  engine prints a `CONSTANTS INCONSISTENCY` notice (jd3 speaker hash) —
  same known state as that tolerated test; absent on fresh CI installs.

## Volet (a) — automatable flash e2e — PASS

`tests/flash_e2e.py` (+ `tests/_flash_vo_probe.py`, run inside the
scratch venv where the engine lives) proves the full chain against the
**installed package**, never the TestClient. Local run (Windows,
py312): PASSED. CI run
[41841838191](https://github.com/FBerthommier/covtl-console/actions/runs/41841838191)
— all six jobs green on `dbbb1a4`:

| job | result | wall clock |
|---|---|---|
| tests (ubuntu / windows) | success | 62 s / 127 s |
| **flash install e2e (ubuntu)** | **success** | 63 s |
| **flash install e2e (windows)** | **success** | 119 s |
| standalone bundle / LaTeX manuals | success | 30 s / 49 s |

Both flash job logs show the identical evidence chain (job links:
[ubuntu](https://github.com/FBerthommier/covtl-console/actions/runs/41841838191/job/12661515438),
windows likewise; artifacts `flash-e2e-log-*` carry `flash_e2e.log`):

- wheel built from the checkout; `covtl_console/ui/` inside (index +
  css + js); `pip install <wheel>` resolves `vtl-synth` 1.1.0,
  `covtl-sandhi` 0.1.0, fastapi, uvicorn **from the wheel metadata**
  (git deps from GitHub — exactly the user path);
- entry point `covtl-console` installed; `__version__ == metadata ==
  3.1.0`; `--help` exits 0;
- health: live engine 1.1.0, sandhi available, six rule languages
  (de en es fr it pt);
- preview fr `bonjour, comment allez-vous` @ standard →
  `bO~ZuR kOma~.ta.le.vu` (liaison `t`);
- compile → **14 anchors / 20 blocks / 3.96 s ± 1 step** (see
  divergence D1); synthesis: `polar_ready` observed BEFORE `wav_ready`,
  WAV duration 3.951 s = structure ± 40 ms, polar payload 13 segments /
  396 points at 100 Hz in display degrees, ρ ≤ 1;
- hiatus pairs `ta~.ata` / `ta.a~ta` / `ta~.a~ta`: three
  pairwise-distinct WAVs; VO (tract column 7) measured **inside the
  engine's own `nasal_hiatus_intervals` windows** — intervals rows
  [160,192) / [192,224) / merged [160,224) at 400 Hz; max VO
  **0.4701 / 0.4701 / 0.4973** (≥ 0.4), middle-half means
  **0.397 / 0.397 / 0.461** (≥ 0.3; the 0.5 target ramps to −0.1 at
  interval edges and the 20 ms velar timer rounds the plateau — hence
  the mean margin); oral control `ta.ata`: no interval, background
  window mean **−0.100** (≤ 0.2);
- liaison `faut il` @ standard → `fo.til`;
- teardown: `pip uninstall` clean, `covtl_console` no longer
  importable, scratch venv deleted.

Also validated: `python install_flash.py` (option A) into
`.venv-covtl` + `run_console.bat` written; the repo-root `server.py`
shim still imports (`import server` → `covtl_console.server`, FastAPI
app); `build_standalone.py` rebuild is byte-identical (bundle tests
6/6). `.tract` files run at **400 Hz** (not the 100 Hz walk rate) —
the probe maps step windows onto rows by `n_rows / n_steps`.
*(Confirmed intentional and locked by a contract test on 2026-11-04 —
see Correction round §400 Hz.)*

## Volet (b) — browser checklist — 35 PASS · 1 PARTIAL · 1 nit-FAIL · 2 N/A · 1 superseded

Walked against the flash-installed console (`.venv-covtl`'s
`covtl-console --port 8422`, UI from site-packages), Chrome-class
embedded browser at 1680×1050. Canvas facts were verified by pixel
scans and a `fillText` recorder instead of eyes; keystrokes that the
embedded browser does not deliver as trusted events (Enter, Escape,
`?`, `R`, `[`, `]`) were dispatched as DOM `KeyboardEvent`s on the
same handlers (harness note H1).

### Probe & mode switching

- Cold load with the bridge down — **N/A (D3)**: `api.js` probes
  same-origin then falls back to 127.0.0.1:8421 by design; the
  reference bridge on 8421 must stay up (guardrail), so a bridge-down
  cold load cannot be produced on this machine. The offline banner /
  offline-state code path exists (`app.js` `#offline-banner`,
  `backend-offline` state, disabled Synthesize with the
  `python -m covtl_console` hint).
- Bridge comes up → flips to live without reload — **PASS** (observed
  live: a page left in the offline state auto-engaged to "backend
  live" within one 15 s poll cycle after the bridge started; caches
  purged, preview re-run).
- Title + header chips — **PASS** (`COVTL Lab Console … (v3)`,
  state · language · speaker/f0 · backend(health) all render).

### Flash install (pip package)

- **PASS** — wheel path proven end-to-end by volet (a); option A
  bootstrap + launcher + root shim verified; `covtl-console --port
  8422` starts LIVE (fr active, sandhi available, six languages) and
  serves the UI from site-packages (served files byte-identical to
  the package).

### Preview

- Word-end auto-preview / mid-word no-fire — **PASS** (typing
  `bonjour` alone left the previous SAMPA untouched; the trailing
  space fired `b@n.ZuR`).
- Preview button feedback — **PASS** (`⏳ Previewing…` + `⏳ 1 in
  flight…` observed mid-flight, restored after).
- Example chips — **PASS** (FR chip fills input, switches language,
  previews immediately; Guard chip used in the guard series).
- Three-line stack worked example — **PASS** at `off`:
  `this is easy for us` → `Dis.iz.i.zi.fOR.@s` (G2P = enriched =
  final, non-expressive). At the default `standard` the same sentence
  gives `Di.sizzi.zi.fO.R@s` (en rules fuse "is easy" → `siz.zi`) —
  see D2.
- Guard warn → error → strip — **PASS**: warn banner "1 symbol will
  be dropped ('c' → k / s)" + "Synthesize anyway (1 symbol dropped)";
  error banner "Synthesis blocked …" + disabled button; strip (in the
  error banner) `cleanpan` → `leanpan`, badge cleared, edited badge on.
- Nasal hiatus labels — **PASS**: `kOma~.a.le.vu` → `a~.a`;
  `ta.a~ta` → `a.a~`; merged `ta~.a~ta` → `a~.a~` (chips and cards).
- Hiatus journey labeled on the polar disc — **PASS**:
  `fillText('a', 447, 277)` recorded exactly 14 px above the green
  target ring on the pure-background journey only (the cluster
  journey drew its own label from the normal path); block strip shows
  `‿a~.a~`.
- Liaison controls — **PASS**: `standard` preselected on a fresh
  profile (localStorage cleared → reload), mode `g2p`; hint lists the
  bridge's rule modules (`de, en, es, fr, it, pt`); changing the
  level re-previews (`Dis.iz…` ↔ `Di.sizzi…`); the level survives a
  reload; `faut il` → `fo.til` (fr) through the UI.
- Input reset (`R`) — **PASS**: with an ortho draft, a phonetic draft
  AND an edited final SAMPA active, one reset cleared both panes,
  dropped the edited badge, hid the editor, emptied the stack, chip →
  *Empty*.
- Reset reaches downstream — **PASS except one nit**: compiler field
  + tiles/chips/cards restored to placeholders, playback stopped,
  polar display and spectrogram genuinely cleared (0 non-background
  pixels, payload dropped), scrub ticks 0, result summary cleared,
  chip *Empty*; a running synthesis is cancelled by the reset (no
  artifacts written). **Nit-FAIL:** the downloads menu is hidden but
  not emptied — re-opening `D` after a reset shows the previous job's
  entries (`app.js` reset hides `#dl-menu` without clearing it; the
  checklist asks for it to be cleared). *(Resolved 2026-11-04 — see
  Correction round §F2.)*
- Fresh preview after reset — **PASS** (immediate; language, speaker,
  timings and history untouched by the reset).

### Compiler

- `C` focus + Enter compiles + auto-follow — **PASS** (`C` focuses
  `#compiler-input`; Enter compiled `kAtS dZiN tSwE` → 13 anchors ·
  15 blocks · 2.44 s; after every preview the field tracks the final
  SAMPA and auto-compiles — `fo.til` → "compiled 2 syllable(s) · 8
  blocks · 7 anchors · 1.62 s").
- Stale-compile guard — **PASS**: `Dis.iz…` compile in flight, field
  edited to `ba da` → the stale response never rendered (only
  `ba da`'s 8 anchors · 9 blocks · 1.36 s appeared, no flicker).
- Metric tiles — **PASS**: 6 syllables · 11 anchors · 16 blocks ·
  7/6 C/V · 2.38 s (worked example, `off` level).
- Stretch labels — **PASS**: chronological `▸, D, i‿s, i‿z, i‿z, i‿f,
  O‿R, @‿s, ·, ◂` with the `‿` coda markers.
- Block cards clickable + "use in phonetic input" — **PASS** (cards
  expand; the push flips the mode to Phonetic with the string staged
  and the source note "compiler blocks (syllabic edition)").

### Synthesis & polar display

- `S` synthesizes; start-early; re-anchor — **PASS** (job strip ⏳;
  display ran "polar-only — audio still rendering" to Block 6/6 while
  the bar was at ~30–50 %, then re-anchored "synced · audio clock").
- Shared-target counts (`i·n` labels) — **PARTIAL**: implemented and
  correct as far as verifiable (`polar.js` dedupes by vowel+position
  and renders `text·count` when count > 1), but no tested string
  (`Dis.iz…`, `iowa a g`, the hiatus pairs) produces two same-target
  blocks **within one journey** — VVV runs split across journeys — so
  the suffix was never observed live. *(Closed N/A justified
  2026-11-04 — measured unreachable under current engine geometry; see
  Correction round §i·n.)*
- Journey-centric display — **PASS**: per-journey label batches only
  (verified by clearing a `fillText` recorder between steps); no
  watermark of past journeys; clean switch at anchor boundaries.
- Origin/target anchors colored — **PASS** (pixel scan of the dynamic
  canvas layer: `#E0524A` red dot and `#3E9B6C` green ring present
  and stacked on the hold, as specified).
- `[` / `]` step exactly — **PASS** (head landed on 0.94 / 0.76 /
  0.56 / 0.40 s and 2.18 → 0.40 s across the worked example — the
  anchor times; scrub ticks = anchors).
- `L` loop + speeds — **PASS** (`loopBlock` on, class `on`; 2× set
  `audio.playbackRate = 2` with the 2× chip active).
- Card seek after synthesis — **PASS** (S0 card → 0.01 s, S1 card →
  0.21 s = `seg.t0 + 5 ms`; a card from a different compile gives an
  explicit toast + recompile of the synthesized string — coherent).
- Spectrogram anchor overlay — **PASS** (5 amber lines at x =
  211/423/592/803/993 on the 1.14 s job = the 5 real anchor times;
  synthetic ▸/◂ anchors dashed cyan as documented).
- Downloads under the exports flag — **PASS for wav+txt (always) and
  tract (flag on)**; **finding F1**: the polar download is missing for
  inputs whose bridge-stem differs from the engine-stem (any string
  containing `.`: bridge `ta~.a~ta` → `ta__a_ta.polar` vs engine
  `ta_.a_ta.*`; the offer glob runs on the engine stem only). MP4 in
  sagittal mode — **N/A** this run (slow-lane job covers it nightly).
  *(F1 fixed 2026-11-04 — see Correction round §F1.)*

### Offline state & standalone

- "Demo mode" item — **SUPERSEDED (D4)**: demo mode was removed
  (`c009a29`); there is no simulated G2P/guard/audio anymore — the
  checklist entry is stale, the README's "no offline mode" is what
  the tree does (explicit offline banner + auto-engage).
- Standalone bundle — **PASS** (served over http because the harness
  cannot navigate `file://`; full UI in one file, engaged the bridge
  and previewed `fau.til` through the inlined modules).
- Rebuild reproduces a working bundle — **PASS** (byte-identical
  rebuild; 6/6 bundle tests).

### Hygiene

- No console errors — **PASS** (a page-level `error` /
  `unhandledrejection` / `console.error` recorder stayed **empty**
  across preview/compile/synthesize/seek/reset cycles, including a
  post-reload cycle; load-time errors assessed via functioning
  features — no error toasts, no `Preview failed` lines after the
  cache bust of H2).
- `?` help / `Esc` cancel — **PASS** (keyboard-map overlay; Escape
  cancelled a running job: "cancel requested…" → "synthesis
  cancelled").
- Every UI string US English — **PASS** (diacritic sweep over
  buttons/labels/headings/hints: matches only in language names and
  example data, never in chrome strings).

## Divergences & findings (never papered over)

- **D1 — compile metrics**: the prompt's "14 anchors / 18 blocks /
  3.68 s" is the **no-sandhi** string; the standard-level preview
  yields `bO~ZuR kOma~.ta.le.vu` (liaison `t`) which compiles to
  **14 / 20 / 3.96 s**. The e2e asserts the liaison variant (it
  previews at the UI default); both are re-derived and recorded.
- **D2 — worked example at the default level**: with `standard`
  preselected, `this is easy for us` → `Di.sizzi.zi.fO.R@s` (en
  sandhi), not the checklist's `Dis.iz.i.zi.fOR.@s` (which the
  checklist itself derives at `off`). Validated both; not a bug.
- **D3 — bridge-down cold load N/A**: the probe's deliberate 8421
  fallback + the guardrail "leave the user's 8421 running" make the
  item unexercisable here; the fallback itself is confirmed (static
  pages engage the 8421 bridge automatically).
- **D4 — demo-mode checklist item is stale** (feature removed in
  `c009a29`); recommend rewording at release sign-off. Not edited by
  the campaign beyond the flash-item cross-link.
- **F1 — polar download lost for dotted inputs** (minor, pre-existing
  — the stem-sanitizer mismatch described above; the file exists and
  feeds the display, it just never enters the offered-files glob).
  Never hit by the e2e because it sends explicit labels.
  *(Fixed 2026-11-04 — see Correction round §F1.)*
- **F2 — downloads menu not emptied by reset** (nit; see the item).
  *(Fixed 2026-11-04 — see Correction round §F2.)*
- **F3 — synced display never replaced by a later compile**
  (deliberate, `0fc562c`): after a synthesis, compiling a different
  string keeps the audio-synced display; the new plan loads on the
  next synthesis or reset, and stale cards explain themselves via a
  toast. Validated as found.
- **H1 — harness**: the embedded browser does not deliver trusted
  Enter/Escape/`?`/letter keydowns to page handlers; the same
  handlers were driven with DOM `KeyboardEvent`s. `type()`-delivered
  characters (input events) work normally.
- **H2 — environment**: serving the UI from a plain static server
  (no `Cache-Control`) lets a browser cache stale modules on that
  origin — observed as `compiler?.follow is not a function` with
  yesterday's `compiler.js`; the bridge's no-cache middleware covers
  everything it serves itself. Bust with `fetch(url,
  {cache:'reload'})` + reload. Not a product defect in normal use.

## Screenshots

Not refreshed: the campaign touched no UI file (tests, CI, docs
only), and the user's `bdec379` had just re-aligned README, manuals
and screenshots — they remain current.

## Recommendation — GO for PyPI, starting with covtl-sandhi

The one-command install is now proven end to end from a clean tree on
both CI operating systems, the browser checklist is green (the two
open findings are minor download-menu nits with no phonetic impact),
and every number in the chain is pinned by an automatable check.
Residual risks to restate at publication time:

1. **VTL binaries redistribution** — posture 1 (publish as-is, as the
   engine already does on GitHub) remains the recommendation; the
   engine wheel embeds `vocaltractlab-cython` from PyPI, which is
   already public.
2. **git+ dependencies** — once the three packages are on PyPI, drop
   the `git+https://…` pins for registry names and version bounds, in
   dependency order: `covtl-sandhi` → `vtl-synth` → `covtl-console`
   (each publish unblocks the next).
3. 2FA + Trusted Publishing need to be enabled on the account before
   the first upload; all three names were still free on 2026-11-03.

Suggested order: publish `covtl-sandhi` 0.1.0 → `vtl-synth` 1.1.0 →
`covtl-console` 3.1.0, then flip the console's dependencies to the
registry and re-run `tests/flash_e2e.py` (now the true user path,
minus the git resolution) plus the flash CI job before tagging.

## Correction round (2026-11-04, evening) — every open item closed

Executed per the maintainer's correction prompt on top of `f9884af`.
One commit per item; **no version bump**; `ci.yml` untouched; the
8421/8422/8423 servers were never touched — manual verification ran on
a dedicated port 8430 against the corrected wheel force-reinstalled
into `.venv-covtl`.

| item | campaign status | status now | commit |
|---|---|---|---|
| F2 — downloads menu not emptied by reset | nit-FAIL | **PASS** (emptied + live-verified) | `e37ead1` |
| shared-target labels (`i·n`) | PARTIAL | **N/A justified** (measured unreachable) | `71282e2` + `040b7a8` |
| F1 — polar download lost for dotted inputs | finding (minor) | **PASS** (engine stem everywhere) | `8e1f1d8` |
| 400 Hz tract vs 100 Hz walk | intentional, open | **contract documented + locked** | `b1eaf1d` |
| TestPyPI publication | not prepared | **workflow ready** (manual dispatch only) | `594fa13` |

### §F2 — reset empties the downloads menu — PASS

`resetInputs()` hid `#dl-menu` without clearing it. The menu content
is the single source of truth for the entries (rebuilt from
`result.files` on each synthesis; there is no persisted download
state), so the reset now also re-renders it empty — reopening `D`
shows the no-artifacts state. Non-regression:
`tests/test_ui_sources.py::test_reset_empties_downloads_menu` (source
contract, engine-less, runs in CI on both OS). Live verification
(port 8430): after a `ta~.a~ta` synthesis the menu offered 4 entries;
Reset input → chip *Empty*; reopening `D` shows
`No artifacts yet — synthesize first.` with **0 stale items** (before
the fix the previous job's 4 entries reappeared).

### §F1 — early artifacts on the engine stem — PASS

Exact divergence, documented before fixing (old bridge
`re.sub(r"[^A-Za-z0-9_\-]", "_", text[:28]).strip("_")` vs the engine's
`label_of` + `Pipeline.run`'s `.rstrip("._")`):

| input | old bridge stem | engine stem |
|---|---|---|
| `ta~.a~ta` (report's case) | `ta__a_ta` | `ta_.a_ta` |
| `foo.bar` / `foo.bar.wav` | `foo_bar` / `foo_bar_wav` | `foo.bar` / `foo.bar.wav` |
| `ta-a` (hyphen) | `ta-a` | `ta_a` |
| `café` (non-ASCII) | `caf` | `café` |
| `a.b-c_d e` | `a_b-c_d_e` | `a.b_c_d_e` |
| `ta_a`, `ba da`, `klinpan` | identical | identical |
| specials only (`...`) | `output` | `output` |
| long inputs | truncated to 28 **before** substitution | truncated to 30 **after** + `rstrip("._")` |

Dots, hyphens and non-ASCII all made the early `.polar` invisible to
the offer glob (dotted inputs were simply the observed case). The
bridge now delegates to the engine's own
`vtl_synth.core.pipeline.label_of` — the import cannot fail (`Pipeline`
is imported from that very module two lines above) — computing
`stem = (label or label_of(text)).rstrip("._") or "output"`, exactly
`Pipeline.run`'s formula, so the two stems are identical by
construction. Non-regression:
`tests/test_synthesis.py::test_dotted_input_offers_polar_download`
(`ta~.a~ta` → offers `ta_.a_ta.polar`, file on disk, HTTP 200).
Live verification (port 8430): the downloads menu for `ta~.a~ta`
lists polar + tract + txt + wav, all under `ta_.a_ta.*`.

### §i·n — shared-target label suffix — N/A justified

Live observation was attempted with the minimal synthetic input that
produces the configuration: a word-internal geminate. `atta` walks
a→a with ONE cluster block carrying `cons_keys ['t','t']` — the only
reachable "same phoneme twice in one journey" case (VVV runs split
across journeys; consecutive identical vowels build background arcs).
A `fillText` recorder over a full scrub sweep of the live display
drew `a`, `t`, `▸`, `◂`, `␣` (+ block-strip labels) and **no `t·2`**.

Reason, measured on the live payload: polar.js's dedup key includes
the target position (`key = 'C:'+ck+':'+rho.toFixed(2)+':'+theta.toFixed(0)`),
and the engine's consonantal arc interpolates monotonically between
the surrounding vowel targets — the geminate's two t's ride different
flanks of the excursion: **t at (ρ 0.40, θ 231°) and (ρ 0.65, θ 173°)**
— never the same rounded position. A 50-candidate sweep (geminates
`atta/abba/akka/adda/appa/ab.ba/abb.a/ab.bba/at.ta/ibbi/uddu`, repeated
vowels `aa/ii/aaa/a.a/i.i`, mixed VV runs, tri-consonants `bbb/atsta`,
the worked example, the e2e phrases) replicating polar.js's keys
exactly over `/api/compile` payloads found **zero** collisions in any
journey. The other collision path — two plateaus of the same vowel
inside one journey — is structurally impossible: each vowel anchor's
plateau belongs to the journey starting at that anchor.

Conclusion: the suffix is correct defensive code (it would render
`t·2` the day the engine plateaus a geminate at a shared target) but
unreachable through any input under the current engine geometry. The
checklist item moves PARTIAL → **N/A justified**;
`tests/test_structure.py::test_geminate_shared_target_segment` pins
the duplicated-key journey and documents the measured geometry so a
changed engine has a data-level probe ready.

### §400 Hz — tract/walk rate contract documented and locked

Maintainer-confirmed: the `.tract` files are **400 Hz by construction**
(engine `TRACT_SR`) — a contract, not a bug; the production rate is
unchanged. The walk (structure blocks, `.polar` payload, display) runs
its own 100 Hz grid and never reads the `.tract` directly; the repo's
tract consumer — `tests/_flash_vo_probe.py` — maps walk step windows
onto tract rows explicitly (`scale = n_rows / n_steps`, measured 4.0,
reported as `tract_hz_per_step` in the e2e log). Locked by
`tests/test_synthesis.py::test_tract_400hz_walk_100hz_contract`:
`.tract` header `sample_rate == 400`, `n_frames == 4 × walk steps`
(measured 544 = 4 × 136 on `ba da`), payload `sample_rate == 100`,
`duration × 100 == steps`. Contract docstrings added at the
artifact-adoption point in `server.py` and in the probe.

### §TestPyPI — publish.yml ready (manual trigger only)

`.github/workflows/publish.yml` (ci.yml untouched): `workflow_dispatch`
only, environment `testpypi` (the maintainer's pending publishers),
`pypa/gh-action-pypi-publish` against `https://test.pypi.org/legacy/`,
sequential publication `covtl-sandhi` → `vtl-synth` → `covtl-console`
in one job (order guaranteed), each stamped to a PEP 440 test version
(`upstream + .devN`, default `dev1`, empty input falls back to
`dev<run number>`). Every dependency-resolving pip install carries
`--extra-index-url https://pypi.org/simple/` (TestPyPI holds no
production dependency). Validated: actionlint 1.7.12 clean, YAML
parse, and the stamping logic exercised against the three real
pyprojects (→ 0.1.0.dev1 / 1.1.0.dev1 / 3.1.0.dev1). Known limitation
(documented in the workflow): the console wheel's engine deps are
still git+ pins, so its TestPyPI install resolves those from GitHub —
the proven flash path — until the registry flip; the upstream wheels
themselves are smoke-installed from TestPyPI in a separate venv.
The publication itself is **ready to be tested manually** by the
maintainer (Actions → publish (TestPyPI) → Run workflow).

### Re-validation on the corrected tree

- Fast suite (engine-backed, Windows): **53 passed / 1 deselected** —
  the campaign's 49 + the four new tests (F2 source contract, F1
  dotted polar, 400 Hz contract, geminate journey).
- `tests/flash_e2e.py`: **PASSED** — same evidence chain as volet (a)
  (wheel → scratch venv → live server; compile 14 anchors / 20 blocks /
  3.96 s; start-early ordering observed; VO gates 0.4701 / 0.4701 /
  0.4973 vs oral control −0.100; three pairwise-distinct WAVs;
  `faut il` → `fo.til`; clean uninstall + venv teardown).
- CI on GitHub after the push: run
  [41889475385](https://github.com/FBerthommier/covtl-console/actions/runs/41889475385)
  — **success**, all six jobs (tests ubuntu + windows with the four new
  tests, flash install e2e ubuntu + windows, standalone bundle, LaTeX
  manuals; slow lane skipped as usual on push).
- Browser re-verification of the two fixed behaviors: see §F2 and §F1
  above (port 8430, corrected wheel).
