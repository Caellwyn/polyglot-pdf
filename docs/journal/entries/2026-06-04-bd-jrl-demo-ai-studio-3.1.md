---
date: 2026-06-04
bead: polyglot-pdf-jrl
type: fix
surfaces: [voice-ai, config-deployment]
tags: [gemini, vertex, ai-studio, auth, deploy, demo, 1008]
files:
  - backend/config.py
  - backend/adapters/live_ai_gemini.py
  - backend/main.py
  - docs/standards/ai-models.md
  - docs/components/config-deployment.md
---

# Demo backend: run Gemini 3.1 via AI Studio (bd polyglot-pdf-jrl)

## Symptom

After a fresh demo deploy, the frontend could not start a voice session. The
browser console showed the WebSocket connecting, reading the disclaimer, then
dropping (`1005` -> `1006`) and failing every reconnect. It looked like a
section-switch reconnect bug.

## Root cause

Not a WebSocket problem. The Cloud Run backend logs showed Gemini rejecting the
model on session start:

```
received 1008 (policy violation) Publisher Model
projects/polyglot-demo-aa709/locations/us-central1/publishers/google/models/gemini-3.1-flash-live-preview
```

`gemini-3.1-flash-live-preview` is **not yet available on Vertex AI**. The demo
backend authenticated to Gemini via Vertex (service-account ADC, `VERTEXAI` was
hardcoded `True`), so every Live session start `1008`'d. When the Gemini session
failed, the backend tore down and the frontend saw the socket drop -- the WS
cascade was a downstream symptom.

The Gemini Developer API (**AI Studio**) *does* have 3.1, but it authenticates
**only by API key** -- there is no ADC / service-account path (confirmed against
ai.google.dev and the vendored `genai_docs/`). So "works from my local env, fails
deployed" was: local pointed at an identity/service with 3.1; the deployed SA on
Vertex does not have it.

## Fix

Run the demo on AI Studio so it can use 3.1; keep prod on Vertex (compliance).

- **config.py**: `VERTEXAI` made env-overridable (`os.getenv("VERTEXAI","true")`),
  was a hardcoded `True`. It selects the **service/auth mode**, not the model.
- **live_ai_gemini.py**: store `self._api_key`. The load-bearing effect is in
  `__init__`: the session loop calls `self._client.aio.live.connect(...)` directly
  on the client built in `__init__` (it does NOT route through the public
  `connect()` method), so persisting the key is what makes the AI-Studio
  (`vertexai=False`) client correct. The public `connect()` method also gained a
  matching keyed-rebuild branch (was bare `ClientCls()` -> ADC fallback), but
  that path is belt-and-suspenders for external callers, not the hot reconnect
  path. Also added a startup warning when `vertexai=False` and the key is missing
  (logs, does not raise -- bare `LiveAIGemini()` is the default in mocked tests).
- **main.py**: `/health` now reports `vertexai`, so a deploy can be verified
  without dumping env vars.
- **Deploy (untracked scripts)**: `deploy-all.sh` gained a `BACKEND_EXTRA_ENV`
  hook; `deploy-demo.sh` sets `VERTEXAI=false,USE_PREMIUM_MODEL=true`. The
  `GEMINI_API_KEY` is injected via Secret Manager (`--set-secrets`), configured
  out-of-band -- never a plaintext env var. `--set-env-vars` does not disturb the
  secret binding, so it survives redeploys.

When 3.1 ships on Vertex, flip the demo back to `VERTEXAI=true` (or drop the
override) for a single compliant path again.

## Verification

- 186 unit tests pass (`closeout_prep.py`); adapter suite 23/23.
- Post-deploy check: `GET /health` should report `vertexai: false`,
  `native: gemini-3.1-flash-live-preview`, `gemini_api_key_present: true`.

## Decisions (defended)

- **Made `VERTEXAI` env-driven rather than hardcoding `false`.** Keeps prod on
  Vertex (the compliance requirement) while the demo opts into AI Studio -- one
  per-environment toggle, mirroring `USE_PREMIUM_MODEL` / `DISABLE_GEMINI_VAD`.
  Internal config form, in service of the bead -> decided.
- **Fixed the reconnect-path key bug in the same PR.** Not in the original ask,
  but it is directly on the AI-Studio reconnect flow this change enables and
  would otherwise cause intermittent demo failures. Small, tested, in-scope.
- **Secret Manager for the key** (maintainer chose this) over a plaintext env
  var -- the key is a real secret, unlike the Firebase web config.

## Out of scope / noted

- Pre-existing bead slip `polyglot-pdf-hrn` (in_progress 3 days) is unrelated to
  this PR; not transitioned here.
- A separate, earlier issue in this session: the demo frontend was building in
  production mode (`.env.production`, which lacks Firebase keys) -> the deploy
  scripts now build `build:schema:demo`. That is deploy-script-only (untracked),
  not part of this tracked PR.
