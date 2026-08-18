/*
 * Russian-session REGISTER listener (si-slim-handoff/RU-REGISTER-REVIEW.md).
 *
 * Question it answers: would a middle/high-school-educated speaker who reads
 * ONLY Russian clearly understand what the assistant says? That needs the
 * model's actual PROSE, so this driver makes it SPEAK and captures the result.
 *
 * How: select Russian (so ASR runs ru-RU), seed ONLY field 1 of the W-7, then
 * LISTEN -- no answers injected. The model asks the remaining section-1 fields
 * itself, and the payload is `reason`: an 8-option checkbox_group whose baked
 * Russian labels are long legal prose the SI must recite in full. That single
 * turn is the densest register sample the form produces.
 *
 * Deliberately does NOT inject the English 'read_all_options' fixture as a
 * nudge -- English audio in a ru-RU session would pollute the very sample being
 * measured, and the recital already fires on the ask.
 *
 * Scoring happens OUTSIDE this driver, from the BACKEND dev transcripts
 * (LIVE_DEV_TRANSCRIPTS): the client never surfaces model transcripts to the
 * page. This driver only drives and records timings.
 *
 * Sibling drivers, different jobs: driver_latin_storage.mjs (en-US Cyrillic
 * storage probe) and driver_latin_storage_ru.mjs (the same probe in a ru-RU
 * session, where Cyrillic actually reaches the model).
 *
 * Env: VFF_FRONTEND_URL, VFF_BACKEND_WS, VFF_PLAYWRIGHT_DIR.
 * (No VFF_PACING -- this driver injects nothing, so there is nothing to pace.)
 *
 * Usage: node tests/e2e/voice-harness/driver_ru_register.mjs
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

// RUSSIAN session so ASR runs ru-RU and the model SPEAKS Russian -- that
// spoken prose is the whole point (register review). Nothing is injected:
// every fixture in this harness is English speech, which a ru-RU recognizer
// would mangle, and the recital fires on the ASK anyway.
const SEED = {
  // Seed ONLY field 1. The point of this driver is to make the model SPEAK the
  // remaining section-1 fields in Russian -- especially 'reason', whose 8
  // option labels are long baked-Russian legal prose. That spoken output is the
  // register sample; seeding more would skip the very text under review.
  application_type: 'apply_new_itin',
};

function log(msg) { process.stderr.write(`[ru-register] ${msg}\n`); }

async function clickButton(page, re, label) {
  await page.waitForFunction(
    (src) => [...document.querySelectorAll('button')]
      .some((b) => new RegExp(src, 'i').test(b.innerText.trim())),
    // 20s was too tight: /ws/fill accept takes ~10s locally (bd
    // polyglot-pdf-020a4 -- three Vertex clients built per connection),
    // and the disclaimer only renders AFTER the socket is up, so the
    // agree button can legitimately be absent for well over 20s.
    re.source, { timeout: 60000 });
  await page.evaluate((src) => {
    const b = [...document.querySelectorAll('button')]
      .find((x) => new RegExp(src, 'i').test(x.innerText.trim()));
    b.click();
  }, re.source);
  log(`clicked ${label}`);
}

/**
 * Click a button only if it is already on screen (bd polyglot-pdf-s1iex.7).
 *
 * Unlike clickButton this does NOT wait or fail when the control is absent --
 * the disclaimer modal's presence at this point depends on the intro-clip
 * flag, and the driver must work under both states.
 */
async function clickIfPresent(page, pattern, label) {
  const button = page.getByRole('button', { name: pattern }).first();
  try {
    if (await button.isVisible({ timeout: 2000 })) {
      await button.click();
      log(`clicked ${label}`);
      return true;
    }
  } catch {
    // Not present yet -- the caller's wait handles the other ordering.
  }
  return false;
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

  // Pick RUSSIAN so the model SPEAKS Russian -- its prose is the sample.
  // The button shows the native name, so match that too, not just "Russian".
  await clickButton(page, /Russkiy|Russian/, 'Russian');
  await clickButton(page, /W-7/, 'W-7 form');

  // Agree FIRST if the disclaimer modal is already up (bd polyglot-pdf-s1iex.7).
  // ORDER IS FLAG-DEPENDENT, so this handles BOTH states rather than swapping:
  //  - intro clip OFF (today): the app connects before Agree, so
  //    __VFF_TEST_INJECT already exists and this click is simply early --
  //    harmless, the modal is up either way.
  //  - intro clip ON: NO session exists until Agree, so the hook does not
  //    exist yet and waiting for it first would hang until timeout.
  // Clicking when present, then waiting, is correct under both.
  // BILINGUAL on purpose: this session's agree button is TRANSLATED
  // ("Prinimayu", not "I Agree") -- the English literal already timed out and
  // crashed a run once, which is why RU_AGREE exists below. An English-only
  // pre-click would silently match nothing here and leave the flag-ON path
  // hanging on the inject-hook wait (bd polyglot-pdf-s1iex.7, fresh-eyes
  // round 1). Escaped to keep this source ASCII (scar #6).
  await clickIfPresent(
    page, new RegExp('\u041f\u0440\u0438\u043d\u0438\u043c\u0430\u044e' + '|I Agree'),
    'disclaimer agree (ru, pre-hook)');

  await page.waitForFunction(
    () => typeof window.__VFF_TEST_INJECT === 'object' && window.__VFF_TEST_INJECT !== null,
    undefined, { timeout: 40000 });
  await page.evaluate(harnessSource);
  await page.waitForFunction(() => typeof window.__VFF_HARNESS === 'object');
  // No fixture preload: this driver injects nothing (see docblock). The sibling
  // storage drivers preload here; that block was dead weight once the lead-in
  // loop went, so it is gone rather than left as an inert no-op.
  log('harness installed');

  // The disclaimer's agree button is TRANSLATED per session language
  // (DisclaimerModal.BUTTON_TRANSLATIONS): a Russian session shows
  // "Prinimayu", NOT "I Agree" -- matching the English literal timed out at
  // 20s and crashed the first run. \u-escaped to keep this source ASCII (scar #6).
  const RU_AGREE = '\u041f\u0440\u0438\u043d\u0438\u043c\u0430\u044e';  // 'Prinimayu'
  await clickButton(page, new RegExp(RU_AGREE + '|I Agree'), 'disclaimer agree (ru)');

  // No VFF_PACING here: nothing is injected, so there is nothing to pace
  // against. The listen loop does its own quiet-detection inline.
  log('seeding field 1, then LISTENING');

  await page.evaluate(({ seed }) => {
    window.__vffRegisterReport = null;
    const H = window.__VFF_HARNESS;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    // NOTE: the client does NOT surface model transcripts to the page (the only
    // vffOn* dev hooks are AgentProcessing / AudioPlayback* / SectionChanged /
    // TurnComplete). So what the model SAID is read from the BACKEND dev log
    // (LIVE_DEV_TRANSCRIPTS -> {heard_from_user, spoken_by_model}) and correlated
    // by the timestamps below -- NOT captured here. An earlier revision hooked a
    // non-existent `vffOnTranscript` and would have reported an empty string as
    // if the model had said nothing.

    (async () => {
      const out = { seed: {}, listen: null };
      try {
        // seedFields verifies each write read back confirmed via sessionStorage,
        // so a silent seed failure surfaces here instead of corrupting the run.
        try {
          out.seed = window.__VFF_HARNESS.seedFields(seed);
        } catch (e) {
          out.error = 'seed failed: ' + String(e && e.message);
        }
        if (out.seed && out.seed.failed && out.seed.failed.length) {
          out.error = 'seed incomplete: ' + out.seed.failed.join(',');
        }
        // NO section wait here. This driver seeds ONE field, so section 1 is
        // never completed and never auto-advances -- the model just asks the
        // next field in place, which is exactly what we want to hear. (The
        // sibling storage drivers DO seed all 7 and must wait for the
        // section-2 switch; copying that wait here made waitForSection(2)
        // time out and abort the listen loop before it ran.)
        await sleep(3000);   // let the opening question land
        if (!out.error) {
          // LISTEN, do not answer. The model asks the remaining section-1
          // fields in Russian one after another; we only need it to SPEAK so
          // the dev transcript captures the prose for register review. The
          // richest sample is 'reason' -- 8 long baked-Russian legal labels
          // the SI must recite in full.
          out.listen = { turns: [] };
          for (let i = 0; i < 4; i++) {
            const t0 = Date.now();
            let quiet = 0;
            while (Date.now() - t0 < 45000 && quiet < 6) {
              const b = (window.__VFF_TEST_INJECT
                && window.__VFF_TEST_INJECT.getPlaybackBacklog
                && window.__VFF_TEST_INJECT.getPlaybackBacklog().aheadSec) || 0;
              quiet = b < 0.15 ? quiet + 1 : 0;
              await sleep(500);
            }
            out.listen.turns.push({ i, tEnd: Date.now() });
            // NO injection. 'reason' is an 8-option checkbox_group, so the SI
            // already requires reading all 8 aloud ON THE ASK -- the recital is
            // the register sample. Injecting the English 'read_all_options'
            // fixture into a ru-RU session would only pollute it with English
            // audio the recognizer must guess at.
            await sleep(3000);
          }
          out.listened = true;
        }
      } catch (e) {
        out.error = String(e && e.message);
      }
      out.done = true;
      window.__vffRegisterReport = out;
    })();
  }, { seed: SEED });

  const deadline = Date.now() + 10 * 60 * 1000;
  let report = null;
  while (Date.now() < deadline) {
    report = await page.evaluate(() => window.__vffRegisterReport);
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
