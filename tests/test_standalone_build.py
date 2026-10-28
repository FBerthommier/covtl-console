# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaging tests for the single-file standalone build — no engine needed.

``build_standalone.py`` regenerates ``covtl-console-standalone.html``;
the bundle's script block must compile, contain no leftover ES-module
import statements, register all 8 modules in ``__mods`` and carry the
per-language example labels.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "covtl-console-standalone.html"
MODULES = ["data", "demo-engine", "render", "api", "polar", "spectrogram",
           "compiler", "app"]
LANG_LABELS = ["EN ·", "FR ·", "ES ·", "DE ·", "IT ·", "PT ·"]


@pytest.fixture(scope="module")
def built():
    import build_standalone
    out = build_standalone.build()
    return out.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script_blocks(built):
    return re.findall(r"<script>(.*?)</script>", built, flags=re.S)


def test_bundle_exists_and_rebuildable():
    assert BUNDLE.exists(), "the committed bundle must ship with the repo"
    import build_standalone
    out = build_standalone.build()          # must run cleanly from the repo
    assert out.exists() and out.stat().st_size > 50_000


def test_no_es_module_imports_left(script_blocks):
    js = "\n".join(script_blocks)
    assert not re.search(r"import\s+\{[^}]*\}\s+from\s+'\./", js), \
        "leftover relative ES-module import in the bundle"
    assert not re.search(r"import\s+\*\s+as\s+\w+\s+from\s+'\./", js)


def test_registers_all_modules(script_blocks):
    js = "\n".join(script_blocks)
    for name in MODULES:
        assert f"__mods[{name!r}]" in js, f"module {name} not registered"
    assert "const __mods = {}" in js


def test_bundle_carries_language_labels(built):
    for label in LANG_LABELS:
        assert label in built, f"example label {label!r} missing from bundle"


def test_bundle_script_compiles(script_blocks):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available for --check syntax validation")
    with tempfile.TemporaryDirectory() as td:
        for i, block in enumerate(script_blocks):
            path = Path(td) / f"block{i}.js"
            path.write_text(block, encoding="utf-8")
            proc = subprocess.run([node, "--check", str(path)],
                                  capture_output=True, text=True)
            assert proc.returncode == 0, \
                f"script block {i} does not compile:\n{proc.stderr[:800]}"


def test_bundle_spdx_headers(built):
    assert "SPDX-License-Identifier: GPL-3.0-or-later" in built
