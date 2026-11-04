# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""UI source contracts — no engine, no browser needed.

Static guards over the shipped JS: each one pins a behavior that the
flash-validation browser checklist verified live, so a regression fails
in CI on both OS instead of waiting for the next manual walkthrough.
"""
from pathlib import Path

import re

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "covtl_console" / "ui" / "js" / "app.js"


def _function_body(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    end = src.index("\n}", start)
    return src[start:end]


def test_reset_empties_downloads_menu():
    """F2 (flash-validation report, volet b): the input reset must EMPTY
    the downloads menu, not merely hide it — re-opening `D` after a
    reset shows the no-artifacts state, never the previous job's
    entries. The menu content is the single source of truth for the
    entries (rebuilt from result.files on each synthesis; no persisted
    download state exists), so re-rendering it empty is the complete
    fix."""
    src = APP_JS.read_text(encoding="utf-8")
    body = _function_body(src, "resetInputs")
    assert "$('#dl-menu').style.display = 'none'" in body, (
        "resetInputs() must keep hiding the downloads menu")
    assert re.search(
        r"R\.renderDownloads\(\s*\$\('#dl-menu'\)\s*,\s*\[\]\s*[,)]", body), (
        "resetInputs() hides #dl-menu but never empties it — stale "
        "entries reappear when the menu is reopened")
