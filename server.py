# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Development launcher — the implementation lives in the package.

This file exists so the historical habits keep working unchanged:

  * ``python server.py`` from a repository checkout starts the bridge;
  * ``import server`` (the test suite, tooling) resolves to the real
    implementation module: this shim installs ``covtl_console.server``
    under the name ``server`` in sys.modules, so attribute access —
    including test monkeypatching — lands on the defining module's
    globals.

New code should import ``covtl_console.server`` directly or use the
``covtl-console`` entry point.
"""
import sys

from covtl_console import server as _impl

sys.modules[__name__] = _impl

main = _impl.main

if __name__ == "__main__":          # python server.py
    main()
