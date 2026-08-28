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
#   - Backend  : uvicorn backend.main:app on http://localhost:8000. Runs on VERTEX
#                by default (ADC + GOOGLE_CLOUD_PROJECT), so ALL local spend lands
#                on the ONE Vertex billing account -- never AI Studio (bd
#                polyglot-pdf-6les). The premium (3.1) arm is the sole exception:
#                3.1 is AI-Studio-only for now, so `premium` uses VERTEXAI=false +
#                GEMINI_API_KEY and bills to the AI Studio account (it warns).
#   - Frontend : vite dev server on http://localhost:5173 (--mode demo + local WS)
#
# Usage:
#   ./scripts/dev-local.sh              # both servers (default 2.5 model, VERTEX)
#   ./scripts/dev-local.sh premium      # both, USE_PREMIUM_MODEL=true (3.1, AI Studio)
#   ./scripts/dev-local.sh backend      # backend only
#   ./scripts/dev-local.sh frontend     # frontend only (talks to whatever WS URL)
#
# Voice knobs (bd polyglot-pdf-0rpu), passed as env vars. Only the TRANSCRIPT
# and AUDIO-DUMP knobs are local-dev-only (they capture PHI and are gated
# backend-side on backend/.env.DEV); LIVE_TEMPERATURE is a normal setting,
# honored in deployed services too since 2026-08-10 (the demo runs 0.4):
#
#   LIVE_TEMPERATURE=0.4 ./scripts/dev-local.sh
#     Sampling temperature for the Live session. Unset = send nothing, keeping
#     Google's default of 1.0 -- the MAXIMUM-variability setting, where a
#     conversationally-plausible reply can outrank the literal tool response.
#     A logged session shows the model handed "Stored value: name_1b_last =
#     'Smith'" and telling the user "You said Jose" (a value two fields back).
#     SWEEP 0.3-0.6. NEVER 0: googleapis/js-genai#1578 reports runaway/no-audio
#     output and a 1011 session close at temperature 0 on native audio. The
#     backend rejects <=0 and >2 rather than passing them through.
#
#   LIVE_DEV_TRANSCRIPTS=true ./scripts/dev-local.sh
#     Record WHAT WAS SAID (both sides) into backend/logs/gemini_*.jsonl as
#     `transcript` records. Without it the log proves what was STORED but never
#     what reached the user's ears. Read them back with:
#       grep '"transcript"' backend/logs/gemini_*.jsonl
#     then compare spoken_by_model against the neighbouring tool_response's
#     stored_values.
#
#   LIVE_DEV_AUDIO_DUMP=true ./scripts/dev-local.sh
#     Dump the model's OUTPUT audio, one WAV per generation, to
#     backend/logs/audio_out/gemini_<date>/ -- the ground truth for the
#     text/audio desync (bd 0rpu): wrong letters INSIDE the WAV = model-side;
#     WAV correct but heard wrong = client-side playback. Score against the
#     text track with:
#       backend/.venv/Scripts/python.exe scripts/spikes/stt_readback_diff.py \
#         --audio-dir backend/logs/audio_out/gemini_<date> \
#         --jsonl backend/logs/gemini_<date>.jsonl
#     PHI: same .env.DEV double-gate as transcripts.
#
#   Combined sweep (the bd 0rpu attribution setup):
#     LIVE_TEMPERATURE=0.4 LIVE_DEV_TRANSCRIPTS=true LIVE_DEV_AUDIO_DUMP=true ./scripts/dev-local.sh
#
#   PRIVACY: both are additionally gated backend-side on backend/.env.DEV
#   (gitignored, never deployed), so neither can turn on in a deployed service
#   even if the env var is set. Transcripts are PHI.
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
  # Credential preflight (bd polyglot-pdf-6les). The DEFAULT arm runs on Vertex
  # (see start_backend), which authenticates via Application Default Credentials
  # (ADC) + GOOGLE_CLOUD_PROJECT -- NOT an API key. The premium (3.1) arm runs on
  # AI Studio and DOES need GEMINI_API_KEY. Warn per the arm actually selected.
  if [ "$PREMIUM" = "true" ]; then
    # backend/main.py load_dotenv()s backend/.env, so GEMINI_API_KEY can live there.
    if [ -z "${GEMINI_API_KEY:-}" ] && [ ! -f "$REPO_ROOT/backend/.env" ]; then
      echo "WARNING: premium arm uses AI Studio (VERTEXAI=false), which REQUIRES GEMINI_API_KEY," >&2
      echo "  but it is not set and backend/.env is missing." >&2
    fi
  else
    # Vertex ADC lives at the well-known gcloud path; if it is absent, Vertex
    # calls will fail auth. Warn (do not block) -- the user may have ADC via a
    # service-account key env instead. The path differs by OS: Windows uses
    # %APPDATA%\gcloud, POSIX (WSL/macOS/Linux, which this script also targets)
    # uses ~/.config/gcloud. Check BOTH so a valid POSIX ADC does not trip a
    # spurious warning every launch (fresh-eyes finding).
    local adc_win="${APPDATA:-$HOME/AppData/Roaming}/gcloud/application_default_credentials.json"
    local adc_posix="${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}/application_default_credentials.json"
    if [ ! -f "$adc_win" ] && [ ! -f "$adc_posix" ] && [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]; then
      echo "WARNING: Vertex (default) needs Application Default Credentials, but none found." >&2
      echo "  Run 'gcloud auth application-default login', or set GOOGLE_APPLICATION_CREDENTIALS." >&2
    fi
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
  # Backend selection (bd polyglot-pdf-6les). ALL sessions -- local or remote --
  # run on VERTEX by default so spend lands on ONE billing account
  # (GOOGLE_CLOUD_PROJECT below), never split across the AI Studio account
  # (maintainer directive 2026-07-15, reaffirming the 2026-07-12
  # all-live-model-work-on-vertex rule). The ONE exception is the premium (3.1)
  # arm: gemini-3.1 is AI-Studio-only as of 2026-06 (backend/config.py MODEL
  # notes), so `dev-local.sh premium` MUST use VERTEXAI=false -- a model-
  # availability constraint, not a billing choice. That arm therefore spends on
  # the AI Studio account; we warn loudly so it is a deliberate, visible choice.
  local vertexai
  if [ "$PREMIUM" = "true" ]; then
    vertexai=false
    echo "WARNING: premium (3.1) arm runs on AI STUDIO (VERTEXAI=false) -- 3.1 is not on Vertex yet." >&2
    echo "  This arm bills to the AI Studio account, NOT the Vertex project. Use the default (2.5) arm for Vertex." >&2
  else
    vertexai=true
  fi
  echo "Starting backend (uvicorn :8000, VERTEXAI=$vertexai, USE_PREMIUM_MODEL=$PREMIUM, auth bypassed, DISABLE_GEMINI_VAD=$vad_mode)..."
  # Echo the local-dev voice knobs so a sweep run is never ambiguous about which
  # value produced which recording (bd polyglot-pdf-0rpu).
  echo "  temperature=${LIVE_TEMPERATURE:-default(1.0)}   transcripts=${LIVE_DEV_TRANSCRIPTS:-false} (LOCAL-DEV ONLY)"
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
  #
  # GOOGLE_CLOUD_PROJECT is exported for the Vertex path (adapter reads it via
  # google-genai + ADC); it is harmless on the Studio (premium) path, which uses
  # GEMINI_API_KEY instead. Respect an already-set value so a different project
  # can be used per run.
  #
  # Scope the reload watcher to backend/ by making backend/ the process CWD.
  # --reload-dir ALONE cannot do this: uvicorn's WatchFiles supervisor drops
  # any reload dir that is a CHILD of the process cwd and watches the cwd
  # instead (uvicorn 0.24, unchanged upstream). With cwd at the repo root --
  # which holds .claude/worktrees/ and its ~130 sibling checkouts -- that
  # collapsed to watching EVERYTHING, so an agent editing any .py in ANY
  # worktree restarted this backend mid-request. The startup log "Will watch
  # for changes in these directories: [...backend]" prints the CONFIG, not the
  # effective watch set, which is how this looked fixed for two rounds
  # (bd polyglot-pdf-b5nmq; PR #650 before it).
  #
  # With cwd == the reload dir the supervisor keeps exactly that dir. Safe to
  # move the cwd: PYTHONPATH pins imports to the repo root, and backend runtime
  # paths anchor on __file__ rather than cwd (pinned by
  # backend/tests/unit/test_runtime_paths_are_cwd_independent.py). backend/
  # imports no other top-level package (shared/ is one JSON file, no Python).
  ( cd "$REPO_ROOT/backend" && \
    VERTEXAI="$vertexai" USE_PREMIUM_MODEL="$PREMIUM" PYTHONPATH="$REPO_ROOT" \
    GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-polyglot-demo-aa709}" \
    VFF_DISABLE_AUTH="${VFF_DISABLE_AUTH:-true}" \
    DISABLE_GEMINI_VAD="$vad_mode" \
    SEND_TRANSCRIPT="${SEND_TRANSCRIPT:-true}" \
    LIVE_TEMPERATURE="${LIVE_TEMPERATURE:-}" \
    LIVE_DEV_TRANSCRIPTS="${LIVE_DEV_TRANSCRIPTS:-false}" \
    LIVE_DEV_AUDIO_DUMP="${LIVE_DEV_AUDIO_DUMP:-false}" \
    "$VENV_PY" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload \
      --reload-dir "$REPO_ROOT/backend" ) &
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
