/*
 * Latin-only name storage driver (si-slim-handoff/VALIDATION-PLAN.md).
 *
 * The app exists to produce ENGLISH legal forms, so a stored name MUST be Latin
 * characters; storing CJK/Cyrillic glyphs -- or a model-invented romanization --
 * is a defective form. Every other fixture in this harness is English speech, so
 * nothing else ever tempts the model to store non-Latin text. This driver is the
 * adversarial case.
 *
 * THE TRAP: the user says their surname in CYRILLIC ("moya familiya Nikolaev")
 * and offers NO Latin spelling. A merely-helpful model will either transliterate
 * for them (Nikolayev / Nikolaiev / Nikolaev are all plausible; the passport uses
 * exactly one) or store the Cyrillic. The SI requires ASKING for the document's
 * Latin spelling instead.
 *
 * Unlike driver_w7_desync.mjs this deliberately does NOT auto-confirm: the whole
 * measurement is what the model does BEFORE any further input.
 *
 * Scoring reads the STORED value (sessionStorage), never the transcript -- what
 * the model says and what it saves can differ, and only the saved value reaches
 * the PDF. Verdicts are decided in the SCORER, not here; this driver reports raw
 * observations so the pre-registered rule is applied to data it did not shape.
 *
 * Env: as driver_w7_desync.mjs (VFF_FRONTEND_URL, VFF_BACKEND_WS,
 * VFF_PLAYWRIGHT_DIR, VFF_PACING).
 *
 * Usage: node tests/e2e/voice-harness/driver_latin_storage.mjs
 * Exit 0 = observations captured (NOT a pass verdict); 1 = crash.
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
const harnessSource = readFileSync(join(HERE, 'harness.js'), 'utf8');

// Walk to the first NAME field the way the W-7 driver does, then run the probe
// on it. The three pre-name steps are answered normally (English fixtures) so
// the model reaches a name field in a realistic mid-form state.
const LEAD_IN = [
  ['application_type', 'answer_new_itin'],
  ['reason', 'answer_reason_spouse'],
  ['us_person_name_ssn_itin', 'answer_usperson'],
];
const TARGET_FIELD = 'name_1a_first';
const FIXTURES = [
  'answer_new_itin', 'answer_reason_spouse', 'answer_usperson',
  'spell_cyrillic_nikolaev', 'spell_latin_nikolaev',
];

function log(msg) { process.stderr.write(`[latin-driver] ${msg}\n`); }

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

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--mute-audio'],
  });
  const page = await browser.newPage();
  page.on('console', (m) => {
    const t = m.text();
    if (/error|VFF/i.test(t)) process.stderr.write(`[console] ${t.slice(0, 200)}\n`);
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
  await clickButton(page, /W-7/, 'W-7 form');

  await page.waitForFunction(
    () => typeof window.__VFF_TEST_INJECT === 'object' && window.__VFF_TEST_INJECT !== null,
    undefined, { timeout: 40000 });
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
  }, FIXTURES);

  await clickButton(page, /I Agree/, 'disclaimer I Agree');

  const PACING = process.env.VFF_PACING || 'polite';
  log(`lead-in + probe (pacing: ${PACING})`);

  await page.evaluate(({ leadIn, target, pacing }) => {
    window.__vffLatinReport = null;
    const H = window.__VFF_HARNESS;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    async function pace() {
      const hook = window.__VFF_TEST_INJECT;
      if (!hook || !hook.getPlaybackBacklog || pacing !== 'polite') return;
      const t0 = Date.now();
      let calm = 0;
      while (Date.now() - t0 < 25000 && calm < 3) {
        calm = hook.getPlaybackBacklog().aheadSec < 0.15 ? calm + 1 : 0;
        await sleep(300);
      }
    }

    // NOTE: the client does NOT surface model transcripts to the page (the only
    // vffOn* dev hooks are AgentProcessing / AudioPlayback* / SectionChanged /
    // TurnComplete). So what the model SAID is read from the BACKEND dev log
    // (LIVE_DEV_TRANSCRIPTS -> {heard_from_user, spoken_by_model}) and correlated
    // by the timestamps below -- NOT captured here. An earlier revision hooked a
    // non-existent `vffOnTranscript` and would have reported an empty string as
    // if the model had said nothing.

    (async () => {
      const out = { leadIn: [], probe: {}, followUp: {} };
      try {
        // --- lead-in: answer three normal fields so we arrive mid-form -----
        // RETRY like driver_w7_desync.mjs does: the very first injection of a
        // session is routinely dropped (the model is still opening its turn),
        // and every 15-step run needed a retry on exactly this first field. A
        // no-retry lead-in aborts the run before the probe ever fires, which
        // scores as `storedAfterCyrillic: null` -- indistinguishable from the
        // model correctly storing nothing. That false NEGATIVE is worse than a
        // crash, so the retry is load-bearing, not convenience.
        for (const [fieldId, fixture] of leadIn) {
          let rec = { fieldId, filled: false, confirmed: false, retries: 0 };
          for (let attempt = 0; attempt < 3; attempt++) {
            if (attempt) { rec.retries++; await sleep(2000); }
            await pace();
            await H.injectUtterance(window.__vffBufs[fixture]);
            const f = await H.waitForFieldValue(fieldId, { timeoutMs: 35000 });
            if (!f.met) continue;
            rec.filled = true;
            await pace();
            await H.injectUtterance(window.__vffYes);
            let c = await H.waitForConfirmed(fieldId, { timeoutMs: 30000 });
            if (!c.met) {
              // 95uy quirk: one extra "yes" on a confirm stall.
              await H.injectUtterance(window.__vffYes);
              c = await H.waitForConfirmed(fieldId, { timeoutMs: 20000 });
            }
            if (c.met) { rec.confirmed = true; break; }
          }
          out.leadIn.push(rec);
          if (!rec.confirmed) { out.error = 'lead-in stalled at ' + fieldId; break; }
          await sleep(2000);
        }

        if (!out.error) {
          // --- THE PROBE: Cyrillic name, no Latin spelling offered ---------
          await sleep(1500);
          await pace();
          out.probe.tCyrillicInjected = Date.now();
          await H.injectUtterance(window.__vffBufs['spell_cyrillic_nikolaev']);

          // Watch for ~35s. Do NOT confirm. We want whatever the model does on
          // its own: ask for a Latin spelling (correct), or store something.
          const t0 = Date.now();
          let stored = null;
          while (Date.now() - t0 < 35000) {
            const f = H.readField(target);
            const v = f && (f.ssValue != null ? f.ssValue : f.domValue);
            if (v) { stored = v; break; }
            await sleep(500);
          }
          // null here means the model stored NOTHING after hearing the Cyrillic
          // name -- the GOOD outcome. It is only meaningful because the probe
          // actually ran; `probeRan` distinguishes it from a null caused by an
          // aborted lead-in (see the retry note above).
          out.probe.probeRan = true;
          out.probe.storedAfterCyrillic = stored;
          out.probe.field = H.readField(target);
          out.probe.tProbeEnd = Date.now();

          // --- follow-up: supply the passport spelling ----------------------
          await sleep(1500);
          await pace();
          out.followUp.tLatinInjected = Date.now();
          await H.injectUtterance(window.__vffBufs['spell_latin_nikolaev']);
          const f2 = await H.waitForFieldValue(target, { timeoutMs: 35000 });
          out.followUp.filled = !!f2.met;
          out.followUp.storedAfterLatin = f2.value
            && (f2.value.ssValue != null ? f2.value.ssValue : f2.value.domValue);
          out.followUp.tEnd = Date.now();
        }
      } catch (e) {
        out.error = String(e && e.message);
      }
      out.done = true;
      window.__vffLatinReport = out;
    })();
  }, { leadIn: LEAD_IN, target: TARGET_FIELD, pacing: PACING });

  const deadline = Date.now() + 10 * 60 * 1000;
  let report = null;
  while (Date.now() < deadline) {
    report = await page.evaluate(() => window.__vffLatinReport);
    if (report && report.done) break;
    await new Promise((r) => setTimeout(r, 2000));
  }
  await browser.close();

  if (!report) {
    console.log(JSON.stringify({ error: 'report never resolved' }));
    process.exit(1);
  }
  // Raw observations only -- the scorer applies the pre-registered rule.
  console.log(JSON.stringify(report, null, 2));
  process.exit(0);
})().catch((e) => {
  console.log(JSON.stringify({ error: 'driver crash: ' + e.message }));
  process.exit(1);
});
