<!-- SPDX-FileCopyrightText: 2026 Frédéric Berthommier -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Quick install

Three commands and a browser. Details, edge cases and the full
per-system matrix live in the [README](README.md#installation--every-system).

```bash
# 1) the engine (anywhere)
git clone https://github.com/FBerthommier/covtl-pipeline.git
cd covtl-pipeline && pip install . && cd ..

# 2) the console
git clone https://github.com/FBerthommier/covtl-console.git
cd covtl-console && pip install fastapi uvicorn

# 3) run
python server.py
```

Open <http://127.0.0.1:8421> in Chrome, Edge or Firefox. The header's
backend chip must read **live** — if it reads *demo*, the engine was not
importable in this interpreter and the console is simulating (see README
§Installation for venv and per-system notes).

**No Python at all?** Double-click `covtl-console-standalone.html` — the
console runs in clearly-labeled demo mode, and automatically uses a live
bridge on 127.0.0.1:8421 whenever one is reachable.
