<!-- SPDX-FileCopyrightText: 2026 Frédéric Berthommier -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Quick install

**Flash (one command, Python 3.9+):**
`pip install git+https://github.com/FBerthommier/covtl-console.git` then
run **`covtl-console`** — the engine (VocalTractLab binaries included in
its wheel), the covtl-sandhi liaison rules and the bridge are resolved
automatically. Locked-down box or portable Python: clone the repo and
`python install_flash.py` (creates the venv, installs everything,
writes a launcher; `--run` starts it).

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

**No Python at all?** Double-click `covtl-console-standalone.html` — the
bridge on 127.0.0.1:8421 whenever one is reachable.
