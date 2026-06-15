---
name: run-local
description: Spin up the polyglot-pdf frontend + backend LOCALLY (backend uvicorn :8000, frontend vite :5173) for development, full-fidelity Gemini I/O logging, and rapid frontend iteration. Wraps scripts/dev-local.sh (bash -- the agent can run this directly) / scripts/dev-local.ps1 (PowerShell, human-facing). Use when the user asks to "run locally", "start the local stack", capture Gemini logs, A/B the Live model, or make/preview frontend changes without deploying. Optional arg: "premium" to run the 3.1 model instead of the default 2.5, or "backend" for backend-only.
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

It does NOT deploy -- it is the LOCAL test stage. Deployment is a separate manual
step via `deploy-*.sh`. As of 2026-06-10 the agent MAY run the demo deploy
(`deploy-demo.sh`), but only after exercising the change here first, with explicit
per-instance maintainer permission, and with a post-deploy test-drive -- see the
demo-deploy gate in [`docs/doctrine/promotion-tiers.md`](../../../docs/doctrine/promotion-tiers.md).
`deploy-production.sh` has no live prod target and stays maintainer-directed.

## What it runs

There are TWO equivalent runners -- a bash one and a PowerShell one. They start
the same stack:

- **Backend** -- `uvicorn backend.main:app` on `http://localhost:8000`.
  Port 8000 is deliberate: the frontend's dev WS URL defaults to
  `ws://localhost:8000/ws/fill` (`frontend/src/shared/config.ts`). It forces
  `VERTEXAI=false` (AI Studio, which has the 3.1 model) so it needs
  `GEMINI_API_KEY` (in the shell or `backend/.env`).
- **Frontend** -- vite on `http://localhost:5173` -- the schema-forms voice
  form-filler SPA. (The bash runner uses `--mode demo` so the committed
  `frontend/.env.demo` Firebase web config loads + the WS URL is overridden to
  the LOCAL backend; it also bypasses auth, so no Firebase sign-in is needed.)

## How to invoke

**PREFER `scripts/dev-local.sh` (bash) -- the agent can run it directly from the
Bash tool.** `powershell.exe` / `pwsh` is blocked by a deny rule in this
environment (the auto-mode classifier treats `pwsh` as routing around that rule),
so the `.ps1` is for a human in a PowerShell window, NOT for the agent. The bash
script is a full worktree-aware counterpart (it resolves the venv from the main
repo) and runs the same stack from Git Bash. Launch it with
`run_in_background: true` so you are notified if it exits; do NOT poll it.

```bash
# Default: both servers, 2.5 (standard) model, full dev logging ON
./scripts/dev-local.sh

# A/B on the 3.1 (premium) model
./scripts/dev-local.sh premium

# Backend only / frontend only
./scripts/dev-local.sh backend
./scripts/dev-local.sh frontend
```

After launching, confirm both are up before driving the browser:
`curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health` and the same
for `:5173` should each return `200` (they usually come up within a few seconds).

The PowerShell runner is the human-facing equivalent (same servers; flags
`-Model premium`, `-BackendOnly`, `-NoDevLog`):

```powershell
./scripts/dev-local.ps1            # both, 2.5
./scripts/dev-local.ps1 -Model premium
./scripts/dev-local.ps1 -BackendOnly
```

Both runners are foreground/long-lived (Ctrl-C tears down both children). If the
bash runner is somehow unavailable AND you cannot run it, ask the user to run
`./scripts/dev-local.ps1` in a PowerShell window -- but try `dev-local.sh` first.

> **Aggressive idle timeout when driving headless.** A connected voice session
> idle-times-out fairly quickly (~30-60s) with no audio being sent (default PTT is
> muted). If you are driving the browser via Chrome MCP for a UI check, the session
> will keep disconnecting between multi-step tool calls. Click the in-overlay
> "Reconnect" control to re-establish it, and do any state inspection in as few
> tool calls as possible (the meter / overlay re-mounts on reconnect, so cached
> React fiber/ref handles go stale -- re-acquire them each time).

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
