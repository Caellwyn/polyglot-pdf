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
 * Usage: node tests/e2e/voice-harness/driver_latin_storage_ru.mjs
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
  application_type: 'apply_new_itin',
  reason: ['e_spouse_of_us_person'],
  relationship_to_us_person: 'Spouse',
  us_person_name_ssn_itin: 'Loretta Johnson 555121212',
  reason_h_details: '',
  treaty_country: '',
  treaty_article_number: '',
};
const LEAD_IN = [];
const TARGET_FIELD = 'name_1a_first';
const FIXTURES = ['spell_cyrillic_nikolaev', 'spell_latin_nikolaev'];

function log(msg) { process.stderr.write(`[latin-driver] ${msg}\n`); }

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

  // RUSSIAN session -> ASR runs ru-RU -> Cyrillic reaches the model intact.
  // The button label is the native name; match on it rather than "Russian".
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
  // ("Prinimayu", not "I Agree" -- DisclaimerModal.BUTTON_TRANSLATIONS). The
  // English literal already timed out at 20s and crashed a run once, which is
  // why this pattern is bilingual: an English-only match would silently hit
  // nothing here and leave the flag-ON path hanging on the inject-hook wait
  // (bd polyglot-pdf-s1iex.7). This is the ONLY Agree click in this driver --
  // a second one below would block once this dismisses the modal. Escaped to
  // keep this source ASCII (scar #6).
  await clickIfPresent(
    page, new RegExp('\u041f\u0440\u0438\u043d\u0438\u043c\u0430\u044e' + '|I Agree'),
    'disclaimer agree (ru, pre-hook)');

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

  // (Agree was already clicked above, before the inject-hook wait -- see the
  // bilingual clickIfPresent there. A second click here would BLOCK: clickButton
  // waits 60s and throws when the modal is already dismissed, which is exactly
  // what happens with the intro flag OFF. bd polyglot-pdf-s1iex.7, cross-surface
  // review round 1 -- the same removal the three non-RU drivers got.)

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
