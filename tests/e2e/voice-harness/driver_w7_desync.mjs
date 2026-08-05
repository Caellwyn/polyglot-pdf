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
 *   VFF_W7_STEPS       (optional: run only the first N steps -- smoke mode)
 *   VFF_PACING         (optional: 'polite' waits for the model's playback
 *                       backlog to drain before each injection; 'rude' waits
 *                       for the model to be MID-SPEECH and barges in; default
 *                       is the original fixed-sleep pacing)
 *
 * Usage: node tests/e2e/voice-harness/driver_w7_desync.mjs
 * Exit 0 = every step filled AND confirmed; 2 = partial; 1 = crash.
 * Per-step epoch timestamps are printed for token-log correlation.
 */

import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

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

// (fieldId, fixture) in W-7 schema order. Names 1a = John/Joshua/Johnson
// (the failing session's names); 1b = Maria/Jose/Smith (distinct on purpose --
// an acoustic loop of the previous spelling must be DETECTABLE, not masked).
const STEPS = [
  ['application_type', 'answer_new_itin'],
  ['reason', 'answer_reason_spouse'],
  ['us_person_name_ssn_itin', 'answer_usperson'],
  ['name_1a_first', 'spell_john'],
  ['name_1a_middle', 'spell_joshua'],
  ['name_1a_last', 'spell_johnson'],
  ['name_1b_first', 'spell_maria'],
  ['name_1b_middle', 'spell_jose'],
  ['name_1b_last', 'spell_smith'],
  ['mailing_street', 'answer_street'],
  ['mailing_city_state_country', 'answer_city'],
  ['foreign_street', 'answer_foreign_street'],
  ['foreign_city_state_country', 'answer_foreign_city'],
  ['date_of_birth', 'answer_dob'],
  ['country_of_birth', 'answer_country_birth'],
];

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
  const fixtures = [...new Set(steps.map(([, f]) => f))];

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
  await clickButton(page, /W-7/, 'W-7 form');

  log('waiting for connection + inject hook');
  await page.waitForFunction(
    () => typeof window.__VFF_TEST_INJECT === 'object' && window.__VFF_TEST_INJECT !== null,
    undefined, { timeout: 30000 });

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

  await clickButton(page, /I Agree/, 'disclaimer I Agree');

  const PACING = process.env.VFF_PACING || 'default';
  log(`running W-7 sequence (pacing: ${PACING})`);
  await page.evaluate((stepList, pacing) => {
    window.__vffSeqReport = null;
    const H = window.__VFF_HARNESS;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    // Pacing arms (bd 0rpu round 2). POLITE waits for the model's playback
    // backlog to fully drain before speaking (no interruptions possible);
    // RUDE waits until the model is demonstrably MID-SPEECH and barges in.
    async function paceBeforeInject(rec, key) {
      const hook = window.__VFF_TEST_INJECT;
      if (!hook || !hook.getPlaybackBacklog || pacing === 'default') return;
      const t0 = Date.now();
      if (pacing === 'polite') {
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

    async function runStep(fieldId, fixture) {
      const rec = { fieldId, fixture, tStart: Date.now(), retries: 0 };
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
      for (const [fieldId, fixture] of stepList) {
        const rec = await runStep(fieldId, fixture);
        out.push(rec);
        if (!rec.confirmed) { rec.aborted = true; break; }
        // Let Gemini speak the next question before the next answer.
        await sleep(2500);
      }
      window.__vffSeqReport = { steps: out, done: true };
    })().catch((e) => {
      window.__vffSeqReport = { steps: [], done: true, error: String(e && e.message) };
    });
  }, steps, PACING);

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
