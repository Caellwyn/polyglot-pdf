---
name: voice-harness
description: Run the automated voice form-fill E2E test against the real app + real Gemini, with scripted audio (no human mic). Drives the cycle "Gemini asks a field -> inject audio answer -> field fills -> inject 'yes' -> confirm/advance" and reports PASS/FAIL/FLAKY. Use when asked to voice-test the form-fill loop, regression-test the tool-call/field-fill path, or verify a voice change end-to-end without speaking. Wraps tests/e2e/voice-harness/ (bd polyglot-pdf-g8w).
---

# Voice form-fill E2E harness

Drives the real frontend against a local backend + real Gemini (Vertex), feeding
committed 16 kHz PCM16 WAV fixtures into the live WebSocket through a dev-gated
in-app hook (`window.__VFF_TEST_INJECT`). Asserts on concrete outcomes (field
value, confirmed flag, advance), not audio. Full detail:
[`tests/e2e/voice-harness/RUNBOOK.md`](../../../tests/e2e/voice-harness/RUNBOOK.md).
The harness module is [`tests/e2e/voice-harness/harness.js`](../../../tests/e2e/voice-harness/harness.js).

**Kit-agnostic (bd polyglot-pdf-tcemw).** Nothing here names a kit's field ids:
kits live in the GCS bucket and their ids move on every republish (CLAUDE.md
scar #10). The harness discovers its targets from the schema the app loaded --
`lastNextField()` is the field the live session is asking, and
`prepareDigitsTarget()` finds a field the digits fixture fits and seeds every
field before it so the next handshake asks it first.

## What it proves

The voice cycle works end to end: scripted audio "one two three four five six
seven" -> Gemini transcribes it -> `update_form_fields` tool call -> the
discovered field fills with `1234567`; then "yes that's correct" -> confirmed ->
advance to the next field. No human speaks.

## Pieces (already in the repo)

- **App hook** `window.__VFF_TEST_INJECT` in `frontend/src/shared/connection.ts`
  (pushes fixture PCM into the same path the mic uses). Double-gated:
  `isTestHarnessEnabled()` requires `__VFF_LOCAL_DEV` AND `__VFF_TEST_HARNESS`
  (window OR localStorage). The same gate installs a **mock auth user**
  (`AuthContext`) so you skip Firebase login. NEVER active in prod/normal dev.
- **Fixtures** `frontend/public/test-fixtures/*.wav`, served by vite at
  `/test-fixtures/*.wav`. Regenerate with `gen_fixtures.py`.
- **Harness** `tests/e2e/voice-harness/harness.js` -> `window.__VFF_HARNESS`
  (`loadFixture`, `injectUtterance`, `runCycle`, `prepareDigitsTarget`,
  `findDigitsTarget`, outcome waiters, `readField`, `lastNextField`).
- **Headless drivers** `driver_playwright.mjs` (the digits cycle) and
  `driver_w7_desync.mjs` (a scripted W-7 conversation incl. six spelled names),
  sharing `driver_common.mjs`.

## The setup that actually works (do NOT improvise these)

1. **A real-origin browser.** This app needs a working `sessionStorage`, so
   drive it through a browser-automation tool that serves real origins (the
   in-app Browser pane, the Chrome connector, or the headless Playwright
   drivers; an opaque-origin sandbox does not).
2. **Frontend in `--mode demo`** (else `firebase/config.ts` throws
   `auth/invalid-api-key` and the app never mounts), on a **CORS-allowed port**
   5173-5177 (`backend/config.py` `LOCAL_BROWSER_ORIGINS`). Use 5174, with
   `VITE_WS_URL=ws://127.0.0.1:8001/ws/fill` -- the IPv4 literal, since uvicorn
   binds IPv4 only and Chrome resolves `localhost` to `[::1]`.
3. **Backend with `VFF_DISABLE_AUTH=true`** on a free port (else the WS
   handshake times out verifying the Firebase token), **on Vertex**
   (`VERTEXAI=true`; never AI Studio), **serving kits from the bucket**
   (`FORM_KITS_MODE=gcs`), and with **`GOOGLE_CLOUD_QUOTA_PROJECT`** set (user
   ADC has no quota project, so Cloud TTS refuses the `name_spellback` tool and
   spelled-name confirms stall).
4. **Seed BEFORE Agree.** With the intro-clip flag OFF (today's default) the
   inject hook exists before the disclaimer is accepted, and Agree re-handshakes
   from sessionStorage -- so `prepareDigitsTarget()` must run first.
5. **Browser-tool JS has no top-level await.** Launch `(async()=>{...})()` that
   writes to a `window.*` var and poll it. Click buttons with `el.click()` in
   JS, not `computer {ref}` (unreliable on this SPA).

## Run it

```
WT=<worktree-abs-path>; PY=<main-repo>/backend/.venv/Scripts/python.exe
# Backend on 8001 (run_in_background):
cd "$WT" && VERTEXAI=true GOOGLE_CLOUD_PROJECT=polyglot-demo-aa709 \
  GOOGLE_CLOUD_QUOTA_PROJECT=polyglot-demo-aa709 USE_PREMIUM_MODEL=false \
  FORM_KITS_MODE=gcs FORM_KITS_GCS_BUCKET=polyglot-demo-aa709-form-kits \
  PYTHONPATH="$WT" VFF_DISABLE_AUTH=true SEND_TRANSCRIPT=true \
  "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
# Frontend on 5174, demo mode (run_in_background):
cd "$WT/frontend" && npm run build:worklet && \
  VITE_WS_URL=ws://127.0.0.1:8001/ws/fill npx vite --mode demo --port 5174 --strictPort
```
(`build:worklet` rewrites the tracked `frontend/public/shared/audio-processor.worklet.js`
-- `git checkout` it afterwards.)

**Headless (preferred):** with Playwright + its headless Chromium installed in a
scratch dir,
```
VFF_PLAYWRIGHT_DIR=<dir>/node_modules node tests/e2e/voice-harness/driver_playwright.mjs
```
prints the report JSON (exit 0 PASS / 2 FLAKY / 1 FAIL). `VFF_KIT=<label regex>`
picks the kit; the default is the first kit `/api/form-kits` lists.

**By hand in a browser tab** (RUNBOOK steps 2-6 have the exact JS):
1. `navigate` to 5174; set `__VFF_LOCAL_DEV` / `__VFF_TEST_HARNESS` /
   `__VFF_BACKEND_URL=ws://127.0.0.1:8001/ws/fill` in localStorage; reload.
2. Click English -> the kit's button (JS `.click()`). Do NOT click Agree yet.
3. Confirm `typeof window.__VFF_TEST_INJECT === 'object'`, inject `harness.js`,
   pre-load the fixtures into `window.__vffDigits/__vffYes`, then
   `window.__vffTarget = window.__VFF_HARNESS.prepareDigitsTarget('1234567')`.
   `fieldId: null` means this kit has no digits-fillable field -- pick another.
4. Click Agree, matching the TRANSLATED label (a Russian session shows
   "Prinimayu", not "I Agree"):
   ```js
   [...document.querySelectorAll('button')]
     .find(b=>/Принимаю|I Agree/i.test(b.innerText)).click();
   ```
   Then confirm `window.__VFF_HARNESS.lastNextField() === window.__vffTarget.fieldId`.
5. Run and poll:
   ```js
   window.__vffReport = null;
   window.__VFF_HARNESS.runCycle({ fieldId: window.__vffTarget.fieldId, expectDigits:'1234567',
     digitsBuf: window.__vffDigits, yesBuf: window.__vffYes }).then(r => window.__vffReport = r);
   ```
   Poll `window.__vffReport` until non-null -> `{ verdict:'PASS'|'FAIL'|'FLAKY', steps, reason? }`.

## Reporting

`runCycle` already classifies PASS/FAIL/FLAKY. For confidence, rerun the whole
cycle (clear `schema_form_state`, reload, redo) up to 3x and report the rate +
the model id (the backend log's `"model"` field). On non-PASS,
capture the browser console and the backend stdout.

## What the harness is for

It catches FunctionResponse plumbing regressions on native-audio fills (a
missing `call_id` echo shows up as fill PASSED, confirm/advance FLAKY), which
unit tests against a mocked session cannot see.
