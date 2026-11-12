# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Startup guard for packaged (frozen) builds — pre-release audit B1.

The 2026-11-06 pre-release audit established that the PyInstaller
6.22.3 onedir bundle fast-fails with 0xC0000409 (STATUS_STACK_BUFFER_
OVERRUN — no traceback, no message, Windows Event ID 1000) as soon as
the executable's path contains a non-ASCII character. Pure-Python
imports keep working in that state; the process dies while loading
the first frozen *extension* module during
``from covtl_console.server import main`` (the historical bug family
is real upstream: PyInstaller issue #5184, fixed once by PR #5189 in
2020, resurfaces here).

Until the regression is fixed upstream, this module converts the
silent crash into an explicit refusal. It runs BEFORE the server
import (see ``covtl_console/__init__.py``), so it strictly precedes
the extension-module loading that kills the process: it prints a
bilingual explanation on stderr — ASCII-safe, the offending path
transliterated so it renders in any console code page — appends one
line to ``covtl-console.log`` next to the executable (UTF-8, exact
path), then exits with code ``EXIT_CODE``. Non-frozen interpreters
(pip installs, dev checkouts, test suites) are never refused —
regular CPython handles Unicode paths; the audit proved the pip/venv
installs are unaffected. The audit also established that pure-Python
modules keep loading in the broken state (cmudict's diagnostic runs
before the crash), which is exactly what this guard relies on.
"""
from __future__ import annotations

import sys

EXIT_CODE = 80
LOG_NAME = "covtl-console.log"

_MESSAGE = """\
----------------------------------------------------------------------
COVTL Console cannot start here.
The path of covtl-console.exe contains non-ASCII characters (accents
or other symbols); the packaged Windows runtime cannot load its
extension modules from such a path yet (known PyInstaller bug family
- pre-release audit B1, 2026-11-06).
Path: {path}
Fix: move or rename the application folder so that every character in
the path is ASCII (unaccented letters, digits, '_', '-'), for example
C:\\Tools\\COVTL, then start covtl-console.exe again.
FR : le chemin du dossier contient des accents. Deplacez ou renommez
le dossier avec des caracteres non accentues (ex. C:\\Tools\\COVTL),
puis relancez covtl-console.exe.
----------------------------------------------------------------------
"""


def path_is_ascii(path: str) -> bool:
    """True when *path* encodes to ASCII (accents, greek, CJK fail)."""
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def offending_path(sys_module=None):
    """The executable path that must be refused, or None to continue.

    Refuses only frozen interpreters with a resolvable non-ASCII
    ``sys.executable``: a missing/empty path is never refused (when we
    cannot tell, we do not block the user).
    """
    sm = sys if sys_module is None else sys_module
    if not getattr(sm, "frozen", False):
        return None                      # regular interpreter: never refuse
    exe = getattr(sm, "executable", "") or ""
    if not exe:
        return None
    return None if path_is_ascii(exe) else exe


def _log_line(path: str) -> str:
    try:
        import time
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:                                 # pragma: no cover
        stamp = "?"
    return f"[guard] {stamp} refused to start: non-ASCII executable path: {path}"


def refuse_nonascii_bundle(sys_module=None, stream=None, log_dir=None):
    """Refuse (``SystemExit(EXIT_CODE)``) when a frozen build sits in a
    non-ASCII path; return None when startup should continue.

    Every step is best-effort: a guard that itself raised would be
    worse than the disease it guards against, so I/O failures are
    swallowed and the refusal (message + exit code) is preserved.
    """
    bad = offending_path(sys_module)
    if bad is None:
        return None
    sm = sys if sys_module is None else sys_module
    try:
        out = stream if stream is not None else getattr(sm, "stderr", None)
        if out is not None:
            text = _MESSAGE.format(path=bad)
            try:
                text.encode("ascii")
            except UnicodeEncodeError:
                # The offending path is non-ASCII; transliterate it so the
                # message renders in ANY console code page (cp437 included)
                # instead of raising UnicodeEncodeError on print.
                text = text.encode("ascii", "backslashreplace").decode("ascii")
            print(text, file=out)
            out.flush()
    except Exception:                                 # pragma: no cover
        pass
    try:  # best-effort trace in the launcher's log, next to the executable
        import os.path
        directory = log_dir if log_dir is not None \
            else (os.path.dirname(bad) or ".")
        with open(os.path.join(directory, LOG_NAME), "a",
                  encoding="utf-8") as fh:
            fh.write(_log_line(bad) + "\n")
    except Exception:                                 # pragma: no cover
        pass
    try:
        if getattr(sm, "stdout", None) is not None:
            sm.stdout.flush()
    except Exception:                                 # pragma: no cover
        pass
    raise SystemExit(EXIT_CODE)
