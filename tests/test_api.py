# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP surface tests — FastAPI TestClient over the bridge app.

Static/transport tests run without the engine; the preview/compile
behavior tests need covtl-pipeline installed (they skip honestly
otherwise, with the reason carried by the ``requires_engine`` marker).
"""
import pytest

from conftest import ENGINE_AVAILABLE, requires_engine

JS_MODULES = ["data", "render", "api", "polar", "spectrogram",
              "compiler", "app"]

# The bridge version literals follow the package version (audit §1/N5
# drift); every version assertion in the suite compares against it.
from covtl_console import __version__ as BRIDGE_VERSION


# ── always-on: static assets, transport headers ────────────────────────
def test_status_shape(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["bridge"] == BRIDGE_VERSION
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
    assert body["bridge"] == BRIDGE_VERSION
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
    notations = [s["notation"] for s in body["segments_preview"]]
    assert notations == ['▸·i*', 'i*·D·i', 'i·s·i', 'i·z·i', 'i·z·i',
                         'i·f·O', 'O·R·@', '@·s·@*', '@*·␣', '␣·◂'], notations
    times = [(s["t0"], s["t1"]) for s in body["segments_preview"]]
    assert times == sorted(times), "tile labels must be chronological"
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
def test_compile_labels_nasal_hiatus(client):
    """V~.V hiatus: handled engine-side since the V1V2 fix (nasal_preproc);
    the plan keeps the hiatus as a background stretch LABELED with its
    vowels instead of a bare '-'."""
    r = client.post("/api/compile", json={
        "text": "kOma~.a.le.vu", "lang": "fr"})
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    backgrounds = [b for b in blocks if b["kind"] == "background"]
    assert backgrounds, "the hiatus background arc is expected in the plan"
    hiatus = [b.get("hiatus") for b in backgrounds if b.get("hiatus")]
    assert hiatus and any("a~" in h for h in hiatus), blocks
    notations = [s["notation"] for s in r.json()["segments_preview"]]
    # the plan keeps ORAL bases: the a~→a hiatus tile reads 'a·a' (the '~'
    # lives in the audio VO gate, not in the notation); the hiatus label
    # itself stays on the background block (asserted above)
    assert 'a·a' in notations, notations


@requires_engine
def test_compile_labels_merged_nasal_hiatus(client):
    """V~.V~ (both members nasal): nasal_hiatus_intervals MERGES the two
    adjacent nasal slots into one velar-open interval keyed on the oral
    bases ('a+a') — the label must still show the nasal notation of the
    run (a~.a~), never the merged key."""
    r = client.post("/api/compile", json={
        "text": "ta~.a~ta", "lang": "fr"})
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    hiatus = [b.get("hiatus") for b in blocks
              if b["kind"] == "background" and b.get("hiatus")]
    assert hiatus == ["a~.a~"], blocks
    notations = [s["notation"] for s in r.json()["segments_preview"]]
    # merged hiatus tile: background a~.a~→a reads 'a·a' (oral bases)
    assert 'a·a' in notations, notations


@requires_engine
def test_compile_h_pairs_labels(client):
    """The three H-pair hiatus typologies label the background arc with
    the run's nasal notation in every direction."""
    for text, want in (("ta~.ata", "a~.a"), ("ta.a~ta", "a.a~")):
        r = client.post("/api/compile", json={"text": text, "lang": "fr"})
        assert r.status_code == 200
        hiatus = [b.get("hiatus") for b in r.json()["blocks"]
                  if b["kind"] == "background" and b.get("hiatus")]
        assert hiatus == [want], (text, r.json()["blocks"])


@requires_engine
def test_sandhi_capability_in_status_and_health(client):
    """The bridge exposes its covtl-sandhi capability (Branch A hook +
    Branch B rule package state) on /api/status and /api/health — the UI
    derives its controls from it."""
    for path in ("/api/status", "/api/health"):
        r = client.get(path)
        assert r.status_code == 200
        cap = r.json()["sandhi"]
        assert isinstance(cap["available"], bool)
        assert "off" in cap["levels"]
        assert "g2p" in cap["modes"]


@requires_engine
def test_preview_sandhi_degrades_without_branch_b(client, monkeypatch):
    """Without the rule package a requested level degrades to off with a
    clear warning — the SAMPA stays the plain G2P output (never a
    silent change, never a crash). The degradation state is forced
    hermetically: this test holds whether or not covtl-sandhi is
    installed on the host."""
    import server
    monkeypatch.setattr(server, "SANDHI", None)
    base = client.post("/api/preview", json={
        "text": "faut il", "mode": "ortho", "lang": "fr"}).json()
    r = client.post("/api/preview", json={
        "text": "faut il", "mode": "ortho", "lang": "fr",
        "sandhi": "standard", "sandhi_mode": "g2p"})
    assert r.status_code == 200
    body = r.json()
    assert body["final_sampa"] == base["final_sampa"], \
        "without Branch B the level must be a no-op on the SAMPA"
    assert any("covtl-sandhi" in w for w in body["warnings"]), body["warnings"]
    assert not body["cache"] and base.get("cache") in (False, True)


@requires_engine
def test_preview_sandhi_fr_liaison_fires(client):
    """With the covtl-sandhi rule package installed, the standard level
    really applies French liaison through the preview's G2P gateway
    (skipped on bridges without the package — CI installs the bare
    engine)."""
    import server
    if server.SANDHI is None:
        pytest.skip("covtl-sandhi rule package (Branch B) not installed")
    r = client.post("/api/preview", json={
        "text": "faut il", "mode": "ortho", "lang": "fr",
        "sandhi": "standard", "sandhi_mode": "g2p"})
    assert r.status_code == 200
    assert r.json()["final_sampa"] == "fo.til", r.json()["final_sampa"]
    assert not any("covtl-sandhi" in w for w in r.json()["warnings"])


@requires_engine
def test_preview_sandhi_invalid_level_422(client):
    r = client.post("/api/preview", json={
        "text": "hello", "mode": "ortho", "lang": "en", "sandhi": "bogus"})
    assert r.status_code == 422
    r2 = client.post("/api/preview", json={
        "text": "hello", "mode": "ortho", "lang": "en", "sandhi_mode": "bogus"})
    assert r2.status_code == 422


@requires_engine
def test_preview_sandhi_ignored_on_phonetic(client):
    """Phonetic SAMPA carries no orthography — a requested level is
    ignored with a warning, mirroring Pipeline.run."""
    r = client.post("/api/preview", json={
        "text": "ta ta", "mode": "phonetic", "lang": "en",
        "sandhi": "standard"})
    assert r.status_code == 200
    assert any("ignored" in w for w in r.json()["warnings"])


@requires_engine
def test_compile_sandhi_level_warns_noop(client):
    """The compiler consumes SAMPA blocks: a sandhi level is a documented
    no-op there (the level acts at the text→SAMPA stage)."""
    r = client.post("/api/compile", json={
        "text": "ta.ta", "lang": "en", "sandhi": "standard"})
    assert r.status_code == 200
    assert any("text→SAMPA" in w for w in r.json()["warnings"])
    assert r.json()["sandhi"]["levels"]  # capability carried for the UI


@requires_engine
def test_error_envelope_shape(client):
    r = client.post("/api/compile", json={
        "text": "cleanpan", "lang": "en", "guard_policy": "error"})
    body = r.json()
    assert "detail" in body                       # v1 compat field
    assert {"class", "message", "hint", "symbols"} <= set(body["error"])
