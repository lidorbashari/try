#!/bin/bash
# QA lead: full release pipeline. Build, then every suite; prints only FAIL lines + one summary line per suite.
Q=$(cd "$(dirname "$0")" && pwd); L=$(dirname "$Q")
cp "$L/app.html" "$L/app_test/app.work.html"
python3 "$L/build.py" | cut -c1-400 || exit 1
python3 "$Q/grep_checks.py" | grep -v '^PASS'
( timeout 400 python3 "$Q/e2e_audio.py" 2>&1 | grep -v '^PASS'; timeout 300 python3 "$Q/e2e_wordplay.py" 2>&1 | grep -v '^PASS' ) > "$Q/log_e2e.txt"   # alone: audio timing is load-sensitive
( cd "$L/app_test"; timeout 300 python3 "$Q/run_ui_suites.py" run_tests.py 2>&1 | grep -v '^PASS\|^built'; timeout 300 python3 "$Q/run_ui_suites.py" run_s7.py 2>&1 | grep -v '^PASS\|^built';
  timeout 300 python3 run_tests.py stub 2>&1 | grep -v '^PASS\|^built' | sed 's/^/[stub] /' ) > "$Q/log_ui.txt" &
wait
# beat sync safety (iPhone stutter regression): every seek / tempo change of a real <audio> element must happen while muted
( cd "$(dirname "$L")/lead_check/beat" && timeout 900 python3 t_sync.py 2>&1 | grep -v '^PASS\|^   ' | sed 's/^/[sync] /' ) > "$Q/log_sync.txt"
cat "$Q/log_e2e.txt" "$Q/log_ui.txt" "$Q/log_sync.txt" | grep -v '^$'
