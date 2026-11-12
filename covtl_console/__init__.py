# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""covtl_console — the COVTL Lab Console (bridge + UI) as a package.

`python -m covtl_console` or the `covtl-console` script starts the
local bridge on http://127.0.0.1:8421. The UI assets live in
``covtl_console/ui/`` and are served by the bridge itself.
"""
__version__ = "3.1.3"

# Audit B1 (2026-11-06): the frozen Windows bundle fast-fails with
# 0xC0000409 (no traceback) when its executable sits in a non-ASCII
# path. Refuse politely BEFORE the server import loads the frozen
# extension modules; inert in every non-frozen interpreter.
from covtl_console._launchguard import refuse_nonascii_bundle
refuse_nonascii_bundle()

from covtl_console.server import main                        # noqa: F401,E402
