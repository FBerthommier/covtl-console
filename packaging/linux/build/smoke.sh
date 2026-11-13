#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Smoke minimal d'un binaire COVTL-Console : démarrage, /api/status,
# synthèse courte via le pool N2, présence du WAV.
# Usage : bash smoke.sh [chemin-binaire] [port]
#        (défauts : dist/linux/covtl-console/covtl-console, 8477)
set -euo pipefail

BIN="${1:-dist/linux/covtl-console/covtl-console}"
PORT="${2:-8477}"
BIN="$(cd "$(dirname "$BIN")" && pwd)/$(basename "$BIN")"
WORK="$(mktemp -d)"
trap '[ -n "${PID:-}" ] && { kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; }' EXIT

( cd "$WORK" && "$BIN" --port "$PORT" > "$WORK/console.log" 2>&1 & echo $! > "$WORK/pid" )
PID=$(cat "$WORK/pid")

S=""
for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:$PORT/api/status" > "$WORK/status.json" 2>/dev/null; then S=up; break; fi
    sleep 1
done
if [ "$S" != "up" ]; then
    echo "ÉCHEC : serveur non démarré en 60 s"
    tail -n 5 "$WORK/console.log" || true
    exit 1
fi
python3 - "$WORK/status.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["backend"] == "live", f"backend: {d['backend']} (attendu: live)"
print(f"    status OK — bridge {d['bridge']}, backend {d['backend']}, {len(d['speakers'])} speakers")
EOF

JID=$(curl -sf -X POST "http://127.0.0.1:$PORT/api/synthesize" -H 'Content-Type: application/json' \
    -d '{"text":"proof","lang":"en","speaker":"jd3","outputDir":"out"}' \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['job_id'])")
STATE=""
for i in $(seq 1 120); do
    STATE=$(curl -sf "http://127.0.0.1:$PORT/api/job/$JID" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['state'])")
    [ "$STATE" = "done" ] && break
    [ "$STATE" = "error" ] && { echo "ÉCHEC : synthèse en erreur (job $JID)"; exit 1; }
    sleep 1
done
if [ "$STATE" != "done" ]; then
    echo "ÉCHEC : synthèse non terminée en 120 s (dernier état: $STATE)"
    exit 1
fi
WAV=$(find "$WORK/out" -name "*.wav" -print -quit)
if [ -z "$WAV" ]; then
    echo "ÉCHEC : WAV introuvable"
    exit 1
fi
python3 - "$WAV" <<'EOF'
import sys, wave
w = wave.open(sys.argv[1])
print(f"    synthèse OK — WAV {w.getframerate()} Hz, {w.getnframes()/w.getframerate():.2f} s")
EOF

# [matplotlib portage] les modes vidéo doivent être disponibles comme
# sur Windows : une synthèse polar doit produire un MP4 via le ffmpeg
# embarqué (matplotlib rendu + encodage).
JIDV=$(curl -sf -X POST "http://127.0.0.1:$PORT/api/synthesize" -H 'Content-Type: application/json' \
    -d '{"text":"p a","lang":"en","speaker":"jd3","outputMode":"polar","outputDir":"outv"}' \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['job_id'])")
STATEV=""
for i in $(seq 1 240); do
    STATEV=$(curl -sf "http://127.0.0.1:$PORT/api/job/$JIDV" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['state'])")
    [ "$STATEV" = "done" ] && break
    [ "$STATEV" = "error" ] && { echo "ÉCHEC : vidéo polar en erreur (matplotlib/ffmpeg ?)"; exit 1; }
    sleep 1
done
if [ "$STATEV" != "done" ]; then
    echo "ÉCHEC : vidéo polar non terminée en 240 s (dernier état: $STATEV)"
    exit 1
fi
MP4=$(find "$WORK/outv" -name "*.mp4" -print -quit)
if [ -z "$MP4" ]; then
    echo "ÉCHEC : MP4 introuvable (modes vidéo indisponibles dans ce bundle ?)"
    exit 1
fi
echo "    vidéo polar OK — MP4 $(stat -c%s "$MP4") octets (matplotlib + ffmpeg embarqués)"

echo "    SMOKE : PASS"
