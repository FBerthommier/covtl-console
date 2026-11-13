<!-- SPDX-FileCopyrightText: 2026 Frédéric Berthommier -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Quick install

**No Python at all — standalone bundles:**

- **Windows x64**: download `COVTL-Console-Windows-x64.zip` from the
  [releases page](https://github.com/FBerthommier/covtl-console/releases),
  unzip anywhere and double-click `covtl-console.exe`. If the
  extraction path contains non-ASCII characters (e.g. accents), the
  launcher stages the app under `%TEMP%\covtl-console-ascii` on first
  run and re-executes from there (the underlying C++ crash is a known
  upstream issue —
  [VocalTractLabBackend-dev#61](https://github.com/TUD-STKS/VocalTractLabBackend-dev/issues/61));
  if staging is impossible the launcher refuses politely with exit
  code 80 instead of crashing. Later launches reuse the staged copy.
- **Linux x64**: `COVTL-Console-Linux-x64.zip` from the
  [linux-standalone release](https://github.com/FBerthommier/covtl-console/releases/tag/linux-standalone)
  — unzip, `chmod +x covtl-console`, run. Video modes (sagittal/polar
  MP4) are bundled, matching the Windows build.

**Pre-release install from TestPyPI (Python 3.9+)** — while the COVTL
chain is staged on [TestPyPI](https://test.pypi.org), use the *safe
scheme*: the three COVTL packages come from TestPyPI **with
`--no-deps`** (TestPyPI also mirrors third-party projects, and a
squatted or newer build there could otherwise shadow the real PyPI
package during dependency resolution), then every external dependency
resolves from the regular PyPI:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows (. .venv/bin/activate on Linux)

# 1) the COVTL chain from TestPyPI, no dependency resolution
pip install --index-url https://test.pypi.org/simple/ --no-deps \
    covtl-console==3.1.6 vtl-synth==1.1.3 covtl-sandhi==0.1.1

# 2) external dependencies from the regular PyPI (the COVTL packages
#    are already satisfied and are not re-downloaded)
pip install --index-url https://pypi.org/simple/ covtl-console==3.1.6

# 3) optional — video modes (polar/sagittal MP4) need matplotlib
pip install --index-url https://pypi.org/simple/ matplotlib

covtl-console
```

The engine (VocalTractLab binaries ship inside the `vtl-synth` wheel)
and the covtl-sandhi liaison rules are already part of the chain —
nothing else to install.

**Flash (one command, Python 3.9+, from GitHub):**
`pip install git+https://github.com/FBerthommier/covtl-console.git` then
run **`covtl-console`** — the engine, the covtl-sandhi liaison rules
and the bridge are resolved automatically. Locked-down box or portable
Python: clone the repo and `python install_flash.py` (creates the venv,
installs everything, writes a launcher; `--run` starts it).

The classic step-by-step install below stays the way to go when you
want a local engine checkout for development; details, edge cases and
the full per-system matrix live in the
[README](README.md#installation--every-system).

```bash
# 1) the engine (anywhere)
git clone https://github.com/FBerthommier/covtl-pipeline.git
cd covtl-pipeline && pip install . && cd ..

# 1b) the cross-word sandhi rules (liaison) — recommended: the UI
#     preselects the 'standard' level
pip install git+https://github.com/FBerthommier/covtl-sandhi.git

# 2) the console
git clone https://github.com/FBerthommier/covtl-console.git
cd covtl-console && pip install fastapi uvicorn

# 3) run
python server.py
```

Open <http://127.0.0.1:8421> in Chrome, Edge or Firefox. The header's
backend chip must read **live** — if it reads *offline*, the engine was not
importable in this interpreter and the console is simulating (see README
§Installation for venv and per-system notes). The hint under the Prosody
sandhi selects lists the rule languages the bridge actually has; if it
shows the *not installed* reason instead, step 1b was skipped and the
sandhi level degrades to `off` with a warning.

**No Python at all and no download?** Double-click
`covtl-console-standalone.html` — the bridge on 127.0.0.1:8421 whenever
one is reachable.
