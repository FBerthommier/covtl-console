<!-- COVTL Console — generic one-page brief · hub for the platform briefs
     (brief-windows.md / brief-linux.md / brief-macos.md). En-US.
     Source facts: covtl.org (2026-11-17/18), FBerthommier/covtl-console
     README & INSTALL.md, lab validation report 2026-11-17. -->

# The COVTL Console — speech you can *watch* taking shape 🎙️

> **Type text. Hear it. See how a human vocal tract will move to say it.**
> Free, open-source, 100% on your machine — no cloud, no account, no
> telemetry.

Most text-to-speech systems are black boxes. This one opens up the box:
the Berthommier **COVTL model** drives **VocalTractLab 2.4** to compute
actual articulatory gestures — tongue, jaw, lips — and the console lets
you watch the **polar representation** update in real time as the sound
plays.

**5 speakers · 6 languages (en · fr · es · de · it · pt) · expressive
prosody · breathy / creaky / whisper · liaison & sandhi · polar display.**

## The 3-step bench

1. **Preview** `P` — type ordinary text; the G2P stack shows the exact
   phonemes the engine understood, with a red rejection guard.
2. **Compile** `C` — syllable blocks with (ρ, θ) articulatory targets.
   Instant, no synthesis.
3. **Synthesize** `S` — play it, scrub anchor by anchor, read the
   spectrogram, watch the polar display, download WAV & MP4.

## Choose your installation path

| Your machine | Go to | Bundle |
|---|---|---|
| Windows 10/11 · x64 | [Windows brief](brief-windows.md) | zip ~122 MB, no Python needed |
| Linux · x64 | [Linux brief](brief-linux.md) | zip ~192 MB, no Python needed |
| macOS · Apple Silicon (M1-M4, macOS 11+) | [macOS brief](brief-macos.md) | zip ~98 MB, no Python needed (unsigned: right-click > Open) |
| Any OS with Python 3.9+ | **one command: `pip install covtl`** | pulls the whole suite: covtl-console (web UI) + covtl-synth (engine) + covtl-sandhi (rules). Then `covtl-console` opens the same interface on http://127.0.0.1:8421, or synthesize from the CLI: `vtl-synth run "this is easy for us" -o out` |

The standalone bundles open the exact same web interface — unzip, run,
no Python required. Full downloads on the
[releases page](https://github.com/FBerthommier/covtl-console/releases).

## Before you trust any link or QR

- **Local only:** the console talks to `127.0.0.1` and nothing else.
- **After you scan, read the address bar.** The only real pages live on
  `github.com/FBerthommier/…` — a lookalike domain or a sticker slapped
  over a printed QR is a classic trick ([FBI IC3
  alert](https://www.ic3.gov/PSA/2022/PSA220118)). When in doubt, type
  the address yourself.
- **Trust, but verify:** check your bundle's SHA-256 (values on
  [covtl.org](https://covtl.org) and in each platform brief) and the
  Sigstore build provenance:
  `gh attestation verify <zip> -R FBerthommier/covtl-console`.

**Next stop:** [user manual & docs](https://github.com/FBerthommier/covtl-console/tree/main/docs) ·
[source](https://github.com/FBerthommier/covtl-console)

*GPL-3.0-or-later · built on VocalTractLab · © Frédéric Berthommier — cite arXiv:2307.02299.*
