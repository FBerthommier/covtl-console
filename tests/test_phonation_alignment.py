# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Phonation alignment tests (wave 5, P1.3): the bridge consumes the
engine's 1.2.0 phonation API correctly.

The engine exposes the phonation modes through
``Pipeline(tag_overrides={'*': {'voicing': 'breathy'}})`` (whole-phrase
wildcard, wave 5; per-key dicts on plain 1.2.0). The bridge's SynthRequest
carries a ``phonation`` field, the worker maps it to the wildcard
override, the cache key and the echo reflect it. These tests lock the
bridge side of that contract against the installed engine — they skip
with an explicit reason when the engine is absent (same policy as the
rest of the suite) or predates 1.2.0.
"""
import importlib.util

import pytest

ENGINE_AVAILABLE = importlib.util.find_spec("vtl_synth") is not None

requires_engine = pytest.mark.skipif(
    not ENGINE_AVAILABLE,
    reason="covtl-pipeline (vtl_synth) not installed in this interpreter")

PHONATION_MODES = ("breathy", "creaky", "whisper")


def _engine_supports_wildcard():
    """The '*' tag-override key landed after 1.2.0 (wave 5); the
    console maps its phonation selector onto it. On a plain-1.2.0
    engine the wildcard is a no-op — detect honestly instead of
    asserting a silently-degraded path."""
    try:
        from vtl_synth.core.tag_system import TagInterpreter
        from vtl_synth.core.prosody_source import Segment
    except Exception:
        return False
    ti = TagInterpreter(tag_overrides={'*': {'voicing': 'whisper'}})
    seg = ti.apply(Segment(key='a', kind='V', t_start=0, t_end=90))
    return seg.glottal_tag == 'whisper'


def test_synthesize_request_has_phonation_field():
    """The SynthRequest model carries the phonation field with the
    four documented modes (no engine needed — pydantic only)."""
    from covtl_console.server import SynthRequest
    req = SynthRequest(text="this is easy for us")
    assert req.phonation == "normal"
    for m in PHONATION_MODES:
        assert SynthRequest(text="ba", phonation=m).phonation == m


def test_synth_key_includes_phonation():
    """Two requests differing only by phonation must NOT share a
    cache entry (the modes produce different audio)."""
    from covtl_console.server import SynthRequest, synth_key
    a = synth_key(SynthRequest(text="ba", phonation="normal"))
    b = synth_key(SynthRequest(text="ba", phonation="breathy"))
    c = synth_key(SynthRequest(text="ba", phonation="breathy"))
    assert a != b and b == c


@requires_engine
@pytest.mark.skipif(not _engine_supports_wildcard(),
                    reason="installed engine predates the '*' wildcard "
                           "(wave 5) — the selector would silently "
                           "degrade to normal")
@pytest.mark.parametrize("mode", PHONATION_MODES)
def test_worker_maps_phonation_to_wildcard_override(mode, S, monkeypatch):
    """The worker builds Pipeline(tag_overrides={'*': {'voicing':
    <mode>}}) from SynthRequest.phonation — locked by intercepting
    the payload handed to the synthesis subprocess."""
    from covtl_console.server import SynthRequest

    captured = {}

    class _FakeResult(dict):
        pass

    def fake_stage2(payload, job):
        captured.update(payload["pipeline"])
        return _FakeResult(stem="probe", sampa="ba", wav_path=None,
                           duration_s=0.0, n_frames=0, tract_path=None,
                           polar_path=None, mp4_path=None, warnings=[])

    monkeypatch.setattr(S, "_run_stage2", fake_stage2)
    req = SynthRequest(text="ba", mode="phonetic", phonation=mode,
                       outputMode="audio", exports=False)
    S.JOBS["job-phonation-probe"] = {
        "id": "job-phonation-probe", "state": "queued", "stage": "g2p",
        "progress": 0.0, "created": 0.0, "error": None,
        "error_class": None, "error_hint": None, "result": None,
        "cancelled": False, "cache_key": None, "echo": {},
        "polar_ready": False, "wav_ready": False, "anchors": None,
        "block_count": None, "structure": None, "notes": []}
    S._worker("job-phonation-probe", req, safe_label="probe")
    assert captured.get("tag_overrides") == {"*": {"voicing": mode}}


@requires_engine
def test_worker_normal_mode_sends_no_override(S, monkeypatch):
    """phonation='normal' (default) must NOT set tag_overrides — the
    nominal chain stays bit-identical to the pre-wave-5 behaviour."""
    from covtl_console.server import SynthRequest

    captured = {}

    def fake_stage2(payload, job):
        captured.update(payload["pipeline"])
        return dict(stem="probe", sampa="ba", wav_path=None,
                    duration_s=0.0, n_frames=0, tract_path=None,
                    polar_path=None, mp4_path=None, warnings=[])

    monkeypatch.setattr(S, "_run_stage2", fake_stage2)
    req = SynthRequest(text="ba", mode="phonetic", outputMode="audio",
                       exports=False)
    S.JOBS["job-phonation-probe-2"] = {
        "id": "job-phonation-probe-2", "state": "queued", "stage": "g2p",
        "progress": 0.0, "created": 0.0, "error": None,
        "error_class": None, "error_hint": None, "result": None,
        "cancelled": False, "cache_key": None, "echo": {},
        "polar_ready": False, "wav_ready": False, "anchors": None,
        "block_count": None, "structure": None, "notes": []}
    S._worker("job-phonation-probe-2", req, safe_label="probe")
    assert "tag_overrides" not in captured


def test_ui_carries_phonation_selector():
    """The UI exposes the selector and app.js forwards it in the
    synth payload + persists it (static source checks — no browser)."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    html = (root / "covtl_console" / "ui" / "index.html").read_text(
        encoding="utf-8")
    js = (root / "covtl_console" / "ui" / "js" / "app.js").read_text(
        encoding="utf-8")
    assert 'id="sel-phonation"' in html
    for mode in PHONATION_MODES:
        assert f'value="{mode}"' in html
    assert "phonation: 'normal'" in js                    # state default
    assert "phonation: state.phonation" in js             # synth payload
    assert "state.phonation = e.target.value" in js       # listener
    assert "'phonation'" in js                            # settings loop
