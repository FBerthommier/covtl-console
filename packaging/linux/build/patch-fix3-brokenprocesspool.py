#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Correctif n°3 de la chaîne de build Linux : import BrokenProcessPool.

Contexte (N2) : covtl_console/_synthproc.py attrape BrokenProcessPool pour
retenter un enfant de synthèse tué, mais server.py — qui référence la même
exception dans son gestionnaire de job — oubliait de l'importer : toute
erreur enfant levait NameError au lieu du fallback prévu. Sur Windows le
build passait car le module était déjà chargé ; en gelé Linux, l'exception
sortait à la première tentative de secours.

Usage : python3 patch-fix3-brokenprocesspool.py [chemin-venv]
      (défaut : ./.venv-build)
Idempotent : sans effet si le correctif est déjà appliqué.
"""
import pathlib
import sys

MARK = "# [XFIX] N2 fallback"
OLD = "from collections import OrderedDict"
NEW = (OLD + "\n"
       + "from concurrent.futures.process import BrokenProcessPool  " + MARK)


def patch(venv: pathlib.Path) -> int:
    cands = sorted(venv.glob(
        "lib/python3.*/site-packages/covtl_console/server.py"))
    if not cands:
        cands = sorted(venv.glob(
            "Lib/site-packages/covtl_console/server.py"))  # venv Windows
    if not cands:
        print(f"ERREUR : server.py introuvable sous {venv}")
        return 1
    p = cands[0]
    src = p.read_text(encoding="utf-8")
    # 3.1.5+ embarque la correction en amont (import près de
    # ProcessPoolExecutor) : détection sémantique en plus du marqueur.
    if MARK in src or "from concurrent.futures.process import BrokenProcessPool" in src:
        print(f"déjà appliqué/présent : {p}")
        return 0
    if OLD not in src:
        print(f"ERREUR : ancre '{OLD}' absente de {p} — paquet inattendu")
        return 1
    p.write_text(src.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"correctif n°3 appliqué : {p}")
    return 0


if __name__ == "__main__":
    venv = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 \
        else pathlib.Path(__file__).resolve().parent / ".venv-build"
    sys.exit(patch(venv))
