# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthesis job lifecycle tests — needs the engine; slow jobs are marked.

Covers the v3 contract: start-early polar ordering, on-disk artifacts,
display-degree segment payload, the exports flag, guard-422-before-job,
cache identity and the cancel path.
"""
import time
import uuid
import wave
from pathlib import Path

import pytest

pytest.importorskip("vtl_synth", reason="covtl-pipeline not installed")

POLL_S = 0.3
TIMEOUT_S = 300.0


def _unique_dir():
    return f"synth_{uuid.uuid4().hex[:6]}"


def _wait_done(S, job_id, timeout_s=TIMEOUT_S):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(POLL_S)
        job = S.JOBS[job_id]
        if job["state"] in ("done", "error", "cancelled"):
            return job
    raise TimeoutError(f"job {job_id} still running after {timeout_s}s")


def _run(client, **kw):
    payload = {
        "text": kw.pop("text", "ba da"),
        "mode": "phonetic", "lang": "en", "speaker": "jd3",
        "outputMode": "audio", "guardPolicy": "warn",
        "outputDir": kw.pop("outputDir", _unique_dir()),
    }
    payload.update(kw)
    r = client.post("/api/synthesize", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_start_early_polar_before_wav(client, S):
    """polar_ready must flip BEFORE wav_ready (start-early): poll at
    0.3 s intervals and assert the ordering event was observable."""
    out = _run(client, text="ba da ga | iowa a g")
    job_id = out["job_id"]
    saw_polar_only = False
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        time.sleep(POLL_S)
        job = S.JOBS[job_id]
        if job["polar_ready"] and not job["wav_ready"]:
            saw_polar_only = True
        if job["state"] in ("done", "error", "cancelled"):
            break
    job = S.JOBS[job_id]
    assert job["state"] == "done", f"job failed: {job.get('error')}"
    assert job["polar_ready"] and job["wav_ready"]
    assert saw_polar_only, \
        "start-early ordering not observed: polar_ready never preceded wav_ready"


def test_done_artifacts_and_payload(client, S):
    out = _run(client, text="Dis.iz.i.zi.fOR.@s")
    job_id = out["job_id"]
    job = _wait_done(S, job_id)
    assert job["state"] == "done", job.get("error")

    paths = job["paths"]
    for ext in ("wav", "txt", "tract", "polar"):
        key = next((k for k in paths if k.endswith(f".{ext}")), None)
        if key is None and ext == "polar":
            # the early-stage artifact registers under the literal key
            # "polar" (the display reads it); the engine's own export
            # lands as <stem>.polar
            key = "polar" if "polar" in paths else None
        assert key, f".{ext} artifact missing from job paths"
        assert Path(paths[key]).exists()

    # WAV duration ≈ structure duration (±40 ms audio quantization)
    wav_key = next(k for k in paths if k.endswith(".wav"))
    with wave.open(paths[wav_key], "rb") as w:
        wav_dur = w.getnframes() / w.getframerate()
    struct_dur = job["anchors"][-1]["t"]
    assert abs(wav_dur - struct_dur) < 0.04

    # segment payload: θ in display degrees (0–360, 0 = top), ρ ≤ 1
    r = client.get(f"/api/job/{job_id}/polar")
    assert r.status_code == 200
    payload = r.json()
    assert payload["sample_rate"] == 100
    assert 0 < payload["rho_max"]
    n_pts = n_c = 0
    for seg in payload["segments"]:
        assert seg["t1"] > seg["t0"] or seg["points"] == []
        for p in seg["points"]:
            if p["theta_v"] is not None:
                assert 0.0 <= p["theta_v"] < 360.0
                assert 0.0 <= p["rho_v"] <= 1.0
                n_pts += 1
            if p["theta_c"] is not None:
                assert 0.0 <= p["theta_c"] < 360.0
                assert 0.0 <= p["rho_c"] <= 1.0
                n_c += 1
    assert n_pts > 0, "vocalic branch points expected"
    assert n_c > 0, "consonantal branch points expected"

    # files are downloadable through the bridge
    files = job["result"]["files"]
    assert any(f["kind"] == "wav" for f in files)
    wav_name = next(f["name"] for f in files if f["kind"] == "wav")
    assert client.get(f"/api/job/{job_id}/files/{wav_name}").status_code == 200


def test_exports_false_limits_downloads(client, S):
    out = _run(client, text="ba da", exports=False)
    job = _wait_done(S, out["job_id"])
    assert job["state"] == "done", job.get("error")
    kinds = [f["kind"] for f in job["result"]["files"]]
    assert "wav" in kinds and "txt" in kinds
    assert "tract" not in kinds and "polar" not in kinds
    # the polar file stays registered for the display even when not offered
    assert any(k.endswith(".polar") or k == "polar" for k in job["paths"])


def test_exports_true_offers_tract_and_polar(client, S):
    out = _run(client, text="ba da", exports=True)
    job = _wait_done(S, out["job_id"])
    assert job["state"] == "done", job.get("error")
    kinds = [f["kind"] for f in job["result"]["files"]]
    assert {"wav", "txt", "tract", "polar"} <= set(kinds)


@pytest.mark.slow
def test_sagittal_mp4(client, S):
    out = _run(client, text="ba da", outputMode="sagittal", exports=True)
    job = _wait_done(S, out["job_id"], timeout_s=900.0)
    assert job["state"] == "done", job.get("error")
    kinds = [f["kind"] for f in job["result"]["files"]]
    assert "mp4" in kinds, f"MP4 not offered: {kinds}"
    mp4_key = next(k for k in job["paths"] if k.endswith(".mp4"))
    assert Path(job["paths"][mp4_key]).stat().st_size > 0


def test_guard_error_422_before_any_job(client, S):
    n_jobs = len(S.JOBS)
    r = client.post("/api/synthesize", json={
        "text": "cleanpan", "mode": "phonetic", "lang": "en",
        "guardPolicy": "error", "outputDir": _unique_dir()})
    assert r.status_code == 422
    assert r.json()["error"]["class"] == "SampaGuardError"
    assert len(S.JOBS) == n_jobs, "no job may start on a guard rejection"


def test_cache_hit_same_job_id(client, S):
    kw = {"text": "ba da", "outputDir": _unique_dir(), "label": "cachehit"}
    first = _run(client, **kw)
    job = _wait_done(S, first["job_id"])
    assert job["state"] == "done"
    second = _run(client, **kw)
    assert second["cached"] is True
    assert second["job_id"] == first["job_id"]


def test_cancel_queued_job(client, S):
    job_id = "cancelprobe1"
    S.JOBS[job_id] = {"id": job_id, "state": "queued", "stage": "g2p",
                      "progress": 0.0, "created": time.time(), "error": None,
                      "error_class": None, "error_hint": None, "result": None,
                      "cancelled": False, "cache_key": "probe", "echo": {},
                      "polar_ready": False, "wav_ready": False,
                      "anchors": None, "block_count": None, "structure": None,
                      "paths": {}}
    r = client.post(f"/api/job/{job_id}/cancel")
    assert r.status_code == 200
    assert r.json()["state"] == "cancelled"
    assert S.JOBS[job_id]["state"] == "cancelled"
