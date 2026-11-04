#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""flash_e2e.py — the one-command flash install, proven end to end.

Builds the wheel from THIS checkout, installs it into a scratch venv
(bare — the engine and covtl-sandhi resolve from GitHub exactly like a
user's ``pip install covtl-console``), starts the installed entry point
as a subprocess and replays the real console chain over HTTP against
it. No TestClient, nothing from the repo on sys.path: everything the
server serves comes from site-packages.

Chain proven (numbers re-derived against the engine @453d0b7 + the
console timing table; see docs/flash-validation-report.md):

  health          live engine, sandhi available, 6 rule languages
  preview         fr "bonjour, comment allez-vous" @ standard
                  -> "bO~ZuR kOma~.ta.le.vu" (liaison t in comment-allez)
  compile         14 anchors / 20 blocks / 3.96 s (+/- 1 step)
  synthesize      polar_ready observed BEFORE wav_ready, WAV duration
                  = structure +/- 40 ms, polar payload in display degrees
  hiatus pairs    ta~.ata / ta.a~ta / ta~.a~ta -> 3 pairwise-distinct
                  WAVs; velum opening (VO, tract column 7) >= 0.4 (max)
                  and >= 0.3 (middle-half mean) inside the engine's
                  nasal_hiatus_intervals windows — never over file
                  halves; the 0.5 target ramps to -0.1 at the edges and
                  the 20 ms velar timer rounds the plateau, hence the
                  mean margin; oral control ta.ata stays <= 0.2 over
                  its background window
  liaison         fr "faut il" @ standard -> "fo.til"
  teardown        pip uninstall clean, scratch venv deleted

Usage:
    python tests/flash_e2e.py           # repo root or tests/ — same

Slow by design (wheel build + git dependency resolution + 5 synthesis
jobs; the engine wheel build dominates). Everything is logged to
flash_e2e.log in the current directory. Set FLASH_E2E_KEEP=1 to keep
the scratch venv for inspection on failure.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = Path(__file__).resolve().parent / "_flash_vo_probe.py"
LOG_PATH = Path("flash_e2e.log").resolve()

# worked-example expectations (engine @ covtl-pipeline main, LANG_DEFAULTS
# timings; the liaison variant carries the sandhi-inserted t in
# "comment allez-vous", hence 20 blocks / 3.96 s — the no-sandhi string
# compiles to 18 blocks / 3.68 s)
FR_TEXT = "bonjour, comment allez-vous"
FR_SAMPA = "bO~ZuR kOma~.ta.le.vu"
FR_ANCHORS, FR_BLOCKS, FR_SECONDS = 14, 20, 3.96
HIATUS_PAIRS = ("ta~.ata", "ta.a~ta", "ta~.a~ta")
ORAL_CONTROL = "ta.ata"
VO_NASAL_MIN, VO_ORAL_MAX = 0.4, 0.2

HEALTH_TIMEOUT_S = 420.0          # cold engine import + lexicon warm-up
JOB_TIMEOUT_S = 300.0
INSTALL_TIMEOUT_S = 1800.0


class Tee:
    def __init__(self, path: Path):
        self._fh = open(path, "w", encoding="utf-8", buffering=1)

    def __call__(self, *msg) -> None:
        line = " ".join(str(m) for m in msg)
        print(line, flush=True)
        self._fh.write(line + "\n")

    def close(self) -> None:
        self._fh.close()


log = Tee(LOG_PATH)


def fail(msg: str) -> None:
    raise AssertionError(msg)


def check(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)
    log("   ok:", msg if len(msg) < 100 else msg[:97] + "...")


def run(cmd, **kw) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    log("  $", " ".join(cmd))
    return subprocess.run(cmd, **kw)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(method: str, url: str, body=None, timeout: float = 90.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw) if raw else {}
    except ValueError:                    # not JSON — binary payload
        return raw


def wait_health(base: str) -> dict:
    deadline = time.time() + HEALTH_TIMEOUT_S
    last = ""
    while time.time() < deadline:
        try:
            h = http("GET", base + "/api/health", timeout=10.0)
            if h.get("status") in ("ok", "degraded"):
                return h
            last = f"status={h.get('status')!r}"
        except Exception as exc:                              # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(1.5)
    fail(f"server did not become healthy within {HEALTH_TIMEOUT_S:.0f}s "
         f"({last})")


def synth_job(base: str, **payload) -> dict:
    """POST + poll to completion; returns (job, saw_polar_before_wav)."""
    defaults = {"mode": "phonetic", "lang": "en", "speaker": "jd3",
                "outputMode": "audio", "guardPolicy": "warn",
                "exports": True, "outputDir": "e2e"}
    defaults.update(payload)
    out = http("POST", base + "/api/synthesize", defaults)
    job_id = out["job_id"]
    saw_polar_only = False
    deadline = time.time() + JOB_TIMEOUT_S
    while time.time() < deadline:
        time.sleep(0.25)
        job = http("GET", base + f"/api/job/{job_id}")
        if job.get("polar_ready") and not job.get("wav_ready"):
            saw_polar_only = True
        if job.get("state") in ("done", "error", "cancelled"):
            if job["state"] != "done":
                fail(f"job {job_id} ended {job['state']}: {job.get('error')}")
            return {"job": job, "saw_polar_only": saw_polar_only,
                    "job_id": job_id}
    fail(f"job {job_id} still running after {JOB_TIMEOUT_S:.0f}s")


def probe_vo(scratch_py: Path, tract: Path, phrase: str) -> dict:
    r = run([scratch_py, PROBE, tract, phrase],
            capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        fail(f"VO probe failed for {phrase!r}: {r.stderr[-800:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> int:
    scratch = Path(tempfile.mkdtemp(prefix="flash_e2e_"))
    server_proc = None
    server_log = None
    keep = os.environ.get("FLASH_E2E_KEEP") == "1"
    try:
        # ── phase 0 — build the wheel from this checkout ──────────────
        log("[0] building the wheel from the repo")
        if importlib.util.find_spec("build") is None:
            run([sys.executable, "-m", "pip", "install",
                 "build"]).check_returncode()
        dist = ROOT / "dist"
        r = run([sys.executable, "-m", "build", "--wheel", "--outdir", dist,
                 ROOT], capture_output=True, text=True,
                timeout=INSTALL_TIMEOUT_S, cwd=ROOT)
        if r.returncode != 0:
            log(r.stdout[-1500:], "\n", r.stderr[-1500:])
            fail("wheel build failed")
        wheels = sorted(dist.glob("covtl_console-*.whl"),
                        key=lambda p: p.stat().st_mtime)
        check(bool(wheels), f"wheel built: {wheels[-1].name}")
        wheel = wheels[-1]

        names = zipfile.ZipFile(wheel).namelist()
        ui = [n for n in names if n.startswith("covtl_console/ui/")]
        check("covtl_console/ui/index.html" in names,
              "wheel carries covtl_console/ui/index.html")
        check(any(n.endswith(".js") for n in ui)
              and any(n.endswith(".css") for n in ui),
              f"wheel carries the UI assets ({len(ui)} ui files)")

        # ── phase 1 — scratch venv + wheel install (the user path) ────
        log("[1] scratch venv + pip install <wheel> (git deps resolve)")
        run([sys.executable, "-m", "venv", scratch]).check_returncode()
        py = scratch / ("Scripts/python.exe" if os.name == "nt"
                        else "bin/python")
        entry = scratch / ("Scripts/covtl-console.exe" if os.name == "nt"
                           else "bin/covtl-console")
        env = {**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1",
               "PIP_PROGRESS_BAR": "off"}
        r = run([py, "-m", "pip", "install", "--no-input", wheel],
                capture_output=True, text=True, timeout=INSTALL_TIMEOUT_S,
                env=env)
        tail = "\n".join((r.stdout or "").strip().splitlines()[-12:])
        log(tail)
        if r.returncode != 0:
            fail("pip install of the wheel failed (see log above)")
        for needle in ("vtl-synth", "covtl-sandhi", "covtl-console",
                       "fastapi", "uvicorn"):
            check(needle in (r.stdout or ""),
                  f"pip resolved {needle} from the wheel metadata")
        check(entry.exists(), "entry point covtl-console installed")

        # ── phase 2 — wheel sanity in the scratch interpreter ─────────
        log("[2] wheel sanity: version + import from site-packages")
        r = run([py, "-c",
                 "import covtl_console as c, importlib.metadata as m; "
                 "print(c.__version__, m.version('covtl-console'))"],
                capture_output=True, text=True)
        check(r.returncode == 0, "import covtl_console works (bare venv)")
        v1, v2 = r.stdout.split()
        check(v1 == v2, f"__version__ == metadata version ({v1})")
        version = v1
        r = run([entry, "--help"], capture_output=True, text=True)
        check(r.returncode == 0, "covtl-console --help exits 0")

        # ── phase 3 — start the installed server, wait for health ─────
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        log(f"[3] starting covtl-console --port {port} (cwd={scratch})")
        server_log = open(scratch / "server.log", "w", encoding="utf-8")
        server_proc = subprocess.Popen(
            [str(entry), "--port", str(port)], cwd=scratch,
            stdout=server_log, stderr=subprocess.STDOUT)
        h = wait_health(base)
        check(h["status"] == "ok", f"health: live engine {h['engine_version']}")
        cap = h["sandhi"]
        check(cap.get("available") is True, "health: sandhi available")
        check(sorted(cap.get("languages") or []) ==
              ["de", "en", "es", "fr", "it", "pt"],
              "health: 6 sandhi rule languages")

        # ── phase 4 — the real chain over HTTP ─────────────────────────
        log("[4] preview -> compile -> synthesize on the installed server")
        p = http("POST", base + "/api/preview",
                 {"text": FR_TEXT, "mode": "ortho", "lang": "fr",
                  "sandhi": "standard"})
        check(p["final_sampa"] == FR_SAMPA,
              f"fr preview @standard -> {p['final_sampa']!r}")

        c = http("POST", base + "/api/compile",
                 {"text": FR_SAMPA, "lang": "fr"})
        m = c["metrics"]
        check(m["anchors"] == FR_ANCHORS,
              f"compile: {m['anchors']} anchors (expected {FR_ANCHORS})")
        check(m["blocks"] == FR_BLOCKS,
              f"compile: {m['blocks']} blocks (expected {FR_BLOCKS})")
        check(abs(m["duration_s"] - FR_SECONDS) <= 0.01,
              f"compile duration {m['duration_s']} s "
              f"(expected {FR_SECONDS} +/- 1 step)")

        job = synth_job(base, text=FR_SAMPA, lang="fr", label="e2e_fr")
        check(job["saw_polar_only"],
              "start-early: polar_ready observed BEFORE wav_ready")
        wav = http("GET", base + f"/api/job/{job['job_id']}/files/e2e_fr.wav")
        if not isinstance(wav, bytes):
            fail(f"wav download returned {type(wav)} for the fr job")
        wav_path = scratch / "e2e_fr.wav"
        wav_path.write_bytes(wav)
        with wave.open(str(wav_path), "rb") as w:
            wav_dur = w.getnframes() / w.getframerate()
        check(abs(wav_dur - FR_SECONDS) <= 0.04,
              f"wav duration {wav_dur:.3f} s == structure {FR_SECONDS} s "
              "+/- 40 ms")
        pol = http("GET", base + f"/api/job/{job['job_id']}/polar")
        n_pts = bad_pts = 0
        for seg in pol["segments"]:
            for pt in seg["points"]:
                if pt["theta_v"] is None:
                    continue
                n_pts += 1
                if not (0.0 <= pt["theta_v"] < 360.0
                        and 0.0 <= pt["rho_v"] <= 1.0):
                    bad_pts += 1
        check(bad_pts == 0 and pol["rho_max"] > 0
              and n_pts >= int(FR_SECONDS * 100) - 4,
              f"polar payload: {len(pol['segments'])} segments, "
              f"{n_pts} vocalic points (100 Hz, one per step) in display "
              "degrees, rho <= 1")

        # hiatus pairs + oral control
        log("[5] nasal hiatus pairs (VO inside the engine intervals)")
        digests = {}
        for i, pair in enumerate(HIATUS_PAIRS + (ORAL_CONTROL,)):
            jj = synth_job(base, text=pair, label=f"hp{i}")
            data = http("GET", base + f"/api/job/{jj['job_id']}/files/"
                        f"hp{i}.wav")
            if not isinstance(data, bytes):
                fail(f"wav download returned {type(data)} for {pair}")
            digests[pair] = hashlib.sha1(data).hexdigest()
            tract = http("GET", base + f"/api/job/{jj['job_id']}/files/"
                         f"hp{i}.tract")
            if not isinstance(tract, bytes):
                fail(f"tract download returned {type(tract)} for {pair}")
            tpath = scratch / f"hp{i}.tract"
            tpath.write_bytes(tract)
            vo = probe_vo(py, tpath, pair)
            if pair == ORAL_CONTROL:
                check(not vo["intervals"], "oral control: no nasal interval")
                check(vo["bg_means"] and max(vo["bg_means"]) <= VO_ORAL_MAX,
                      f"oral control: VO <= {VO_ORAL_MAX} on background "
                      f"windows {['%.3f' % x for x in vo['bg_means']]}")
            else:
                check(bool(vo["intervals"]),
                      f"{pair}: engine reports a nasal interval "
                      f"{vo['intervals']}")
                check(all(x >= VO_NASAL_MIN for x in vo["nasal_max"]),
                      f"{pair}: max VO {vo['nasal_max']} >= {VO_NASAL_MIN} "
                      "inside nasal_hiatus_intervals")
                check(all(x >= 0.3 for x in vo["nasal_core_means"]),
                      f"{pair}: sustained VO (middle-half means "
                      f"{['%.3f' % x for x in vo['nasal_core_means']]})")
        a, b, cc = (digests[p] for p in HIATUS_PAIRS)
        check(len({a, b, cc}) == 3,
              "the three hiatus pairs give pairwise-distinct WAVs")

        p = http("POST", base + "/api/preview",
                 {"text": "faut il", "mode": "ortho", "lang": "fr",
                  "sandhi": "standard"})
        check(p["final_sampa"] == "fo.til",
              f"liaison faut il @standard -> {p['final_sampa']!r}")

        log(f"PASSED — flash install e2e green (covtl-console {version}, "
            f"engine {h['engine_version']}, log: {LOG_PATH})")
        return 0
    finally:
        # ── teardown — kill the server, uninstall, delete the venv ────
        # log-only: a failure here must never mask the original error
        log("[T] teardown")
        try:
            if server_proc is not None:
                server_proc.terminate()
                try:
                    server_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server_proc.kill()
            if server_log is not None:
                server_log.close()
            py = scratch / ("Scripts/python.exe" if os.name == "nt"
                            else "bin/python")
            if py.exists():
                r = run([py, "-m", "pip", "uninstall", "-y",
                         "covtl-console"], capture_output=True, text=True,
                        timeout=300)
                check(r.returncode == 0, "pip uninstall covtl-console clean")
                r = run([py, "-c", "import covtl_console"],
                        capture_output=True, cwd=scratch)
                check(r.returncode != 0,
                      "covtl_console no longer importable in the venv")
            if keep:
                log(f"FLASH_E2E_KEEP=1 — scratch venv kept: {scratch}")
            else:
                shutil.rmtree(scratch, ignore_errors=True)
                log("scratch venv deleted")
        except Exception as exc:                              # noqa: BLE001
            log(f"teardown warning (non-fatal): {exc}")
        log.close()


if __name__ == "__main__":
    sys.exit(main())
