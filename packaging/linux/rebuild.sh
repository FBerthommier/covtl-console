#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Reconstruction du binaire Linux COVTL-Console à partir de ce bundle.
#
# Usage :
#   bash rebuild.sh                # venv + install 2 phases + correctifs + build + emballage
#   RUN_SMOKE=1 bash rebuild.sh    # + smoke de validation (démarrage + synthèse, ~2 min)
#
# Résultat : releases/COVTL-Console-Linux-x64.zip régénéré avec la porte
# d'hygiène B2, et validation/SHA256SUMS.txt actualisé.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "==> [0/6] Prérequis"
python3 -c "import sys; assert sys.version_info[:2] == (3, 12), 'Python 3.12 requis (wheels cp312 de vocaltractlab_cython)'"

echo "==> [1/6] venv neuf : $ROOT/.venv-build"
if [ -d .venv-build ]; then rm -rf .venv-build; fi
python3 -m venv .venv-build
.venv-build/bin/pip install --quiet --upgrade pip

echo "==> [2/6] Phase 1 — dépendances réelles (PyPI)"
.venv-build/bin/pip install --quiet -r build/requirements-build.txt

echo "==> [3/6] Phase 2 — chaîne covtl (TestPyPI)"
.venv-build/bin/pip install --quiet --index-url https://test.pypi.org/simple/ "covtl-console==3.1.5"
.venv-build/bin/pip check
.venv-build/bin/pip freeze > build/requirements-freeze-run.txt

echo "==> [4/6] Correctif n°3 (import BrokenProcessPool)"
python3 build/patch-fix3-brokenprocesspool.py .venv-build

echo "==> [5/6] Build PyInstaller (onedir)"
.venv-build/bin/pyinstaller build/covtl-console-linux.spec --noconfirm \
    --distpath "$ROOT/dist/linux" --workpath "$ROOT/build/pyinstaller" \
    > build/pyinstaller-run.log 2>&1
tail -n 1 build/pyinstaller-run.log

if [ "${RUN_SMOKE:-0}" = "1" ]; then
    echo "==> [+] Smoke de validation"
    bash build/smoke.sh "$ROOT/dist/linux/covtl-console/covtl-console"
fi

echo "==> [6/6] Emballage release + porte d'hygiène B2"
python3 build/zip-release-b2.py "$ROOT/dist/linux/covtl-console"

echo ""
echo "Terminé — release régénérée : releases/COVTL-Console-Linux-x64.zip"
echo "Sommes de contrôle actualisées : validation/SHA256SUMS.txt"
