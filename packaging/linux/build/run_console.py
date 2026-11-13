# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point PyInstaller — demarre le pont local (voir server.main).

Adaptation pour l'application gelee (pool de synthese N2) :

* freeze_support() gere les enfants "-B -S -I --multiprocessing-fork"
  (resource tracker, enfant fork).
* Le rthook PyInstaller 6.22.3 ne detourne PAS la commande "-c" du
  SPAWN de worker (uniquement resource_tracker / forkserver) : le
  process worker re-executait ce script entier et mourrait sur
  l'argparse du serveur (flags internes "-B -S -I -c" rejetes ->
  BrokenProcessPool immediat). On detourne donc ce cas ici : le
  worker execute sa commande spawn_main et sort.
"""
import multiprocessing
import sys

multiprocessing.freeze_support()

def _mp_spawn_worker_argv(argv):
    if "-c" not in argv:
        return None
    i = argv.index("-c")
    if len(argv) > i + 1 and argv[i + 1].startswith(
            "from multiprocessing.spawn import spawn_main"):
        return argv[i + 1]
    return None

_cmd = _mp_spawn_worker_argv(sys.argv)
if _cmd is None:
    from covtl_console.__main__ import main            # noqa: E402
    main()
else:
    exec(_cmd)
    sys.exit(0)
