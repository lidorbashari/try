#!/bin/bash
# DJ Lab release check: tests -> audio QA -> catalog -> Rekordbox XML -> site -> Playwright smoke test.
# Usage: bash .claude/skills/release-check/scripts/release_check.sh [--quick]   (--quick skips pytest + audio QA)
# Prints a PASS/FAIL/SKIP table; exit code = number of failed steps (0 = ready to release).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$ROOT" || exit 99
PY="$(command -v python3 || command -v python)"
QUICK=0; [ "${1:-}" = "--quick" ] && QUICK=1
LOGDIR="$(mktemp -d "${TMPDIR:-/tmp}/djlab-release.XXXXXX")"
declare -a RESULTS=()
FAILS=0

run() { # run <name> <cmd...>
  local name="$1"; shift
  local log="$LOGDIR/$(echo "$name" | tr ' /' '__').log"
  printf '▶ %-22s ' "$name"
  if "$@" >"$log" 2>&1; then
    echo "PASS"; RESULTS+=("PASS  $name")
  else
    echo "FAIL  (log: $log)"; tail -n 15 "$log" | sed 's/^/    /'
    RESULTS+=("FAIL  $name  -> $log"); FAILS=$((FAILS+1))
  fi
}
skip() { printf '▶ %-22s SKIP (%s)\n' "$1" "$2"; RESULTS+=("SKIP  $1 ($2)"); }

if [ $QUICK -eq 0 ]; then
  if [ -d engine/tests ]; then run "pytest" "$PY" -m pytest engine/tests -q; else skip "pytest" "no engine/tests"; fi
  if [ -f tools/verify_audio.py ] && ls music/tracks/*/*.mp3 >/dev/null 2>&1; then
    run "verify_audio tracks" "$PY" tools/verify_audio.py music/tracks
    for d in music/practice music/transitions; do
      ls "$d"/*.mp3 >/dev/null 2>&1 && run "verify_audio ${d#music/}" "$PY" tools/verify_audio.py "$d"
    done
  else skip "verify_audio" "no tool or no rendered tracks"; fi
else
  skip "pytest" "--quick"; skip "verify_audio" "--quick"
fi

if ls crates/*.csv >/dev/null 2>&1; then
  run "validate crates" "$PY" .claude/skills/crate-research/scripts/validate_crate.py crates/*.csv
else skip "validate crates" "no crates/*.csv"; fi
for t in build_catalog build_rekordbox_xml build_site; do
  if [ -f "tools/$t.py" ]; then run "$t" "$PY" "tools/$t.py"; else skip "$t" "tools/$t.py missing"; fi
done
if ls music/rekordbox/*.xml >/dev/null 2>&1; then
  run "rekordbox xml parse" "$PY" -c "
import sys, glob, xml.etree.ElementTree as ET
for f in glob.glob('music/rekordbox/*.xml'):
    r = ET.parse(f).getroot(); n = len(r.findall('.//COLLECTION/TRACK'))
    assert n > 0, f + ': no tracks'; print(f, n, 'tracks')"
fi
# repo hygiene: audio only under music/, no WAV, no oversized covers
run "repo hygiene" "$PY" - <<'PYEOF'
import subprocess, sys, os
files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True).stdout.split()
bad = [f for f in files if f.lower().endswith((".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg")) and not f.startswith("music/")]
bad += [f for f in files if f.lower().endswith((".wav", ".aif", ".aiff", ".flac"))]
big = [f for f in files if f.endswith(".jpg") and f.startswith("music/") and os.path.getsize(f) > 200 * 1024]
for f in bad: print("audio outside music/ or lossless file in repo:", f)
for f in big: print("cover > 200 KB:", f)
sys.exit(1 if bad or big else 0)
PYEOF

if [ -f docs/index.html ] && command -v node >/dev/null 2>&1; then
  PORT=$(( 8100 + RANDOM % 800 ))
  "$PY" -m http.server "$PORT" --bind 127.0.0.1 >"$LOGDIR/http.log" 2>&1 &
  SRV=$!
  sleep 1
  # serve the repo root so ../music/... paths used by the site resolve like on GitHub Pages
  if curl -fs "http://127.0.0.1:$PORT/docs/index.html" >/dev/null 2>&1; then
    run "site smoke (playwright)" node .claude/skills/release-check/scripts/site_smoke.cjs "http://127.0.0.1:$PORT/docs/" --screens "$LOGDIR/screens"
  else
    skip "site smoke" "http.server did not start"
  fi
  kill "$SRV" 2>/dev/null
else
  skip "site smoke" "no docs/index.html or node"
fi

echo
echo "================ DJ Lab release check ================"
printf '%s\n' "${RESULTS[@]}"
echo "logs: $LOGDIR"
[ $FAILS -eq 0 ] && echo "✅ ready" || echo "❌ $FAILS step(s) failed"
exit $FAILS
