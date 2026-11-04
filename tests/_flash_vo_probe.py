# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Nasal-hiatus VO probe for the flash e2e run — executed by the SCRATCH
venv interpreter (the one that pip-installed the console wheel), because
only that environment has the engine (vtl_synth) and numpy.

Recomputes the engine's own nasal_hiatus_intervals for a phrase (same
call chain as build_phrase_tract / the bridge's early polar stage),
loads the synthesized .tract file and measures the velum-opening column
(numpy column 7 of the native 30-column layout) inside those windows —
never over file halves.

Usage (from flash_e2e.py):
    python _flash_vo_probe.py <tract.txt> <phrase>

Prints one JSON object on stdout:
    {"n_rows": n, "intervals": [[r0, r1, key], ...],   # rows in the file
     "nasal_core_means": [...],   # mean VO over the middle half
     "nasal_max": [...],          # max VO inside each interval
     "bg_windows": [[r0, r1], ...], "bg_means": [...]}
"""
import json
import sys

import numpy as np


def main() -> int:
    tract_path, phrase = sys.argv[1], sys.argv[2]
    from vtl_synth.core.continuous import _normalize_ipa
    from vtl_synth.core.syltraj import _normalize_word
    from vtl_synth.core.nasal_preproc import (split_nasal_hiatus,
                                              nasal_hiatus_intervals,
                                              _background_groups)
    import vtl_synth.core.syltraj as syl

    data = np.loadtxt(tract_path)
    vo = data[:, 7]                       # velum opening (native layout)

    # exact engine walk for en defaults: t_cons 100 ms -> 10 steps,
    # t_voy 80 ms -> 8 steps (the console's LANG_DEFAULTS["en"])
    ipa = _normalize_ipa(_normalize_word(phrase))
    motor, plan = split_nasal_hiatus(ipa)
    _, blocks, _, _ = syl.build_phrase_pval(
        motor, t_cons=10, t_voy=8, pause_short_ms=200.0,
        pause_long_ms=320.0, sampa_guard="off")
    ivs = nasal_hiatus_intervals(blocks, plan, t_voy=8)

    # the walk runs at 100 Hz; the .tract file is written at the VTL
    # target rate (400 Hz) — map step windows onto rows
    n_steps = sum(int(b.n_steps) for b in blocks)
    scale = len(vo) / n_steps if n_steps else 1.0

    def to_rows(t0: int, t1: int):
        return int(round(t0 * scale)), int(round(t1 * scale))

    def core_mean(r0: int, r1: int) -> float:
        # middle half: the VO ramps are capped at n//4 per side, so the
        # core is pure nasal plateau (VO_NASALIZED_VOWEL = 0.5)
        a, b = r0 + (r1 - r0) // 4, r1 - (r1 - r0) // 4
        if b <= a:
            a, b = r0, r1
        a, b = max(0, a), min(b, len(vo))
        return float(np.mean(vo[a:b])) if b > a else float("nan")

    out = {
        "n_rows": int(len(vo)),
        "tract_hz_per_step": round(scale, 4),
        "intervals": [list(to_rows(t0, t1)) + [k] for t0, t1, k in ivs],
        "nasal_core_means": [], "nasal_max": [],
        "bg_windows": [list(to_rows(g0, g0 + gt))
                       for g0, gt in _background_groups(blocks)],
    }
    for t0, t1, _ in ivs:
        r0, r1 = to_rows(t0, t1)
        out["nasal_core_means"].append(core_mean(r0, r1))
        out["nasal_max"].append(
            round(float(np.max(vo[max(0, r0):min(r1, len(vo))])), 4)
            if min(r1, len(vo)) > max(0, r0) else 0.0)
    out["bg_means"] = [
        float(np.mean(vo[max(0, r0):min(r1, len(vo))]))
        if min(r1, len(vo)) > max(0, r0) else float("nan")
        for r0, r1 in out["bg_windows"]]
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
