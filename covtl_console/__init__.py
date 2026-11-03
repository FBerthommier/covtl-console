# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""covtl_console — the COVTL Lab Console (bridge + UI) as a package.

`python -m covtl_console` or the `covtl-console` script starts the
local bridge on http://127.0.0.1:8421. The UI assets live in
``covtl_console/ui/`` and are served by the bridge itself.
"""
__version__ = "3.1.0"

from covtl_console.server import main                        # noqa: F401,E402
