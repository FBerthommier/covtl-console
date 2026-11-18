<!-- COVTL Console — Windows one-page brief · QR target for covtl.org
     En-US. Companion pages: brief-linux.md, brief-macos.md. -->

# The COVTL Console on Windows 🎙️

> **Type text. Hear it. See how a human vocal tract will move to say it.**
> Free, open-source, 100% on your machine — no cloud, no account, no
> telemetry.

**You are on Windows 10/11 · x64** — this is the right page.

## Get the console (no Python needed)

1. Download **[COVTL-Console-Windows-x64.zip (~122 MB)](
   https://github.com/FBerthommier/covtl-console/releases/download/windows-standalone/COVTL-Console-Windows-x64.zip)**
   (official asset: `releases/download/windows-standalone/…`).
2. **Check the SHA-256** of the zip — it must be
   `36e2e0223182fff2b09f4c5ac53c8a2be8370ef80fe2e72b7d98f6524155f418`
   (or the value shown on [covtl.org](https://covtl.org) / the release
   page). `certutil -SHA256 COVTL-Console-Windows-x64.zip`
3. Unzip anywhere **ASCII** (e.g. `C:\COVTL`) and run
   `covtl-console.exe` — your browser opens on `http://127.0.0.1:8421`.
4. **SmartScreen note**: the build is not code-signed. On first launch,
   Windows may show a blue warning — click *More info* > *Run anyway*.
   Non-ASCII install paths are handled automatically (local `%TEMP%`
   staging).

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
  (`gh attestation verify COVTL-Console-Windows-x64.zip -R FBerthommier/covtl-console`)
  are the real proof, beyond any QR code.

**Next stop:** [releases](https://github.com/FBerthommier/covtl-console/releases) ·
[all briefs & docs](https://github.com/FBerthommier/covtl-console/tree/main/docs) ·
[Linux brief](brief-linux.md) · [macOS brief](brief-macos.md) ·
[source](https://github.com/FBerthommier/covtl-console)

*GPL-3.0-or-later · built on VocalTractLab · © Frédéric Berthommier — cite arXiv:2307.02299.*
