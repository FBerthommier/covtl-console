<!-- SPDX-FileCopyrightText: 2026 Frédéric Berthommier -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Frontend checklist — manual browser series (release sign-off)

Mirrors the flows validated on the reference machine (Chrome, live bridge
on 127.0.0.1:8421, engine installed). Walk it before any release tag.
Automatable counterparts live in `tests/`; everything here needs eyes.

Setup: `python server.py` → open <http://127.0.0.1:8421>; the backend chip
must read **live**.

## Probe & mode switching

- [ ] Cold load with the bridge down (static server): banner shows **demo
      mode**, surfaces labeled as simulated.
- [ ] Bridge comes up → probe flips the UI to live without a manual reload
      of more than one poll cycle.
- [ ] `Covtl Console v3` title, header chips render: state · language ·
      speaker/f0 · backend(health).

## Preview (step 1)

- [ ] Word-end auto-preview fires when finishing a word (space / word
      boundary); typing **mid-word must NOT fire** a preview.
- [ ] Preview button shows feedback: label becomes `⏳ Previewing…` and the
      in-flight pill reads `⏳ n in flight…` while the request runs.
- [ ] Example chips (EN/FR/ES/DE/IT/PT + phonetic + guard demo) fill the
      input and preview immediately.
- [ ] Orthographic text produces the three-line preview stack: G2P →
      enriched → final SAMPA (worked example `this is easy for us` →
      `Dis.iz.i.zi.fOR.@s`).
- [ ] Guard error → switch policy to `warn`: the same input relabels from
      blocking error to inline red-reject warning; suggestions offered
      (`c` → `k, s`); strip action removes the red symbols.
- [ ] **Input reset (`R` / Reset input button)**: with an ortho draft, a
      phonetic draft AND an edited final SAMPA active, one reset clears
      both panes, drops the edited badge, hides the editor, empties the
      preview stack and returns the state chip to *Empty* — no stale
      edited SAMPA can steer a later synthesis.
- [ ] **Reset reaches the downstream panels**: after a preview + compile
      + synthesis, one reset empties the compiler field and its tiles /
      chips / cards (restored placeholders), stops playback, clears the
      polar display, the spectrogram, the scrub ticks, the result
      summary and the downloads menu; the state chip reads *Empty* even
      from the post-synthesis *Ready* state; a running synthesis is
      cancelled.
- [ ] After a reset, a fresh preview works immediately (no cache of the
      old chain); language, speaker, timings and history are untouched
      by the reset.

## Compiler (step 2)

- [ ] `C` focuses the compiler; Enter compiles; auto-follow: the compiler
      preview tracks the stage's final SAMPA after each preview.
- [ ] Stale-compile guard: edit the SAMPA while a compile is in flight →
      the old response is dropped when it lands (no flicker of stale data).
- [ ] Metric tiles (syllables · anchors · blocks · C/V · duration) match
      the engine metrics for the worked example (6 · 11 · 16 · … · 2.38 s).
- [ ] Stretch labels are chronological and coda stretches carry the `‿`
      coarticulation marker (e.g. in `Dis.iz.i.zi.fOR.@s`).
- [ ] Block cards are clickable; “use in phonetic input” pushes the string
      to the stage.

## Synthesis & polar display (step 3)

- [ ] `S` synthesizes; ⏳ progress visible; the polar display starts while
      the WAV still renders (**start-early**, own clock), then re-anchors
      seamlessly on the audio clock at block boundaries.
- [ ] Polar phonetic labels include shared-target counts (`i·4` style).
- [ ] **Journey-centric display**: the polar disc shows exactly ONE
      journey — the anchor pair under the head: its full vocalic arc
      (start anchor → end anchor) and, when the journey carries a
      cluster, the complete blue excursion drawn jointly (departure
      vowel → consonant targets → landing on the arrival vowel). No
      watermark of past journeys; switching journeys is a clean switch
      at the anchor boundary; reduced vowels (@, 6) show as hollow
      rings; phonetic labels cover the current journey only.
- [ ] **Origin/target anchors colored**: the current journey's origin is
      a red dot and its target a green ring, both drawn above the white
      head (on a stationary hold they stack: green ring around the red
      dot); the blue excursion always reads from the red dot to the
      green ring. No amber ``next anchor'' ring remains.
- [ ] `[` / `]` step anchors exactly (head lands on the anchor tick, not
      between); the scrub bar's ticks ARE the anchors.
- [ ] `L` loops the current block; speeds 0–3 (0.25×/0.5×/1×/2×) apply to
      playback and the polar head.
- [ ] After synthesis, clicking a compiler block card seeks the polar
      display to exactly that segment.
- [ ] Spectrogram anchor overlay: ticks align with the same anchor times
      as the scrub bar.
- [ ] Downloads menu (`D`) respects the exports flag: wav+txt always;
      tract/polar only when optional exports are enabled; MP4 offered in
      sagittal mode.

## Demo mode & standalone

- [ ] Demo mode: simulated G2P/guard/audio and the approximate compiler
      are clearly labeled as demo.
- [ ] `covtl-console-standalone.html` opened from `file://`: full UI, demo
      engine; with the bridge running, it goes live on 127.0.0.1:8421.
- [ ] Rebuild (`python build_standalone.py`) reproduces a working bundle.

## Hygiene

- [ ] No console errors (F12) on load, preview, compile, synthesize, seek.
- [ ] `?` opens the shortcut help; `Esc` cancels a running job.
- [ ] Every UI string is US English.
