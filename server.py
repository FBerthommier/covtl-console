#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""COVTL Console v3 — local FastAPI bridge for covtl-pipeline.

Implements the COVTL Lab Console design brief (October 2026) on top of the
v2 bridge: the Python engine stays the single source of truth, and the
continuous polar display consumes the *real* syltraj structure — anchors,
anchor-to-anchor segments, dissociated vocalic/consonantal branches — never
a re-segmentation invented by the UI.

v3 changes over v2 (see CHANGES_v3.md for the full record):
  * Continuous polar data model (brief ch. 6 / annex A.4):
      - the synthesis worker builds the trajectory structure FIRST
        (anchors + blocks + .polar file, cheap pure-Python stage) so
        polar_ready flips before the VTL/WAV stage → the display can
        start on its own clock ("start-early", honest: same engine data);
      - GET /api/job/{id}/polar returns the segment payload:
        anchors[{i,t,label,kind}], segments[{segment_index, t0, t1,
        anchor_from/to, markers, points[{t, rho_v, theta_v, rho_c,
        theta_c}]}] at 100 Hz, θ pre-converted to the display convention
        (0° top, clockwise) and ρ normalized 0..1 over the job's radius
        range (rho_max carried in the payload).
  * Anchor timestamps come from an instrumented replay of
    syltraj.build_phrase_pval (the SylBlock constructor + the
    _collect_consonants call mark anchor-pair boundaries — the same
    monkeypatch idiom as vtl_synth.video.polar_video) with hard drift
    checks that raise if the engine's walk ever changes shape.
  * POST /api/compile — the syllable block compiler (eml-formalization
    inspired): SAMPA syllable blocks → engine structure (anchors, blocks,
    per-phoneme polar targets, metrics) without any synthesis.
  * Brief endpoints: GET /api/health, /api/languages, /api/speakers
    (registry metadata + unverified-combination warning), job payloads
    with stage/progress/polar_ready/wav_ready/anchors/block_count.
  * The v2 API surface is preserved (preview cache, synthesis cache with
    guard re-validation, cancel states, structured errors); the synthesis
    cache key now includes the engine version (stale-cache guard).

Run:
    python server.py                     # http://127.0.0.1:8421
    uvicorn server:app --port 8421       # equivalent

Requirements:
    pip install fastapi uvicorn
    pip install .            # covtl-pipeline itself (optional — without it
                             # the server answers /api/status with backend
                             # "mock" and the console runs its browser demo)

License: GPL-3.0-or-later (matches covtl-pipeline).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
OUT_ROOT = ROOT / "out"
OUT_ROOT.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────────
# Engine import — live when covtl-pipeline is installed
# ──────────────────────────────────────────────────────────────────────
LIVE = False
ENGINE_VERSION = "unknown"
_import_errors: List[str] = []
try:
    from vtl_synth import Pipeline                                   # noqa: F401
    from vtl_synth.core.sampa_guard import unknown_symbols           # noqa: F401
    LIVE = True
    try:
        from importlib.metadata import version as _pkg_version
        ENGINE_VERSION = _pkg_version("vtl-synth")
    except Exception:
        ENGINE_VERSION = "installed"
except Exception as exc:                                   # pragma: no cover
    _import_errors.append(f"{type(exc).__name__}: {exc}")

SPEAKERS = [
    {"id": "jd3", "name": "JD3", "origin": "reference (SynthVTL24b original)", "f0": 102.216},
    {"id": "s1",  "name": "S1",  "origin": "DVTD MRI subject 1 (male), calibrated v3", "f0": 114.908},
    {"id": "s2",  "name": "S2",  "origin": "DVTD MRI subject 2 (female), calibrated v3", "f0": 181.008},
    {"id": "m01", "name": "M01", "origin": "official VTL 2.4 ZIP (male)", "f0": 120.0},
    {"id": "w02", "name": "W02", "origin": "official VTL 2.4 ZIP (female)", "f0": 232.5},
]
LANG_DEFAULTS = {
    "en": {"tcons": 100, "tvoy": 80,  "tpause": 200, "tpauseLong": 320},
    "fr": {"tcons": 140, "tvoy": 120, "tpause": 200, "tpauseLong": 320},
    "es": {"tcons": 120, "tvoy": 100, "tpause": 200, "tpauseLong": 320},
    "de": {"tcons": 100, "tvoy": 90,  "tpause": 200, "tpauseLong": 320},
    "it": {"tcons": 120, "tvoy": 100, "tpause": 200, "tpauseLong": 320},
    "pt": {"tcons": 110, "tvoy": 100, "tpause": 200, "tpauseLong": 320},
}
LANG_NAMES = {"en": "English", "fr": "French", "es": "Spanish", "de": "German",
              "it": "Italian", "pt": "Portuguese"}
BREATH_MS = 130
UNVERIFIED_WARNING = ("Unverified combination: language-pack vowels are "
                      "calibrated on jd3 only. Audio may differ on other speakers.")

VOWELS = list("aeiouyEO@269")
CONSONANTS = ["p", "b", "t", "d", "k", "g", "f", "v", "s", "z", "S", "Z",
              "T", "D", "tS", "dZ", "m", "n", "J", "l", "R", "j", "w", "h", "ɥ"]
MARKERS = {" ", ".", "-", "|", "~", ",", "%"}
INVENTORY = set(VOWELS) | set(CONSONANTS)

SUGGESTIONS: Dict[str, List[str]] = {
    "c": ["k", "s"], "x": ["k", "s"], "q": ["k"],
    "ʃ": ["S"], "ʒ": ["Z"], "ŋ": ["J"], "ɲ": ["J"], "θ": ["T"], "ð": ["D"],
    "ə": ["@"], "ɛ": ["E"], "ɔ": ["O"], "ɪ": ["i"], "ʊ": ["u"], "ʌ": ["6"],
    "ɑ": ["a"], "æ": ["a"], "ø": ["2"], "œ": ["9", "2"], "ʏ": ["y"],
    "ã": ["a~"], "õ": ["o~"], "ĩ": ["i~"], "ẽ": ["e~"], "ũ": ["u~"],
    "ɐ": ["@", "6"], "ɜ": ["@"], "ɡ": ["g"], "ɾ": ["R", "t"], "ʀ": ["R"],
    "ʁ": ["R"], "ʎ": ["j"], "ʝ": ["j"], "ç": ["s"], "tʃ": ["tS"], "dʒ": ["dZ"],
    "A": ["a"], "B": ["b"], "C": ["k"], "F": ["f"], "G": ["g"], "H": ["h"],
    "I": ["i"], "K": ["k"], "L": ["l"], "M": ["m"], "N": ["n"], "P": ["p"],
    "Q": ["k"], "U": ["u"], "V": ["v"], "W": ["w"], "X": ["k", "s"], "Y": ["y"],
}
REJECT_REASON = ("not in the engine inventory (ALL_PHONEME_KEYS) — the "
                 "longest-match tokenizer would silently drop it")


def _suggest(symbol: str) -> List[str]:
    out = list(SUGGESTIONS.get(symbol, []))
    low, up = symbol.lower(), symbol.upper()
    if low != symbol and low in INVENTORY and low not in out:
        out.append(low)
    if up != symbol and up in INVENTORY and up not in out:
        out.append(up)
    return [s for s in out if s in INVENTORY or s in MARKERS][:3]


def enrich_rejected(rejected: List[Tuple[str, int]]) -> List[Dict[str, Any]]:
    return [{"symbol": s, "position": p, "reason": REJECT_REASON,
             "suggestions": _suggest(s)} for s, p in rejected]


def tokenize(sampa: str) -> List[Dict[str, Any]]:
    """Longest-match walk — mirrors sampa_guard.unknown_symbols()."""
    tokens, i = [], 0
    while i < len(sampa):
        ch = sampa[i]
        if ch in MARKERS:
            kind = ("pause" if ch in " |,%" else
                    "link" if ch in ".-" else "feature")
            if ch == "|":
                kind = "pause-long"
            elif ch == "%":
                kind = "pause-breath"
            elif ch in " ,":
                kind = "pause-short"
            tokens.append({"sym": ch, "kind": kind, "position": i})
            i += 1
            continue
        for d in ("tS", "dZ"):
            if sampa.startswith(d, i):
                tokens.append({"sym": d, "kind": "consonant", "position": i})
                i += 2
                break
        else:
            if ch in INVENTORY and i + 1 < len(sampa) and sampa[i + 1] == "~":
                tokens.append({"sym": ch + "~", "kind": "vowel", "position": i})
                i += 2
                continue
            if ch in INVENTORY:
                tokens.append({"sym": ch, "kind": "vowel" if ch in VOWELS else "consonant", "position": i})
                i += 1
                continue
            tokens.append({"sym": ch, "kind": "rejected", "position": i})
            i += 1
    return tokens


def local_rejected(sampa: str) -> List[Dict[str, Any]]:
    return enrich_rejected([(t["sym"], t["position"])
                            for t in tokenize(sampa) if t["kind"] == "rejected"])


_NASAL_LINK_RE = re.compile(r"[aeiouyEO@269]~[.\-]?[aeiouyEO@269]")
_NASAL_LINK_WARNING = (
    "nasal vowel followed by a linked vowel (V~.V): the syltraj walk drops "
    "this sequence — replace the dot with a short pause (space), or make "
    "the second vowel oral")


def nasal_link_warning(sampa: str) -> List[str]:
    """Warn about nasal-vowel + linked-vowel sequences (V~.V / V~V).

    All symbols are valid so the guard cannot flag them, but the syltraj
    walk silently reduces the sequence to a background block (both vowels
    are lost from the plan and the audio). Kept on record in the engine
    CHANGELOG; the FR G2P avoids it since the nasal-boundary fix.
    """
    if _NASAL_LINK_RE.search(sampa or ""):
        return [_NASAL_LINK_WARNING]
    return []


def inventory_digest() -> Dict[str, Any]:
    return {
        "vowels": " ".join(VOWELS) + " (+ nasalized V~)",
        "consonants": " ".join(CONSONANTS),
        "markers": ". ␣ | %",
        "count": len(INVENTORY),
    }


# ──────────────────────────────────────────────────────────────────────
# Structured errors — every failure the UI can display
# ──────────────────────────────────────────────────────────────────────
ERROR_HINTS = {
    "SampaGuardError": "The guard policy is “error” and the input contains symbols "
                       "outside ALL_PHONEME_KEYS. Fix or strip the red symbols in the final SAMPA.",
    "LookupError": "The language pack is not installed. Run: python setup_lang.py install --lang xx",
    "ModuleNotFoundError": "A required engine dependency is missing (e.g. pip install cmudict).",
    "ValueError": "Check the input: the engine found no phonetic content, or a parameter "
                  "is out of range. See the message for the exact offender.",
    "FileNotFoundError": "A speaker / language resource file is missing from the registry. "
                         "Check vtl_synth/data/ and install_speaker.py.",
    "StructureDrift": "The syltraj walk changed shape — the bridge refuses to guess anchor "
                      "positions. Report with the log lines.",
    "Cancelled": "The job was cancelled before it produced audio.",
}


def api_error(status: int, error_class: str, message: str,
              hint: Optional[str] = None, symbols: Optional[List[Dict[str, Any]]] = None,
              detail: Optional[str] = None) -> JSONResponse:
    body: Dict[str, Any] = {
        "detail": detail or message,                      # v1 compat field
        "error": {
            "class": error_class,
            "message": message,
            "hint": hint or ERROR_HINTS.get(error_class, ""),
            "symbols": symbols or [],
        },
    }
    return JSONResponse(status_code=status, content=body)


def guard_error(rejected: List[Dict[str, Any]]) -> JSONResponse:
    sym = ", ".join(f"'{r['symbol']}'@{r['position']}" for r in rejected)
    return api_error(
        422, "SampaGuardError",
        f"sampa_guard policy=error: {len(rejected)} symbol(s) outside ALL_PHONEME_KEYS: {sym}",
        symbols=rejected)


app = FastAPI(title="COVTL Console bridge", version="3.0.0",
              description="Local REST bridge for covtl-pipeline (vtl-synth).")


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):  # noqa: ANN001
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": detail,
                                 "error": {"class": "HTTPError", "message": detail,
                                           "hint": "", "symbols": []}})


@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception):  # noqa: ANN001
    return JSONResponse(status_code=500,
                         content={"detail": str(exc),
                                  "error": {"class": type(exc).__name__, "message": str(exc),
                                            "hint": ERROR_HINTS.get(type(exc).__name__, ""), "symbols": []}})


app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])   # local tool: UI may run from file://


@app.middleware("http")
async def no_cache_assets(request: Request, call_next):  # noqa: ANN001
    """Static assets must always revalidate: a stale cached app.js hides
    new features (the per-language examples were invisible this way)."""
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or p.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# ──────────────────────────────────────────────────────────────────────
# syltraj structure — anchors, blocks, per-phoneme targets (brief ch. 2.9)
#
# The walk inside syltraj.build_global_pval iterates over consecutive
# anchor pairs; every appended block is a SylBlock instance and every
# iteration calls _collect_consonants exactly once (after the possible
# departure plateau). Recording both gives anchor timestamps on the
# 100 Hz block timeline with no reimplementation — the same
# monkeypatch idiom as vtl_synth.video.polar_video._recorded_build_pval,
# with hard drift checks that raise instead of guessing.
# ──────────────────────────────────────────────────────────────────────
def _instrumented_phrase_build(phrase: str, t_cons: int, t_voy: int,
                               pause_short_ms: float, pause_long_ms: float,
                               pause_breath_ms: Optional[float] = None) -> Dict[str, Any]:
    """One phrase → dict(anchors, blocks, nodes, n_steps) with anchor times."""
    import vtl_synth.core.syltraj as syl

    ledger: List[Any] = []          # SylBlock instances, in construction order
    iter_marks: List[int] = []      # len(ledger) at each anchor-pair iteration

    orig_block = syl.SylBlock
    orig_cc = syl._collect_consonants

    class RecBlock(orig_block):     # noqa: D801 — records construction order
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            ledger.append(self)

    def cc_hooked(nodes, start, end):
        iter_marks.append(len(ledger))
        return orig_cc(nodes, start, end)

    syl.SylBlock = RecBlock
    syl._collect_consonants = cc_hooked
    try:
        _pval, blocks, nodes, anchors = syl.build_phrase_pval(
            phrase, t_cons=t_cons, t_voy=t_voy,
            pause_short_ms=pause_short_ms, pause_long_ms=pause_long_ms,
            pause_breath_ms=pause_breath_ms, sampa_guard="off")
    finally:
        syl.SylBlock = orig_block
        syl._collect_consonants = orig_cc

    if len(ledger) != len(blocks):
        raise RuntimeError(
            f"structure drift: {len(ledger)} recorded blocks vs {len(blocks)} engine blocks")
    if len(iter_marks) != max(0, len(anchors) - 1):
        raise RuntimeError(
            f"structure drift: {len(iter_marks)} walk iterations vs "
            f"{max(0, len(anchors) - 1)} anchor pairs")

    def _steps(n: int) -> int:
        return sum(b.n_steps for b in ledger[:n])

    # anchor k sits at the start of walk iteration k (its departure plateau,
    # if any, is emitted at the head of that iteration and belongs to it)
    anchor_t: List[int] = []
    for k, mark in enumerate(iter_marks):
        s = _steps(mark)
        if k > 0 and mark > iter_marks[k - 1]:
            last = ledger[mark - 1]
            prev_kind_slice_has_plateau_tail = last.kind == "plateau"
            # a plateau at the slice tail is this iteration's departure hold
            # (iterations never emit plateaus after their _collect_consonants)
            if prev_kind_slice_has_plateau_tail:
                s -= last.n_steps
        anchor_t.append(s)
    anchor_t.append(sum(b.n_steps for b in ledger))   # terminal anchor

    def _node_key(a) -> str:
        if a.kind == "V":
            i = min(max(a.i, 0), len(nodes) - 1)
            return str(nodes[i].key)
        if a.kind == "pause":
            return "%" if a.breath else ("|" if a.long else "␣")
        return "▸" if a.i < 0 else "◂"

    out_anchors = [
        {"i": k, "t": anchor_t[k] / 100.0, "kind": a.kind, "label": _node_key(a),
         "long": bool(a.long), "breath": bool(a.breath),
         "hold": bool(a.hold), "word_end": bool(a.is_word_end),
         "pt": ([float(a.pt[0]), float(a.pt[1])] if a.pt else None)}
        for k, a in enumerate(anchors)
    ]
    step = 0
    out_blocks = []
    for b in ledger:
        out_blocks.append({
            "kind": b.kind, "n_steps": int(b.n_steps),
            "t0": step / 100.0, "t1": (step + b.n_steps) / 100.0,
            "n_cons": int(b.n_cons), "cons_keys": list(b.cons_keys),
            "vowel_key": b.vowel_key, "pre": b.pre_token, "post": b.post_token,
            "long": bool(b.long), "breath": bool(b.breath),
        })
        step += b.n_steps

    return {"anchors": out_anchors, "blocks": out_blocks,
            "nodes": [{"kind": n.kind, "key": str(n.key),
                       "rho": float(n.rho), "theta": float(n.theta),
                       "in_cluster": bool(n.in_cluster)} for n in nodes],
            "n_steps": int(step)}


def _phrases_of(sampa: str) -> List[str]:
    """Same phrase split as Pipeline.run."""
    return [p.strip() for p in sampa.split("|") if p.strip()]


def _timings_of(lang: str, timings: Dict[str, float]) -> Dict[str, float]:
    d = LANG_DEFAULTS.get(lang, LANG_DEFAULTS["en"])
    return {**d, **{k: v for k, v in (timings or {}).items() if v}}


def structure_compile(sampa: str, lang: str = "en",
                      timings: Optional[Dict[str, float]] = None,
                      pause_breath_ms: Optional[float] = None) -> Dict[str, Any]:
    """SAMPA → engine structure (anchors + blocks + nodes + metrics).

    Shared by POST /api/compile (syllable compiler panel) and the
    synthesis worker (early polar stage). No synthesis, no audio."""
    t = _timings_of(lang, timings)
    anchors: List[Dict[str, Any]] = []
    blocks: List[Dict[str, Any]] = []
    nodes: List[Dict[str, Any]] = []
    offset = 0.0
    phrase_span: List[Tuple[int, int]] = []      # (anchor_lo, anchor_hi) per phrase
    for phrase in _phrases_of(sampa):
        st = _instrumented_phrase_build(
            phrase, max(1, round(t["tcons"] / 10.0)), max(1, round(t["tvoy"] / 10.0)),
            t["tpause"], t["tpauseLong"], pause_breath_ms)
        phrase_span.append((len(anchors), len(anchors) + len(st["anchors"]) - 1))
        for a in st["anchors"]:
            a = dict(a)
            a["i"] = len(anchors)
            a["t"] = round(a["t"] + offset, 4)
            anchors.append(a)
        for b in st["blocks"]:
            b = dict(b)
            b["t0"] = round(b["t0"] + offset, 4)
            b["t1"] = round(b["t1"] + offset, 4)
            blocks.append(b)
        nodes.extend(st["nodes"])
        offset += st["n_steps"] / 100.0

    # dedupe consecutive same-time anchors across phrase joints (the
    # terminal '◂' of one phrase and the '▸' of the next share t when no
    # inter-phrase pause block exists — keep both, the display skips
    # zero-length segments)
    syllables = sum(1 for b in blocks if b["kind"] == "plateau")
    clusters = [b for b in blocks if b["kind"] == "cluster"]
    cons_total = sum(b["n_cons"] for b in clusters)
    metrics = {
        "anchors": len(anchors),
        "segments": max(0, len(anchors) - 1),
        "blocks": len(blocks),
        "syllables": syllables,
        "clusters": len(clusters),
        "consonants": cons_total,
        "vowels": sum(1 for n in nodes if n["kind"] == "V"),
        "steps": int(round(offset * 100)),
        "duration_s": round(offset, 3),
    }
    return {"anchors": anchors, "blocks": blocks, "nodes": nodes,
            "metrics": metrics, "phrases": _phrases_of(sampa),
            "phrase_spans": phrase_span}


# ──────────────────────────────────────────────────────────────────────
# Polar segment payload (brief annex A.4)
# ──────────────────────────────────────────────────────────────────────
def _theta_display(rad: float) -> float:
    """Trigonometric radians (0 East, CCW) → display degrees (0 top, CW)."""
    return round((90.0 - math.degrees(rad)) % 360.0, 2)


def _rho_max_of(polar_doc: Dict[str, Any]) -> float:
    m = 1.45
    for inv in polar_doc.get("inventory", []):
        m = max(m, float(inv.get("rho", 0.0)))
    return m


def build_segment_payload(job: Dict[str, Any], from_k: int = 0,
                          mode: str = "inc") -> Dict[str, Any]:
    """Merge the recorded structure (anchors/blocks) with the .polar
    trajectories into the anchor-to-anchor segment payload."""
    polar_path = (job.get("paths") or {}).get("polar")
    if not polar_path or not Path(polar_path).exists():
        raise HTTPException(404, "polar data not available for this job")
    doc = json.loads(Path(polar_path).read_text(encoding="utf-8"))
    st = job.get("structure") or {}
    anchors = st.get("anchors") or []
    blocks = st.get("blocks") or []
    if not anchors:
        raise HTTPException(404, "anchor structure not recorded for this job")

    traj = doc.get("trajectory") or {}
    vr = traj.get("vocalic", {}).get("rho", [])
    vt = traj.get("vocalic", {}).get("theta", [])
    cr = traj.get("consonantal", {}).get("rho", [])
    ct = traj.get("consonantal", {}).get("theta", [])
    n_steps = doc.get("n_steps") or len(vr)
    rho_max = _rho_max_of(doc)

    def pt_row(i: int) -> Dict[str, Any]:
        row: Dict[str, Any] = {"t": round(i / 100.0, 3)}
        row["rho_v"] = round(float(vr[i]) / rho_max, 4) if i < len(vr) else None
        row["theta_v"] = _theta_display(float(vt[i])) if i < len(vt) else None
        row["rho_c"] = (round(float(cr[i]) / rho_max, 4)
                        if i < len(cr) and cr[i] is not None else None)
        row["theta_c"] = (_theta_display(float(ct[i]))
                          if i < len(ct) and ct[i] is not None else None)
        return row

    segs_out: List[Dict[str, Any]] = []
    for k in range(max(0, from_k), len(anchors) - 1):
        a0, a1 = anchors[k], anchors[k + 1]
        i0, i1 = int(round(a0["t"] * 100)), int(round(a1["t"] * 100))
        if i1 <= i0:
            points = []
        else:
            points = [pt_row(i) for i in range(i0, min(i1, n_steps))]
        span_blocks = [b for b in blocks if b["t0"] < a1["t"] - 1e-9
                       and b["t1"] > a0["t"] + 1e-9]
        markers = {
            "syllable_links": sum(1 for b in span_blocks if b["kind"] == "cluster"),
            "short_pauses": sum(1 for b in span_blocks
                                if b["kind"] == "pause" and not b["long"] and not b["breath"]),
            "long_pauses": sum(1 for b in span_blocks
                               if b["kind"] in ("pause", "terminal") and b["long"]),
            "breaths": sum(1 for b in span_blocks if b["breath"]),
        }
        segs_out.append({
            "segment_index": k, "t0": round(a0["t"], 3), "t1": round(a1["t"], 3),
            "anchor_from": a0["i"], "anchor_to": a1["i"],
            "label_from": a0["label"], "label_to": a1["label"],
            "blocks": [{kk: b[kk] for kk in ("kind", "n_steps", "cons_keys",
                                             "vowel_key", "long", "breath",
                                             "t0", "t1")}
                       for b in span_blocks],
            "markers": markers,
            "points": points,
        })
    if mode == "full":
        anchors_out = anchors
    else:
        anchors_out = anchors[max(0, from_k):max(0, from_k) + len(segs_out) + 1]
    return {
        "job_id": job["id"],
        "segment_count": max(0, len(anchors) - 1),
        "from": max(0, from_k),
        "rho_max": round(rho_max, 3),
        "duration_s": round(n_steps / 100.0, 3),
        "sample_rate": 100,
        "anchors": anchors_out,
        "segments": segs_out,
    }


# ──────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────
class PreviewRequest(BaseModel):
    text: Optional[str] = None
    sampa: Optional[str] = None          # re-enrich an edited G2P string
    mode: str = "ortho"                  # 'ortho' → G2P, 'phonetic' → guard only
    lang: str = "en"
    expressive: bool = False
    policy: Optional[str] = None         # informational; policy never changes spans


class GuardRequest(BaseModel):
    sampa: str
    policy: Optional[str] = None


class CompileRequest(BaseModel):
    text: str                            # phonetic SAMPA (syllable blocks)
    lang: str = "en"
    timings: Dict[str, float] = {}
    guard_policy: str = "warn"
    expressive: bool = False             # accepted for key symmetry; breath via '%'


class SynthRequest(BaseModel):
    text: str
    mode: str = "ortho"                  # 'ortho' → use_g2p=True
    lang: str = "en"
    speaker: str = "jd3"
    expressive: bool = False
    f0: Optional[float] = None
    timings: Dict[str, float] = {}
    engine: str = "syl"
    ortho: bool = True
    outputMode: str = "audio"            # audio | sagittal | polar — audio-only default
    guardPolicy: Optional[str] = None
    outputDir: str = "out"
    label: Optional[str] = None
    exports: bool = True                 # keep tract/polar/txt offered as downloads


# ──────────────────────────────────────────────────────────────────────
# Caches
# ──────────────────────────────────────────────────────────────────────
PREVIEW_CACHE: "OrderedDict[Tuple, Dict[str, Any]]" = OrderedDict()
PREVIEW_CACHE_MAX = 128
PREVIEW_HITS = {"n": 0}

COMPILE_CACHE: "OrderedDict[Tuple, Dict[str, Any]]" = OrderedDict()
COMPILE_CACHE_MAX = 64
COMPILE_HITS = {"n": 0}

SYNTH_CACHE: "OrderedDict[str, str]" = OrderedDict()   # param-key → job_id
SYNTH_CACHE_MAX = 32
SYNTH_HITS = {"n": 0}


def preview_key(req: PreviewRequest) -> Tuple:
    return (req.text or "", req.sampa or "", req.mode, req.lang, bool(req.expressive))


def synth_key(req: SynthRequest) -> str:
    """Cache key over the parameters that change the produced audio.
    guardPolicy is deliberately excluded: warn/off yield identical audio and
    the error policy is re-validated on every hit (see synthesize()).
    The engine version is included — an engine upgrade invalidates entries
    rather than serving old-engine audio (brief §11.1)."""
    payload = {
        "engine_version": ENGINE_VERSION,
        "text": req.text, "mode": req.mode, "lang": req.lang,
        "speaker": req.speaker, "expressive": req.expressive and req.mode == "ortho",
        "f0": req.f0, "timings": {k: req.timings.get(k) for k in
                                  ("tcons", "tvoy", "tpause", "tpauseLong")},
        "engine": req.engine, "ortho": req.ortho, "outputMode": req.outputMode,
        "exports": req.exports,
        "label": req.label, "outputDir": req.outputDir,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────
# Health / registry endpoints (brief ch. 10.3–10.4)
# ──────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health() -> Dict[str, Any]:
    warnings: List[str] = []
    status = "offline"
    engine_version = ENGINE_VERSION if LIVE else None
    active_speaker = None
    active_lang = None
    if LIVE:
        status = "ok"
        try:
            from vtl_synth.core import speaker_registry as sr
            active_speaker = sr.active_name()
        except Exception as exc:
            status = "degraded"
            warnings.append(f"speaker registry probe failed: {exc}")
        try:
            from vtl_synth.core import constants as _c
            active_lang = getattr(_c, "ACTIVE_LANG", "en")
        except Exception:
            active_lang = "en"
        try:
            from vtl_synth.utils.lexicon_loader import LEXICONS, has_lexicon
            for code in LEXICONS:
                if not has_lexicon(code):
                    warnings.append(f"lexicon for '{code}' absent (rules only)")
        except Exception:
            pass
    return {"status": status, "engine_version": engine_version,
            "bridge": "3.0.0", "active_speaker": active_speaker,
            "active_lang": active_lang, "registry_warnings": warnings}


@app.get("/api/languages")
def languages() -> Dict[str, Any]:
    out = []
    for code, name in LANG_NAMES.items():
        entry: Dict[str, Any] = {"id": code, "name": name,
                                 "prosody_profile": True, "lexicon_present": True}
        if LIVE:
            try:
                from vtl_synth.utils.lexicon_loader import LEXICONS, has_lexicon
                entry["lexicon_present"] = bool(has_lexicon(code)) or code == "en"
            except Exception:
                pass
        out.append(entry)
    return {"languages": out, "active": health().get("active_lang")}


@app.get("/api/speakers")
def speakers(lang: str = "en") -> Dict[str, Any]:
    active = health().get("active_speaker")
    out = []
    for s in SPEAKERS:
        verified = s["id"] == "jd3"
        out.append({"id": s["id"], "label": f"{s['id']} — {s['origin']}",
                    "f0_default": s["f0"], "verified_with_lang": verified,
                    "active": (active or "").lower().startswith(s["id"])})
    warning = UNVERIFIED_WARNING if lang != "en" else None
    return {"speakers": out, "warning_when_unverified": warning,
            "calibration_speaker": "jd3"}


# ──────────────────────────────────────────────────────────────────────
# Status (v2 surface, extended)
# ──────────────────────────────────────────────────────────────────────
@app.get("/api/status")
def status() -> Dict[str, Any]:
    active = [j for j in JOBS.values() if j["state"] in ("queued", "running", "cancelling")]
    info: Dict[str, Any] = {
        "backend": "live" if LIVE else "mock",
        "engine": "vtl-synth",
        "version": ENGINE_VERSION,
        "bridge": "3.0.0",
        "mode": "vtl_synth" if LIVE else "vtl_synth not importable",
        "speakers": SPEAKERS,
        "languages": list(LANG_DEFAULTS.keys()),
        "defaults": LANG_DEFAULTS,
        "cache": {
            "preview_entries": len(PREVIEW_CACHE), "preview_hits": PREVIEW_HITS["n"],
            "compile_entries": len(COMPILE_CACHE), "compile_hits": COMPILE_HITS["n"],
            "synth_entries": len(SYNTH_CACHE), "synth_hits": SYNTH_HITS["n"],
        },
        "jobs": {"active": len(active), "registered": len(JOBS)},
        "inventory_digest": inventory_digest(),
        "out_root": str(OUT_ROOT),          # where artifacts actually land
    }
    if not LIVE:
        info["reason"] = "; ".join(_import_errors) or "vtl_synth not installed"
    if LIVE:
        try:
            from vtl_synth.core import speaker_registry as sr
            info["active"] = {"speaker": sr.active_name()}
        except Exception:
            pass
        try:
            from vtl_synth.core import constants as _c
            info["active"]["lang"] = getattr(_c, "ACTIVE_LANG", "en")
        except Exception:
            info.setdefault("active", {})["lang"] = "en"
        lex: Dict[str, str] = {}
        try:
            from vtl_synth.utils.lexicon_loader import LEXICONS, has_lexicon, lexicon_size
            for code in LEXICONS:
                lex[code] = f"{lexicon_size(code)} entries" if has_lexicon(code) else "absent (rules only)"
        except Exception:
            pass
        lex.setdefault("en", "cmudict")
        info["lexicons"] = lex
    return info


# ──────────────────────────────────────────────────────────────────────
# Unified preview — ONE round trip for the preview stack
# ──────────────────────────────────────────────────────────────────────
@app.post("/api/preview")
def preview(req: PreviewRequest) -> Dict[str, Any]:
    key = preview_key(req)
    hit = PREVIEW_CACHE.get(key)
    if hit is not None:
        PREVIEW_CACHE.move_to_end(key)
        PREVIEW_HITS["n"] += 1
        out = dict(hit)
        out["cache"] = True
        return out

    phonetic = req.mode == "phonetic" and req.sampa is None
    if req.sampa is not None:
        phonetic = False                    # re-enrich an edited G2P string
    if not LIVE and not phonetic and req.sampa is None:
        return api_error(503, "BackendUnavailable",
                         "vtl_synth not installed on the server — the console falls back "
                         "to its browser demo engine for G2P.",
                         hint="Start the bridge on a machine with covtl-pipeline installed, "
                              "or keep using demo mode (interface + guard semantics only).")

    warnings: List[str] = []
    groups: List[Dict[str, Any]] = []
    g2p_string: Optional[str] = None
    words: List[Dict[str, Any]] = []

    if req.sampa is not None:
        sampa = req.sampa
        if req.expressive:
            try:
                profile = _profile(req.lang)
                sampa = _chunk_like_engine(req.sampa, profile, warnings)
            except Exception as exc:
                warnings.append(f"expressive re-enrichment unavailable: {exc}")
    elif phonetic:
        sampa = (req.text or "").strip()
    else:
        profile = _profile(req.lang)
        raw_warnings: List[str] = []
        raw = profile.g2p_callable(req.text or "", warnings=raw_warnings)
        g2p_string = raw
        if req.expressive:
            try:
                from vtl_synth.utils.prosody_f0 import plan_expressive_text
                sampa, _plans = plan_expressive_text(
                    req.text or "", req.lang, profile.g2p_callable,
                    getattr(profile, "expressivity", None), warnings)
            except Exception as exc:
                warnings.append(f"expressive preview unavailable ({exc}); monotone path used")
                sampa = raw
            warnings.extend(w for w in raw_warnings if w not in warnings)
        else:
            sampa = raw
            warnings.extend(raw_warnings)
        g2p_string = raw
        words = _word_chips(req.text or "", profile, raw_warnings)

    enriched = sampa
    if req.expressive:
        groups = _groups_from_sampa(enriched)
    final = enriched

    try:
        if LIVE:
            rejected = enrich_rejected(list(unknown_symbols(final)))
            tokens = tokenize(final)
        else:
            tokens = tokenize(final)
            rejected = [{"symbol": t["sym"], "position": t["position"],
                         "reason": REJECT_REASON, "suggestions": _suggest(t["sym"])}
                        for t in tokens if t["kind"] == "rejected"]
    except Exception:
        tokens = tokenize(final)
        rejected = local_rejected(final)

    out = {
        "g2p_string": g2p_string,
        "enriched_string": enriched,
        "final_sampa": final,
        "words": words,
        "groups": groups,
        "warnings": warnings + nasal_link_warning(final),
        "tokens": tokens,
        "rejected_symbols": rejected,
        "language": req.lang,
        "lexicon": _lexicon_info(req.lang) if not phonetic else None,
        "inventory_digest": inventory_digest(),
        "cache": False,
    }
    PREVIEW_CACHE[key] = out
    PREVIEW_CACHE.move_to_end(key)
    while len(PREVIEW_CACHE) > PREVIEW_CACHE_MAX:
        PREVIEW_CACHE.popitem(last=False)
    return out


def _profile(lang: str):
    from vtl_synth.utils.setlang import get_profile
    try:
        return get_profile(lang)
    except LookupError as exc:
        raise HTTPException(400, str(exc))


def _chunk_like_engine(sampa: str, profile, warnings: List[str]) -> str:
    try:
        from vtl_synth.utils.chunking import chunk_phrase
        return chunk_phrase(sampa, profile)
    except Exception:
        raise RuntimeError("utils.chunking API mismatch")


def _groups_from_sampa(sampa: str) -> List[Dict[str, Any]]:
    groups = []
    for phrase in sampa.split(" | "):
        for g in phrase.split(" % "):
            g = g.strip()
            if g:
                groups.append({"sampa": g, "words": len(g.replace(".", " ").split())})
    return groups


def _word_chips(text: str, profile, warnings: List[str]) -> List[Dict[str, Any]]:
    unknown = set(re.findall(r"kept verbatim\): '([^']+)'", " ".join(warnings)))
    words = re.findall(r"[A-Za-zÀ-ɏ'’]+", text)
    out = []
    for w in words:
        key = w.lower()
        if key in unknown:
            out.append({"word": w, "sampa": key, "known": False})
            continue
        try:
            sampa = profile.g2p_callable(w, warnings=[])
            sampa = sampa.replace(" | ", " ").strip()
        except Exception:
            sampa = key
        out.append({"word": w, "sampa": sampa, "known": True})
    return out


def _lexicon_info(lang: str) -> str:
    try:
        from vtl_synth.utils.lexicon_loader import LEXICONS, has_lexicon, lexicon_size
        if lang in LEXICONS:
            return f"{lexicon_size(lang)} entries" if has_lexicon(lang) else "absent (rules only)"
    except Exception:
        pass
    return "cmudict" if lang == "en" else "Wikipron (language pack)"


# ── deprecated v1 endpoints (kept working; the UI now uses /api/preview) ──
class G2PRequest(BaseModel):
    text: Optional[str] = None
    sampa: Optional[str] = None
    lang: str = "en"
    expressive: bool = False


@app.post("/api/preview/g2p")
def preview_g2p(req: G2PRequest) -> Dict[str, Any]:
    r = preview(PreviewRequest(text=req.text, sampa=req.sampa, lang=req.lang,
                               expressive=req.expressive, mode="ortho"))
    return {"sampa": r["enriched_string"], "warnings": r["warnings"],
            "words": r["words"], "groups": r["groups"],
            "language": r["language"], "lexicon": r["lexicon"]}


@app.post("/api/preview/sampa")
def preview_sampa(req: GuardRequest) -> Dict[str, Any]:
    return {"tokens": tokenize(req.sampa), "rejected": local_rejected(req.sampa)}


# ──────────────────────────────────────────────────────────────────────
# Syllable block compiler (eml-formalization-inspired panel)
#
# "Compile" here means exactly what the engine does before synthesizing:
# tokenize the SAMPA phrase, walk syltraj's anchors, emit the block
# schedule. No audio, no tract file — the cheap structural half, so the
# user can iterate on syllable blocks the way the eml dashboard compiles
# expression blocks (metric tiles → string → clickable block tree).
# ──────────────────────────────────────────────────────────────────────
@app.post("/api/compile")
def compile_blocks(req: CompileRequest) -> Dict[str, Any]:
    if not LIVE:
        return api_error(503, "BackendUnavailable",
                         "vtl_synth not installed — the syllable compiler needs the "
                         "engine's syltraj walk (demo mode offers an approximate one).",
                         hint="Start the bridge on a machine with covtl-pipeline installed.")
    key = (req.text, req.lang, json.dumps(req.timings, sort_keys=True))
    hit = COMPILE_CACHE.get(key)
    if hit is not None:
        COMPILE_CACHE.move_to_end(key)
        COMPILE_HITS["n"] += 1
        out = dict(hit)
        out["cache"] = True
        return out

    src = (req.text or "").strip()
    if not src:
        return api_error(422, "invalid_input", "nothing to compile — the source is empty")
    rejected = enrich_rejected(list(unknown_symbols(src)))
    if req.guard_policy == "error" and rejected:
        return guard_error(rejected)

    warnings: List[str] = []
    breath_ms: Optional[float] = BREATH_MS if "%" in src else None
    warnings.extend(nasal_link_warning(src))
    try:
        st = structure_compile(src, req.lang, req.timings, breath_ms)
    except RuntimeError as exc:
        return api_error(500, "StructureDrift", str(exc))

    # per-phoneme polar targets for the clickable block cards
    try:
        from vtl_synth.core.constants import VOWEL_TARGETS
        from vtl_synth.core.projection import get_consonant_target
        targets = {}
        for key_, (rho, theta) in VOWEL_TARGETS.items():
            targets[key_] = {"rho": float(rho), "theta": float(theta), "category": "V"}
        for c in CONSONANTS:
            if c in targets:
                continue
            ct = get_consonant_target(c, math.pi)
            if ct is not None:
                targets[c] = {"rho": float(ct[0]), "theta": float(ct[1]), "category": "C"}
    except Exception as exc:
        warnings.append(f"polar targets unavailable: {exc}")
        targets = {}

    # block → segment grouping (same rule as build_segment_payload)
    anchors = st["anchors"]
    labeled: List[Dict[str, Any]] = []
    for k in range(len(anchors) - 1):
        a0, a1 = anchors[k], anchors[k + 1]
        span = [b for b in st["blocks"] if b["t0"] < a1["t"] - 1e-9 and b["t1"] > a0["t"] + 1e-9]
        cons = [c for b in span for c in b["cons_keys"]]
        vowel = next((b["vowel_key"] for b in span if b["kind"] == "plateau"), "")
        label = ("".join(cons) + (vowel or "")) or a0["label"] or a1["label"] or "-"
        # chronological stretch string: engine order, '‿' marks consonants
        # following a vowel inside the same stretch (coda fused with the
        # next onset — coarticulation, not a syllable boundary)
        out_s: str = ""
        saw_vowel = False
        for b in span:
            if b["kind"] == "plateau":
                out_s += (b["vowel_key"] or "@")
                saw_vowel = True
            elif b["kind"] == "cluster" and b["cons_keys"]:
                out_s += ("‿" if saw_vowel else "") + "".join(b["cons_keys"])
            elif b["breath"]:
                out_s += "%"
            elif b["kind"] == "pause":
                out_s += ("|" if b["long"] else "␣")
            elif b["kind"] in ("decay", "attack"):
                out_s += "·"
            elif b["kind"] == "initial" and not out_s:
                out_s += "▸"
            elif b["kind"] == "terminal":
                out_s += "◂"
        labeled.append({"segment_index": k, "t0": a0["t"], "t1": a1["t"],
                        "label": label, "stretch": out_s or "-",
                        "cons": cons, "vowel": vowel,
                        "kinds": [b["kind"] for b in span],
                        "n_steps": int(round((a1["t"] - a0["t"]) * 100))})

    out = {
        "source": src,
        "sampa": src,
        "anchors": st["anchors"],
        "blocks": st["blocks"],
        "nodes": st["nodes"],
        "metrics": st["metrics"],
        "segments_preview": labeled,
        "targets": targets,
        "rejected_symbols": rejected,
        "warnings": warnings,
        "inventory_digest": inventory_digest(),
        "cache": False,
    }
    COMPILE_CACHE[key] = out
    COMPILE_CACHE.move_to_end(key)
    while len(COMPILE_CACHE) > COMPILE_CACHE_MAX:
        COMPILE_CACHE.popitem(last=False)
    return out


# ──────────────────────────────────────────────────────────────────────
# Synthesis jobs (async, cacheable, cancellable)
# ──────────────────────────────────────────────────────────────────────
JOBS: Dict[str, Dict[str, Any]] = {}
LOCK = threading.Lock()
JOBS_MAX = 128


def _prune_jobs() -> None:
    terminal = [jid for jid, j in JOBS.items()
                if j["state"] in ("done", "error", "cancelled")]
    while len(JOBS) > JOBS_MAX and terminal:
        JOBS.pop(terminal.pop(0), None)


@app.post("/api/synthesize")
def synthesize(req: SynthRequest) -> Dict[str, Any]:
    if not LIVE:
        return api_error(503, "BackendUnavailable",
                         "vtl_synth not installed — run the console in demo mode "
                         "or install covtl-pipeline (pip install .).")
    key = synth_key(req)

    # guard validation happens on EVERY path (fresh or cached)
    if req.guardPolicy == "error":
        probe = (req.text or "").strip() if req.mode == "phonetic" else None
        if probe:
            rejected = enrich_rejected(list(unknown_symbols(probe)))
            if rejected:
                return guard_error(rejected)

    with LOCK:
        cached_id = SYNTH_CACHE.get(key)
    if cached_id and cached_id in JOBS and JOBS[cached_id]["state"] == "done":
        job = JOBS[cached_id]
        if all(Path(p).exists() for p in (job.get("paths") or {}).values()):
            SYNTH_CACHE.move_to_end(key)
            SYNTH_HITS["n"] += 1
            return {"job_id": cached_id, "cached": True, "echo": job.get("echo") or {}}

    job_id = uuid.uuid4().hex[:12]
    t = _timings_of(req.lang, req.timings)
    echo = {"lang": req.lang, "speaker": req.speaker, "engine": req.engine,
            "ortho": req.ortho, "expressive": req.expressive, "guard": req.guardPolicy or "warn",
            "tcons": t["tcons"], "tvoy": t["tvoy"], "tpause": t["tpause"],
            "tpause_long": t["tpauseLong"], "engine_version": ENGINE_VERSION}
    job = {"id": job_id, "state": "queued", "stage": "g2p", "progress": 0.0,
           "created": time.time(), "error": None, "error_class": None, "error_hint": None,
           "result": None, "cancelled": False, "cache_key": key, "echo": echo,
           "polar_ready": False, "wav_ready": False, "anchors": None,
           "block_count": None, "structure": None}
    with LOCK:
        JOBS[job_id] = job
        _prune_jobs()
    threading.Thread(target=_worker, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id, "cached": False, "echo": echo}


def _resolve_sampa(req: SynthRequest, warnings: List[str]) -> str:
    """Same G2P path as /api/preview and Pipeline.run (engine callables)."""
    if req.mode == "phonetic":
        return (req.text or "").strip()
    profile = _profile(req.lang)
    if req.expressive:
        from vtl_synth.utils.prosody_f0 import plan_expressive_text
        sampa, _plans = plan_expressive_text(
            req.text or "", req.lang, profile.g2p_callable,
            getattr(profile, "expressivity", None), warnings)
        return sampa
    return profile.g2p_callable(req.text or "", warnings=warnings)


def _worker(job_id: str, req: SynthRequest) -> None:
    job = JOBS[job_id]
    try:
        if job["cancelled"]:
            job.update(state="cancelled", error="cancelled before start",
                       error_class="Cancelled")
            return
        import inspect
        from vtl_synth import Pipeline
        sig = inspect.signature(Pipeline.__init__).parameters
        kwargs: Dict[str, Any] = {}
        if "speaker" in sig: kwargs["speaker"] = req.speaker
        if "engine" in sig: kwargs["engine"] = req.engine
        if "use_orthogonal" in sig: kwargs["use_orthogonal"] = req.ortho
        if "f0_hz" in sig and req.f0: kwargs["f0_hz"] = req.f0
        if "lang" in sig: kwargs["lang"] = req.lang
        if "expressive" in sig and req.expressive and req.mode == "ortho":
            kwargs["expressive"] = True
        t = _timings_of(req.lang, req.timings)
        if "t_cons_ms" in sig: kwargs["t_cons_ms"] = t["tcons"]
        if "t_voy_ms" in sig: kwargs["t_voy_ms"] = t["tvoy"]
        if "pause_short_ms" in sig: kwargs["pause_short_ms"] = t["tpause"]
        if "pause_long_ms" in sig: kwargs["pause_long_ms"] = t["tpauseLong"]

        pipe = Pipeline(**kwargs)
        job.update(state="running", stage="g2p", progress=0.05)
        out_dir = (OUT_ROOT / re.sub(r"[^A-Za-z0-9_\-]", "_", req.outputDir or "out"))
        out_dir.mkdir(parents=True, exist_ok=True)
        use_g2p = req.mode == "ortho"
        video = req.outputMode != "audio"
        stem = req.label or re.sub(r"[^A-Za-z0-9_\-]", "_",
                                   (req.text or "output")[:28]).strip("_") or "output"

        # ── stage 1 — trajectory structure (cheap, pure Python) ──
        # Anchors + block schedule + .polar trajectories are built BEFORE
        # the VTL synthesis so the display can start on real engine data
        # while the audio renders (brief §6.2, start-early). The .polar
        # content is byte-identical to what Pipeline.run(polar=True)
        # writes — same engine functions, same parameters.
        job.update(stage="trajectory", progress=0.12)
        warnings: List[str] = []
        sampa = _resolve_sampa(req, warnings)
        job["sampa"] = sampa
        structure = None
        polar_path = out_dir / f"{stem}.polar"
        if req.engine == "syl":
            try:
                # '%' is engine syntax wherever it appears (not only under
                # expressive prosody): give breath nodes their 130 ms
                breath_ms = BREATH_MS if "%" in sampa else None
                structure = structure_compile(sampa, req.lang, req.timings, breath_ms)
                job["structure"] = structure
                job["anchors"] = structure["anchors"]
                job["block_count"] = structure["metrics"]["segments"]
                from vtl_synth.video.polar_video import build_polar, write_polar
                t_cons = max(1, round(t["tcons"] / 10.0))
                t_voy = max(1, round(t["tvoy"] / 10.0))
                polar_data = build_polar(_phrases_of(sampa), t_cons=t_cons, t_voy=t_voy,
                                         pause_short_ms=t["tpause"],
                                         pause_long_ms=t["tpauseLong"])
                write_polar(polar_path, polar_data)
                job.setdefault("paths", {})["polar"] = str(polar_path)
                job["polar_ready"] = True
            except Exception as exc:
                job.setdefault("notes", []).append(
                    f"early polar stage failed ({type(exc).__name__}: {exc}); "
                    "the display will wait for the engine's own polar export")
        else:
            job.setdefault("notes", []).append(
                "legacy engine: the continuous anchor display requires the syl engine")

        # ── stage 2 — full synthesis (tract + wav, [+ mp4]) ──
        stop = threading.Event()

        def tick() -> None:
            p = 0.18
            while not stop.wait(0.3):
                p = min(0.86, p + 0.02)
                with LOCK:
                    if job["state"] == "running":
                        job["progress"] = p
                        if p > 0.3: job["stage"] = "vtl"

        threading.Thread(target=tick, daemon=True).start()

        result = pipe.run(req.text, output_dir=str(out_dir), use_g2p=use_g2p,
                          video=video, label=req.label, polar=req.outputMode == "polar",
                          sampa_guard=req.guardPolicy)
        stop.set()

        if job["cancelled"]:
            job.update(state="cancelled", stage="wav", progress=1.0,
                       error="cancelled during run (result discarded)",
                       error_class="Cancelled")
            return

        stem = result.tract_path.stem
        files = []
        paths: Dict[str, str] = dict(job.get("paths") or {})
        for p in sorted(out_dir.glob(f"{stem}.*")):
            kind = p.suffix.lstrip(".").lower()
            # the polar file stays registered in `paths` (the continuous
            # display reads it) but is only OFFERED as a download when the
            # optional-exports flag was on for the job (brief §5.6: wav and
            # sampa text are always offered; tract/polar behind the flag)
            offered = kind == "wav" or kind == "txt" or req.exports
            if offered:
                files.append({"name": p.name, "kind": "wav" if kind == "wav" else kind,
                              "size": f"{p.stat().st_size / 1024:.0f} KiB",
                              "url": f"/api/job/{job_id}/files/{p.name}",
                              "available": True})
            paths[p.name] = str(p)

        # if the early polar stage was skipped/failed but the engine wrote
        # its own .polar (polar video mode), adopt it and rebuild structure
        if not job.get("polar_ready") and result.polar_path and Path(result.polar_path).exists():
            paths["polar"] = str(result.polar_path)
            if structure is None:
                try:
                    structure = structure_compile(result.sampa, req.lang, req.timings)
                    job["structure"] = structure
                    job["anchors"] = structure["anchors"]
                    job["block_count"] = structure["metrics"]["segments"]
                except Exception:
                    pass
            job["polar_ready"] = True

        job.update(
            state="done", stage="wav" if not video else "video", progress=1.0,
            wav_ready=True,
            result={
                "sampa": result.sampa, "warnings": result.warnings,
                "duration": result.duration_s, "frames": result.n_frames,
                "phrases": len(result.phrases),
                "files": files, "label": stem,
                "wav_url": f"/api/job/{job_id}/files/{stem}.wav",
            })
        job["paths"] = paths
        with LOCK:
            SYNTH_CACHE[job["cache_key"]] = job_id
            SYNTH_CACHE.move_to_end(job["cache_key"])
            while len(SYNTH_CACHE) > SYNTH_CACHE_MAX:
                SYNTH_CACHE.popitem(last=False)
    except Exception as exc:
        cls = type(exc).__name__
        job.update(state="error", error=str(exc), error_class=cls,
                   error_hint=ERROR_HINTS.get(cls, ""))


@app.get("/api/job/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, f"unknown job {job_id}")
    out = {k: v for k, v in job.items() if k not in ("paths", "cache_key", "structure")}
    # brief-style summary fields (annex A.3) — anchors + block_count come
    # from the engine structure; duration lands with the wav
    out["duration_s"] = (job.get("result") or {}).get("duration")
    out["block_count"] = job.get("block_count")
    return out


@app.get("/api/job/{job_id}/polar")
def job_polar(job_id: str, mode: str = "full") -> Dict[str, Any]:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, f"unknown job {job_id}")
    return build_segment_payload(job, 0, "full")


@app.post("/api/job/{job_id}/cancel")
def cancel_job(job_id: str) -> Dict[str, Any]:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    job["cancelled"] = True
    if job["state"] == "queued":
        job.update(state="cancelled", error="cancelled before start",
                   error_class="Cancelled")
    elif job["state"] == "running":
        job.update(state="cancelling")
    return {"ok": True, "state": job["state"]}


@app.get("/api/job/{job_id}/files/{name}")
def job_file(job_id: str, name: str) -> FileResponse:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    path = (job.get("paths") or {}).get(name)
    if not path or not Path(path).exists():
        raise HTTPException(404, f"file {name} not found")
    return FileResponse(path, filename=name)


# ──────────────────────────────────────────────────────────────────────
# Static UI
# ──────────────────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory=str(ROOT), html=True), name="ui")

def _warmup() -> None:
    try:
        profile = _profile("en")
        profile.g2p_callable("warmup", warnings=[])
    except Exception:
        pass


# warm-up: the first G2P call loads the lexicon/rules (can take seconds on
# a cold start — it once exceeded the UI's preview timeout). It must NOT
# run in a thread at module import: importing vtl_synth modules in a
# background thread races uvicorn's own imports on the per-module import
# locks and can deadlock the event loop (observed). So:
#   * __main__ runs it SYNCHRONOUSLY before uvicorn starts (server comes
#     up fully warm), and
#   * the startup event covers `uvicorn server:app`, where imports are
#     already complete when the loop starts.
@app.on_event("startup")
def _warm_startup() -> None:
    if getattr(app.state, "_warmed", False):
        return
    app.state._warmed = True
    threading.Thread(target=_warmup, daemon=True).start()


if __name__ == "__main__":
    import uvicorn
    _warmup()                                   # synchronous, pre-server
    app.state._warmed = True
    print("COVTL Console v3 — http://127.0.0.1:8421")
    print(f"engine: {'LIVE (vtl_synth ' + ENGINE_VERSION + ')' if LIVE else 'MOCK (vtl_synth not importable)'}")
    print("preview: POST /api/preview · compile: POST /api/compile · synthesis: POST /api/synthesize")
    print("polar segments: GET /api/job/{id}/polar")
    uvicorn.run(app, host="127.0.0.1", port=8421, log_level="warning")
