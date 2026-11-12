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

# UI assets ship INSIDE the package (pip installs serve them from
# site-packages); synthesis artifacts land in the current working
# directory's out/ — the same place when run from a repository checkout.
ASSETS = Path(__file__).resolve().parent / "ui"
OUT_ROOT = Path.cwd() / "out"
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

# Cross-word sandhi (covtl-sandhi) — guarded capability probe. The engine
# ships Branch A (the hook + a stub whose every entry point is the
# identity, SANDHI_FULL=False); the RULES live in the companion package
# (Branch B — https://github.com/FBerthommier/covtl-sandhi), resolved by
# the same two states the engine's Pipeline accepts: copied over the stub
# or pip-installed (top-level 'sandhi' import). SANDHI stays None until a
# rule package is actually present: every consumer then degrades with a
# clear message instead of crashing the bridge — mirrors the engine's own
# degradation (requested level -> off + warning, bit-identical outputs).
SANDHI = None
try:
    from vtl_synth.utils import sandhi as _sandhi_hook
    _sandhi_pkg = _sandhi_hook
    if not getattr(_sandhi_pkg, "SANDHI_FULL", False):
        try:
            import sandhi as _sandhi_full              # pip covtl-sandhi
            _sandhi_pkg = _sandhi_full
        except Exception:
            pass
    if getattr(_sandhi_pkg, "SANDHI_FULL", False):
        SANDHI = _sandhi_pkg
except Exception:
    SANDHI = None


def sandhi_capability() -> Dict[str, Any]:
    """What the bridge can offer for cross-word sandhi (liaison)."""
    if SANDHI is None:
        return {"available": False, "levels": ["off"], "modes": ["g2p"],
                "languages": [],
                "reason": "covtl-sandhi rule package (Branch B) not "
                          "installed on the engine — levels degrade to "
                          "'off' with a warning"}
    return {"available": True, "levels": list(SANDHI.SANDHI_LEVELS),
            "modes": list(SANDHI.SANDHI_MODES),
            "languages": sorted(SANDHI.SANDHI_LANGS)}

SPEAKERS = [
    {"id": "jd3", "name": "JD3", "origin": "reference (SynthVTL24b original)", "f0": 102.216},
    {"id": "s1",  "name": "S1",  "origin": "DVTD MRI subject 1 (male), calibrated v3", "f0": 114.908},
    {"id": "s2",  "name": "S2",  "origin": "DVTD MRI subject 2 (female), calibrated v3", "f0": 181.008},
    {"id": "m01", "name": "M01", "origin": "official VTL 2.4 ZIP (male)", "f0": 120.0},
    {"id": "w02", "name": "W02", "origin": "official VTL 2.4 ZIP (female)", "f0": 232.5},
]
# Speaker layer semantics (audit N1 fix, 2026-11-07): a per-request
# speaker is VALIDATED against the registry and two layers follow it
# in-process (orthogonal branch .speaker file + f0 from the registry
# entry — distinct audio per speaker); the geometry/constants layer
# and the audio anatomy (wheel resource loaded at DLL import) remain
# process-global — a FULL swap still goes through install_speaker.py
# + restart (the wheel exposes no hot reload).
SPEAKER_LAYERS = {
    "per_request": ["orthogonal_branch (VS/VO/TRX/TRY/TS3)", "f0"],
    "process_global": ["geometry/constants", "audio anatomy (wheel resource)"],
    "full_swap": "install_speaker.py + server restart",
}
# N2 (audit 2026-11-07): server-side bound on the synthesis text.
# The UI already caps its input at 2 000 characters (app.js MAX_CHARS);
# the API used to accept anything — 4 900 characters froze /api/health
# for ~13 minutes. The bound matches the UI and is documented in the
# 422 payload; the VTL stage ALSO runs in a subprocess now, so an
# in-bound 2 000-character job no longer stalls the console either.
MAX_SYNTH_CHARS = 2000
# N3 (audit 2026-11-07): an explicit label becomes a file stem inside
# out/ — validation happens at request time (422) and the surviving
# characters are sanitized exactly like the engine's sanitize_label.
_LABEL_SEPARATORS = re.compile(r"[\\/:]")
_LABEL_UNSAFE = re.compile(r"[^A-Za-z0-9_.\-]")
_LABEL_MAX = 64
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
    "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3",
    "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}
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


# NOTE: nasal-vowel + linked-vowel sequences (V~.V) are handled by the
# engine since the V1V2 fix (nasal_preproc + VO gate over the hiatus
# background arc) — no warning needed; the compiler labels the hiatus
# stretch with its vowels instead.


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


# ───────────────────────────────────────────────────────────────────────
# Request validation — N1/N2/N3 (audit 2026-11-07)
# ───────────────────────────────────────────────────────────────────────

def _canonical_speaker(speaker: str) -> Optional[str]:
    """Canonical registry name for ``speaker`` (case-insensitive).

    Returns the registered canonical name ('JD3' → 'jd3'), the
    ``"__unknown__"`` sentinel for a name that is NOT registered, or
    ``None`` when the speaker registry itself is unavailable (degraded
    engine — validation is then skipped and the engine keeps its
    historical label semantics).
    """
    try:
        from vtl_synth.core import speaker_registry as sr
        if not sr.registry_available():
            return None
        names = sr.list_speakers()
    except Exception:
        return None
    wanted = str(speaker or "").strip().lower()
    for n in names:
        if n.lower() == wanted:
            return n
    return "__unknown__"


def validate_synth_request(req: "SynthRequest") -> Optional[JSONResponse]:
    """Pre-flight validation for POST /api/synthesize.

    Returns an error response (422) or None when the request is
    acceptable. Runs BEFORE any job is created — a rejected request
    leaves no trace in JOBS (same contract as the guard 422).

    N2 — text length bound: MAX_SYNTH_CHARS (2 000, the UI's own cap).
    N1 — speaker must be a REGISTERED name (unknown → 422 instead of
         the former silent acceptance with jd3 audio).
    N3 — label must not contain path separators / control characters,
         Windows reserved names, or exceed _LABEL_MAX characters.
    """
    text = req.text or ""
    if len(text) > MAX_SYNTH_CHARS:
        return api_error(
            422, "TextTooLong",
            f"text is {len(text)} characters — the server bound is "
            f"{MAX_SYNTH_CHARS} (the UI enforces the same cap). Long "
            "inputs monopolize the synthesis engine for minutes; "
            "split the text into sentences and synthesize them "
            "separately.")
    if LIVE:
        canonical = _canonical_speaker(req.speaker)
        if canonical == "__unknown__":
            try:
                from vtl_synth.core import speaker_registry as sr
                registered = "/".join(sr.list_speakers())
            except Exception:
                registered = "jd3/s1/s2/m01/w02"
            return api_error(
                422, "UnknownSpeaker",
                f"unknown speaker {req.speaker!r} — registered: "
                f"{registered}. Speaker names are validated against "
                "vtl_synth/data/speakers/registry.json (full swap of "
                "the geometry/audio-anatomy layers: install_speaker.py "
                "+ restart).")
    label = req.label
    if label is not None:
        if _LABEL_SEPARATORS.search(label):
            return api_error(
                422, "InvalidLabel",
                f"label must not contain path separators ('/', '\\', ':'): "
                f"{label!r} — labels become file names inside out/.")
        if any(ord(ch) < 32 for ch in label):
            return api_error(
                422, "InvalidLabel",
                f"label must not contain control characters: {label!r}")
        if len(label) > _LABEL_MAX:
            return api_error(
                422, "InvalidLabel",
                f"label is {len(label)} characters — the bound is "
                f"{_LABEL_MAX}.")
        probe = label.rstrip("._").upper()
        if probe and probe in _WINDOWS_RESERVED:
            return api_error(
                422, "InvalidLabel",
                f"label {label!r} is a reserved device name on Windows.")
    return None


def sanitize_request_label(label: Optional[str]) -> Optional[str]:
    """Sanitizes an ALREADY VALIDATED label (N3 defense in depth).

    Mirrors the engine's sanitize_label: every character outside
    [A-Za-z0-9_.-] maps to '_' — neutralizes glob metacharacters that
    a downstream ``glob(f'{stem}.*')`` would expand ('*', '?', '[')
    and any other filename-hostile character. Dots are kept (the
    engine's label_of keeps them: 'ta~.a~ta' → 'ta_.a_ta').
    """
    if label is None:
        return None
    return _LABEL_UNSAFE.sub("_", label)


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
    """One phrase → dict(anchors, blocks, nodes, n_steps) with anchor times.

    Mirrors the engine's build_phrase_tract: normalize, then oralize the
    nasal members of linked hiatuses (V~.V, nasal_preproc V1V2) before the
    walk — nasality is re-injected in the audio layer (VO gate); the plan
    keeps the hiatus as a background diphthong arc, labeled with its
    vowels below. Requires an engine carrying the V1V2 fix: with an older
    engine the import fails and the walk falls back to the raw normalized
    phrase (conservative, pre-V1V2 behavior)."""
    import vtl_synth.core.syltraj as syl
    from vtl_synth.core.continuous import _normalize_ipa
    from vtl_synth.core.syltraj import _normalize_word as _syl_norm

    ipa = _normalize_ipa(_syl_norm(phrase))
    try:
        from vtl_synth.core.nasal_preproc import split_nasal_hiatus, \
            nasal_hiatus_intervals
        motor, nasal_plan = split_nasal_hiatus(ipa)
        nasal_plan["intervals"] = None
    except ImportError:
        # engine without the V1V2 fix: conservative fallback
        motor, nasal_plan = ipa, {"runs": [], "events": []}

        def nasal_hiatus_intervals(block_info, plan, t_voy=None):
            return []

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
            motor, t_cons=t_cons, t_voy=t_voy,
            pause_short_ms=pause_short_ms, pause_long_ms=pause_long_ms,
            pause_breath_ms=pause_breath_ms, sampa_guard="off")
    finally:
        syl.SylBlock = orig_block
        syl._collect_consonants = orig_cc

    try:
        hiatus_intervals = nasal_hiatus_intervals(
            ledger, nasal_plan, t_voy=int(round(t_voy)))
    except Exception:
        hiatus_intervals = []

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

    def _mute_label(a) -> str:
        """Muted anchor label: key of the vowel whose point this anchor's
        pt derives from (theta match, nearest node index), suffixed '*'.
        '*' alone when no vowel node matches."""
        best, best_d = None, None
        if a.pt:
            for i, n in enumerate(nodes):
                if n.kind != "V":
                    continue
                d_theta = abs(float(n.theta) - float(a.pt[1]))
                d_idx = abs(i - a.i)
                if best_d is None or (d_theta, d_idx) < best_d:
                    best, best_d = n, (d_theta, d_idx)
            if best is not None:
                return str(best.key) + "*"
        return "*"

    out_anchors = [
        {"i": k, "t": anchor_t[k] / 100.0, "kind": a.kind,
         "label": _mute_label(a) if (a.is_vowel_onset or a.is_word_end)
                  else _node_key(a),
         "mute": bool(a.is_vowel_onset or a.is_word_end),
         "syl_onset": bool(a.is_syl_vowel_onset),
         "long": bool(a.long), "breath": bool(a.breath),
         "hold": bool(a.hold), "word_end": bool(a.is_word_end),
         "pt": ([float(a.pt[0]), float(a.pt[1])] if a.pt else None)}
        for k, a in enumerate(anchors)
    ]
    step = 0
    out_blocks = []
    for b in ledger:
        rec = {
            "kind": b.kind, "n_steps": int(b.n_steps),
            "t0": step / 100.0, "t1": (step + b.n_steps) / 100.0,
            "n_cons": int(b.n_cons), "cons_keys": list(b.cons_keys),
            "vowel_key": b.vowel_key, "pre": b.pre_token, "post": b.post_token,
            "long": bool(b.long), "breath": bool(b.breath),
        }
        if b.kind == "background" and hiatus_intervals:
            # hiatus members realized as this background arc (nasal_preproc);
            # label with the ORIGINAL nasal notation from the plan runs
            # (node keys are oral bases — nasality is a flag there)
            keys = [k for (t0, t1, k) in hiatus_intervals
                    if t0 < step + b.n_steps and t1 > step]
            if keys:
                # adjacent nasal members arrive MERGED into one interval
                # (V~.V~: the velum stays open start-to-end) with their
                # base keys joined by '+' — re-derive the nasal notation
                # from the plan runs instead of showing the merged key
                merged = "+".join(keys)
                labels = []
                for run in (nasal_plan.get("runs") or []):
                    run_keys = "+".join(m["key"] for m in run)
                    if any(m["key"] in keys for m in run) or run_keys == merged:
                        labels.append(".".join(
                            m["key"] + ("~" if m.get("nasal") else "")
                            for m in run))
                rec["hiatus"] = " + ".join(labels) or merged
        out_blocks.append(rec)
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


def segment_notation(a0: Dict[str, Any], a1: Dict[str, Any],
                     span_blocks: List[Dict[str, Any]]) -> str:
    """Tile notation for ONE anchor-to-anchor segment:
    FROM · CONSONANTS · TO (no consonants: FROM·TO).

    FROM / TO are the bounding anchor labels --- a real vowel keeps its key,
    a muted anchor carries the key of the vowel its point derives from plus
    '*' (e.g. "i*"); pauses and terminals keep "␣" "|" "%" "▸" "◂".
    CONSONANTS is the concatenated cons_keys of the cluster blocks strictly
    inside the interval. '·' is a field separator, NOT an anchor: "i·b·a" is
    a single segment i → a whose interior consonant block is b."""
    frm = a0.get("label") or "*"
    to = a1.get("label") or "*"
    cons = "".join(ck for b in span_blocks if b.get("kind") == "cluster"
                   for ck in (b.get("cons_keys") or []))
    return "·".join(x for x in (frm, cons, to) if x)


def build_segment_payload(job: Dict[str, Any], from_k: int = 0,
                          mode: str = "inc") -> Dict[str, Any]:
    """Merge the recorded structure (anchors/blocks) with the .polar
    trajectories into the anchor-to-anchor segment payload."""
    polar_path = (job.get("paths") or {}).get("polar")
    if not polar_path or not Path(polar_path).exists():
        raise HTTPException(404, "polar data not available for this job")
    doc = json.loads(Path(polar_path).read_text(encoding="utf-8"))
    st = job.get("structure") or {}
    return _segments_from(doc, st.get("anchors") or [], st.get("blocks") or [],
                          job_id=job["id"], from_k=from_k, mode=mode)


def _segments_from(polar_doc: Dict[str, Any], anchors: List[Dict[str, Any]],
                   blocks: List[Dict[str, Any]], job_id: str = "",
                   from_k: int = 0, mode: str = "inc") -> Dict[str, Any]:
    """Data-level segment payload from a .polar-shaped doc + structure."""
    if not anchors:
        raise HTTPException(404, "anchor structure not recorded for this job")

    traj = polar_doc.get("trajectory") or {}
    vr = traj.get("vocalic", {}).get("rho", [])
    vt = traj.get("vocalic", {}).get("theta", [])
    cr = traj.get("consonantal", {}).get("rho", [])
    ct = traj.get("consonantal", {}).get("theta", [])
    n_steps = polar_doc.get("n_steps") or len(vr)
    rho_max = _rho_max_of(polar_doc)

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
            "notation": segment_notation(a0, a1, span_blocks),
            "blocks": [{kk: b.get(kk) for kk in ("kind", "n_steps", "cons_keys",
                                                 "vowel_key", "long", "breath",
                                                 "hiatus", "t0", "t1")}
                       for b in span_blocks],
            "markers": markers,
            "points": points,
        })
    if mode == "full":
        anchors_out = anchors
    else:
        anchors_out = anchors[max(0, from_k):max(0, from_k) + len(segs_out) + 1]
    return {
        "job_id": job_id,
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
    sandhi: str = "off"                  # cross-word sandhi level (covtl-sandhi)
    sandhi_mode: str = "g2p"             # gateway implementation


class GuardRequest(BaseModel):
    sampa: str
    policy: Optional[str] = None


class CompileRequest(BaseModel):
    text: str                            # phonetic SAMPA (syllable blocks)
    lang: str = "en"
    timings: Dict[str, float] = {}
    guard_policy: str = "warn"
    expressive: bool = False             # accepted for key symmetry; breath via '%'
    sandhi: str = "off"                  # accepted for symmetry; SAMPA has no
    sandhi_mode: str = "g2p"             #   orthography — a level yields a warning


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
    sandhi: str = "off"                  # cross-word sandhi level (covtl-sandhi)
    sandhi_mode: str = "g2p"


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
    return (req.text or "", req.sampa or "", req.mode, req.lang,
            bool(req.expressive), str(req.sandhi or "off").lower(),
            str(req.sandhi_mode or "g2p").lower())


SANDHI_LEVELS = ("off", "minimal", "standard", "careful")
SANDHI_MODES = ("g2p", "post", "pre")


def _resolve_sandhi(req: PreviewRequest, warnings: List[str]
                    ) -> Tuple[str, str]:
    """Validate the requested level/mode and degrade with a clear
    warning, never silently — mirrors Pipeline.run's degradation order:
    off for phonetic input (no orthography), off when the covtl-sandhi
    rule package (Branch B) is missing, off for languages without a
    rule module."""
    level = str(req.sandhi or "off").lower()
    mode = str(req.sandhi_mode or "g2p").lower()
    if level not in SANDHI_LEVELS:
        raise HTTPException(422, f"sandhi must be one of "
                                 f"{'/'.join(SANDHI_LEVELS)}, got {req.sandhi!r}")
    if mode not in SANDHI_MODES:
        raise HTTPException(422, f"sandhi_mode must be one of "
                                 f"{'/'.join(SANDHI_MODES)}, got {req.sandhi_mode!r}")
    if level == "off":
        return level, mode
    if req.sampa is not None or req.mode == "phonetic":
        warnings.append("sandhi ignored: the input is a phonetic SAMPA "
                        "string — the level applies to the text→SAMPA "
                        "(G2P) stage")
        return "off", mode
    if SANDHI is None:
        warnings.append("covtl-sandhi rule package (Branch B) not "
                        "installed on the engine — sandhi "
                        f"{level!r} degrades to 'off'")
        return "off", mode
    if not SANDHI.sandhi_supported(req.lang):
        warnings.append(f"sandhi {level!r} ignored: no rule module for "
                        f"{req.lang!r} "
                        f"({'/'.join(sorted(SANDHI.SANDHI_LANGS))})")
        return "off", mode
    return level, mode


def _apply_sandhi_ortho(req: PreviewRequest, text: str, level: str,
                        mode: str, profile, warnings: List[str]):
    """Text → SAMPA through the sandhi gateways — the exact monotone
    path of Pipeline.run (g2p gateway / post-processor / pre rewrite)."""
    g2p = profile.g2p_callable
    if mode == "g2p":
        # the gateway owns the g2p view: per-word oracle + pair merge
        return SANDHI.apply_sandhi_text(req.lang, text, g2p, level,
                                        "g2p", warnings)
    raw = g2p(text, warnings=warnings)
    if mode == "post":
        return SANDHI.apply_sandhi_text(req.lang, text, g2p, level,
                                        "post", warnings)
    return raw


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
        "sandhi": str(req.sandhi or "off").lower(),
        "sandhi_mode": str(req.sandhi_mode or "g2p").lower(),
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
            "active_lang": active_lang, "registry_warnings": warnings,
            "sandhi": sandhi_capability()}


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
    # N1 (audit 2026-11-07): the selector is now WIRED — a per-request
    # speaker changes the audio (orthogonal branch + f0). The payload
    # says so honestly, and still names the two layers that remain
    # process-global (geometry/constants + audio anatomy: full swap
    # through install_speaker.py + restart, the wheel has no hot
    # reload). Speakers are cross-checked against the engine registry:
    # an entry the registry does not know is marked unavailable instead
    # of being silently offered.
    registry_names = None
    if LIVE:
        try:
            from vtl_synth.core import speaker_registry as sr
            if sr.registry_available():
                registry_names = {n.lower() for n in sr.list_speakers()}
        except Exception:
            registry_names = None
    out = []
    for s in SPEAKERS:
        verified = s["id"] == "jd3"
        in_registry = (s["id"] in registry_names
                       if registry_names is not None else True)
        out.append({"id": s["id"], "label": f"{s['id']} — {s['origin']}",
                    "f0_default": s["f0"], "verified_with_lang": verified,
                    "active": (active or "").lower().startswith(s["id"]),
                    "per_request": True,          # selector is functional (N1)
                    "in_registry": in_registry})
    warning = UNVERIFIED_WARNING if lang != "en" else None
    return {"speakers": out, "warning_when_unverified": warning,
            "calibration_speaker": "jd3",
            "speaker_layers": SPEAKER_LAYERS}


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
    info["sandhi"] = sandhi_capability()
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
    sandhi_level, sandhi_mode = _resolve_sandhi(req, warnings)

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
        # sandhi 'pre' rewrites the orthography BEFORE the g2p stage —
        # both the expressive and the monotone path get it (Pipeline.run)
        text_in = req.text or ""
        if sandhi_level != "off" and sandhi_mode == "pre":
            text_in = SANDHI.sandhi_rewrite_text(
                req.lang, text_in, profile.g2p_callable, sandhi_level,
                warnings)
        if req.expressive:
            try:
                from vtl_synth.utils.prosody_f0 import plan_expressive_text
                plan_g2p = profile.g2p_callable
                if sandhi_level != "off" and sandhi_mode == "g2p":
                    # the gateway owns the per-word g2p view (closed-class
                    # fixes) — same construction as Pipeline.run
                    plan_g2p = (lambda gp: (lambda w, warnings=None, **kw:
                                            SANDHI.sandhi_oracle(
                                                req.lang, w, gp)))(
                                                profile.g2p_callable)
                sampa, _plans = plan_expressive_text(
                    text_in, req.lang, plan_g2p,
                    getattr(profile, "expressivity", None), warnings)
                if sandhi_level != "off" and sandhi_mode in ("g2p", "post"):
                    sampa = SANDHI.apply_sandhi_sampa(
                        req.lang, text_in, sampa, profile.g2p_callable,
                        sandhi_level, sandhi_mode, warnings)
            except Exception as exc:
                warnings.append(f"expressive preview unavailable ({exc}); monotone path used")
                sampa = profile.g2p_callable(text_in, warnings=raw_warnings)
            warnings.extend(w for w in raw_warnings if w not in warnings)
            g2p_string = sampa
        elif sandhi_level != "off":
            sampa = _apply_sandhi_ortho(req, text_in, sandhi_level,
                                        sandhi_mode, profile, warnings)
            raw = sampa                    # the gateway output IS the g2p view
            g2p_string = raw
        else:
            sampa = profile.g2p_callable(text_in, warnings=raw_warnings)
            warnings.extend(raw_warnings)
            g2p_string = sampa
        words = _word_chips(req.text or "", profile, raw_warnings,
                            g2p_override=(
                                lambda w: SANDHI.sandhi_oracle(
                                    req.lang, w, profile.g2p_callable))
                            if sandhi_level != "off" and SANDHI is not None
                            and sandhi_mode == "g2p" else None)

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
        "warnings": warnings,
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


def _word_chips(text: str, profile, warnings: List[str],
                g2p_override=None) -> List[Dict[str, Any]]:
    unknown = set(re.findall(r"kept verbatim\): '([^']+)'", " ".join(warnings)))
    words = re.findall(r"[A-Za-zÀ-ɏ'’]+", text)
    out = []
    for w in words:
        key = w.lower()
        if key in unknown:
            out.append({"word": w, "sampa": key, "known": False})
            continue
        try:
            g2p = g2p_override or profile.g2p_callable
            sampa = g2p(w, warnings=[])
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
    key = (req.text, req.lang, json.dumps(req.timings, sort_keys=True),
           str(req.sandhi or "off").lower(),
           str(req.sandhi_mode or "g2p").lower())
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
    if str(req.sandhi or "off").lower() != "off":
        # honest no-op notice: the compiler consumes SAMPA blocks, which
        # carry no orthography — the cross-word sandhi level acts at the
        # text→SAMPA stage (preview / synthesize). A liaison consonant
        # inserted there shows up in the plan like any onset cluster.
        warnings.append(
            "sandhi level ignored: the compiler takes SAMPA blocks — "
            "the cross-word sandhi level applies to the text→SAMPA "
            "stage (preview / synthesize)")
    breath_ms: Optional[float] = BREATH_MS if "%" in src else None
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
        hiatus = next((b["hiatus"] for b in span if b.get("hiatus")), "")
        label = ("".join(cons) + (vowel or "")) or hiatus or a0["label"] \
            or a1["label"] or "-"
        # tile notation (single definition, _segments_from shares it):
        # FROM · CONSONANTS · TO for one anchor-to-anchor segment
        notation = segment_notation(a0, a1, span)
        labeled.append({"segment_index": k, "t0": a0["t"], "t1": a1["t"],
                        "label": label, "notation": notation,
                        "label_to": a1["label"], "cons": cons, "vowel": vowel,
                        "kinds": [b["kind"] for b in span],
                        "n_steps": int(round((a1["t"] - a0["t"]) * 100))})

    # polar trajectories — the full symbolic output of syltraj (no audio):
    # the same engine functions the synthesis polar stage uses, so Compile
    # can populate the continuous display without any VTL run.
    polar_payload = None
    try:
        t = _timings_of(req.lang, req.timings)
        from vtl_synth.video.polar_video import build_polar, _jfloats
        from vtl_synth.core.continuous import _normalize_ipa
        from vtl_synth.core.syltraj import _normalize_word
        tc = max(1, round(t["tcons"] / 10.0))
        tv = max(1, round(t["tvoy"] / 10.0))
        phrases = [_normalize_ipa(_normalize_word(ph)) for ph in _phrases_of(src)]
        polar_data = build_polar(phrases, t_cons=tc, t_voy=tv,
                                 pause_short_ms=t["tpause"],
                                 pause_long_ms=t["tpauseLong"])
        doc = {
            "n_steps": polar_data["n_steps"],
            "inventory": polar_data["inventory"],
            "trajectory": {
                "vocalic": {"rho": polar_data["traj_v"][:, 0].tolist(),
                            "theta": polar_data["traj_v"][:, 1].tolist()},
                "consonantal": {"rho": _jfloats(polar_data["traj_c"][:, 0]),
                                "theta": _jfloats(polar_data["traj_c"][:, 1])},
            },
        }
        polar_payload = _segments_from(doc, st["anchors"], st["blocks"],
                                       job_id="compile", from_k=0, mode="full")
    except Exception as exc:
        warnings.append(f"polar trajectories unavailable: {exc}")

    out = {
        "source": src,
        "sampa": src,
        "anchors": st["anchors"],
        "blocks": st["blocks"],
        "nodes": st["nodes"],
        "metrics": st["metrics"],
        "segments_preview": labeled,
        "polar": polar_payload,
        "targets": targets,
        "rejected_symbols": rejected,
        "warnings": warnings,
        "inventory_digest": inventory_digest(),
        "sandhi": sandhi_capability(),
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

    # N1/N2/N3 pre-flight (audit 2026-11-07): bound, speaker registry,
    # label safety — BEFORE any job is created, on every path.
    rejected_request = validate_synth_request(req)
    if rejected_request is not None:
        return rejected_request

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
    sandhi_level = str(req.sandhi or "off").lower()
    sandhi_mode = str(req.sandhi_mode or "g2p").lower()
    echo = {"lang": req.lang, "speaker": req.speaker, "engine": req.engine,
            "ortho": req.ortho, "expressive": req.expressive, "guard": req.guardPolicy or "warn",
            "tcons": t["tcons"], "tvoy": t["tvoy"], "tpause": t["tpause"],
            "tpause_long": t["tpauseLong"], "engine_version": ENGINE_VERSION,
            "sandhi": sandhi_level, "sandhi_mode": sandhi_mode}
    # N1 honesty: when the requested speaker differs from the ACTIVE
    # (installed) one, the echo says which layers follow the request —
    # orthogonal branch + f0 — and which stay process-global.
    canonical = _canonical_speaker(req.speaker)
    if canonical is not None and canonical != "__unknown__":
        echo["speaker"] = canonical
        try:
            from vtl_synth.core import speaker_registry as _sr
            active = _sr.active_name()
        except Exception:
            active = None
        if active is not None and canonical != active:
            echo["speaker_note"] = (
                f"per-request layers: orthogonal branch + f0 ({canonical}); "
                f"geometry and audio anatomy still follow the installed "
                f"speaker '{active}' — full swap: install_speaker.py + "
                "server restart")
    if sandhi_level != "off" and SANDHI is None:
        # same degradation the engine will print — surfaced in the job
        # payload so the UI shows it without reading server stdout
        echo["sandhi_note"] = (
            "covtl-sandhi rule package (Branch B) not installed: "
            f"sandhi {sandhi_level!r} degrades to 'off' "
            "(bit-identical output)")
    job = {"id": job_id, "state": "queued", "stage": "g2p", "progress": 0.0,
           "created": time.time(), "error": None, "error_class": None, "error_hint": None,
           "result": None, "cancelled": False, "cache_key": key, "echo": echo,
           "polar_ready": False, "wav_ready": False, "anchors": None,
           "block_count": None, "structure": None}
    with LOCK:
        JOBS[job_id] = job
        _prune_jobs()
    # N3: the worker (and the engine) receive the SANITIZED label —
    # same string the early polar stage uses for its stem.
    safe_label = sanitize_request_label(req.label)
    threading.Thread(target=_worker, args=(job_id, req, safe_label),
                     daemon=True).start()
    return {"job_id": job_id, "cached": False, "echo": echo}


def _resolve_sampa(req: SynthRequest, warnings: List[str]) -> str:
    """Same G2P path as /api/preview and Pipeline.run (engine callables).

    When a cross-word sandhi level is requested, the SAME gateways as
    Pipeline.run are applied here — the early polar stage must see the
    SAMPA the engine will actually speak (compile plan == synth plan)."""
    if req.mode == "phonetic":
        return (req.text or "").strip()
    profile = _profile(req.lang)
    g2p = profile.g2p_callable
    text = req.text or ""
    level = str(getattr(req, "sandhi", "off") or "off").lower()
    mode = str(getattr(req, "sandhi_mode", "g2p") or "g2p").lower()
    if level != "off" and SANDHI is not None:
        if mode == "pre":
            text = SANDHI.sandhi_rewrite_text(req.lang, text, g2p, level,
                                              warnings)
        if req.expressive:
            plan_g2p = g2p
            if mode == "g2p":
                plan_g2p = (lambda gp: (lambda w, warnings=None, **kw:
                                        SANDHI.sandhi_oracle(req.lang, w,
                                                             gp)))(g2p)
            from vtl_synth.utils.prosody_f0 import plan_expressive_text
            sampa, _plans = plan_expressive_text(
                text, req.lang, plan_g2p,
                getattr(profile, "expressivity", None), warnings)
            if mode in ("g2p", "post"):
                sampa = SANDHI.apply_sandhi_sampa(req.lang, text, sampa,
                                                  g2p, level, mode, warnings)
            return sampa
        if mode == "g2p":
            return SANDHI.apply_sandhi_text(req.lang, text, g2p, level,
                                            "g2p", warnings)
        sampa = g2p(text, warnings=warnings)
        if mode == "post":
            sampa = SANDHI.apply_sandhi_text(req.lang, text, g2p, level,
                                             "post", warnings)
        return sampa
    if req.expressive:
        from vtl_synth.utils.prosody_f0 import plan_expressive_text
        sampa, _plans = plan_expressive_text(
            req.text or "", req.lang, profile.g2p_callable,
            getattr(profile, "expressivity", None), warnings)
        return sampa
    return profile.g2p_callable(req.text or "", warnings=warnings)


# ──────────────────────────────────────────────────────────────────────
# N2 — subprocess isolation of the VTL synthesis stage (audit 2026-11-07)
# ──────────────────────────────────────────────────────────────────────
# vocaltractlab_cython.synth_block is a native extension that does not
# release the GIL: in a Python thread it starved the uvicorn loop and
# the Starlette threadpool (/api/health unresponsive >= 30 s for a
# 570-character job, ~13 min for 4 900 — audit N2). The stage-2 run
# therefore executes in a dedicated worker PROCESS (GIL irrelevant);
# max_workers=1 serializes synthesis jobs (the engine is CPU-bound on
# one core) and keeps the registry's global state consistent.
_SYNTH_POOL = None                        # ProcessPoolExecutor | None
_SYNTH_POOL_LOCK = threading.Lock()
_SYNTH_POOL_BROKEN = False                # in-process fallback latched


def _synth_pool():
    """The singleton synthesis pool, or None when unavailable."""
    global _SYNTH_POOL, _SYNTH_POOL_BROKEN
    if _SYNTH_POOL_BROKEN:
        return None
    with _SYNTH_POOL_LOCK:
        if _SYNTH_POOL is None:
            try:
                from concurrent.futures import ProcessPoolExecutor
                _SYNTH_POOL = ProcessPoolExecutor(max_workers=1)
            except Exception:
                _SYNTH_POOL_BROKEN = True
                return None
        return _SYNTH_POOL


def _run_stage2(payload: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    """Executes the full synthesis stage and returns the result dict.

    Subprocess path (normal): the payload — plain picklable primitives
    — runs through covtl_console._synthproc.run_synthesis in the pool
    worker; engine exceptions cross the process boundary unchanged
    (pickle by reference) and land in the job error path as today.
    In-process fallback (degraded environments): the SAME function is
    called directly, with a job note saying the console may stall
    during long syntheses (the pre-fix behaviour, now explicit).
    """
    global _SYNTH_POOL_BROKEN
    from covtl_console import _synthproc
    pool = _synth_pool()
    if pool is not None:
        try:
            return pool.submit(_synthproc.run_synthesis, payload).result()
        except BrokenProcessPool:
            # worker died (shutdown / OS kill): latch the fallback and
            # retry once in-process — the job still completes.
            _SYNTH_POOL_BROKEN = True
            job.setdefault("notes", []).append(
                "synthesis subprocess pool broken — retrying in-process "
                "(the console may stall during long syntheses)")
        except Exception:
            raise                    # engine error: job error path, as before
    else:
        job.setdefault("notes", []).append(
            "synthesis subprocess isolation unavailable — running "
            "in-process (the console may stall during long syntheses)")
    return _synthproc.run_synthesis(payload)


@app.on_event("shutdown")
def _shutdown_synth_pool() -> None:
    """Stops the synthesis pool without waiting for an in-flight job.

    concurrent.futures joins its workers at interpreter exit; a
    minutes-long synthesis must not hold Ctrl+C hostage (the
    pre-fix daemon-thread behaviour). Best-effort terminate.
    """
    pool = _SYNTH_POOL
    if pool is None:
        return
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    # _processes is a dict {pid: Process} up to py3.11 and a list since
    # py3.12 — normalize before the best-effort terminate.
    procs = getattr(pool, "_processes", None) or ()
    if isinstance(procs, dict):
        procs = list(procs.values())
    for proc in list(procs):
        try:
            proc.terminate()
        except Exception:
            pass


def _worker(job_id: str, req: SynthRequest,
            safe_label: Optional[str] = None) -> None:
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
        # sandhi options exist only when the engine carries the
        # covtl-sandhi hook (Branch A); a level without the Branch B
        # rule package is passed through anyway — the Pipeline itself
        # degrades to off with a printed warning (bit-identical output)
        if "sandhi" in sig and str(getattr(req, "sandhi", "off") or "off").lower() != "off":
            kwargs["sandhi"] = str(req.sandhi).lower()
        if "sandhi_mode" in sig and str(getattr(req, "sandhi_mode", "g2p") or "g2p").lower() != "g2p":
            kwargs["sandhi_mode"] = str(req.sandhi_mode).lower()
        t = _timings_of(req.lang, req.timings)
        if "t_cons_ms" in sig: kwargs["t_cons_ms"] = t["tcons"]
        if "t_voy_ms" in sig: kwargs["t_voy_ms"] = t["tvoy"]
        if "pause_short_ms" in sig: kwargs["pause_short_ms"] = t["tpause"]
        if "pause_long_ms" in sig: kwargs["pause_long_ms"] = t["tpauseLong"]

        job.update(state="running", stage="g2p", progress=0.05)
        out_dir = (OUT_ROOT / re.sub(r"[^A-Za-z0-9_\-]", "_", req.outputDir or "out"))
        out_dir.mkdir(parents=True, exist_ok=True)
        use_g2p = req.mode == "ortho"
        video = req.outputMode != "audio"
        # The early-stage artifacts must land on the ENGINE's stem: after
        # the run, the offered-files glob matches result.tract_path.stem
        # (Pipeline.run derives it as (label or label_of(text)).rstrip('._')).
        # A divergent local sanitizer once wrote ta__a_ta.polar for the
        # input ta~.a~ta while the glob looked for ta_.a_ta.* — the polar
        # download silently vanished for any dotted input (finding F1).
        # Delegating to the engine's own label_of keeps the two identical
        # by construction (the import cannot fail: Pipeline above already
        # loaded this very module).
        #
        # N3 (audit 2026-11-07): an EXPLICIT label arrives here ALREADY
        # sanitized by the bridge (validate_synth_request +
        # sanitize_request_label — separators rejected 422, unsafe
        # characters mapped to '_'); the engine re-applies its own
        # sanitize_label (idempotent on this input), so both stems agree.
        from vtl_synth.core.pipeline import label_of as _engine_label_of
        stem = (safe_label if safe_label is not None
                else _engine_label_of(req.text or "output")).rstrip("._") \
            or "output"

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

        # N2 (audit 2026-11-07): the VTL stage runs in a WORKER
        # SUBPROCESS — the native synth_block holds the GIL for the
        # whole synthesis, which starved the uvicorn loop (health
        # unresponsive >= 30 s for 570 characters, ~13 min for 4 900).
        # max_workers=1 also serializes synthesis jobs (the engine is
        # CPU-bound on one core; the registry's global state stays
        # consistent). In-process fallback when no pool can be created.
        payload = {
            "pipeline": kwargs,
            "text": req.text,
            "output_dir": str(out_dir),
            "use_g2p": use_g2p,
            "video": video,
            "label": safe_label,
            "polar": req.outputMode == "polar",
            "sampa_guard": req.guardPolicy,
        }
        result = _run_stage2(payload, job)
        stop.set()

        if job["cancelled"]:
            job.update(state="cancelled", stage="wav", progress=1.0,
                       error="cancelled during run (result discarded)",
                       error_class="Cancelled")
            return

        stem = result["stem"]
        # Rate contract (maintainer-confirmed 2026-11-04, locked by
        # tests/test_synthesis.py::test_tract_400hz_walk_100hz_contract):
        # the .tract files are 400 Hz BY CONSTRUCTION (the engine's
        # TRACT_SR) and must stay so; the walk — structure blocks,
        # .polar payload, display — runs its own 100 Hz grid and every
        # consumer maps explicitly (4 tract rows per step, e.g.
        # tests/_flash_vo_probe.py).
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
        engine_polar = result.get("polar_path")
        if not job.get("polar_ready") and engine_polar and Path(engine_polar).exists():
            paths["polar"] = str(engine_polar)
            if structure is None:
                try:
                    structure = structure_compile(result["sampa"], req.lang, req.timings)
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
                "sampa": result["sampa"], "warnings": result["warnings"],
                "duration": result["duration_s"], "frames": result["n_frames"],
                "phrases": result["phrases"],
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
app.mount("/", StaticFiles(directory=str(ASSETS), html=True), name="ui")

def _warmup() -> None:
    try:
        profile = _profile("en")
        profile.g2p_callable("warmup", warnings=[])
    except Exception:
        pass


def main(argv: Optional[List[str]] = None) -> None:
    """Console entry point (`covtl-console` or `python server.py`).

    Warm-up is synchronous and pre-server: the first G2P call loads the
    lexicon/rules (seconds on a cold start) and must never happen inside
    the running loop (importing vtl_synth in a background thread races
    uvicorn's own imports — observed deadlock)."""
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser(
        prog="covtl-console",
        description="COVTL Lab Console — local bridge + UI "
                    "(http://127.0.0.1:8421)")
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1 — local only)")
    ap.add_argument("--port", type=int, default=8421,
                    help="bind port (default 8421)")
    args = ap.parse_args(argv)
    _warmup()                                   # synchronous, pre-server
    app.state._warmed = True
    print("COVTL Console v3 — "
          f"http://{args.host}:{args.port}")
    print(f"engine: {'LIVE (vtl_synth ' + ENGINE_VERSION + ')' if LIVE else 'MOCK (vtl_synth not importable)'}")
    print("preview: POST /api/preview · compile: POST /api/compile · synthesis: POST /api/synthesize")
    print("polar segments: GET /api/job/{id}/polar")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


# warm-up: the first G2P call loads the lexicon/rules (can take seconds on
# a cold start — it once exceeded the UI's preview timeout). It must NOT
# run in a thread at module import: importing vtl_synth modules in a
# background thread races uvicorn's own imports on the per-module import
# locks and can deadlock the event loop (observed). So:
#   * __main__ / the covtl-console entry point run it SYNCHRONOUSLY
#     before uvicorn starts (server comes up fully warm), and
#   * the startup event covers `uvicorn server:app`, where imports are
#     already complete when the loop starts.
@app.on_event("startup")
def _warm_startup() -> None:
    if getattr(app.state, "_warmed", False):
        return
    app.state._warmed = True
    threading.Thread(target=_warmup, daemon=True).start()


if __name__ == "__main__":
    main()
