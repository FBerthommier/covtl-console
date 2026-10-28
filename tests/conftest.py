# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures for the covtl-console test suite.

The suite runs green against a machine with covtl-pipeline installed and
degrades honestly without it: engine-required tests skip with an explicit
reason, packaging/static tests keep running.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENGINE_AVAILABLE = importlib.util.find_spec("vtl_synth") is not None

requires_engine = pytest.mark.skipif(
    not ENGINE_AVAILABLE,
    reason="covtl-pipeline (vtl_synth) not installed in this interpreter — "
           "engine-required tests skip; see README §Installation")


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient over the bridge app (same process, no server)."""
    from fastapi.testclient import TestClient
    import server as S
    with TestClient(S.app) as c:
        yield c


@pytest.fixture(scope="session")
def S():
    """The bridge module (jobs dict, models, helpers) for direct inspection."""
    import server as server_module
    return server_module
