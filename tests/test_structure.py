# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine structure tests — anchors, blocks, metrics (needs the engine).

These exercise ``server.structure_compile`` — the shared structural half
of the bridge used by both the syllable compiler panel and the synthesis
worker's early polar stage. No audio is produced here; the deep,
synthesis-backed 20-check series lives in ``anchor_rigor.py``.
"""
import pytest

pytest.importorskip("vtl_synth", reason="covtl-pipeline not installed")

WORKED_EXAMPLE = "Dis.iz.i.zi.fOR.@s"
RIGOR_PHRASES = [
    WORKED_EXAMPLE,
    "ba da ga | iowa a g",
    "bO~ZuR kOma~.a.le.vu",   # nasal vowels
    "pta.kli.pra",            # complex clusters
]


@pytest.fixture(scope="module")
def structures():
    import server as S
    return {text: S.structure_compile(text, "en") for text in RIGOR_PHRASES}


def test_worked_example_metrics(structures):
    """The brief's worked example: 11 anchors, 16 blocks, 6 syllable
    plateaus, 238 steps (2.38 s ± 1 step)."""
    st = structures[WORKED_EXAMPLE]
    m = st["metrics"]
    assert m["anchors"] == 11
    assert m["blocks"] == 16
    assert m["syllables"] == 6
    assert abs(m["steps"] - 238) <= 1
    assert abs(m["duration_s"] - 2.38) <= 0.011


def test_multi_phrase_anchor_count(structures):
    st = structures["ba da ga | iowa a g"]
    assert st["metrics"]["anchors"] == 22
    assert all(a["t"] >= 0 for a in st["anchors"])


def test_breath_input_has_breath_anchor():
    import server as S
    st = S.structure_compile("bonjour % comment allez vous", "fr")
    breath = [a for a in st["anchors"] if a.get("breath")]
    assert breath, "expected a '%' (breath) anchor in the anchor list"
    assert breath[0]["kind"] == "pause"


def test_geminate_shared_target_segment():
    """Shared-target configuration for the polar label suffix (the
    `i·n` checklist item, flash-validation PARTIAL 2026-11-04): within
    ONE journey (anchor pair) a phoneme key must appear twice so the
    display's label dedupe (polar.js — same key + same target position)
    renders `t·2` instead of two separate labels. A word-internal
    geminate produces exactly that: 'atta' walks a→a with a single
    cluster block carrying cons_keys ['t','t'] (VVV runs split across
    journeys — which is why no natural phrase of the campaign ever
    showed the suffix)."""
    import server as S
    st = S.structure_compile("atta", "en")
    anchors, blocks = st["anchors"], st["blocks"]
    hits = []
    for k in range(len(anchors) - 1):
        a0, a1 = anchors[k], anchors[k + 1]
        span = [b for b in blocks if b["t0"] < a1["t"] - 1e-9
                and b["t1"] > a0["t"] + 1e-9]
        keys: list = []
        for b in span:
            if b["kind"] == "plateau" and b.get("vowel_key"):
                keys.append(b["vowel_key"])
            keys.extend(b.get("cons_keys") or [])
        dups = {key for key in keys if keys.count(key) > 1}
        if dups:
            hits.append((k, a0["label"], a1["label"], sorted(dups)))
    assert hits, (
        "no journey of 'atta' carries a duplicated phoneme key — the "
        "shared-target label suffix has no data to count")
    assert any(d == ["t"] for _, _, _, d in hits), (
        f"expected the a->a geminate journey to duplicate 't': {hits}")


@pytest.mark.parametrize("text", RIGOR_PHRASES)
def test_structure_invariants(structures, text):
    """Anchor list sanity shared by every rigor phrase: non-decreasing
    times (phrase joints share t by design), 100 Hz grid, block timeline
    contiguous, metrics coherent."""
    st = structures[text]
    ts = [a["t"] for a in st["anchors"]]
    assert all(b >= a for a, b in zip(ts, ts[1:]))
    assert all(abs(t * 100 - round(t * 100)) < 1e-6 for t in ts)

    blocks = st["blocks"]
    step = 0
    for b in blocks:
        assert abs(b["t0"] - step / 100.0) < 1e-6
        step += b["n_steps"]
    assert step == st["metrics"]["steps"]

    m = st["metrics"]
    n_phrases = len(st["phrases"])
    assert m["segments"] == m["anchors"] - 1
    assert m["segments"] >= n_phrases
    assert m["syllables"] == sum(1 for b in blocks if b["kind"] == "plateau")
    assert m["vowels"] == sum(1 for n in st["nodes"] if n["kind"] == "V")
    assert abs(m["duration_s"] * 100 - m["steps"]) < 1e-6
