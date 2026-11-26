"""Console plumbing of the display_schwa_route toggle (schwa audit
2026-11-24, rectification audit 2026-11-26).

The toggle is DISPLAY-ONLY by contract: the payload is accepted by
CompileRequest / SynthRequest (default False), forwarded to the engine's
polar builder, cached separately per flag state, and never changes the
audio or the engine treatment (which is unconditional).

Since the 2026-11-26 engine audit, closing VV arcs (« buib », u→i) keep
their DIRECT path with a probe-tuned TCY/TBY rectification toward the
schwa values — the two-leg dep → @ → arr routing survives only as the
engine FALLBACK (when no rectification amplitude opens the corridor):

  - ON, nominal (rectified arc): the compiled polar payload draws the
    direct family arc — no π crossing (theta_v = 270 display degrees),
    same as OFF. The rectification stays below polar-path resolution.
  - ON, fallback (engine forced with a closing stub): the routed
    dep → @ → arr legs — the vocalic trajectory passes through the
    schwa waypoint, whose payload coordinates are theta_v = 270
    (display degrees of the π meridian) at rho_v = 0.580 / rho_max.
  - OFF (default): the legacy direct arc — no π crossing (the direct
    u→i chord sweeps through 0°, display 90°).

Engine-required: skipped when covtl-pipeline is not importable; the
routed-geometry assertions need a polar builder that knows the toggle
(engine main after the audit) and skip honestly otherwise.
"""
import numpy as np
import pytest

pytest.importorskip("vtl_synth")

from covtl_console import server  # noqa: E402


def _rho_at_pi_crossing(polar_payload):
    """Normalized rho at the closest π-meridian (theta_v = 270) point,
    or None when the trajectory never comes near it."""
    if not polar_payload:
        return None
    th, rh = [], []
    for seg in polar_payload["segments"]:
        for p in seg["points"]:
            if p["theta_v"] is not None and p["rho_v"] is not None:
                th.append(p["theta_v"])
                rh.append(p["rho_v"])
    if not th:
        return None
    th, rh = np.asarray(th), np.asarray(rh)
    i = int(np.argmin(np.abs(th - 270.0)))
    if abs(th[i] - 270.0) > 0.05:      # display degrees, 2-decimal round
        return None
    return float(rh[i])


def _schwa_toggle_known():
    """True when the installed engine's polar builder accepts the flag."""
    import inspect
    from vtl_synth.video.polar_video import build_polar
    return ("display_schwa_route"
            in inspect.signature(build_polar).parameters)


def test_requests_accept_toggle_default_off():
    assert server.CompileRequest(text="buib").display_schwa_route is False
    assert server.SynthRequest(text="ba").display_schwa_route is False
    assert server.SynthRequest(
        text="ba", display_schwa_route=True).display_schwa_route is True


def test_synth_cache_key_separates_toggle():
    k_off = server.synth_key(server.SynthRequest(text="ba da"))
    k_on = server.synth_key(
        server.SynthRequest(text="ba da", display_schwa_route=True))
    # same audio, different .polar payload — two cache entries, never a
    # shared job (the drawn trajectory would be wrong for one of them)
    assert k_off != k_on


def test_compile_polar_rectified_when_on():
    """ON, nominal: the rectified arc (audit 2026-11-26) stays on the
    direct family path — no π crossing, like OFF (the TCY/TBY
    rectification is below polar-path resolution)."""
    if not _schwa_toggle_known():
        pytest.skip("engine predates the schwa display toggle")
    r = server.compile_blocks(server.CompileRequest(
        text="buib", lang="en", display_schwa_route=True))
    assert _rho_at_pi_crossing(r["polar"]) is None, \
        "rectified display keeps the direct family arc (no pi crossing)"


def test_compile_polar_fallback_route_when_on(monkeypatch):
    """ON, fallback: an always-closing probe forces the two-leg
    routing — the trajectory passes exactly through the schwa
    waypoint (rho 0.580 at the π meridian, display 270°)."""
    if not _schwa_toggle_known():
        pytest.skip("engine predates the schwa display toggle")
    from vtl_synth.video import polar_video as pv

    def _closing_probe(block):
        return 0.0

    monkeypatch.setattr(pv, '_vv_probe', lambda: _closing_probe)
    r = server.compile_blocks(server.CompileRequest(
        text="buib", lang="en", display_schwa_route=True))
    rho = _rho_at_pi_crossing(r["polar"])
    assert rho is not None, "fallback routing must pass through pi/270"
    # payload rho is normalized by rho_max (>= 1.45); the waypoint radius
    # 0.580 lands at 0.580 / rho_max — compare against the payload's own
    # normalization
    assert rho == pytest.approx(0.580 / r["polar"]["rho_max"], abs=1e-3)


def test_compile_polar_direct_by_default():
    if not _schwa_toggle_known():
        pytest.skip("engine predates the schwa display toggle")
    r = server.compile_blocks(server.CompileRequest(text="buib", lang="en"))
    assert _rho_at_pi_crossing(r["polar"]) is None, \
        "default OFF draws the legacy direct arc (no pi crossing)"
