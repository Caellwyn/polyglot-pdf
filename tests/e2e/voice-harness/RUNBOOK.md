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
  `sendActivityEnd`, `isNativeVad`, `getLastNextField`, `resetFieldState`, and
  `seedFieldConfirmed` (bd polyglot-pdf-8k8 -- seeds a field filled+confirmed via
  the real `SchemaFormStateManager` write path, for the multi-section scenario).
- **Fixtures** (`frontend/public/test-fixtures/`): committed 16 kHz mono PCM16
  WAVs -- `digits_1234567.wav` ("one two three four five six seven"),
  `confirm_yes.wav` ("yes that's correct"), `digits_12345.wav` ("one two three
  four five", the 5-digit section-2 ZIP), `read_all_options.wav` ("Can you
  please read me the whole list of options?", the bd polyglot-pdf-bxra
  long-standard-list read-out request), plus the secretary/wsao fixtures --
  `gen_fixtures.py`'s UTTERANCES list is the authoritative inventory. Vite
  serves them at `http://localhost:5173/test-fixtures/<name>.wav`. Regenerate
  with `gen_fixtures.py` (one-time; output is committed).
- **Harness** (`tests/e2e/voice-harness/harness.js`): browser module installed as
  `window.__VFF_HARNESS` via `preview_eval`. Provides `loadFixture`,
  `injectUtterance`, `waitForGeminiQuestion`, `readField`, `lastNextField`,
  `runCycle` (single field), and -- for the multi-section demo rehearsal --
  `runMultiSectionScenario`, `seedFields`, `getCurrentSection`,
  `getCompletedSections`, `waitForSection`, `waitForSectionGreeting`.

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
The form loads and the disclaimer ("I Agree") appears.

**Whether the voice auto-connects HERE depends on the intro-clip flag** (bd
`polyglot-pdf-s1iex.7`):

- **`VITE_INTRO_CLIP_ENABLED` off (today's default)** -- the app connects
  BEFORE Agree, so confirm status is `connected` and
  `typeof window.__VFF_TEST_INJECT === 'object'` at this point, then click
  Agree.
- **Flag on** -- there is NO session until Agree (Sol's clip plays against
  nothing), so `__VFF_TEST_INJECT` does not exist yet. Click Agree FIRST, then
  wait for the hook.

Clicking Agree when the modal is up and waiting for the hook afterwards is
correct under BOTH states -- which is exactly what the five drivers do via
their `clickIfPresent` helper. Do not wait for the hook before clicking, or
the flag-on path hangs until timeout.

**Match the TRANSLATED label.** The agree button is per-language
(`DisclaimerModal.BUTTON_TRANSLATIONS`), so a Russian session shows
"Prinimayu", not "I Agree" -- the two RU drivers pass a bilingual pattern for
exactly this reason (an English-only match silently hits nothing and leaves
the flag-on path hanging). Any new driver in a non-English session must do the
same.

### 4. Install the harness + pre-load fixtures

Inject the FULL body of `tests/e2e/voice-harness/harness.js` (it self-installs
`window.__VFF_HARNESS`). Then pre-load the fixtures into window vars (so the cycle
never awaits the network mid-turn). The third fixture (`digits_12345.wav`) is only
needed for the multi-section scenario (step 6b); the single-field cycle needs only
the first two:
```js
Promise.all([
  window.__VFF_HARNESS.loadFixture('/test-fixtures/digits_1234567.wav'),
  window.__VFF_HARNESS.loadFixture('/test-fixtures/confirm_yes.wav'),
  window.__VFF_HARNESS.loadFixture('/test-fixtures/digits_12345.wav')
]).then(([d,y,d2]) => { window.__vffDigits = d; window.__vffYes = y; window.__vffDigits2 = d2; window.__vffReady = true; });
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

### 6a. Assert the thinking indicator armed (bd polyglot-pdf-fa4x)

`runCycle` records the backend `agent_processing` (thinking-indicator) signal it
observed during the cycle in `report.thinking`. In NATIVE VAD this proves the START
signal -- `input_transcription` -> `on_user_activity` -> `agent_processing:true` ->
the frontend dots -- fired without a human at the mic (the wpw.5 gap fa4x closed).
The observer is installed at harness install and auto-resets each `runCycle`.

- `report.thinking.sawStart` -- a `processing:true` arrived (the START fired). In
  native VAD this is the fa4x assertion.
- `report.thinking.sawClearAfterStart` -- a matching `processing:false` followed (the
  CLEAR, at the agent's first response audio).
- `report.thinking.count` -- raw event count (expect ~2 per turn: true then false).

It is OBSERVATIONAL -- it never flips the PASS/FAIL/FLAKY verdict (a signal-timing
quirk must not fail a clean fill/confirm/advance). To drive it standalone:
`__VFF_HARNESS.resetThinkingObserver()` -> inject an utterance -> read
`__VFF_HARNESS.thinkingObserved()`. The app fires `window.vffOnAgentProcessing` on
every `agent_processing` message (a dev-only hook; undefined in production).

A live native-VAD run (2.5 native-audio, START=HIGH) showed
`{sawStart:true, sawClearAfterStart:true, count:4}` across two turns -- the indicator
arms and clears in native VAD.

### 6b. Run the MULTI-SECTION scenario (the demo rehearsal -- bd polyglot-pdf-8k8)

The single-field cycle (step 6) proves one field round-trips. The **demo** the epic
(`polyglot-pdf-wpw`) is judged by is a multi-field run that crosses a SECTION
boundary. `runMultiSectionScenario` is that rehearsal. Launch it the same async-poll
way:
```js
window.__vffMultiReport = null;
window.__VFF_HARNESS.runMultiSectionScenario({
  digitsBuf: window.__vffDigits, yesBuf: window.__vffYes,
  s2DigitsBuf: window.__vffDigits2
}).then(r => { window.__vffMultiReport = r; });
```
Poll `window.__vffMultiReport` until non-null.

**What it does (Strategy A -- seed-and-confirm):** Section 1 of the I-90 has 9
fields, but only the numeric `p1_line1_aliennumber` is fillable by the canned
digit/yes audio. So the scenario **seeds the other section-1 fields confirmed**
through the dev hook (`__VFF_TEST_INJECT.seedFieldConfirmed`, which routes through
the SAME `SchemaFormStateManager` write path a real confirm uses), leaving the
alien-number as the LAST unconfirmed field. It sets `p1_checkbox4` to a non-"[0]"
option so the three `show_if`-gated `p1_line5*` name fields stay HIDDEN and don't
block completion. Then:
- **Leg 1 (section 1):** voice-fill + confirm `p1_line1_aliennumber`. Because it is
  now the last unconfirmed VISIBLE field, the FE's REAL auto-advance fires
  (`handleConfirmFieldRequest` -> `computeNextField` null -> `switchToSection`).
- **section-cross:** assert `getCurrentSection().order === 2`, the old section is in
  `completedSections`, `vffOnSectionChanged` fired, and `lastNextField` points at
  the first section-2 field.
- **Leg 2 (section 2):** voice-fill + confirm `p1_line6f_zipcode` (the 5-digit
  `digits_12345.wav` fixture) -- proves a SECOND field fills in a DIFFERENT section
  after the switch.

Returns `{ verdict: 'PASS'|'FAIL'|'FLAKY', crossedToSection: bool, legs: [...] }`.
Confirm is **order-tolerant** (the `runCycle` change for bd par/tfz): a proactive
2.5 confirm that lands on the verify turn BEFORE "yes" counts as success.

**Known-RED path (do NOT confuse with a harness regression):** the scenario above
crosses sections via the FE auto-advance / `manual_section_switch` path, which is
sound. The **AI-initiated** switch -- where Gemini calls the `switch_section` tool
mid-section -- is still broken by the receive-loop teardown race **bd
polyglot-pdf-0c1 (y4a)**: the handler cancels the receive task before the
`switch_section` FunctionResponse is delivered, so that path stalls intermittently.
**That AI-switch path is NOT gated by any test here.** The
`@pytest.mark.external` sequence regression
(`backend/tests/contract/test_tool_contracts.py`) only drives
`update_form_fields` -> `confirm_field` for one field -- it never invokes the
`switch_section` tool, so it does NOT cover the y4a teardown race. The y4a defect
is covered by the unit work in **bd polyglot-pdf-0c1** (a fake-LiveAI test
asserting the switch_section response is sent before the receive task is
cancelled); until that lands the AI-initiated switch is ungated. Do not drive an
AI-initiated `switch_section` in this browser scenario and expect green.

### 6c. Run the SECRETARY cross-field query (bd polyglot-pdf-p68s / jnjj.45d)

This proves the secretary's two client-owned inputs round-trip end to end: the
full-form catalog sent at handshake (`full_schema`) and per-field `shown`. It asks
the live model a plain-language question about a PAST answer in a DIFFERENT field,
which the thin principal must route to the `ask_secretary` tool.

Pre-load the query fixture alongside the others (step 4):
```js
window.__VFF_HARNESS.loadFixture('/test-fixtures/secretary_query_alien.wav')
  .then(b => { window.__vffSecretaryQ = b; });
```
Then launch the scenario (async-poll, like the others):
```js
window.__vffSecReport = null;
window.__VFF_HARNESS.runSecretaryQuery({
  seedFieldId: 'p1_line1_aliennumber', seedValue: '1234567',
  queryBuf: window.__vffSecretaryQ
}).then(r => { window.__vffSecReport = r; });
```
Poll `window.__vffSecReport` until non-null. It seeds the alien number confirmed
(the recallable answer), waits for Gemini's field question, injects "what alien
registration number did I give earlier?", and waits out the model turn. A
`verdict: 'DRIVEN'` means the query audio went out after a clean seed.

**Authoritative assertion = the BACKEND LOG, not the browser.** The secretary
answer rides Gemini's audio/transcript (not on the webFormConnection message path
the harness observes), and the tool dispatch + answer are backend-side. Confirm in
the backend stdout:
- an `ask_secretary_complete` line with `field_count` > 0, `shown_count` >= 0, and
  `answer_len` > 0 -- the tool ran with the WHOLE-form catalog + a real shown_map
  and returned a non-empty prose answer. (`field_count` reflects the full form's
  field values, not just the current section -- the p68s point.)
- NO `ask_secretary_no_schema` / `ask_secretary_no_text_ai` / `ask_secretary_timeout`
  fail-open lines for that turn.

The live model is non-deterministic about WHEN it calls a tool; if no
`ask_secretary_complete` appears, re-run (the model may have answered from context
or asked a clarifying question first) -- treat it like the PASS/FLAKY policy below.

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
  signature of the since-fixed bd polyglot-pdf-0ux receive-loop crash and is
  correctly FLAKY, not PASS.)

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

> **Same-page rerun (no reload).** The reload path above is still the recommended
> retry. If you DO rerun on the same page, `clearFieldState` now prefers the app's
> `__VFF_TEST_INJECT.resetFieldState(FIELD)` hook (bd polyglot-pdf-o1c), which clears
> the field through `SchemaFormStateManager` (save + `schemaFormStateChange`
> dispatch) and refreshes the live `WebFormConnection` state -- so SchemaForm's React
> state and the connection's in-memory copy are reset too, not just sessionStorage.
> It still cannot undo a stale value already sent in an EARLIER handshake, so a fresh
> connect is needed if one was already established with the old value.

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
  manual VAD brackets with activity_start/end; native VAD streams the utterance
  then CONTINUOUS real-time silence until the next utterance (bd
  polyglot-pdf-95uy: a fixed 500 ms tail then dead air never closes the turn --
  Gemini's native VAD needs an unbroken stream). `stopSilenceStream()` ends it
  explicitly if a driver needs quiet. `runCycle` also retries the "yes" once on
  a confirm timeout (the 95uy ctrl46 second-turn_complete stall quirk). No
  caller action needed.
- **FIXED backend bug (bd polyglot-pdf-0ux, fixed 2026-06-09):** on native-audio
  the `update_form_fields` FunctionResponse could be sent without an `id`,
  crashing the receive loop AFTER the first fill (fill PASSED, confirm/advance
  FLAKY-timed-out). `_build_function_response` now echoes the `call_id` on both
  receive paths. The harness CAUGHT this on its first live run; a
  confirm-without-advance FLAKY is no longer expected from this cause.
- **Never commit** `backend/.env.DEV` or `backend/logs/*.jsonl` (PII). The
  fixtures and harness contain no PII and ARE committed.
