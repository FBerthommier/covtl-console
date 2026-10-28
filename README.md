# COVTL Lab Console — local laboratory interface for covtl-pipeline

The COVTL Lab Console is a **local web interface** for the open-source
articulatory speech engine [covtl-pipeline](https://github.com/FBerthommier/covtl-pipeline)
(`vtl_synth`, CLI `vtl-synth`), which wraps VocalTractLab 2.4. It gives
phoneticians and students a laboratory bench for the COVTL polar model:
type ordinary text or SAMPA, watch the grapheme-to-phoneme preview and the
live SAMPA guard, **compile** the utterance into the engine's own syllable
blocks, **synthesize** it through VocalTractLab, and follow the utterance on
a **continuous polar (ρ, θ) display that advances anchor by anchor through
the real syltraj trajectory**. The Python engine stays the single source of
truth for every phonetic decision; the browser only previews, displays and
controls. Nothing leaves your machine — no cloud, no telemetry.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Header: COVTL Lab · state · Language · Speaker/f0 · Backend(health)      │
├────────────┬─────────────────────────────────────────────────────────────┤
│ Controls   │ Stage                                                       │
│ 1 Lang&Spk │  Preview stack: G2P → enriched → final SAMPA (red reject)   │
│ 2 Input    │  Action bar: Preview(P) · Synthesize(S) · from edited(E)    │
│ 3 Timings  │  Syllable compiler: tiles · block sequence · block cards    │
│ 4 Prosody  │  Continuous polar display: Block k/n · A_k→A_k+1 · ρ/θ      │
│ 5 Engine   │  Transport: play · A− A+ · scrub(anchor ticks) · speeds     │
│   & Guard  │  Spectrogram with anchor overlay                            │
│ 6 Display  │  Log (every job echoes the full parameter set)              │
├────────────┴─────────────────────────────────────────────────────────────┤
│ license GPL-3.0-or-later · local only · no cloud · no telemetry          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Features

- **Continuous polar display** — the utterance is the engine's anchor list;
  segments run from one anchor to the next, each carrying its 100 Hz points
  (`t, rho_v, theta_v, rho_c, theta_c`, null = inactive branch). The head
  advances block by block over the real syltraj trajectory — never a
  UI-invented re-segmentation.
- **Start-early polar-only mode** — the bridge builds the trajectory
  structure (anchors + blocks + `.polar`) *before* the VocalTractLab stage,
  so `polar_ready` flips while the WAV still renders: the display starts on
  its own monotonic clock, then re-anchors on the audio clock. No chunked
  re-synthesis, ever.
- **Syllable block compiler** — `POST /api/compile` runs the engine's own
  anchor walk over your SAMPA blocks (no synthesis): metric tiles
  (syllables · anchors · blocks · C/V · duration), the block sequence as
  labeled chips, and clickable block cards exposing onset clusters with
  their (ρ, θ) targets and vowel plateaus. After synthesis, clicking a card
  seeks the polar display to exactly that segment.
- **Red-reject SAMPA guard** — symbols outside the engine inventory are
  highlighted in red with suggestions (`c` → `k, s`, IPA `ʃ` → `S`, …);
  policies `warn` / `error` / `off`, one-click strip action.
- **Per-language examples** — ready-made example chips for English, French,
  Spanish, German, Italian and Portuguese.
- **Spectrogram with anchor overlay** — FFT spectrogram of the synthesized
  WAV with the same anchor ticks as the scrub bar.
- **WYSIWYG synthesis** — Synthesize always uses exactly the SAMPA shown on
  screen (deterministic ortho path, edited-phonetic path, or compiler output).
- **Result caching** — preview LRU, compile LRU and a synthesis cache keyed
  on the full parameter set *including the engine version* (guard policy
  deliberately excluded; the `error` policy is re-validated on every hit).
- **Demo mode** — with no Python at all, the console runs a clearly-labeled
  browser simulation of G2P, guard and audio.
- **Single-file standalone build** — `build_standalone.py` inlines every
  module into `covtl-console-standalone.html`, which works from `file://`
  and talks to the bridge on 127.0.0.1:8421 when one is running.

## Requirements

- **Python 3.9 or later** (3.12 recommended) with `pip`
- A browser: Chrome, Edge or Firefox (current versions)
- The engine **covtl-pipeline** installed — `pip install .` from a clone of
  <https://github.com/FBerthommier/covtl-pipeline> (see its
  `INSTALLATION.md` for the VocalTractLab native binaries it manages)
- Bridge dependencies: `fastapi` and `uvicorn`

Without the engine the console still runs in **demo mode** (see below) —
simulated G2P/guard/audio and an approximate compiler — clearly labeled as
such in the UI.

## Installation — every system

Full matrices live here; [INSTALL.md](INSTALL.md) is the condensed
quick-start. In all cases: clone the engine first, install it into the
Python environment you will use for the console, then start the bridge.

### Windows 10/11 (PowerShell)

```powershell
# 1) engine
git clone https://github.com/FBerthommier/covtl-pipeline.git
cd covtl-pipeline
py -3.12 -m pip install .
# (VocalTractLab natives: follow INSTALLATION.md in the engine repo)

# 2) console
cd ..
git clone https://github.com/FBerthommier/covtl-console.git
cd covtl-console
py -3.12 -m pip install fastapi uvicorn

# 3) run
py -3.12 server.py     # → http://127.0.0.1:8421
```

On machines where the Python installer is not available (locked-down
corporate boxes), portable Python works fine — for example the NuGet
package, which needs no installer and no admin rights:

```powershell
nuget install python.portable -Version 3.12.10 -ExcludeVersion
# interpreter at .\python.portable\tools\python.exe — use it for every
# py -3.12 … line above, and add -m pip as needed
```

### macOS (zsh)

```zsh
# Xcode Command Line Tools may be needed to build engine dependencies:
xcode-select --install

git clone https://github.com/FBerthommier/covtl-pipeline.git
cd covtl-pipeline && python3 -m pip install . && cd ..

git clone https://github.com/FBerthommier/covtl-console.git
cd covtl-console
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install fastapi uvicorn
python server.py        # → http://127.0.0.1:8421
```

### Linux — Debian/Ubuntu (bash)

```bash
sudo apt update
sudo apt install -y python3 python3-dev python3-venv python3-pip git
# (portaudio19 / ALSA headers only if the engine's INSTALLATION.md asks
#  for them on your build)

git clone https://github.com/FBerthommier/covtl-pipeline.git
cd covtl-pipeline && python3 -m pip install . && cd ..

git clone https://github.com/FBerthommier/covtl-console.git
cd covtl-console
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install fastapi uvicorn
python server.py        # → http://127.0.0.1:8421
```

On Debian/Ubuntu systems where `pip install .` into the system interpreter
is blocked (PEP 668), create the venv **before** installing the engine and
use its `python3 -m pip` for both `pip install` steps.

### Linux — Fedora (bash)

```bash
sudo dnf install -y python3 python3-devel git
# (ALSA/portaudio development packages only if the engine build needs them)

git clone https://github.com/FBerthommier/covtl-pipeline.git
cd covtl-pipeline && python3 -m pip install . && cd ..

git clone https://github.com/FBerthommier/covtl-console.git
cd covtl-console
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install fastapi uvicorn
python server.py        # → http://127.0.0.1:8421
```

### No-Python demo mode

Any static file server will do (ES modules need http):

```bash
python -m http.server 8080     # then open http://localhost:8080
```

or simply double-click **`covtl-console-standalone.html`** — a single file
that works from `file://`. When a live bridge is reachable on
127.0.0.1:8421 the standalone uses it; otherwise it runs the browser demo
engine (simulated G2P/guard/audio, approximate syllable compiler, demo
polar segments — the UI labels every demo surface as such).

### Ports and artifacts

- Live bridge: **127.0.0.1:8421** (localhost only). The v2 workbench port
  8420 is untouched — both consoles can run side by side.
- Synthesis artifacts (`.wav`, `.txt`, `.tract`, `.polar`, `.mp4`) land in
  the `out/` folder under the console folder; the UI displays the resolved
  absolute path (from `/api/status → out_root`).

### Speakers and languages

The engine ships a multi-speaker registry and a six-language pack; the
console only exposes what the engine has installed:

```bash
python setup_lang.py list                  # available + current language
python setup_lang.py install --lang fr     # install/activate French
python setup_lang.py setlang de            # switch language
python install_speaker.py list             # registered + active speaker
python install_speaker.py install m01      # swap speaker (reversible)
python install_speaker.py restore          # back to jd3
```

Language-pack vowels are calibrated on the **jd3** speaker only; picking
another speaker with a non-English language triggers the console's
*unverified combination* warning (audio may differ).

## First run — the three-step flow

1. **Preview** — pick a language, click an example chip (or type text),
   press `P`. The preview stack shows G2P output → enriched string → final
   SAMPA; symbols outside the engine inventory are red with suggestions.
2. **Compile** — press `C`, type or edit SAMPA syllable blocks, press
   Enter. The compiler panel shows metric tiles, the block sequence, and
   clickable cards with (ρ, θ) targets — the engine's own anchor walk, no
   synthesis.
3. **Synthesize** — press `S` (or `E` to synthesize exactly the edited
   SAMPA shown on screen). Watch ⏳ progress, then play the result, read
   the spectrogram, follow the polar display anchor by anchor, and download
   artifacts from the downloads menu (`D`).

| Key | Action | Key | Action |
|---|---|---|---|
| `Space` / `K` | Play / pause | `[` / `]` | Previous / next anchor |
| `Shift+S` | Stop (back to start) | `L` | Loop current block |
| `P` | Preview (never synthesizes) | `0–3` | Speed 0.25× / 0.5× / 1× / 2× |
| `S` | Synthesize from current source | `E` | Synthesize from edited SAMPA |
| `C` | Focus the compiler (Enter compiles) | `D` | Downloads menu |
| `Esc` | Cancel synthesis / stop playback | `?` | Shortcut help |

## Documentation

- **User manual** (didactic, no programming background needed):
  [docs/user-manual/user-manual.pdf](docs/user-manual/user-manual.pdf)
- **Technical reference** (bridge API, anchor instrumentation, clock model,
  caching, extension guide):
  [docs/tech-manual/tech-manual.pdf](docs/tech-manual/tech-manual.pdf)
- Change record for v3: [CHANGES_v3.md](CHANGES_v3.md)

## Testing

With covtl-pipeline installed (engine-required tests skip with an explicit
reason otherwise):

```bash
pip install pytest httpx
pytest tests/ -v            # add -m "not slow" to skip long synthesis jobs
```

`tests/test_frontend_checklist.md` is the manual browser series used for
release sign-off.

## Licensing

covtl-console is licensed **GPL-3.0-or-later** — the same license as
covtl-pipeline — so it stays linkable with the engine and with
VocalTractLab. See [LICENSE](LICENSE) (verbatim GNU GPL v3) and the SPDX
headers in every source file.

This repository depends on **covtl-pipeline** (GPL-3.0-or-later) and drives
VocalTractLab 2.4 synthesis through it. **No VocalTractLab code or binaries
are redistributed here** — users obtain the engine through covtl-pipeline,
which manages those dependencies. Third-party components used by the engine
(Wikipron lexicons, CC BY-SA 3.0; CMUdict; `vocaltractlab-cython`) are
referenced, not copied: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citing

The console drives the engine — please cite **covtl-pipeline**
(GPL-3.0-or-later, <https://github.com/FBerthommier/covtl-pipeline>) and
the underlying articles of the Berthommier COVTL model, as the engine's
README does:

1. F. Berthommier, "A mathematical model of the vowel space",
   arXiv:2111.00868 [eess.AS], 2021.
   DOI: 10.48550/arXiv.2111.00868 — <https://arxiv.org/abs/2111.00868>
2. F. Berthommier, "Why can big.bi be changed to bi.gbi? A mathematical
   model of syllabification and articulatory synthesis",
   arXiv:2307.02299 [eess.AS], 2023 — the COVTL polar model the console
   displays.
   DOI: 10.48550/arXiv.2307.02299 — <https://arxiv.org/abs/2307.02299>

Please also cite VocalTractLab itself (see the engine's
THIRD_PARTY_NOTICES.md).
