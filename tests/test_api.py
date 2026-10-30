# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP surface tests — FastAPI TestClient over the bridge app.

Static/transport tests run without the engine; the preview/compile
behavior tests need covtl-pipeline installed (they skip honestly
otherwise, with the reason carried by the ``requires_engine`` marker).
"""
import pytest

from conftest import ENGINE_AVAILABLE, requires_engine

JS_MODULES = ["data", "demo-engine", "render", "api", "polar", "spectrogram",
              "compiler", "app"]


# ── always-on: static assets, transport headers ────────────────────────
def test_status_shape(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["bridge"] == "3.0.0"
    assert body["engine"] == "vtl-synth"
    assert body["backend"] in ("live", "mock")
    if ENGINE_AVAILABLE:
        assert body["backend"] == "live"
    import pathlib
    p = pathlib.Path(body["out_root"])
    assert p.is_absolute() and p.exists(), "out_root must be the resolved absolute path"
    digest = body["inventory_digest"]
    assert {"vowels", "consonants", "markers", "count"} <= set(digest)


def test_health_shape(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded", "offline")
    assert body["bridge"] == "3.0.0"
    if ENGINE_AVAILABLE:
        assert body["status"] in ("ok", "degraded")
        assert body["engine_version"]


def test_languages_six(client):
    r = client.get("/api/languages")
    assert r.status_code == 200
    langs = r.json()["languages"]
    assert len(langs) == 6
    assert {l["id"] for l in langs} == {"en", "fr", "es", "de", "it", "pt"}


def test_speakers_unverified_warning(client):
    r = client.get("/api/speakers", params={"lang": "fr"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["speakers"]) >= 3
    assert body["calibration_speaker"] == "jd3"
    assert body["warning_when_unverified"], \
        "non-English language must carry the unverified-combination warning"


def test_cache_control_no_cache(client):
    for path in ("/", "/js/app.js", "/css/app.css"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers.get("cache-control") == "no-cache", path


def test_static_assets_all_modules(client):
    for name in JS_MODULES:
        r = client.get(f"/js/{name}.js")
        assert r.status_code == 200, name
    assert client.get("/index.html").status_code == 200


def test_unknown_job_404(client):
    assert client.get("/api/job/doesnotexist").status_code == 404
    assert client.get("/api/job/doesnotexist/polar").status_code == 404


# ── engine-backed: preview / compile behavior ──────────────────────────
@requires_engine
def test_preview_ortho_worked_example(client):
    r = client.post("/api/preview", json={
        "text": "this is easy for us", "mode": "ortho", "lang": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["final_sampa"] == "Dis.iz.i.zi.fOR.@s"
    assert body["g2p_string"] == "Dis.iz.i.zi.fOR.@s"
    assert body["rejected_symbols"] == []
    assert body["cache"] is False


@requires_engine
def test_preview_ortho_cache_hit(client):
    payload = {"text": "this is easy for us", "mode": "ortho", "lang": "en"}
    client.post("/api/preview", json=payload)
    r = client.post("/api/preview", json=payload)
    assert r.status_code == 200
    assert r.json()["cache"] is True


@requires_engine
def test_preview_phonetic_guard_rejects_c(client):
    r = client.post("/api/preview", json={
        "text": "cleanpan", "mode": "phonetic", "lang": "en"})
    assert r.status_code == 200
    rejected = r.json()["rejected_symbols"]
    c_rej = [x for x in rejected if x["symbol"] == "c"]
    assert c_rej, "the 'c' in cleanpan must be rejected"
    assert c_rej[0]["suggestions"] == ["k", "s"]


@requires_engine
def test_compile_metrics_and_stretches(client):
    r = client.post("/api/compile", json={
        "text": "Dis.iz.i.zi.fOR.@s", "lang": "en"})
    assert r.status_code == 200
    body = r.json()
    m = body["metrics"]
    assert m["anchors"] == 11
    assert m["anchors"] == m["segments"] + 1
    stretches = [s["stretch"] for s in body["segments_preview"]]
    assert any("‿" in s for s in stretches), \
        "coda stretches must carry the ‿ coarticulation marker"
    times = [(s["t0"], s["t1"]) for s in body["segments_preview"]]
    assert times == sorted(times), "stretch labels must be chronological"
    assert body["targets"], "per-phoneme polar targets expected"


@requires_engine
def test_compile_cache_hit(client):
    payload = {"text": "Dis.iz.i.zi.fOR.@s", "lang": "en"}
    client.post("/api/compile", json=payload)
    r = client.post("/api/compile", json=payload)
    assert r.status_code == 200
    assert r.json()["cache"] is True


@requires_engine
def test_compile_guard_error_422(client):
    r = client.post("/api/compile", json={
        "text": "cleanpan", "lang": "en", "guard_policy": "error"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["class"] == "SampaGuardError"
    assert any(s["symbol"] == "c" for s in err["symbols"])


@requires_engine
def test_compile_warns_on_nasal_link(client):
    """Hand-written V~.V is dropped by the syltraj walk (engine limitation,
    kept on record): /api/compile must warn about it."""
    r = client.post("/api/compile", json={
        "text": "kOma~.a.le.vu", "lang": "fr"})
    assert r.status_code == 200
    warnings = r.json()["warnings"]
    assert any("V~.V" in w for w in warnings), warnings
    # and the plan indeed lacks the nasal vowel (background block instead)
    vowels = [b["vowel_key"] for b in r.json()["blocks"] if b["kind"] == "plateau"]
    assert "a~" not in vowels


@requires_engine
def test_preview_warns_on_nasal_link(client):
    r = client.post("/api/preview", json={
        "text": "kOma~.a.le.vu", "mode": "phonetic", "lang": "fr"})
    assert r.status_code == 200
    assert any("V~.V" in w for w in r.json()["warnings"])


@requires_engine
def test_error_envelope_shape(client):
    r = client.post("/api/compile", json={
        "text": "cleanpan", "lang": "en", "guard_policy": "error"})
    body = r.json()
    assert "detail" in body                       # v1 compat field
    assert {"class", "message", "hint", "symbols"} <= set(body["error"])
