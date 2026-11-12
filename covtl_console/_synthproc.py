# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthesis runner executed in a worker subprocess (N2 fix, 2026-11-07).

Why a subprocess
----------------
The VTL audio stage runs through ``vocaltractlab_cython.synth_block`` —
a native C/C++ extension that does NOT release the GIL.  Running it in
a Python thread (the historical bridge worker) starves the uvicorn
event loop and the Starlette threadpool: /api/health stopped answering
for >= 30 s on a 570-character job and for ~13 minutes on a
4 900-character job (audit N2).  In a separate PROCESS the GIL is
irrelevant: the console stays responsive while the engine works.

Design
------
* The runner lives in its own module — a fresh interpreter (spawn start
  method, Windows) imports THIS file only, not the whole bridge (no
  FastAPI app, no UI mount, no warm-up).
* The payload and the result are plain picklable dictionaries: paths
  travel as strings, the engine result is flattened to the fields the
  bridge actually consumes.
* The pool is created by the bridge with ``max_workers=1``: synthesis
  jobs are serialized (the engine is CPU-bound on one core anyway) and
  the global-state semantics of the speaker registry stay safe.
  In-process fallback (same function!) covers environments where no
  process pool can be created.
"""
from __future__ import annotations

from typing import Any, Dict


def run_synthesis(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Builds a Pipeline from primitive kwargs and runs the full chain.

    Parameters
    ----------
    payload : dict
        ``pipeline``: Pipeline(**payload["pipeline"]) constructor kwargs;
        ``text``, ``output_dir`` (absolute path str), ``use_g2p``,
        ``video``, ``label`` (already sanitized by the bridge, N3),
        ``polar``, ``sampa_guard``: Pipeline.run parameters.

    Returns
    -------
    dict
        sampa, warnings, phrases (count), duration_s, n_frames,
        tract_path / wav_path / polar_path / mp4_path (str or None),
        stem (the engine's resolved file stem).
    """
    from vtl_synth import Pipeline

    pipe = Pipeline(**payload["pipeline"])
    result = pipe.run(
        payload["text"],
        output_dir=payload["output_dir"],
        use_g2p=payload["use_g2p"],
        video=payload["video"],
        label=payload["label"],
        polar=payload["polar"],
        sampa_guard=payload["sampa_guard"],
    )
    return {
        "sampa": result.sampa,
        "warnings": list(result.warnings),
        "phrases": len(result.phrases),
        "duration_s": result.duration_s,
        "n_frames": int(result.n_frames),
        "tract_path": str(result.tract_path),
        "wav_path": str(result.wav_path),
        "polar_path": (str(result.polar_path)
                       if result.polar_path is not None else None),
        "mp4_path": (str(result.mp4_path)
                     if getattr(result, "mp4_path", None) is not None
                     else None),
        "stem": result.tract_path.stem,
    }
