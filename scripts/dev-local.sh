#!/usr/bin/env bash
#
# dev-local.sh -- run the polyglot-pdf stack LOCALLY for development + testing.
#
# Bash counterpart to scripts/dev-local.ps1 (the repo targets Windows, but this
# runs the same stack from Git Bash / WSL / macOS / Linux). It fixes the
# frontend Firebase "auth/invalid-api-key" crash you hit with `npm run dev`: plain
# vite loads only .env/.env.local/.env.development (none of which exist here), so
# the VITE_FIREBASE_* vars are undefined. We run vite with `--mode demo` so it
# loads the committed frontend/.env.demo (which carries the Firebase web config),
# and we OVERRIDE VITE_WS_URL to the LOCAL backend so the SPA talks to the uvicorn
# we start here (the .env.demo default points at Cloud Run).
#
# Starts:
#   - Backend  : uvicorn backend.main:app on http://localhost:8000 (VERTEXAI=false,
#                AI Studio -- needs GEMINI_API_KEY in the env or backend/.env)
#   - Frontend : vite dev server on http://localhost:5173 (--mode demo + local WS)
#
# Usage:
#   ./scripts/dev-local.sh              # both servers (default 2.5 model)
#   ./scripts/dev-local.sh premium      # both, USE_PREMIUM_MODEL=true (3.1)
#   ./scripts/dev-local.sh backend      # backend only
#   ./scripts/dev-local.sh frontend     # frontend only (talks to whatever WS URL)
#
# Ctrl+C stops both.

set -euo pipefail

MODE="${1:-both}"
PREMIUM="false"
if [ "$MODE" = "premium" ]; then PREMIUM="true"; MODE="both"; fi

# Resolve the SOURCE repo root (this script's repo, worktree-aware) and the MAIN
# repo (where backend/.venv lives -- worktrees do not have their own venv).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GIT_COMMON_DIR="$(cd "$REPO_ROOT" && git rev-parse --path-format=absolute --git-common-dir)"
MAIN_REPO="$(dirname "$GIT_COMMON_DIR")"
VENV_PY="$MAIN_REPO/backend/.venv/Scripts/python.exe"
[ -x "$VENV_PY" ] || VENV_PY="$MAIN_REPO/backend/.venv/bin/python"   # POSIX venv layout

LOCAL_WS_URL="ws://localhost:8000/ws/fill"

echo "Source repo : $REPO_ROOT"
echo "Main repo   : $MAIN_REPO (venv)"
echo "Mode        : $MODE (premium=$PREMIUM)"
echo ""

PIDS=()
NM_JUNCTION_CREATED=0   # 1 if WE created frontend/node_modules as a junction
cleanup() {
  echo ""
  echo "Stopping local stack..."
  # taskkill /T kills the whole tree (uvicorn --reload + vite spawn children that
  # a plain kill on the shell-job PID misses, leaving an orphan on :8000).
  for pid in "${PIDS[@]:-}"; do
    [ -n "${pid:-}" ] || continue
    if command -v taskkill >/dev/null 2>&1; then
      taskkill //PID "$pid" //T //F >/dev/null 2>&1 || true
    else
      kill "$pid" 2>/dev/null || true
    fi
  done
  # Remove the node_modules link we created (worktrees have no own install).
  # Windows junction -> rmdir via cmd.exe; POSIX symlink -> rm.
  if [ "$NM_JUNCTION_CREATED" = "1" ]; then
    if command -v cmd.exe >/dev/null 2>&1 && command -v cygpath >/dev/null 2>&1; then
      cmd.exe //c rmdir "$(cygpath -w "$REPO_ROOT/frontend/node_modules")" >/dev/null 2>&1 || true
    else
      rm -f "$REPO_ROOT/frontend/node_modules" || true
    fi
  fi
}
trap cleanup EXIT INT TERM

# Worktrees have no frontend/node_modules (the install lives in the MAIN repo).
# Junction to it so vite resolves -- the same trick the test runs use. No-op when
# the worktree already has a real node_modules, or when we ARE the main repo.
ensure_frontend_deps() {
  if [ -d "$REPO_ROOT/frontend/node_modules" ]; then
    return 0
  fi
  local main_nm="$MAIN_REPO/frontend/node_modules"
  if [ ! -d "$main_nm" ]; then
    echo "ERROR: no frontend/node_modules in this worktree OR the main repo ($main_nm)." >&2
    echo "  Run 'npm install' in the MAIN repo's frontend/ first." >&2
    exit 1
  fi
  echo "Linking frontend/node_modules -> main repo install (worktree has none)..."
  # Windows/MSYS (Git-Bash): a directory JUNCTION via cmd.exe mklink. The cmd
  # switches must be //c //J (double slash) and the Windows paths passed as separate
  # quoted args -- NOT one quoted string. POSIX (WSL/macOS/Linux): a plain symlink
  # (Codex review PR #119 -- the advertised POSIX case must not call cygpath/cmd.exe).
  if command -v cmd.exe >/dev/null 2>&1 && command -v cygpath >/dev/null 2>&1; then
    cmd.exe //c mklink //J "$(cygpath -w "$REPO_ROOT/frontend/node_modules")" \
                          "$(cygpath -w "$main_nm")" >/dev/null 2>&1 \
      || { echo "ERROR: failed to create node_modules junction." >&2; exit 1; }
  else
    ln -s "$main_nm" "$REPO_ROOT/frontend/node_modules" \
      || { echo "ERROR: failed to symlink node_modules." >&2; exit 1; }
  fi
  NM_JUNCTION_CREATED=1
}

start_backend() {
  if [ ! -x "$VENV_PY" ]; then
    echo "ERROR: backend venv python not found at $VENV_PY" >&2
    echo "Create it in the MAIN repo: python -m venv backend/.venv && \\" >&2
    echo "  backend/.venv/Scripts/pip install -r backend/requirements.txt" >&2
    exit 1
  fi
  # backend/main.py load_dotenv()s backend/.env, so GEMINI_API_KEY can live there.
  if [ -z "${GEMINI_API_KEY:-}" ] && [ ! -f "$REPO_ROOT/backend/.env" ]; then
    echo "WARNING: GEMINI_API_KEY not set and backend/.env missing." >&2
    echo "  Local dev uses AI Studio (VERTEXAI=false), which REQUIRES an API key." >&2
  fi
  # Enable the dev Gemini I/O file logger (backend/logs/gemini_<date>.jsonl): it is
  # gated on backend/.env.DEV existing (DEV_LOGGING_ENABLED). This is the ONLY place
  # full message bodies -- tool-call args, hints, model responses -- are captured
  # (Cloud Run never logs them, PII policy), so it is essential for debugging why
  # Gemini does/doesn't respond. Created if absent; left in place (gitignored).
  local DEV_MARKER="$REPO_ROOT/backend/.env.DEV"
  if [ ! -f "$DEV_MARKER" ]; then
    echo "# Marker: enables backend dev file logging (gemini_<date>.jsonl). Local only." > "$DEV_MARKER"
    echo "Created backend/.env.DEV (enables Gemini I/O logging to backend/logs/)."
  fi

  # VAD mode (bd polyglot-pdf-6vo debugging): DISABLE_GEMINI_VAD chooses who detects
  # turn boundaries. Default here is NATIVE (false) to match prod, but you can flip to
  # MANUAL mode -- where the client sends explicit activity_start/end (PTT or Silero)
  # and Gemini does NOT rely on detecting silence in a continuous stream -- with:
  #   DISABLE_GEMINI_VAD=true ./scripts/dev-local.sh
  local vad_mode="${DISABLE_GEMINI_VAD:-false}"
  echo "Starting backend (uvicorn :8000, VERTEXAI=false, USE_PREMIUM_MODEL=$PREMIUM, auth bypassed, DISABLE_GEMINI_VAD=$vad_mode)..."
  # Run from the SOURCE repo root so backend.main imports THIS checkout's code.
  # VFF_DISABLE_AUTH=true bypasses Firebase token verification on /ws/fill: locally,
  # firebase_admin uses ADC and verify_id_token() validates the token against the
  # ADC project + fetches Google's signing keys -- which times out / mismatches the
  # demo project's token, so the WS handshake silently times out and the SPA falls
  # back to Cloud Run (your local backend never sees the session). The bypass is the
  # documented dev path (backend/services/auth.py). Override per run: VFF_DISABLE_AUTH=false ./dev-local.sh
  # SEND_TRANSCRIPT=true (default in local dev) turns on input/output audio
  # transcription so the dev log captures what Gemini HEARD from the mic -- the
  # decisive datapoint for "audio reaches Gemini but it stays silent". Safe for
  # native-audio (adds only *_audio_transcription config, not TEXT modality).
  ( cd "$REPO_ROOT" && \
    VERTEXAI=false USE_PREMIUM_MODEL="$PREMIUM" PYTHONPATH="$REPO_ROOT" \
    VFF_DISABLE_AUTH="${VFF_DISABLE_AUTH:-true}" \
    DISABLE_GEMINI_VAD="$vad_mode" \
    SEND_TRANSCRIPT="${SEND_TRANSCRIPT:-true}" \
    "$VENV_PY" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload ) &
  PIDS+=("$!")
}

start_frontend() {
  echo "Starting frontend (vite :5173, --mode demo, WS -> $LOCAL_WS_URL)..."
  # build:worklet first (plain `vite` has no worklet hook), then run vite in demo
  # mode so .env.demo provides the Firebase web config.
  #
  # WS override: we point the SPA at the LOCAL backend by exporting VITE_WS_URL as a
  # PROCESS env var. This is deliberate -- vite's file precedence is
  # `.env.[mode]` > `.env.local`, so a .env.local CANNOT override .env.demo's cloud
  # VITE_WS_URL under `--mode demo` (verified). A process-env VITE_* beats every
  # .env file, so it is the only reliable override here. Every other VITE_*
  # (Firebase config) still comes from .env.demo.
  ( cd "$REPO_ROOT/frontend" && \
    npm run build:worklet && \
    VITE_WS_URL="$LOCAL_WS_URL" npm run dev -- --mode demo ) &
  PIDS+=("$!")
}

# Resolve frontend deps BEFORE starting the backend so a missing-deps failure
# can't leave an orphaned uvicorn on :8000.
case "$MODE" in
  backend)  start_backend ;;
  frontend) ensure_frontend_deps; start_frontend ;;
  both)     ensure_frontend_deps; start_backend; start_frontend ;;
  *) echo "Unknown mode: $MODE (use: both | premium | backend | frontend)" >&2; exit 1 ;;
esac

echo ""
echo "Local stack up. Frontend: http://localhost:5173  Backend: http://localhost:8000"
echo "Press Ctrl+C to stop."
wait
