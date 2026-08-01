#!/bin/bash

# PDF Schema Editor - Quick Launch Script
#
# Starts BOTH halves of the editor:
#   1. the backend (uvicorn :8000) -- the authoritative Python linter, the
#      translation drift sweep, repair, division regeneration
#   2. the editor frontend (vite :3001)
#
# WHY THE BACKEND TOO (bd polyglot-pdf-cpiw): the editor used to run frontend-
# only in local mode, so it fell back to a LIGHTER client-side lint that drops
# rule ids. The guidance-staleness gate keys on a rule id, so it silently never
# fired -- a field whose name changed after its guidance was written still read
# green, with no prompt to re-check it. The translation drift sweep never ran
# either, so "Mark complete" could publish a kit with zero translations.
# Running the real backend removes that whole class of local-vs-hosted drift:
# local behaves exactly like hosted, with ONE implementation of every rule
# instead of two that silently disagree.
#
# The ONE sanctioned difference is the LLM provider: local uses the `claude`
# CLI on the maintainer's Claude Code subscription (effectively free), hosted
# spends metered Gemini tokens. That is a backend-side choice
# (EDITOR_TEXT_PROVIDER) the editor never sees.
#
# Usage: ./scripts/run-schema-editor.sh
#        ./scripts/run-schema-editor.sh --no-backend   (frontend only; the
#            editor then shows a "limited checking" notice)

set -e  # Exit on error

EDITOR_DIR="schema-editor"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"

START_BACKEND=1
for arg in "$@"; do
    case "$arg" in
        --no-backend) START_BACKEND=0 ;;
    esac
done

echo "======================================"
echo " PDF Schema Editor - Launch Script"
echo "======================================"
echo ""

# --- backend ---------------------------------------------------------------- #
# The venv lives in the MAIN repo even when this script runs from a worktree
# (the same resolution dev-local.ps1 uses), so resolve it via the git common dir.
BACKEND_PID=""
if [ "$START_BACKEND" = "1" ]; then
    COMMON_DIR="$(cd "$ROOT_DIR" && git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -n "$COMMON_DIR" ]; then
        MAIN_REPO="$(dirname "$COMMON_DIR")"
    else
        MAIN_REPO="$ROOT_DIR"
    fi
    VENV_PYTHON="$MAIN_REPO/backend/.venv/Scripts/python.exe"
    [ -x "$VENV_PYTHON" ] || VENV_PYTHON="$MAIN_REPO/backend/.venv/bin/python"

    if [ ! -x "$VENV_PYTHON" ]; then
        echo "WARNING: backend venv not found under $MAIN_REPO/backend/.venv"
        echo "  Create it:  python -m venv backend/.venv"
        echo "              backend/.venv/Scripts/pip install -r backend/requirements.txt"
        echo "  Continuing WITHOUT a backend -- the editor will show a"
        echo "  'limited checking' notice and cannot translate or regenerate."
        echo ""
        START_BACKEND=0
    fi
fi

if [ "$START_BACKEND" = "1" ]; then
    echo "Starting backend on ${BACKEND_URL} ..."
    # EDITOR_TEXT_PROVIDER=claude-cli: authoring-time text work (the translation
    # sweep, guidance regeneration) goes through the local `claude` CLI on the
    # maintainer's subscription instead of metered Gemini tokens. Override with
    # EDITOR_TEXT_PROVIDER=gemini to check hosted parity.
    if command -v claude >/dev/null 2>&1; then
        EDITOR_PROVIDER="${EDITOR_TEXT_PROVIDER:-claude-cli}"
    else
        EDITOR_PROVIDER="${EDITOR_TEXT_PROVIDER:-gemini}"
        echo "  NOTE: the 'claude' CLI is not on PATH -- falling back to"
        echo "        EDITOR_TEXT_PROVIDER=gemini (this SPENDS API tokens)."
    fi
    echo "  Text provider: ${EDITOR_PROVIDER}"

    (
        cd "$ROOT_DIR"
        PYTHONPATH="$ROOT_DIR" \
        PYTHONUNBUFFERED=1 \
        EDITOR_TEXT_PROVIDER="$EDITOR_PROVIDER" \
        GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-polyglot-demo-aa709}" \
        "$VENV_PYTHON" -m uvicorn backend.main:app \
            --host 127.0.0.1 --port "$BACKEND_PORT" --reload
    ) &
    BACKEND_PID=$!

    # Stop the backend when this script exits (Ctrl+C on the frontend, or any
    # error under `set -e`) so a re-run never collides on the port.
    trap 'if [ -n "$BACKEND_PID" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi' EXIT INT TERM

    # Wait for readiness rather than sleeping a fixed amount: a cold import of
    # the backend takes a few seconds, and the editor reads VITE_BACKEND_URL at
    # load, so a frontend that opened first would render its no-backend state.
    echo -n "  waiting for the backend to answer"
    for _ in $(seq 1 60); do
        if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
            echo " ready"
            break
        fi
        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo ""
            echo "  ERROR: the backend exited during startup (see its output above)."
            exit 1
        fi
        echo -n "."
        sleep 1
    done
    echo ""
fi

cd "$ROOT_DIR/$EDITOR_DIR"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    echo ""
    npm install
    echo ""
    echo "Dependencies installed."
    echo ""
else
    echo "Dependencies already installed"
    echo ""
fi

echo "Starting schema editor..."
echo ""
echo "   The editor will open at: http://localhost:3001"
if [ "$START_BACKEND" = "1" ]; then
    echo "   Backend (full checks):   ${BACKEND_URL}"
else
    echo "   NO BACKEND -- limited checking, no translation or regeneration."
fi
echo ""
echo "   To stop: Press Ctrl+C"
echo ""
echo "======================================"
echo ""

# VITE_BACKEND_URL is what flips the editor's hasBackend() on, which routes the
# lint through the authoritative Python rules and enables the server-side
# actions. Deliberately a SEPARATE variable from the hosted VITE_API_BASE_URL so
# a local session can never inherit the committed Cloud Run URL and start
# writing to the shared store.
if [ "$START_BACKEND" = "1" ]; then
    VITE_BACKEND_URL="$BACKEND_URL" npm run dev
else
    npm run dev
fi
