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
 * Env: as driver_w7_desync.mjs (VFF_FRONTEND_URL, VFF_BACKEND_WS,
 * VFF_PLAYWRIGHT_DIR, VFF_PACING).
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

// RUSSIAN-SESSION variant. The point of this run is that ASR is ru-RU, so the
// Cyrillic utterance reaches the model AS CYRILLIC -- in the en-US sessions the
// recognizer force-romanized it ("Familie Nikolai") and the probe tested nothing
// (see VALIDATION-PLAN.md, "MEASURED CONFOUND").
//
// NO ENGLISH LEAD-IN: every lead-in fixture is English speech, which a ru-RU
// recognizer would mangle. Reaching the name field: SEED the six fields ahead of it (through the real
// SchemaFormStateManager write path, the same one a genuine confirm uses) rather
// than voice-filling them. Voice lead-in is not an option here -- every lead-in
// fixture is English speech and this session's recognizer is ru-RU.
const SEED = {
  // Seed ONLY field 1. The point of this driver is to make the model SPEAK the
  // remaining section-1 fields in Russian -- especially 'reason', whose 8
  // option labels are long baked-Russian legal prose. That spoken output is the
  // register sample; seeding more would skip the very text under review.
  application_type: 'apply_new_itin',
};
const LEAD_IN = [];
const TARGET_FIELD = 'name_1a_first';
const FIXTURES = [];

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

  // RUSSIAN session -> ASR runs ru-RU -> Cyrillic reaches the model intact.
  // The button label is the native name; match on it rather than "Russian".
  await clickButton(page, /Russkiy|Russian/, 'Russian');
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

  // The disclaimer's agree button is TRANSLATED per session language
  // (DisclaimerModal.BUTTON_TRANSLATIONS): a Russian session shows
  // "Prinimayu", NOT "I Agree" -- matching the English literal timed out at
  // 20s and crashed the first run. \u-escaped to keep this source ASCII (scar #6).
  const RU_AGREE = '\u041f\u0440\u0438\u043d\u0438\u043c\u0430\u044e';  // 'Prinimayu'
  await clickButton(page, new RegExp(RU_AGREE + '|I Agree'), 'disclaimer agree (ru)');

  const PACING = process.env.VFF_PACING || 'polite';
  log(`lead-in + probe (pacing: ${PACING})`);

  await page.evaluate(({ leadIn, target, pacing, seed }) => {
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
      const out = { leadIn: [], probe: {}, followUp: {}, seed: {} };
      try {
        // Seed the fields ahead of the name field so the model lands on it.
        // seedFields verifies each write read back confirmed via sessionStorage,
        // so a silent seed failure surfaces here instead of corrupting the probe.
        try {
          out.seed = window.__VFF_HARNESS.seedFields(seed);
        } catch (e) {
          out.error = 'seed failed: ' + String(e && e.message);
        }
        if (out.seed && out.seed.failed && out.seed.failed.length) {
          out.error = 'seed incomplete: ' + out.seed.failed.join(',');
        }
        // Seeding all 7 fields of section 1 COMPLETES it, so the app
        // auto-advances to section 2 (where the name fields live). That switch
        // tears down and re-opens the Gemini session. The first attempt probed
        // during that window and the audio went out over a still-CONNECTING
        // socket: 699x "send() called but WebSocket not open! readyState:0",
        // a "Section switch timed out", ZERO Cyrillic in the transcript -- and
        // the run STILL reported a stored value, i.e. a fake result.
        //
        // The switch is REQUIRED (the target field is in section 2), so wait
        // for it authoritatively -- waitForSection is the harness's own
        // section-cross proof -- and record the outcome so a bad window is
        // visible in the data instead of silently scoring.
        const sec = await H.waitForSection(2, { timeoutMs: 60000 });
        out.sectionCrossed = !!(sec && sec.met);
        if (!out.sectionCrossed) {
          out.error = 'section switch to 2 never completed after seeding';
        }
        await H.waitForSectionGreeting({ timeoutMs: 25000 });
        await sleep(3000);   // let the re-opened session settle
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
          // LISTEN, do not answer. The model asks the remaining section-1
          // fields in Russian one after another; we only need it to SPEAK so
          // the dev transcript captures the prose for register review. The
          // richest sample is 'reason' -- 8 long baked-Russian legal labels
          // the SI must recite in full.
          //
          // Nudge it forward with a single injected utterance when it goes
          // quiet, rather than answering properly: an answer would advance the
          // field and cut the recital short.
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
          out.probe.probeRan = true;   // listening completed
        }
      } catch (e) {
        out.error = String(e && e.message);
      }
      out.done = true;
      window.__vffLatinReport = out;
    })();
  }, { leadIn: LEAD_IN, target: TARGET_FIELD, pacing: PACING, seed: SEED });

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
