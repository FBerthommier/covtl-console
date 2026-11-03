#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""install_flash.py — the belt-and-braces flash installer (option A).

For machines where the one-command pip route is awkward (locked-down
boxes, portable Python such as the NuGet package, no `py` launcher),
this script does the whole flash install step by step:

    python install_flash.py                # create .venv-covtl + install + launcher
    python install_flash.py --run          # ... and start the bridge
    python install_flash.py --python D:\\py312\\python.exe --venv myenv
    python install_flash.py --engine D:\\path\\to\\covtl-pipeline   # local engine

It creates a virtual environment, installs the engine (VocalTractLab
binaries included in its wheel), the covtl-sandhi liaison rules, the
bridge dependencies and the console itself, then writes a launcher
(``run_console.bat`` / ``run_console.sh``). Equivalent to the one
command of option B (``pip install git+…covtl-console.git``), just
explicit — see README §Flash install.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE_URL = "git+https://github.com/FBerthommier/covtl-pipeline.git"
SANDHI_URL = "git+https://github.com/FBerthommier/covtl-sandhi.git"


def run(cmd: list, **kw) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="install_flash.py",
        description="Flash install of the COVTL Lab Console "
                    "(venv + engine + sandhi rules + bridge)")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter used to create the venv "
                         "(default: the current one)")
    ap.add_argument("--venv", default=".venv-covtl",
                    help="venv directory to create (default .venv-covtl)")
    ap.add_argument("--engine", default=ENGINE_URL,
                    help="engine source: a git URL or a local checkout "
                         "path (default: GitHub main)")
    ap.add_argument("--no-sandhi", action="store_true",
                    help="skip the covtl-sandhi liaison rules (the UI "
                         "default 'standard' level then degrades to "
                         "'off' with a warning)")
    ap.add_argument("--run", action="store_true",
                    help="start the bridge when done")
    args = ap.parse_args()

    venv_dir = ROOT / args.venv
    run([args.python, "-m", "venv", venv_dir])
    py = venv_dir / ("Scripts/python.exe" if os_name() == "nt"
                     else "bin/python")
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    engine = args.engine if "://" in args.engine or args.engine.endswith(
        ".git") else str(Path(args.engine).resolve())
    run([py, "-m", "pip", "install", engine])
    if not args.no_sandhi:
        run([py, "-m", "pip", "install", SANDHI_URL])
    run([py, "-m", "pip", "install", "fastapi", "uvicorn"])
    run([py, "-m", "pip", "install", str(ROOT)])

    launcher = ROOT / ("run_console.bat" if os_name() == "nt"
                       else "run_console.sh")
    if os_name() == "nt":
        launcher.write_text(
            f'@echo off\r\n"{py}" -m covtl_console %*\r\n',
            encoding="utf-8")
    else:
        launcher.write_text(
            f'#!/bin/sh\nexec "{py}" -m covtl_console "$@"\n',
            encoding="utf-8")
        launcher.chmod(0o755)
    print(f"\nDone. Launcher written: {launcher}")
    print(f"  start the bridge:  {launcher.name}")
    print(f"  or directly:       \"{py}\" -m covtl_console")
    print("  UI assets, engine, sandhi rules: all installed in the venv.")
    if args.run:
        run([py, "-m", "covtl_console"])
    return 0


def os_name() -> str:
    return "nt" if sys.platform.startswith("win") else "posix"


if __name__ == "__main__":
    sys.exit(main())
