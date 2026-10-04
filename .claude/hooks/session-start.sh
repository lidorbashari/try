#!/bin/bash
# DJ Lab SessionStart hook.
# In Claude Code cloud sessions (CLAUDE_CODE_REMOTE=true) make sure engine/requirements.txt is installed.
# Fast + idempotent: a stamp keyed on the requirements hash skips pip entirely on later sessions.
# Never fatal: always exits 0 so a flaky network can't block the session.
set -u
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
REQ="engine/requirements.txt"
[ -f "$REQ" ] || exit 0

PY="$(command -v python3 || command -v python)" || exit 0
STAMP_DIR="${HOME:-/tmp}/.cache/djlab"
mkdir -p "$STAMP_DIR" 2>/dev/null || STAMP_DIR="/tmp"
HASH="$(sha256sum "$REQ" 2>/dev/null | cut -c1-16)"
STAMP="$STAMP_DIR/requirements-${HASH:-none}.ok"
LOG="$STAMP_DIR/pip-install.log"

if [ ! -f "$STAMP" ]; then
  if "$PY" -m pip install -q --disable-pip-version-check -r "$REQ" >"$LOG" 2>&1 \
     || "$PY" -m pip install -q --disable-pip-version-check --break-system-packages -r "$REQ" >>"$LOG" 2>&1; then
    touch "$STAMP"
  else
    echo "DJ Lab hook: pip install of $REQ failed (log: $LOG). Install manually: pip install -r $REQ"
  fi
fi
command -v ffmpeg >/dev/null 2>&1 || echo "DJ Lab hook: ffmpeg is missing - rendering and tools/analyze_library.py need it (apt-get install -y ffmpeg)."
exit 0
