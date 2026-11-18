/*
 * Headless Playwright driver for the voice-harness RUNBOOK (bd polyglot-pdf-95uy).
 *
 * Automates the RUNBOOK steps that were previously executed by hand with the
 * Chrome MCP tools: open the demo-mode frontend with the test gates set, walk
 * the language -> form flow, install harness.js, DISCOVER a field the digits
 * fixture can fill and seed every field before it, accept the disclaimer (whose
 * re-handshake then points the model at that field), preload the audio
 * fixtures, run runCycle, and print the report JSON.
 *
 * NO KIT OR FIELD ID IS NAMED HERE (bd polyglot-pdf-tcemw): kits live in the
 * GCS bucket and are republished constantly. The kit is VFF_KIT (a label
 * regex) or else the first kit the backend's /api/form-kits lists; the field
 * comes from harness.findDigitsTarget() over the schema the app loaded.
 *
 * Prereqs (see RUNBOOK "Environment"):
 *   - backend on :8001 with VFF_DISABLE_AUTH=true (and the model/VAD env you
 *     want to test)
 *   - frontend on :5174 via `npx vite --mode demo --port 5174 --strictPort`
 *     with VITE_WS_URL=ws://127.0.0.1:8001/ws/fill (the IPv4 literal: uvicorn
 *     binds IPv4 only and Chrome resolves localhost to [::1])
 *   - `npm i playwright && npx playwright install chromium` somewhere node can
 *     resolve it (pass its dir via VFF_PLAYWRIGHT_DIR if outside the repo)
 *
 * Env: VFF_FRONTEND_URL, VFF_BACKEND_WS, VFF_PLAYWRIGHT_DIR (as the other
 * drivers), VFF_KIT (optional kit-label regex; default the first listed kit).
 *
 * --multi runs the section-reset scenario, which needs CONTINUOUS_SESSION=false
 * on the backend AND explicit ids: pass VFF_MULTI_OPTS as a JSON object of
 * runMultiSectionScenario's id/seed options (s1FieldId, s1Seed, s2FieldId,
 * s2Seed) chosen for the kit under test.
 *
 * Usage: node tests/e2e/voice-harness/driver_playwright.mjs [--multi]
 * Exits 0 on PASS, 2 on FLAKY, 1 on FAIL/error; report JSON on stdout.
 */

import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// ESM does not honor NODE_PATH; resolve playwright from the repo, or from an
// out-of-repo install pointed at by VFF_PLAYWRIGHT_DIR (e.g. /tmp/node_modules).
const require_ = createRequire(import.meta.url);
const playwrightPath = process.env.VFF_PLAYWRIGHT_DIR
  ? join(process.env.VFF_PLAYWRIGHT_DIR, 'playwright')
  : 'playwright';
const { chromium } = require_(playwrightPath);

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = process.env.VFF_FRONTEND_URL || 'http://localhost:5174';
const BACKEND_WS = process.env.VFF_BACKEND_WS || 'ws://127.0.0.1:8001/ws/fill';
const MULTI = process.argv.includes('--multi');
const EXPECT_DIGITS = '1234567';

const harnessSource = readFileSync(join(HERE, 'harness.js'), 'utf8');

function log(msg) {
  process.stderr.write(`[driver] ${msg}\n`);
}

// The backend's HTTP origin, derived from the WS URL (ws://h:p/ws/fill).
function backendHttp() {
  const u = new URL(BACKEND_WS);
  u.protocol = u.protocol === 'wss:' ? 'https:' : 'http:';
  return u.origin;
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * The kit-button regex: VFF_KIT if set, else the first kit the backend lists.
 * The test backend runs with VFF_DISABLE_AUTH=true, so any bearer passes.
 */
async function resolveKitPattern() {
  if (process.env.VFF_KIT) return new RegExp(process.env.VFF_KIT, 'i');
  const resp = await fetch(backendHttp() + '/api/form-kits', {
    headers: { Authorization: 'Bearer harness' },
  });
  if (!resp.ok) throw new Error('GET /api/form-kits -> ' + resp.status);
  const forms = (await resp.json()).forms || [];
  if (!forms.length) throw new Error('backend lists no form kits');
  log(`kit (first listed): ${forms[0].id} "${forms[0].label}"`);
  return new RegExp(escapeRe(forms[0].label), 'i');
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

  async function setupFail(reason) {
    await browser.close();
    console.log(JSON.stringify({ verdict: 'FLAKY', reason: 'setup-error: ' + reason }));
    process.exit(2);
  }

  log(`opening ${FRONTEND}`);
  await page.goto(FRONTEND, { waitUntil: 'domcontentloaded' });
  await page.evaluate((ws) => {
    localStorage.setItem('__VFF_LOCAL_DEV', 'true');
    localStorage.setItem('__VFF_TEST_HARNESS', 'true');
    localStorage.setItem('__VFF_BACKEND_URL', ws);
    sessionStorage.removeItem('schema_form_state');
  }, BACKEND_WS);
  await page.goto(FRONTEND, { waitUntil: 'domcontentloaded' });

  const kitPattern = await resolveKitPattern();
  await clickButton(page, /^English/, 'English');
  await clickButton(page, kitPattern, 'form ' + kitPattern);

  // Seed BEFORE Agree. Accepting the disclaimer re-handshakes from
  // sessionStorage (switchToFirstSection), so a prefix seeded now makes the
  // discovered target the model's first question. That needs the inject hook
  // before Agree, i.e. the intro-clip flag OFF (today's default): with it ON
  // no session -- and no hook -- exists until Agree, and this wait fails as a
  // setup error instead of hanging.
  log('waiting for schema + inject hook (pre-Agree)');
  try {
    await page.waitForFunction(
      () => typeof window.__VFF_TEST_INJECT === 'object' && window.__VFF_TEST_INJECT !== null
        && !!sessionStorage.getItem('schema_form_state'),
      undefined, { timeout: 30000 });
  } catch {
    await setupFail('inject hook / schema never appeared before Agree (intro-clip flag ON?)');
  }

  await page.evaluate(harnessSource);
  await page.waitForFunction(() => typeof window.__VFF_HARNESS === 'object');

  let target = null;
  if (!MULTI) {
    target = await page.evaluate(
      (d) => window.__VFF_HARNESS.prepareDigitsTarget(d), EXPECT_DIGITS);
    log('target: ' + JSON.stringify(target));
    if (!target.fieldId) await setupFail(target.reason);
    if (target.failed && target.failed.length) {
      await setupFail('seed did not read back confirmed: ' + target.failed.join(','));
    }
  }

  await clickButton(page, /I Agree/, 'disclaimer I Agree');

  if (target) {
    // Prove the post-Agree handshake points the model at the target before
    // spending audio on it (the app sets lastNextField at handshake time).
    try {
      await page.waitForFunction(
        (id) => !!window.__VFF_TEST_INJECT && window.__VFF_TEST_INJECT.getLastNextField() === id,
        target.fieldId, { timeout: 30000 });
    } catch {
      const got = await page.evaluate(
        () => window.__VFF_TEST_INJECT && window.__VFF_TEST_INJECT.getLastNextField());
      await setupFail(`handshake pointed at ${got}, not the seeded target ${target.fieldId}`);
    }
  }

  // The disclaimer restart re-creates the connection manager, which
  // re-publishes the inject hook; the harness reads it lazily, so no reinstall.
  log('preloading fixtures');
  await page.evaluate(async () => {
    const H = window.__VFF_HARNESS;
    const [d, y, d2] = await Promise.all([
      H.loadFixture('/test-fixtures/digits_1234567.wav'),
      H.loadFixture('/test-fixtures/confirm_yes.wav'),
      H.loadFixture('/test-fixtures/digits_12345.wav'),
    ]);
    window.__vffDigits = d; window.__vffYes = y; window.__vffDigits2 = d2;
  });

  log(MULTI ? 'running multi-section scenario' : 'running single-field cycle on ' + target.fieldId);
  const multiOpts = MULTI ? JSON.parse(process.env.VFF_MULTI_OPTS || '{}') : null;
  await page.evaluate(({ multi, opts, fieldId, expectDigits }) => {
    window.__vffReport = null;
    const H = window.__VFF_HARNESS;
    const p = multi
      ? H.runMultiSectionScenario(Object.assign({}, opts, {
          digitsBuf: window.__vffDigits, yesBuf: window.__vffYes,
          s2DigitsBuf: window.__vffDigits2,
        }))
      : H.runCycle({
          fieldId, expectDigits,
          digitsBuf: window.__vffDigits, yesBuf: window.__vffYes,
        });
    p.then((r) => { window.__vffReport = r; })
      .catch((e) => { window.__vffReport = { verdict: 'FAIL', reason: 'driver: ' + e.message }; });
  }, { multi: MULTI, opts: multiOpts, fieldId: target && target.fieldId, expectDigits: EXPECT_DIGITS });

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
  if (target) report.target = target;
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.verdict === 'PASS' ? 0 : report.verdict === 'FLAKY' ? 2 : 1);
}

main().catch((e) => {
  console.log(JSON.stringify({ verdict: 'FAIL', reason: 'driver crash: ' + e.message }));
  process.exit(1);
});
