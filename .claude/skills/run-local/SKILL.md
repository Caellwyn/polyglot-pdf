---
name: run-local
description: Spin up the polyglot-pdf frontend + backend LOCALLY (backend uvicorn :8000, frontend vite :5173) for development, full-fidelity Gemini I/O logging, and rapid frontend iteration. Wraps scripts/dev-local.ps1. Use when the user asks to "run locally", "start the local stack", capture Gemini logs, A/B the Live model, or make/preview frontend changes without deploying. Optional arg: "premium" to run the 3.1 model instead of the default 2.5, or "backend" for backend-only.
---

# Run the local dev stack

This skill launches the polyglot-pdf app on the developer's machine so you can:

- **Capture full Gemini I/O** to `backend/logs/gemini_<date>.jsonl` (the dev file
  logger turns on automatically because the runner creates `backend/.env.DEV`).
  This is the ONLY place full message bodies (tool-call args, tool responses,
  hints) are logged -- Cloud Run never logs them (PII policy). So local is where
  we debug tool-call behavior.
- **A/B the Live model** (3.1 vs 2.5) by restarting with a different flag.
- **Iterate on the frontend** with vite HMR and (later) drive it via the preview
  tools for rapid UI tweaks.

It does NOT deploy. Deployment stays manual via `deploy-*.sh` (maintainer only).

## What it runs

`scripts/dev-local.ps1` (PowerShell; the repo targets Windows) starts:

- **Backend** -- `uvicorn backend.main:app` on `http://localhost:8000`.
  Port 8000 is deliberate: the frontend's dev WS URL defaults to
  `ws://localhost:8000/ws/fill` (`frontend/src/shared/config.ts`). It forces
  `VERTEXAI=false` (AI Studio, which has the 3.1 model) so it needs
  `GEMINI_API_KEY` (in the shell or `backend/.env`).
- **Frontend** -- `npm run dev` (vite) on `http://localhost:5173` -- the
  schema-forms voice form-filler SPA.

## How to invoke

Run the script with the backend venv's environment. From the repo root:

```powershell
# Default: both servers, 2.5 (standard) model -- the deployed default -- full dev logging ON
./scripts/dev-local.ps1

# A/B on the 3.1 model
./scripts/dev-local.ps1 -Model premium

# Backend only (e.g. when driving an already-running frontend, or pure log capture)
./scripts/dev-local.ps1 -BackendOnly

# Production-style redacted logging locally (no .env.DEV created)
./scripts/dev-local.ps1 -NoDevLog
```

The script is a foreground runner: it stays attached and tears down both child
processes on Ctrl-C. **It is a long-lived process** -- launch it with
`run_in_background: true` (Bash tool) so you are notified if it exits, and do NOT
poll it; the user drives the browser while it runs.

> **Permissions note.** Invoking `powershell.exe` / `pwsh` may be blocked by a
> deny rule in this environment. If you cannot launch the `.ps1` from the Bash
> tool, STOP and ask the user to run `./scripts/dev-local.ps1` themselves in a
> PowerShell window, then continue (e.g. read the captured logs). Do not try to
> route around the deny rule.

## After it's up

- **Backend health:** `http://localhost:8000/health` (also `/version`).
- **Reproduce the issue** in the browser at `http://localhost:5173`.
- **Read the captured session:** `backend/logs/gemini_<today>.jsonl` -- one JSON
  object per line: `direction` (send/receive), `message_type` (tool_call,
  tool_response, text, etc.), `content` (FULL bodies in dev mode), `seq`, and
  timestamps. This is the evidence for tool-call debugging.

## Preflight the script already does

- Verifies the main-repo venv python exists (worktrees have no venv).
- Warns (does not block) if `GEMINI_API_KEY` is absent and `backend/.env` is
  missing.
- Checks `frontend/node_modules` exists (else tells the user to `npm install`).
- Creates `backend/.env.DEV` (gitignored) unless `-NoDevLog`.

## Guardrails

- **Never commit** `backend/.env.DEV` or `backend/logs/*.jsonl` -- both are
  gitignored (full message bodies are PII/PHI). If asked to share a log, redact
  field values first.
- **Local only.** This runner never deploys and never touches Cloud Run.
- **One model per run.** Switching 3.1 <-> 2.5 needs a restart (re-run with the
  other `-Model`); that's intentional -- each run is a clean A/B sample.
