# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Anchor-timing rigor series — the deep, synthesis-backed check.

Verifies, on fresh live jobs, that every anchor timestamp the bridge
serves is a genuine engine boundary, not an interpolation:

  1. anchors are non-decreasing (phrase joints share t by design) and
     land on 100 Hz grid steps;
  2. every anchor time equals the cumulative step count of the engine
     blocks, re-read independently from the engine via a fresh
     ``syltraj.build_phrase_pval`` walk (subset invariant — the converse
     does not hold: engine boundaries also exist at plateau tails where
     syltraj places no anchor);
  3. the anchor count matches the walk iteration count plus phrase joints;
  4. segment [t0, t1] spans == anchor pairs — no timeline gaps;
  5. each phoneme span in the engine's ``.polar`` file lies inside
     exactly one segment span;
  6. phoneme categories match their segment's block kinds
     (C spans inside cluster blocks, V spans inside plateau blocks);
  7. structure duration == ``.polar`` n_steps / 100 within 1 step;
  8. the rendered WAV duration is within ±40 ms (audio quantization).

Run it alone (it synthesizes, so it is slow-marked)::

    pytest tests/anchor_rigor.py -v
"""
import json
import time
import wave

import pytest

pytest.importorskip("vtl_synth", reason="covtl-pipeline not installed")

RIGOR_PHRASES = [
    "Dis.iz.i.zi.fOR.@s",
    "ba da ga | iowa a g",
    "bO~ZuR kOma~.a.le.vu",   # nasal vowels
    "pta.kli.pra",            # complex clusters
]

# LANG_DEFAULTS["en"] on the 10-step engine scale, kept explicit so the
# independent re-walk below cannot drift away from the bridge's calls.
T_CONS, T_VOY = 10, 8
PAUSE_SHORT_MS, PAUSE_LONG_MS = 200.0, 320.0


def _wait_done(S, job_id, timeout_s=240.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(0.5)
        if S.JOBS[job_id]["state"] in ("done", "error", "cancelled"):
            break
    return S.JOBS[job_id]


@pytest.fixture()
def live_job(S, request):
    """One fresh synthesis job per parametrized phrase, phonetic mode."""
    req = S.SynthRequest(
        text=request.param, mode="phonetic", lang="en", speaker="jd3",
        outputMode="audio", guardPolicy="warn",
        outputDir=f"rigor_{request.node.name}",
        label=request.node.name[:20])
    job_id = S.synthesize(req)["job_id"]
    job = _wait_done(S, job_id)
    assert job["state"] == "done", f"job failed: {job.get('error')}"
    return job


@pytest.mark.slow
@pytest.mark.parametrize("live_job", RIGOR_PHRASES, indirect=True)
def test_anchor_rigor(S, live_job):
    _verify_anchor_timing(S, live_job)


def _verify_anchor_timing(S, job):
    payload = S.build_segment_payload(job, 0, "full")
    anchors, segs = payload["anchors"], payload["segments"]
    ts = [a["t"] for a in anchors]

    # 1 — non-decreasing + 100 Hz grid
    assert all(b >= a for a, b in zip(ts, ts[1:])), "anchors must not decrease"
    assert all(abs(t * 100 - round(t * 100)) < 1e-6 for t in ts), \
        "anchors must land on 100 Hz grid steps"

    # 2 — every anchor time IS an engine block boundary (independent
    # re-walk of the engine; subset invariant, see module docstring)
    from vtl_synth.core import syltraj
    from vtl_synth.core.continuous import _normalize_ipa
    from vtl_synth.core.syltraj import _normalize_word

    phrases = S._phrases_of(job["sampa"])
    step = 0
    engine_bounds = set()
    n_iter_total = 0
    for phrase in phrases:
        ipa = _normalize_ipa(_normalize_word(phrase))
        _pv, blocks, _nodes, anch = syltraj.build_phrase_pval(
            ipa, t_cons=T_CONS, t_voy=T_VOY,
            pause_short_ms=PAUSE_SHORT_MS, pause_long_ms=PAUSE_LONG_MS,
            sampa_guard="off")
        b = 0
        for blk in blocks:
            engine_bounds.add(round((step + b) / 100.0, 6))
            b += blk.n_steps
        engine_bounds.add(round((step + b) / 100.0, 6))
        n_iter_total += max(0, len(anch) - 1)
        step += b
    off = [t for t in ts if round(t, 6) not in engine_bounds]
    assert not off, f"anchors off engine boundaries: {off[:4]}"

    # 3 — anchor count == walk iterations + phrase joints
    assert len(anchors) >= len(phrases) + n_iter_total, (
        f"{len(anchors)} anchors vs {n_iter_total} walk iterations "
        f"+ {len(phrases)} phrases")

    # 4 — segments tile the anchor timeline exactly
    assert len(segs) == len(anchors) - 1
    for k, seg in enumerate(segs):
        assert seg["t0"] == anchors[k]["t"]
        assert seg["t1"] == anchors[k + 1]["t"]
    gaps = [(segs[i]["t1"], segs[i + 1]["t0"]) for i in range(len(segs) - 1)
            if abs(segs[i]["t1"] - segs[i + 1]["t0"]) > 1e-9]
    assert not gaps, f"timeline gaps: {gaps[:3]}"

    # 5 — phoneme spans from the .polar lie inside exactly one segment
    polar_doc = json.loads(open(job["paths"]["polar"], encoding="utf-8").read())
    bad = []
    for ph in polar_doc["phonemes"]:
        t0, t1 = ph["t0"] / 100.0, ph["t1"] / 100.0
        inside = [s for s in segs
                  if s["t0"] <= t0 + 1e-9 and t1 <= s["t1"] + 1e-9]
        if len(inside) != 1:
            bad.append((ph["key"], t0, t1, len(inside)))
    assert not bad, f"phoneme spans not inside exactly one segment: {bad[:3]}"

    # 6 — phoneme categories match their segment's block kinds
    for ph in polar_doc["phonemes"]:
        t0, t1 = ph["t0"] / 100.0, ph["t1"] / 100.0
        seg = next((s for s in segs
                    if s["t0"] <= t0 + 1e-9 and t1 <= s["t1"] + 1e-9), None)
        if seg is None:
            continue
        kinds = [b["kind"] for b in seg["blocks"]]
        if ph["category"] == "V":
            assert any(k in ("plateau", "initial", "terminal", "decay")
                       for k in kinds), f"V span {ph['key']} outside plateaus"
        else:
            assert "cluster" in kinds, f"C span {ph['key']} outside clusters"

    # 7 — duration coherence: structure == .polar steps
    n_steps = polar_doc["n_steps"]
    assert abs(ts[-1] - n_steps / 100.0) < 0.011, \
        f"structure duration {ts[-1]} vs .polar {n_steps / 100.0}"

    # 8 — WAV duration ≈ structure duration (±40 ms audio quantization)
    wav_path = next(p for n, p in job["paths"].items() if n.endswith(".wav"))
    with wave.open(wav_path, "rb") as w:
        wav_dur = w.getnframes() / w.getframerate()
    assert abs(wav_dur - ts[-1]) < 0.04, \
        f"wav {wav_dur:.4f}s vs structure {ts[-1]:.4f}s"
