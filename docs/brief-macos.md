<!-- COVTL Console — macOS one-page brief · QR target for covtl.org
     En-US. Companion pages: brief-windows.md, brief-linux.md. -->

# The COVTL Console on macOS 🍎

> **Type text. Hear it. See how a human vocal tract will move to say it.**
> Free, open-source, 100% on your machine — no cloud, no account, no
> telemetry.

**You are on macOS · Apple Silicon** (M1/M2/M3/M4, macOS 11+) — this is
the right page. Intel Macs are not covered.

## Get the console (no Python needed)

1. Download **[COVTL-Console-macOS.zip (~98 MB)](
   https://github.com/FBerthommier/covtl-console/releases/download/macos-standalone/COVTL-Console-macOS.zip)**
   (official asset: `releases/download/macos-standalone/…`).
2. **Check the SHA-256** of the zip — it must be
   `810836e371eb9d4399a1224524e7163defe3593c5821616e7505f1233371d6f2`
   (or the value shown on [covtl.org](https://covtl.org) / the release
   page). `shasum -a 256 COVTL-Console-macOS.zip`
3. Unzip and open **COVTL Console.app**.
4. **Gatekeeper note**: the build is not signed / notarized. On first
   launch, **right-click the app > Open** (not a plain double-click) —
   or remove the quarantine flag:
   `xattr -d com.apple.quarantine "/Applications/COVTL Console.app"`.
   Honesty note: the native arm64 engine was verified by cross-checks on
   Linux (structure, Mach-O audit, pure-Python tests) and has never run
   on a physical Mac in the build environment — report anything odd via
   [Issues](https://github.com/FBerthommier/covtl-console/issues).

## The 3-step bench

1. **Preview** `P` — type ordinary text; the G2P stack shows the exact
   phonemes, with a red rejection guard.
2. **Compile** `C` — syllable blocks with articulatory targets.
3. **Synthesize** `S` — play it, watch the polar display, download
   WAV & MP4.

5 speakers · 6 languages (en · fr · es · de · it · pt) · expressive
prosody · breathy / creaky / whisper · liaison & sandhi.

## Security notes

- **Local only:** the console talks to `127.0.0.1` and nothing else.
- **After you scan, read the address bar.** The only real pages live on
  `github.com/FBerthommier/…` — a sticker swapped on a printed QR is a
  classic trick ([FBI IC3](https://www.ic3.gov/PSA/2022/PSA220118)).
- **Trust, but verify:** the SHA-256 above and the
  [Sigstore attestation](https://github.com/FBerthommier/covtl-console/releases)
  (`gh attestation verify COVTL-Console-macOS.zip -R FBerthommier/covtl-console`)
  are the real proof, beyond any QR code.

**Next stop:** [releases](https://github.com/FBerthommier/covtl-console/releases) ·
[all briefs & docs](https://github.com/FBerthommier/covtl-console/tree/main/docs) ·
[Windows brief](brief-windows.md) · [Linux brief](brief-linux.md) ·
[source](https://github.com/FBerthommier/covtl-console)

*GPL-3.0-or-later · built on VocalTractLab · © Frédéric Berthommier — cite arXiv:2307.02299.*
