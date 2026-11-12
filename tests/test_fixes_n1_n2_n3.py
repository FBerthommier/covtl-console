# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for the N1/N2/N3 correction round (audit 2026-11-07).

N1 — the speaker parameter is now functional per request: unknown
      names are rejected (422, no job), and two registered speakers
      produce DIFFERENT audio through the bridge (before the fix all
      five were byte-identical jd3 audio).
N2 — server-side text bound (422 above MAX_SYNTH_CHARS = the UI's own
      2 000-char cap, no job started) and /api/health stays responsive
      while a synthesis runs (the VTL stage executes in a subprocess —
      the native synth_block holds the GIL and used to starve the
      server for the whole job).
N3 — an explicit label is validated (path separators/control chars/
      reserved names → 422, no job) and sanitized (glob metacharacters
      → '_'); files stay inside out/.
"""
import hashlib
import time
import uuid
import wave
from pathlib import Path

import pytest

from conftest import requires_engine


def _unique_dir():
    return f"fix_{uuid.uuid4().hex[:6]}"


def _wait_done(S, job_id, timeout_s=300.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(0.2)
        job = S.JOBS[job_id]
        if job["state"] in ("done", "error", "cancelled"):
            return job
    raise TimeoutError(f"job {job_id} still running after {timeout_s}s")


def _post(client, **kw):
    payload = {"text": kw.pop("text", "p a p a"), "mode": "phonetic",
               "lang": "en", "speaker": "jd3", "outputMode": "audio",
               "outputDir": kw.pop("outputDir", _unique_dir())}
    payload.update(kw)
    return client.post("/api/synthesize", json=payload)


# ──────────────────────────────────────────────────────────────────────
# N2 — text length bound
# ──────────────────────────────────────────────────────────────────────

def test_overlong_text_422_no_job(client, S):
    n_jobs = len(S.JOBS)
    r = _post(client, text="a" * (S.MAX_SYNTH_CHARS + 1))
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["class"] == "TextTooLong"
    assert str(S.MAX_SYNTH_CHARS) in body["error"]["message"]
    assert len(S.JOBS) == n_jobs, "no job may start on an overlong text"


def test_bound_matches_the_ui_cap(S):
    """The server bound equals the UI's client-side MAX_CHARS (app.js)
    — the API was the unguarded side (audit N2)."""
    ui = (Path(S.ASSETS) / "js" / "app.js").read_text(encoding="utf-8")
    m = __import__("re").search(r"const MAX_CHARS = (\d+);", ui)
    assert m, "UI MAX_CHARS not found"
    assert S.MAX_SYNTH_CHARS == int(m.group(1))


@pytest.mark.slow
def test_text_at_the_bound_is_accepted(client, S):
    """A text exactly at the bound passes the pre-flight (a full
    2 000-character synthesis takes minutes — hence the slow mark; it
    may still fail later in the engine for phonetic reasons, not our
    concern here; the 200 is what matters)."""
    r = _post(client, text="p a " * (S.MAX_SYNTH_CHARS // 4))
    assert r.status_code == 200, r.text
    job = _wait_done(S, r.json()["job_id"], timeout_s=900.0)
    assert job["state"] in ("done", "error"), job.get("error")


# ──────────────────────────────────────────────────────────────────────
# N1 — speaker validation + distinct audio
# ──────────────────────────────────────────────────────────────────────

@requires_engine
def test_unknown_speaker_422_no_job(client, S):
    """speaker='nobody' used to be silently accepted (200 + job done
    with jd3 audio — audit N1)."""
    n_jobs = len(S.JOBS)
    r = _post(client, speaker="nobody")
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["class"] == "UnknownSpeaker"
    assert "jd3" in body["error"]["message"]       # registered list shown
    assert len(S.JOBS) == n_jobs, "no job may start on an unknown speaker"


@requires_engine
def test_speaker_case_insensitive_accepted(client, S):
    r = _post(client, speaker="JD3", label="caseinsens")
    assert r.status_code == 200
    assert r.json()["echo"]["speaker"] == "jd3"    # canonicalized


@requires_engine
def test_speakers_endpoint_documents_layers(client):
    r = client.get("/api/speakers")
    assert r.status_code == 200
    body = r.json()
    assert body["speaker_layers"]["per_request"]
    assert body["speaker_layers"]["process_global"]
    assert body["speaker_layers"]["full_swap"].startswith("install_speaker")
    for s in body["speakers"]:
        assert s["per_request"] is True
        assert s["in_registry"] is True


@requires_engine
def test_echo_carries_speaker_note_when_not_active(client, S):
    """Requesting a speaker other than the installed one says WHICH
    layers follow the request (honesty — the geometry and audio
    anatomy stay with the installed speaker)."""
    from vtl_synth.core import speaker_registry as sr
    if sr.active_name() == "s1":
        pytest.skip("s1 is the active speaker on this machine")
    r = _post(client, speaker="s1", label="noteecho")
    assert r.status_code == 200
    echo = r.json()["echo"]
    assert echo["speaker"] == "s1"
    assert "orthogonal branch" in echo.get("speaker_note", "")
    job = _wait_done(S, r.json()["job_id"])
    assert job["state"] == "done", job.get("error")


@requires_engine
def test_two_speakers_distinct_audio(client, S):
    """Audit N1 acceptance criterion through the bridge: same phrase,
    two speakers → two DIFFERENT wav files (before the fix: identical
    bytes, SHA256 411c3daa… ×5)."""
    hashes = {}
    for spk in ("jd3", "s1"):
        r = _post(client, speaker=spk, label=f"spk{spk}",
                  outputDir=_unique_dir())
        assert r.status_code == 200, r.text
        job = _wait_done(S, r.json()["job_id"])
        assert job["state"] == "done", job.get("error")
        wav_key = next(k for k in job["paths"] if k.endswith(".wav"))
        with wave.open(job["paths"][wav_key], "rb") as w:
            hashes[spk] = (hashlib.sha256(
                w.readframes(w.getnframes())).hexdigest(),
                w.getframerate())
    assert hashes["jd3"][0] != hashes["s1"][0], \
        "identical audio across speakers (N1 regression)"


# ──────────────────────────────────────────────────────────────────────
# N2 — health responsiveness during a synthesis (subprocess isolation)
# ──────────────────────────────────────────────────────────────────────

@requires_engine
def test_health_responsive_during_synthesis(client, S):
    """The audit measured /api/health unresponsive for >= 30 s while a
    570-character synthesis ran in-process (GIL held by synth_block).
    The VTL stage now runs in a worker subprocess: health must answer
    in the sub-second range WHILE the job is running."""
    text = " ".join(["ba da ga"] * 12)            # ~140 chars
    r = _post(client, text=text, label="healthprobe")
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    latencies = []
    while S.JOBS[job_id]["state"] not in ("done", "error", "cancelled"):
        t0 = time.time()
        h = client.get("/api/health")
        latencies.append(time.time() - t0)
        assert h.status_code == 200
        assert h.json()["status"] == "ok"
        time.sleep(0.05)
    assert S.JOBS[job_id]["state"] == "done", S.JOBS[job_id].get("error")
    assert latencies, "job finished before any probe ran"
    assert max(latencies) < 2.0, (
        f"/api/health stalled {max(latencies):.1f}s during synthesis "
        "(N2 regression — subprocess isolation broken?)")
    # the synthesis really ran in the subprocess pool, not the fallback
    assert S._SYNTH_POOL is not None and not S._SYNTH_POOL_BROKEN
    notes = S.JOBS[job_id].get("notes") or []
    assert not any("in-process" in n for n in notes), notes


# ──────────────────────────────────────────────────────────────────────
# N3 — label validation + sanitization
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", [
    "..\\..\\trav_poc",          # audit D.1 — wrote outside out/ on Windows
    "../escape",
    "a/b",
    "a\\b",
    "C:ads",
    "x" * 65,                    # over the 64-char bound
    "CON",                       # Windows reserved device name
])
def test_bad_labels_422_no_job(client, S, label):
    n_jobs = len(S.JOBS)
    r = _post(client, label=label)
    assert r.status_code == 422, f"label {label!r} must be rejected"
    assert r.json()["error"]["class"] == "InvalidLabel"
    assert len(S.JOBS) == n_jobs, "no job may start on an invalid label"


def test_label_control_characters_422(client, S):
    n_jobs = len(S.JOBS)
    r = _post(client, label="bad\x00name")
    assert r.status_code == 422
    assert r.json()["error"]["class"] == "InvalidLabel"
    assert len(S.JOBS) == n_jobs


@requires_engine
def test_glob_metachar_label_sanitized(client, S):
    """A label like '*' must not expand in the post-run glob (it would
    offer every file of the output directory); unsafe characters map
    to '_' while dots stay (engine label_of semantics)."""
    r = _post(client, label="a*b?c")
    assert r.status_code == 200, r.text
    job = _wait_done(S, r.json()["job_id"])
    assert job["state"] == "done", job.get("error")
    assert job["result"]["label"] == "a_b_c"
    # every artifact of the job stayed inside its out/ subdirectory
    out_dir = Path(next(iter(job["paths"].values()))).parent
    assert out_dir.is_relative_to(Path(S.OUT_ROOT))
    for p in out_dir.glob("a_b_c.*"):
        assert p.parent == out_dir


@requires_engine
def test_dotted_label_still_works(client, S):
    """Dots in labels are legitimate (engine label_of keeps them -
    finding F1): 'v1.2' must reach disk unchanged."""
    r = _post(client, label="v1.2")
    assert r.status_code == 200
    job = _wait_done(S, r.json()["job_id"])
    assert job["state"] == "done", job.get("error")
    assert job["result"]["label"] == "v1.2"
    wav_key = next(k for k in job["paths"] if k.endswith(".wav"))
    assert Path(job["paths"][wav_key]).name == "v1.2.wav"


# ──────────────────────────────────────────────────────────────────────
# N5 — cosmetic audit findings (bridge version, lax preview/g2p,
# unbounded timings)
# ──────────────────────────────────────────────────────────────────────

def test_bridge_version_matches_package():
    """The bridge surface version must track the covtl-console package
    version (audit N5: the fields said 3.0.0 while the package is 3.1.x)."""
    from covtl_console import __version__ as pkg_version
    import covtl_console.server as _srv
    assert _srv.BRIDGE_VERSION == pkg_version


@pytest.mark.parametrize("timings", [
    {"tcons": -50},       # audit n15 — was silently accepted
    {"tvoy": 0},
    {"tpause": -1.5},
])
def test_nonpositive_timings_422_no_job(client, S, timings):
    n_jobs = len(S.JOBS)
    r = _post(client, timings=timings)
    assert r.status_code == 422, timings
    assert r.json()["error"]["class"] == "InvalidTimings"
    assert len(S.JOBS) == n_jobs, "no job may start on invalid timings"


def test_preview_g2p_empty_text_422(client):
    """The deprecated v1 endpoint used to answer 200 on an empty text
    (Optional field) while /api/synthesize rejects it — same contract."""
    r = client.post("/api/preview/g2p", json={"lang": "fr"})
    assert r.status_code == 422
    assert r.json()["error"]["class"] == "EmptyText"
    r = client.post("/api/preview/g2p", json={"text": "   ", "lang": "fr"})
    assert r.status_code == 422
