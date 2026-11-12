# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fix B1 + N5(version) tests — pre-release audit round 2026-11-12.

B1 (blocking): the frozen Windows bundle fast-fails 0xC0000409 when
its executable sits in a non-ASCII path. The package now refuses such
starts politely, before the server import (which is where the frozen
extension modules — the actual crash point — get loaded).

N5 (version cosmetics): the bridge version literals had drifted to
3.0.0 while the package is 3.1.0; they now derive from
``covtl_console.__version__``. The frozen ``engine_version`` fallback
now reads the module attribute ("1.1.0") instead of the literal
"installed" the audit observed in the UI.
"""
import importlib
import sys
from types import SimpleNamespace

import pytest

from conftest import requires_engine

from covtl_console import __version__ as PKG_VERSION
from covtl_console import _launchguard as guard


# ── B1: who gets refused — and who never does ──────────────────────────
def test_refuses_frozen_nonascii_executable(tmp_path):
    """A frozen build in a non-ASCII folder is refused with the guard's
    exit code, and the refusal is traced to the log next to the exe."""
    home = tmp_path / "Café"                 # non-ASCII folder, real on Linux
    home.mkdir()
    exe = home / "covtl-console.exe"
    fake = SimpleNamespace(frozen=True, executable=str(exe),
                           stderr=sys.stderr, stdout=sys.stdout)
    with pytest.raises(SystemExit) as ei:
        guard.refuse_nonascii_bundle(sys_module=fake)
    assert ei.value.code == guard.EXIT_CODE
    log = home / guard.LOG_NAME
    assert log.is_file()
    line = log.read_text(encoding="utf-8")
    assert "non-ASCII executable path" in line and str(exe) in line


def test_frozen_ascii_allowed(tmp_path):
    exe = tmp_path / "covtl-console.exe"
    fake = SimpleNamespace(frozen=True, executable=str(exe))
    assert guard.refuse_nonascii_bundle(sys_module=fake) is None


def test_regular_interpreter_never_refused(tmp_path):
    """pip installs / dev checkouts / test suites must never be blocked:
    a non-ASCII sys.executable is legal there (audit: venv installs OK)."""
    fake = SimpleNamespace(frozen=False,
                           executable=str(tmp_path / "Ém" / "python.exe"))
    assert guard.offending_path(fake) is None
    assert guard.refuse_nonascii_bundle(sys_module=fake) is None


def test_unresolvable_executable_never_refuses():
    """When we cannot tell (missing/empty path), we do not block."""
    for exe in ("", None):
        fake = SimpleNamespace(frozen=True, executable=exe)
        assert guard.offending_path(fake) is None


def test_guard_survives_hostile_io(tmp_path):
    """A guard that itself raised would be worse than no guard: broken
    stderr and an unwritable log must not cancel the refusal."""
    class BrokenStream:
        def write(self, *_): raise OSError("stdout lost")
        def flush(self): raise OSError("stdout lost")

    fake = SimpleNamespace(frozen=True, executable=str(tmp_path / "Ω"),
                           stderr=BrokenStream(), stdout=BrokenStream())
    with pytest.raises(SystemExit) as ei:
        guard.refuse_nonascii_bundle(sys_module=fake,
                                     log_dir=str(tmp_path / "no-such-dir"))
    assert ei.value.code == guard.EXIT_CODE


# ── B1: the refusal must be legible in a Windows console ──────────────
def test_printed_message_ascii_any_console(tmp_path):
    """What lands on stderr renders in any Windows code page (cp437
    included): the message is pure ASCII, the offending path shown
    transliterated (backslashreplace); the log line (UTF-8) keeps the
    exact path. The audit's crash was silent — this is the part that
    makes it loud on every console."""
    import io
    home = tmp_path / "Ω café"
    home.mkdir()
    exe = home / "covtl-console.exe"
    fake = SimpleNamespace(frozen=True, executable=str(exe),
                           stderr=io.StringIO(), stdout=io.StringIO())
    with pytest.raises(SystemExit) as ei:
        guard.refuse_nonascii_bundle(sys_module=fake)
    assert ei.value.code == guard.EXIT_CODE
    printed = fake.stderr.getvalue()
    printed.encode("ascii")                    # pure ASCII by construction
    assert "cannot start here" in printed
    assert "\\u03a9" in printed and "\\xe9" in printed   # transliterated Ω, é
    line = (home / guard.LOG_NAME).read_text(encoding="utf-8")
    assert str(exe) in line and "non-ASCII executable path" in line


def test_path_is_ascii_classifier():
    assert guard.path_is_ascii("C:\\Tools\\COVTL ok _-1")
    assert guard.path_is_ascii("")                     # empty encodes trivially
    assert not guard.path_is_ascii("C:\\Users\\Émilie")
    assert not guard.path_is_ascii("/tmp/Ω")


# ── B1: the guard must run before the server import ────────────────────
def test_guard_runs_before_server_import():
    """`covtl_console/__init__.py` must call the guard BEFORE importing
    the server module — the audit located the crash inside the frozen
    extension-module loading triggered by that very import."""
    src = (importlib.util.find_spec("covtl_console")
           .origin.replace("__init__.py", ""))
    text = open(src + "__init__.py", encoding="utf-8").read()
    guard_pos = text.index("refuse_nonascii_bundle()")
    import_pos = text.index("from covtl_console.server import main")
    assert guard_pos < import_pos


# ── N5: version single source of truth ─────────────────────────────────
def test_bridge_version_single_source(client):
    """Every place that said 3.0.0 now follows the package version."""
    import covtl_console.server as S
    assert S.BRIDGE_VERSION == PKG_VERSION
    assert S.app.version == PKG_VERSION
    status = client.get("/api/status").json()
    assert status["bridge"] == PKG_VERSION
    health = client.get("/api/health").json()
    assert health["bridge"] == PKG_VERSION


@requires_engine
def test_engine_version_falls_back_to_module_attribute(monkeypatch):
    """Frozen bundles ship no dist-info, so importlib.metadata raises
    PackageNotFoundError; the fallback must read vtl_synth.__version__
    ("1.1.0") instead of the literal "installed" (audit §1/UI)."""
    import vtl_synth
    import covtl_console.server as S
    import importlib.metadata as md

    def boom(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", boom)
    try:
        importlib.reload(S)
        assert S.LIVE
        assert S.ENGINE_VERSION == vtl_synth.__version__
        assert S.ENGINE_VERSION != "installed"
        # what /api/health would report
        from fastapi.testclient import TestClient
        with TestClient(S.app) as c:
            body = c.get("/api/health").json()
            assert body["engine_version"] == vtl_synth.__version__
    finally:
        monkeypatch.undo()
        importlib.reload(S)                    # restore the real metadata
    # restored state: dist-info when pip-installed, module attribute when
    # the engine is only importable (e.g. a PYTHONPATH checkout).
    try:
        expected = importlib.metadata.version("vtl-synth")
    except importlib.metadata.PackageNotFoundError:
        expected = vtl_synth.__version__
    assert S.LIVE and S.ENGINE_VERSION == expected


# ── B2 sanity (repo side): out/ can never re-enter the tree ────────────
def test_out_tree_never_committed():
    """The smoke-test residue root is git-ignored and lives outside the
    importable package, so no commit and no wheel can ever ship it (the
    release-ZIP staging that shipped it is build-machine side — see this
    round's instructions for the external agent)."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run(["git", "check-ignore", "-q", "out/"], cwd=root)
    assert r.returncode == 0, "out/ must stay git-ignored"
    assert not (root / "covtl_console" / "out").exists(), \
        "synthesis outputs must never land inside the importable package"
