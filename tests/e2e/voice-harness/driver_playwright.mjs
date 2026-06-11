/*
 * Headless Playwright driver for the voice-harness RUNBOOK (bd polyglot-pdf-95uy).
 *
 * Automates the RUNBOOK steps that were previously executed by hand with the
 * Chrome MCP tools: open the demo-mode frontend with the test gates set, walk
 * the language -> form -> disclaimer flow, install harness.js, preload the
 * audio fixtures, run runCycle on the first field, and print the report JSON.
 *
 * Prereqs (see RUNBOOK "Environment"):
 *   - backend on :8001 with VFF_DISABLE_AUTH=true (and the model/VAD env you
 *     want to test)
 *   - frontend on :5174 via `npx vite --mode demo --port 5174 --strictPort`
 *     with VITE_WS_URL=ws://localhost:8001/ws/fill
 *   - `npm i playwright && npx playwright install chromium` somewhere node can
 *     resolve it (pass its dir via NODE_PATH if outside the repo)
 *
 * Usage: node tests/e2e/voice-harness/driver_playwright.mjs [--multi]
 * Exits 0 on PASS, 2 on FLAKY, 1 on FAIL/error; report JSON on stdout.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = process.env.VFF_FRONTEND_URL || 'http://localhost:5174';
const BACKEND_WS = process.env.VFF_BACKEND_WS || 'ws://localhost:8001/ws/fill';
const MULTI = process.argv.includes('--multi');

const harnessSource = readFileSync(join(HERE, 'harness.js'), 'utf8');

function log(msg) {
  process.stderr.write(`[driver] ${msg}\n`);
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

  log(`opening ${FRONTEND}`);
  await page.goto(FRONTEND, { waitUntil: 'domcontentloaded' });
  await page.evaluate((ws) => {
    localStorage.setItem('__VFF_LOCAL_DEV', 'true');
    localStorage.setItem('__VFF_TEST_HARNESS', 'true');
    localStorage.setItem('__VFF_BACKEND_URL', ws);
    sessionStorage.removeItem('schema_form_state');
  }, BACKEND_WS);
  await page.goto(FRONTEND, { waitUntil: 'domcontentloaded' });

  await clickButton(page, /^English/, 'English');
  await clickButton(page, /i-90/, 'I-90 form');

  log('waiting for connection + inject hook');
  await page.waitForFunction(
    () => typeof window.__VFF_TEST_INJECT === 'object' && window.__VFF_TEST_INJECT !== null,
    undefined, { timeout: 30000 });

  await page.evaluate(harnessSource);
  await page.waitForFunction(() => typeof window.__VFF_HARNESS === 'object');
  log('harness installed; preloading fixtures');
  await page.evaluate(async () => {
    const H = window.__VFF_HARNESS;
    const [d, y, d2] = await Promise.all([
      H.loadFixture('/test-fixtures/digits_1234567.wav'),
      H.loadFixture('/test-fixtures/confirm_yes.wav'),
      H.loadFixture('/test-fixtures/digits_12345.wav'),
    ]);
    window.__vffDigits = d; window.__vffYes = y; window.__vffDigits2 = d2;
  });

  await clickButton(page, /I Agree/, 'disclaimer I Agree');

  log(MULTI ? 'running multi-section scenario' : 'running single-field cycle');
  await page.evaluate((multi) => {
    window.__vffReport = null;
    const H = window.__VFF_HARNESS;
    const p = multi
      ? H.runMultiSectionScenario({
          digitsBuf: window.__vffDigits, yesBuf: window.__vffYes,
          s2DigitsBuf: window.__vffDigits2,
        })
      : H.runCycle({
          fieldId: 'p1_line1_aliennumber', expectDigits: '1234567',
          digitsBuf: window.__vffDigits, yesBuf: window.__vffYes,
        });
    p.then((r) => { window.__vffReport = r; })
      .catch((e) => { window.__vffReport = { verdict: 'FAIL', reason: 'driver: ' + e.message }; });
  }, MULTI);

  const deadline = Date.now() + 240000;
  let report = null;
  while (Date.now() < deadline) {
    report = await page.evaluate(() => window.__vffReport);
    if (report) break;
    await new Promise((r) => setTimeout(r, 3000));
  }
  await page.evaluate(() => window.__VFF_HARNESS && window.__VFF_HARNESS.stopSilenceStream());
  await browser.close();

  if (!report) {
    console.log(JSON.stringify({ verdict: 'FLAKY', reason: 'driver: report never resolved' }));
    process.exit(2);
  }
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.verdict === 'PASS' ? 0 : report.verdict === 'FLAKY' ? 2 : 1);
}

main().catch((e) => {
  console.log(JSON.stringify({ verdict: 'FAIL', reason: 'driver crash: ' + e.message }));
  process.exit(1);
});
