# Voice form-fill E2E harness -- runbook

**Bead:** `polyglot-pdf-g8w`. **What this proves:** the live voice cycle --
Gemini asks a field -> user audio answer -> field fills -> Gemini asks to verify
-> user audio confirm -> Gemini advances -- works end to end, against the real
frontend + backend + Gemini, without a human at the mic.

This is a procedure **the agent executes with the `preview_*` (Chrome) tools**. It
is not an automated test runner; the agent is the driver. It injects scripted
audio fixtures into the running app through a dev-gated hook and reads back field
state for assertions.

## Pieces

- **App hook** (`frontend/src/shared/connection.ts`): `window.__VFF_TEST_INJECT`,
  installed only when `window.__VFF_LOCAL_DEV === true` **and**
  `window.__VFF_TEST_HARNESS === true`. Exposes `sendAudio`, `sendActivityStart`,
  `sendActivityEnd`, `isNativeVad`, `getLastNextField`.
- **Fixtures** (`frontend/public/test-fixtures/`): committed 16 kHz mono PCM16
  WAVs -- `digits_1234567.wav` ("one two three four five six seven") and
  `confirm_yes.wav` ("yes that's correct"). Vite serves them at
  `http://localhost:5173/test-fixtures/<name>.wav`. Regenerate with
  `gen_fixtures.py` (one-time; output is committed).
- **Harness** (`tests/e2e/voice-harness/harness.js`): browser module installed as
  `window.__VFF_HARNESS` via `preview_eval`. Provides `loadFixture`,
  `injectUtterance`, `waitForGeminiQuestion`, `readField`, `lastNextField`.

## Environment (the part that bites you)

The browser tooling and the app's auth/CORS shape force a specific setup. This is
the configuration that actually works (verified live on bd polyglot-pdf-g8w):

- **Use the Chrome MCP, NOT the Claude Preview tool.** Preview renders in an
  opaque-origin sandbox (`location.origin === "null"`) where `localStorage` /
  `sessionStorage` throw `SecurityError` -- and this app's whole state model is
  `sessionStorage["schema_form_state"]`, so it cannot run there. Drive a real
  Chrome tab: `list_connected_browsers` -> `select_browser` ->
  `tabs_context_mcp {createIfEmpty:true}` -> `navigate`.
- **Frontend must run in `--mode demo`** so `.env.demo` provides the Firebase web
  config; otherwise `firebase/config.ts` throws `auth/invalid-api-key` at import
  and the app never mounts. Run vite yourself (the preview tool runs a plain
  `npm run dev`, which is NOT demo mode):
  `cd frontend && npm run build:worklet && VITE_WS_URL=ws://localhost:8001/ws/fill npx vite --mode demo --port 5174 --strictPort`
- **Pick a CORS-allowed frontend port.** The backend `allow_origins`
  (`backend/main.py`) lists `localhost:5173-5177`. Port `5174` works; a stray
  port (e.g. 5180) fails the `/api/form-kits` preflight and the form list won't
  load ("Unable to load available forms").
- **Run a backend with auth disabled.** The WS handshake hangs (10s timeout, then
  "Localhost failed, trying cloud") unless the backend runs with
  `VFF_DISABLE_AUTH=true` (it otherwise tries to verify the Firebase id token via
  ADC and times out). Start a worktree backend on a free port:
  `VERTEXAI=false VFF_DISABLE_AUTH=true PYTHONPATH=$WT <venv>/python -m uvicorn backend.main:app --port 8001`
  and point the frontend WS at it via `localStorage['__VFF_BACKEND_URL']`.
- **`javascript_tool` has NO top-level await.** Use `.then()` chains, or launch an
  `(async()=>{...})()` that writes its result to a `window.*` object and poll it
  with later evals. And use `el.click()` in JS for buttons -- `computer {ref}`
  clicks were unreliable on this SPA's React modals.

## Steps

### 1. Start backend (auth off) + frontend (demo mode)

Bash is not deny-blocked (powershell is). From the worktree:
```
WT=<worktree-abs-path>; PY=<main-repo>/backend/.venv/Scripts/python.exe
# backend on 8001, auth disabled (run_in_background):
cd "$WT" && VERTEXAI=false USE_PREMIUM_MODEL=false PYTHONPATH="$WT" \
  VFF_DISABLE_AUTH=true DISABLE_GEMINI_VAD=false SEND_TRANSCRIPT=true \
  "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
# frontend on 5174, demo mode (run_in_background):
cd "$WT/frontend" && npm run build:worklet && \
  VITE_WS_URL=ws://localhost:8001/ws/fill npx vite --mode demo --port 5174 --strictPort
```
Wait for `http://localhost:8001/health` and `http://localhost:5174` to respond.
(2.5 is the default model; `USE_PREMIUM_MODEL=true` A/Bs 3.1 -- known to skip
`update_form_fields` more, expect more FLAKY.)

### 2. Open the app with the gates on (Chrome MCP)

`navigate` the tab to `http://localhost:5174/`, then via `javascript_tool`:
```js
localStorage.setItem('__VFF_LOCAL_DEV','true');
localStorage.setItem('__VFF_TEST_HARNESS','true');
localStorage.setItem('__VFF_BACKEND_URL','ws://localhost:8001/ws/fill');
```
Then `navigate` to the URL again (reload) so the app boots with the gates set
(they live in localStorage now, so they survive the reload -- `isTestHarnessEnabled()`
reads window OR localStorage). The harness gate also installs a **mock auth user**
(AuthContext bypass) so you skip Firebase login.

### 3. Walk to the form (JS clicks)

Language modal: click the English button, then -- after the React re-render -- the
i-90 form button. Use `el.click()` in JS (not `computer {ref}`):
```js
[...document.querySelectorAll('button')].find(b=>/^English/i.test(b.innerText.trim())).click();
// (re-read; then on the form step)
[...document.querySelectorAll('button')].find(b=>/i-90/i.test(b.innerText)).click();
```
The form loads, voice auto-connects to :8001, and the disclaimer ("I Agree")
appears. Confirm status is `connected` and `typeof window.__VFF_TEST_INJECT === 'object'`.

### 4. Install the harness + pre-load fixtures

Inject the FULL body of `tests/e2e/voice-harness/harness.js` (it self-installs
`window.__VFF_HARNESS`). Then pre-load both fixtures into window vars (so the cycle
never awaits the network mid-turn):
```js
Promise.all([
  window.__VFF_HARNESS.loadFixture('/test-fixtures/digits_1234567.wav'),
  window.__VFF_HARNESS.loadFixture('/test-fixtures/confirm_yes.wav')
]).then(([d,y]) => { window.__vffDigits = d; window.__vffYes = y; window.__vffReady = true; });
```

### 5. Agree to the disclaimer

```js
[...document.querySelectorAll('button')].find(b=>/I Agree/i.test(b.innerText)).click();
```
This calls `switchToFirstSection` -> restarts Gemini for field 1 on the same
connection (the hook stays valid; `isNativeVad()` still resolves).

### 6. Run the cycle (outcome-gated)

Launch `runCycle` async and poll its result object (no top-level await):
```js
window.__vffReport = null;
window.__VFF_HARNESS.runCycle({
  fieldId: 'p1_line1_aliennumber', expectDigits: '1234567',
  digitsBuf: window.__vffDigits, yesBuf: window.__vffYes
}).then(r => { window.__vffReport = r; });
```
Then poll `window.__vffReport` every few seconds until non-null. `runCycle` gates
on CONCRETE OUTCOMES, not audio: it clears stale state, injects the digits, waits
for the field to hold a value (`waitForFieldValue`), checks `digits === '1234567'`,
injects "yes", waits for the authoritative sessionStorage confirm
(`waitForConfirmed` -- the `ssConfirmed` flag, NOT the fill-time `domConfirmed`
decoration), and then waits for the ADVANCE (`lastNextField` moving to a NEW field
id). PASS requires fill AND confirm AND advance. It returns
`{ verdict: 'PASS'|'FAIL'|'FLAKY', steps:[...], reason? }`.

**Why outcome-gated:** audio-end (`vffOnAudioPlaybackEnd`) is an unreliable turn
signal -- Gemini streams many tiny chunks and an automated tab may not fire
`onended` at all. On the first live run every `waitForGeminiQuestion` timed out
even though the fill SUCCEEDED. The field value / confirmed / advanced flags are
the only trustworthy signals; `waitForGeminiQuestion` is kept for pacing only.

**Assert (advanced):** `preview_eval`: `window.__VFF_HARNESS.lastNextField()`.
PASS if it is a DIFFERENT, expected field id (not `FIELD`). Corroborate with
`preview_network` (a `next_field_hint` message should have gone out).

### 7. Report

Read back `window.__vffReport`. Summarize its `verdict` + `steps`, and on any
non-PASS capture `read_console_messages` + the backend stdout (the dev log file
`backend/logs/gemini_<date>.jsonl` only exists if `backend/.env.DEV` is present --
the raw uvicorn command above does NOT create it; create the marker file first if
you want full-body Gemini I/O).

## Pass / fail / flaky policy

Real Gemini is non-deterministic; 2.5 and 3.1 differ in tool-call reliability
(see bd `gemini-3p1-skips-update-form-fields`). Do NOT treat one run as ground
truth. `runCycle` already classifies:

- **PASS** -- field filled with normalized `digits === '1234567'` AND the field is
  **confirmed**. Confirmation is the invariant under test, so PASS requires it;
  advance is corroboration, not a substitute.
- **FAIL** -- field filled with the WRONG value (`reason: wrong value`), OR the
  field advanced WITHOUT being confirmed (`reason: advanced without confirming` --
  the confirmation step was skipped).
- **FLAKY** -- field never filled, confirmed but never advanced, or never
  confirmed within the timeout (`reason: field never filled` /
  `field never confirmed` / `confirmed but never advanced`). The model behaved
  unexpectedly but not provably wrong. (PASS requires fill AND confirm AND advance
  -- the full fill -> confirm -> advance invariant; confirm-without-advance is the
  signature of the bd polyglot-pdf-0ux receive-loop crash and is correctly FLAKY,
  not PASS.)

**Retry -- clear state BEFORE the reload.** `sessionStorage["schema_form_state"]`
survives a reload, and on the next boot the app RESTORES the old DOM value,
auto-connects, and `capturePreFilledValues()` sends the stale (already-confirmed)
value in the WS handshake -- BEFORE `runCycle` can clear it. So a naive "reload and
redo" can have Gemini start on the NEXT field or with stale context, and is not a
clean rerun of the first-field cycle. **Before each retry's reload, clear the
field state explicitly:** `preview`/`javascript_tool`-eval
`sessionStorage.removeItem('schema_form_state')` (or
`window.__VFF_HARNESS.clearFieldState(FIELD)` then also clear the rest), THEN
reload and redo steps 5-6. (`runCycle`'s own `clearFieldState` at cycle start is a
same-session backstop; it cannot undo a stale value already sent in a prior
handshake.) Run up to 3 times; report PASS if >= 2/3 pass; FAIL if 0/3; FLAKY
otherwise -- with the per-run breakdown and the model (2.5 vs 3.1). The harness
reports the rate, not a brittle boolean.

## Notes / gotchas

- **Gate on OUTCOMES, not audio.** `runCycle` uses `waitForFieldValue` (fill) and
  `waitForConfirmed` (the authoritative sessionStorage `confirmed` flag), plus an
  advance wait. `waitForGeminiQuestion` (`vffOnAudioPlaybackEnd`) is PACING-only and
  routinely times out in an automated tab -- never gate correctness on it.
  (`vffOnTurnComplete` was removed from this surface and is not used.)
- **`domConfirmed` is NOT a confirm signal.** `fieldManager.applyUpdates` sets
  `data-vff-confirmed="true"` at FILL time, so it is true before any "yes" is
  processed. The real confirm signal is `ssConfirmed` (sessionStorage), set only by
  the `confirm_field` round-trip. `readField` returns both; `runCycle` gates on
  `ssConfirmed`.
- **Inject only after the field/connection settles.** Injecting during a section
  switch can be dropped by the backend's `drop_audio` guard; the disclaimer-agree
  -> first-question pacing wait covers this.
- **VAD mode is auto-handled.** `injectUtterance` branches on `isNativeVad()`:
  manual VAD brackets with activity_start/end; native VAD streams continuous audio
  + trailing silence. No caller action needed.
- **Known backend bug (bd polyglot-pdf-0ux):** on native-audio, the
  `update_form_fields` FunctionResponse can be sent without an `id`, raising in
  `send_tool_response` and crashing the receive loop AFTER the first fill. Until
  it's fixed, the fill step PASSES but confirm/advance will FLAKY-timeout. The
  harness CAUGHT this on its first live run.
- **Never commit** `backend/.env.DEV` or `backend/logs/*.jsonl` (PII). The
  fixtures and harness contain no PII and ARE committed.
