---
name: voice-harness
description: Run the automated voice form-fill E2E test against the real app + real Gemini, with scripted audio (no human mic). Drives the cycle "Gemini asks a field -> inject audio answer -> field fills -> inject 'yes' -> confirm/advance" and reports PASS/FAIL/FLAKY. Use when asked to voice-test the form-fill loop, regression-test the tool-call/field-fill path, or verify a voice change end-to-end without speaking. Wraps tests/e2e/voice-harness/ (bd polyglot-pdf-g8w).
---

# Voice form-fill E2E harness

**CURRENTLY BROKEN (bd polyglot-pdf-tcemw):** this harness targets the i-90
kit. The "click i-90" navigation step below is FINE again -- that kit id is
back in the catalogue, now serving the applicant-only v2 schema. What is still
broken is harness.js's default field ids: `p1_line1_aliennumber` and
`p1_line2_acctidentifier` do NOT exist in the v2 schema (verified), which
renamed every field. Their closest counterparts are `a_number` and
`uscis_account`, but do not just swap the strings in -- v2 is applicant-only
and dropped Parts 6/7 entirely, so repointing correctly means picking fields
that still play the same structural role in the harness's cycle. Tracked in
the linked bead.

Drives the real frontend (Chrome) against a local backend + real Gemini, feeding
committed 16 kHz PCM16 WAV fixtures into the live WebSocket through a dev-gated
in-app hook (`window.__VFF_TEST_INJECT`). Asserts on concrete outcomes (field
value, confirmed flag, advance), not audio. Full detail:
[`tests/e2e/voice-harness/RUNBOOK.md`](../../../tests/e2e/voice-harness/RUNBOOK.md).
The harness module is [`tests/e2e/voice-harness/harness.js`](../../../tests/e2e/voice-harness/harness.js).

## What it proves

The voice cycle works end to end: scripted audio "one two three four five six
seven" -> Gemini transcribes it -> `update_form_fields` tool call -> the field
fills with `1234567`; then "yes that's correct" -> confirmed / advance to the next
field. No human speaks.

## Pieces (already in the repo)

- **App hook** `window.__VFF_TEST_INJECT` in `frontend/src/shared/connection.ts`
  (pushes fixture PCM into the same path the mic uses). Double-gated:
  `isTestHarnessEnabled()` requires `__VFF_LOCAL_DEV` AND `__VFF_TEST_HARNESS`
  (window OR localStorage). The same gate installs a **mock auth user**
  (`AuthContext`) so you skip Firebase login. NEVER active in prod/normal dev.
- **Fixtures** `frontend/public/test-fixtures/{digits_1234567,confirm_yes}.wav`,
  served by vite at `/test-fixtures/*.wav`. Regenerate with `gen_fixtures.py`
  (needs `pip install "setuptools<81"` for librosa's `pkg_resources`).
- **Harness** `tests/e2e/voice-harness/harness.js` -> `window.__VFF_HARNESS`
  (`loadFixture`, `injectUtterance`, `runCycle`, outcome waiters, `readField`).

## The setup that actually works (do NOT improvise these)

1. **Chrome MCP, not Claude Preview.** Preview is an opaque-origin sandbox
   (`origin null`, storage denied) -- this app needs real `sessionStorage`. Use
   `mcp__Claude_in_Chrome__*`: `list_connected_browsers` -> `select_browser` ->
   `tabs_context_mcp {createIfEmpty:true}` -> `navigate`.
2. **Frontend in `--mode demo`** (else `firebase/config.ts` throws
   `auth/invalid-api-key` and the app never mounts).
3. **CORS-allowed port** for the frontend: 5173-5177 (`backend/main.py`
   `allow_origins`). Use 5174. A stray port fails `/api/form-kits` preflight
   ("Unable to load available forms").
4. **Backend with `VFF_DISABLE_AUTH=true`** on a free port (else the WS handshake
   times out 10s verifying the Firebase token). Point the frontend WS at it via
   `localStorage['__VFF_BACKEND_URL']`.
5. **`javascript_tool` has no top-level await.** Launch
   `(async()=>{...})()` that writes to a `window.*` var and poll it. Click buttons
   with `el.click()` in JS, not `computer {ref}` (unreliable on this SPA).

## Run it (bash is allowed; powershell is deny-blocked)

```
WT=<worktree-abs-path>; PY=<main-repo>/backend/.venv/Scripts/python.exe
# Backend on 8001, auth off (run_in_background):
cd "$WT" && VERTEXAI=false USE_PREMIUM_MODEL=false PYTHONPATH="$WT" \
  VFF_DISABLE_AUTH=true DISABLE_GEMINI_VAD=false SEND_TRANSCRIPT=true \
  "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
# Frontend on 5174, demo mode (run_in_background):
cd "$WT/frontend" && npm run build:worklet && \
  VITE_WS_URL=ws://localhost:8001/ws/fill npx vite --mode demo --port 5174 --strictPort
```

Then in a Chrome tab (see RUNBOOK steps 2-7 for the exact JS):
1. `navigate` 5174; set `__VFF_LOCAL_DEV` / `__VFF_TEST_HARNESS` /
   `__VFF_BACKEND_URL=ws://localhost:8001/ws/fill` in localStorage; reload.
2. Click English -> i-90 (JS `.click()`), then click Agree as soon as the
   modal is up -- BEFORE waiting for the hook. With the intro-clip flag OFF
   (today's default) the app is already `connected` here; with it ON there is
   no session until Agree, so waiting first would hang. Clicking first is
   correct under both (bd `polyglot-pdf-s1iex.7`). Match the TRANSLATED label
   -- a Russian session shows "Prinimayu", not "I Agree":
   ```js
   [...document.querySelectorAll('button')]
     .find(b=>/Принимаю|I Agree/i.test(b.innerText)).click();
   ```
3. Confirm `typeof window.__VFF_TEST_INJECT === 'object'`, then inject
   `harness.js` and pre-load both fixtures into `window.__vffDigits/__vffYes`.
4. (Agree already clicked in step 2 -- nothing to do here.)
5. Run and poll:
   ```js
   window.__vffReport = null;
   window.__VFF_HARNESS.runCycle({ fieldId:'p1_line1_aliennumber', expectDigits:'1234567',
     digitsBuf: window.__vffDigits, yesBuf: window.__vffYes }).then(r => window.__vffReport = r);
   ```
   Poll `window.__vffReport` until non-null -> `{ verdict:'PASS'|'FAIL'|'FLAKY', steps, reason? }`.

## Reporting

`runCycle` already classifies PASS/FAIL/FLAKY. For confidence, rerun the whole
cycle (reload + redo) up to 3x and report the rate + model (2.5 default vs 3.1
premium, which skips tool calls more). On non-PASS, capture
`read_console_messages` and the backend stdout.

## Known issue the harness catches

bd polyglot-pdf-0ux (FIXED 2026-06-09): on native-audio the `update_form_fields`
FunctionResponse could be sent without an `id`, crashing the receive loop AFTER
the first fill -- fill PASSED but confirm/advance FLAKY-timed-out. Fixed by
echoing the `call_id` on both receive paths; kept here as the canonical example
of the failure class the harness catches.
