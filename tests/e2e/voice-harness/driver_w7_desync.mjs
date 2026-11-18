/*
 * Headless W-7 desync-attribution driver (bd polyglot-pdf-0rpu, Stage 1).
 *
 * Drives the FULL W-7 sequence the failing 2026-08-05 sessions walked --
 * checkboxes -> 6 spelled name fields -> non-name fields -- so a compression
 * eviction lands mid-run and read-backs exist on BOTH sides of it, including
 * non-name read-backs AFTER the eviction (the maintainer-flagged confound:
 * eviction timing vs the checkbox->names transition).
 *
 * Fork of driver_playwright.mjs (same environment prereqs; see RUNBOOK).
 * The backend must run with LIVE_DEV_TRANSCRIPTS=true LIVE_DEV_AUDIO_DUMP=true
 * so stt_readback_diff.py can score the run afterward.
 *
 * Env:
 *   VFF_FRONTEND_URL   (default http://localhost:5174)
 *   VFF_BACKEND_WS     (default ws://127.0.0.1:8001/ws/fill)
 *   VFF_PLAYWRIGHT_DIR (node_modules dir holding playwright, if out-of-repo)
 *   VFF_KIT            (optional kit-label regex; default 'W-7')
 *   VFF_W7_STEPS       (optional: run only the first N steps -- smoke mode)
 *   VFF_PACING         (optional: 'polite' waits for the model's playback
 *                       backlog to drain before each injection; 'rude' waits
 *                       for the model to be MID-SPEECH and barges in; default
 *                       is the original fixed-sleep pacing; 'readback' is
 *                       POLITE plus, before each "yes", a bounded wait for
 *                       the model to START speaking -- needed for a
 *                       call-then-speak model such as gemini-3.8-live)
 *
 * Usage: node tests/e2e/voice-harness/driver_w7_desync.mjs
 * Exit 0 = every step filled AND confirmed; 2 = partial; 1 = crash.
 * Per-step epoch timestamps are printed for token-log correlation.
 */

import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { agreeAndWaitForHook } from './driver_common.mjs';

const require_ = createRequire(import.meta.url);
const playwrightPath = process.env.VFF_PLAYWRIGHT_DIR
  ? join(process.env.VFF_PLAYWRIGHT_DIR, 'playwright')
  : 'playwright';
const { chromium } = require_(playwrightPath);

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = process.env.VFF_FRONTEND_URL || 'http://localhost:5174';
const BACKEND_WS = process.env.VFF_BACKEND_WS || 'ws://127.0.0.1:8001/ws/fill';
const MAX_STEPS = parseInt(process.env.VFF_W7_STEPS || '0', 10) || 0;

const harnessSource = readFileSync(join(HERE, 'harness.js'), 'utf8');

// The scripted ANSWERS, in the order a W-7 session asks its questions. NO
// field id is named here (bd polyglot-pdf-tcemw: kits live in the bucket and
// are republished, so ids move). Each step answers WHATEVER field the app is
// pointing the model at when the step starts (the inject hook's
// getLastNextField, set at the handshake and on every advance), and the report
// records which field each answer landed in -- so a republished kit that
// reorders its questions shows up as a mis-paired step, not a silent timeout.
// The "kind" is what the fixture says, for reading the report:
//   choice  -- a radio/checkbox answer ("a new ITIN", "spouse of a U.S. person")
//   spell   -- a name spelled letter by letter (the desync subject)
//   text    -- a free-text answer
// Names 1a = John/Joshua/Johnson (the failing session's names); 1b =
// Maria/Jose/Smith (distinct on purpose -- an acoustic loop of the previous
// spelling must be DETECTABLE, not masked).
const STEPS = [
  ['answer_new_itin', 'choice'],
  ['answer_reason_spouse', 'choice'],
  ['answer_usperson', 'text'],
  ['spell_john', 'spell'],
  ['spell_joshua', 'spell'],
  ['spell_johnson', 'spell'],
  ['spell_maria', 'spell'],
  ['spell_jose', 'spell'],
  ['spell_smith', 'spell'],
  ['answer_street', 'text'],
  ['answer_city', 'text'],
  ['answer_foreign_street', 'text'],
  ['answer_foreign_city', 'text'],
  ['answer_dob', 'text'],
  ['answer_country_birth', 'text'],
];

// The kit-button regex: VFF_KIT overrides (a label regex); default the W-7,
// which is what this conversation script answers.
const KIT_PATTERN = new RegExp(process.env.VFF_KIT || 'W-7', 'i');

function log(msg) {
  process.stderr.write(`[w7-driver] ${msg}\n`);
}

async function clickButton(page, re, label) {
  await page.waitForFunction(
    (src) => [...document.querySelectorAll('button')]
      .some((b) => new RegExp(src, 'i').test(b.innerText.trim())),
    re.source, { timeout: 20000 });
  await page.evaluate((src) => {
    const b = [...document.querySelectorAll('button')]
      .find((x) => new RegExp(src, 'i').test(x.innerText.trim()));
    b.click();
  }, re.source);
  log(`clicked ${label}`);
}

async function main() {
  const steps = MAX_STEPS > 0 ? STEPS.slice(0, MAX_STEPS) : STEPS;
  const fixtures = [...new Set(steps.map(([f]) => f))];

  const browser = await chromium.launch({
    headless: true,
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
      '--autoplay-policy=no-user-gesture-required',
    ],
  });
  const page = await browser.newPage();
  page.on('console', (m) => {
    const t = m.text();
    if (/error|SUSPICIOUS|VFF/i.test(t)) process.stderr.write(`[console] ${t.slice(0, 200)}\n`);
  });

  log(`opening ${FRONTEND} (steps: ${steps.length})`);
  await page.goto(FRONTEND, { waitUntil: 'domcontentloaded' });
  await page.evaluate((ws) => {
    localStorage.setItem('__VFF_LOCAL_DEV', 'true');
    localStorage.setItem('__VFF_TEST_HARNESS', 'true');
    localStorage.setItem('__VFF_BACKEND_URL', ws);
    sessionStorage.removeItem('schema_form_state');
  }, BACKEND_WS);
  await page.goto(FRONTEND, { waitUntil: 'domcontentloaded' });

  await clickButton(page, /^English/, 'English');
  await clickButton(page, KIT_PATTERN, 'form ' + KIT_PATTERN);

  log('waiting for connection + inject hook');
  // Agree + inject hook, in whichever order the intro-clip flag presents
  // them (driver_common.mjs agreeAndWaitForHook; bd polyglot-pdf-s1iex.7).
  await agreeAndWaitForHook(page, /I Agree/, log);

  await page.evaluate(harnessSource);
  await page.waitForFunction(() => typeof window.__VFF_HARNESS === 'object');
  log('harness installed; preloading fixtures');
  await page.evaluate(async (names) => {
    const H = window.__VFF_HARNESS;
    window.__vffBufs = {};
    for (const n of names) {
      window.__vffBufs[n] = await H.loadFixture('/test-fixtures/' + n + '.wav');
    }
    window.__vffYes = await H.loadFixture('/test-fixtures/confirm_yes.wav');
  }, fixtures);

  // Step 1 answers whatever the post-Agree handshake points at, so wait for
  // that handshake to set it (the restarted connection manager starts empty).
  await page.waitForFunction(
    () => !!window.__VFF_TEST_INJECT && !!window.__VFF_TEST_INJECT.getLastNextField(),
    undefined, { timeout: 30000 });

  const PACING = process.env.VFF_PACING || 'default';
  log(`running W-7 sequence (pacing: ${PACING})`);
  await page.evaluate(({ stepList, pacing }) => {
    window.__vffSeqReport = null;
    const H = window.__VFF_HARNESS;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    // turn_complete timestamps for READBACK pacing (chains any existing hook).
    window.__vffTcAt = 0;
    const prevTc = window.vffOnTurnComplete;
    window.vffOnTurnComplete = () => {
      window.__vffTcAt = Date.now();
      if (typeof prevTc === 'function') prevTc();
    };

    // Pacing arms (bd 0rpu round 2). POLITE waits for the model's playback
    // backlog to fully drain before speaking (no interruptions possible);
    // RUDE waits until the model is demonstrably MID-SPEECH and barges in.
    async function paceBeforeInject(rec, key) {
      const hook = window.__VFF_TEST_INJECT;
      if (!hook || !hook.getPlaybackBacklog || pacing === 'default') return;
      const t0 = Date.now();
      // READBACK (bd polyglot-pdf-r3ham.3): a call-then-speak model
      // (gemini-3.8-live) speaks its read-back AFTER update_form_fields, so at
      // the moment the field fills the playback backlog is still empty and
      // POLITE would inject "yes" over the read-back it never heard. Before the
      // "yes", first wait (bounded) for the model to START speaking, then drain.
      if (pacing === 'readback' && key === 'backlogAtYes') {
        while (Date.now() - t0 < 8000 && hook.getPlaybackBacklog().aheadSec < 0.2) {
          await sleep(100);
        }
        if (rec) rec.readbackStartMs = Date.now() - t0;
        // A spelled read-back pauses between letters, which briefly drains
        // the playback backlog; draining alone then injects "yes" MID
        // read-back. Also require a server turn_complete that arrives AFTER
        // the read-back started. Known weak: the WS turn_complete is sent per
        // output-transcription chunk, not at the true turn end (bd ucmpg).
        const speakAt = Date.now();
        while (Date.now() - t0 < 25000 && !(window.__vffTcAt > speakAt)) {
          await sleep(100);
        }
        if (rec) rec.turnCompleteMs = Date.now() - t0;
      }
      if (pacing === 'polite' || pacing === 'readback') {
        let calm = 0;
        while (Date.now() - t0 < 25000 && calm < 3) {
          calm = hook.getPlaybackBacklog().aheadSec < 0.15 ? calm + 1 : 0;
          await sleep(300);
        }
      } else if (pacing === 'rude') {
        while (Date.now() - t0 < 20000
               && hook.getPlaybackBacklog().aheadSec < 0.6) {
          await sleep(120);
        }
      }
      if (rec) rec[key] = hook.getPlaybackBacklog().aheadSec;
    }

    async function confirmOnce(fieldId, rec) {
      await paceBeforeInject(rec, 'backlogAtYes');
      await H.injectUtterance(window.__vffYes);
      const c = await H.waitForConfirmed(fieldId, { timeoutMs: 30000 });
      if (c.met) return c;
      // 95uy quirk: one extra "yes" on a confirm stall.
      await H.injectUtterance(window.__vffYes);
      return H.waitForConfirmed(fieldId, { timeoutMs: 20000 });
    }

    async function runStep(fixture, kind) {
      // The field the app is asking right now -- discovered, not scripted.
      // It must be an UNCONFIRMED field: right after a confirm the advance can
      // lag, and answering the field just confirmed would false-pass (its
      // value is already there for waitForFieldValue to find).
      const cur = await H.waitForCondition(() => {
        const id = H.lastNextField();
        return id && H.readField(id).ssConfirmed !== true ? id : false;
      }, { timeoutMs: 15000 });
      const fieldId = cur.met ? cur.value : null;
      const rec = { fieldId, fixture, kind, tStart: Date.now(), retries: 0 };
      if (!fieldId) {
        rec.confirmed = false;
        rec.reason = 'app never pointed at an unconfirmed field (lastNextField=' + H.lastNextField() + ')';
        return rec;
      }
      for (let attempt = 0; attempt < 2; attempt++) {
        if (attempt) { rec.retries++; await sleep(2000); }
        await paceBeforeInject(rec, 'backlogAtAnswer');
        await H.injectUtterance(window.__vffBufs[fixture]);
        const f = await H.waitForFieldValue(fieldId, { timeoutMs: 35000 });
        if (!f.met) continue;
        rec.value = f.value && (f.value.domValue != null ? f.value.domValue : f.value.ssValue);
        rec.tFill = Date.now();
        const c = await confirmOnce(fieldId, rec);
        if (c.met) {
          rec.confirmed = true;
          rec.tConfirm = Date.now();
          rec.advancedTo = c.value && c.value._lastNextField;
          return rec;
        }
      }
      rec.confirmed = !!rec.confirmed;
      return rec;
    }

    (async () => {
      const out = [];
      for (const [fixture, kind] of stepList) {
        const rec = await runStep(fixture, kind);
        out.push(rec);
        if (!rec.confirmed) { rec.aborted = true; break; }
        // Let Gemini speak the next question before the next answer.
        await sleep(2500);
      }
      window.__vffSeqReport = { steps: out, done: true };
    })().catch((e) => {
      window.__vffSeqReport = { steps: [], done: true, error: String(e && e.message) };
    });
  }, { stepList: steps, pacing: PACING });

  // 15 fields x ~60s worst case + slack.
  const deadline = Date.now() + 20 * 60 * 1000;
  let report = null;
  while (Date.now() < deadline) {
    report = await page.evaluate(() => window.__vffSeqReport);
    if (report && report.done) break;
    await new Promise((r) => setTimeout(r, 4000));
  }
  // Grace so the final generation's audio + transcript flush, then stop.
  await new Promise((r) => setTimeout(r, 5000));
  await page.evaluate(() => window.__VFF_HARNESS && window.__VFF_HARNESS.stopSilenceStream());
  await browser.close();

  if (!report) {
    console.log(JSON.stringify({ verdict: 'FLAKY', reason: 'report never resolved' }));
    process.exit(2);
  }
  const confirmed = (report.steps || []).filter((s) => s.confirmed).length;
  const verdict = confirmed === steps.length ? 'PASS' : 'PARTIAL';
  console.log(JSON.stringify({ verdict, confirmed, total: steps.length, ...report }, null, 2));
  process.exit(verdict === 'PASS' ? 0 : 2);
}

main().catch((e) => {
  console.log(JSON.stringify({ verdict: 'FAIL', reason: 'driver crash: ' + e.message }));
  process.exit(1);
});
