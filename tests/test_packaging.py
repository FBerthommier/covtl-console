# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Flash-install packaging tests — no engine needed.

The console is pip-installable with its UI assets inside the package
(covtl_console/ui/) and a `covtl-console` entry point; the repo-root
server.py shim keeps `python server.py` and `import server` working.
"""
from pathlib import Path

import pytest

try:
    import tomllib                                  # py3.11+
except ModuleNotFoundError:                          # pragma: no cover
    tomllib = None

ROOT = Path(__file__).resolve().parent.parent


def test_package_layout():
    pkg = ROOT / "covtl_console"
    assert (pkg / "server.py").is_file()
    assert (pkg / "ui" / "index.html").is_file()
    assert (pkg / "ui" / "js" / "app.js").is_file()
    assert (pkg / "ui" / "css" / "app.css").is_file()


@pytest.mark.skipif(tomllib is None, reason="tomllib needs Python 3.11+")
def test_pyproject_declares_flash_install():
    import tomllib                                            # py3.11+
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(
        encoding="utf-8"))
    deps = " ".join(data["project"]["dependencies"])
    assert "vtl-synth==1.1.2" in deps
    assert "covtl-sandhi==0.1.1" in deps
    scripts = data["project"]["scripts"]
    assert scripts.get("covtl-console") == "covtl_console.server:main"
    ui = data["tool"]["setuptools"]["package-data"]["covtl_console"]
    assert any("ui/index.html" == u for u in ui)


def test_shim_resolves_to_implementation():
    # 'import server' from the repo root must land on the real module
    # (the shim aliases sys.modules) — the suite's monkeypatching and
    # direct module access depend on it.
    import sys
    sys.path.insert(0, str(ROOT))
    import server as S                                        # noqa: E402
    import covtl_console.server as impl                       # noqa: E402
    assert S is impl
    assert callable(impl.main)


@pytest.mark.skipif(tomllib is None, reason="tomllib needs Python 3.11+")
def test_package_version_matches_pyproject():
    import tomllib
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(
        encoding="utf-8"))
    import covtl_console
    assert covtl_console.__version__ == data["project"]["version"]
