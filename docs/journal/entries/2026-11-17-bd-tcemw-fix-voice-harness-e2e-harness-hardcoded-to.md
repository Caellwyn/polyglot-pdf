---
date: 2026-11-17
bead: polyglot-pdf-tcemw
title: "fix(voice-harness): E2E harness hardcoded to deleted i-90 kit (UI nav + field defaults)"
tags: [harness, testing]
---

## Trigger

The voice-harness E2E (`tests/e2e/voice-harness/`) was hardcoded to the deleted
i-90 kit: the drivers clicked an "i-90" picker button and `harness.js` defaulted
to `p1_line1_aliennumber` / `p1_line2_acctidentifier`, ids that no longer exist.
The skill carried a "CURRENTLY BROKEN" banner. It became urgent because the
gemini-3.8-live validation epic (`polyglot-pdf-r3ham`) needs a working harness
for its spelling-aloud re-test (`r3ham.3`: run `driver_w7_desync.mjs` with
`SPELLBACK_TOOL_ENABLED=false` to decide whether the Cloud TTS `name_spellback`
workaround can retire).

## What shipped

- **Discovery instead of hardcoding.** Since the bead was written, CLAUDE.md scar
  #10 made kits bucket-only and forbade naming a kit's field ids in tests, so
  "repoint at w7/f1040" became "name no id at all". `harness.js` gained
  `getSchema`, `findDigitsTarget`, `seedPrefixBefore` and `prepareDigitsTarget`:
  pick, in schema order, an unconditionally shown single-line text/number field
  whose own `validation.pattern` accepts `1234567` (tier `pattern`) or whose id /
  `spoken_name` reads as a number (tier `numeric-label`), and which the app's own
  `validateField` accepts the value into; seed every field before it confirmed.
  Seeding happens BEFORE the disclaimer Agree, because Agree's
  `switchToFirstSection` re-handshakes from sessionStorage -- so the model's first
  question is the target. `runCycle` defaults to `lastNextField()`;
  `runMultiSectionScenario` and `runSecretaryQuery` now REQUIRE their ids.
- **`validateFieldValue` on the dev-gated inject hook** (`connection.ts`): runs the
  app's `validateField` -- the gate every AI fill passes -- so discovery cannot
  pick a field (format_preset ssn/zip/..., min_length, numeric bounds) whose fill
  the app would reject. Without the hook method, a conservative local check
  rejects any `format_preset` field.
- **`driver_playwright.mjs`:** kit = `VFF_KIT` or the first kit `/api/form-kits`
  lists; seeds pre-Agree; asserts `getLastNextField() === target` before
  spending audio. **`driver_w7_desync.mjs`:** each scripted answer goes to
  whatever field the app is asking (`lastNextField`, waited until unconfirmed),
  and the report records where each answer landed.
- **`driver_common.mjs` `agreeAndWaitForHook`:** all four W-7 drivers clicked
  Agree only if it was visible within 2 s; a slower modal left the session parked
  on the disclaimer forever (the first live W-7 run timed out exactly so). Now
  polls until Agree is clicked AND the hook exists.
- **RUNBOOK / SKILL:** Vertex only, kits from the bucket (`FORM_KITS_MODE=gcs`),
  `GOOGLE_CLOUD_QUOTA_PROJECT`, the 127.0.0.1 WS URL, the discovery flow, a
  headless-drivers section; banner removed.
- **Live verification (Vertex `gemini-3.8-live`):** `driver_playwright` PASS on
  W-7 (discovered `foreign_tax_id_number`: fill -> confirm -> advance), re-run
  PASS after the validator fix; `driver_w7_desync` with `VFF_W7_STEPS=5` PASS 5/5
  (`name_1a_first`=JOHN, `name_1a_middle`=JOSHUA, `name_spellback` delivered).
- **Tests:** `frontend/src/shared/voiceHarnessTargetDiscovery.test.ts` (14 cases,
  synthetic schemas only); each of 17 mutations of the discovery/seed rules
  turns it red.
- **Review record.** Fresh-eyes (sonnet), 1 round: NO-GAPS; it filed
  `polyglot-pdf-w04up` (the Latin/Russian W-7 arm drivers still hardcode W-7
  ids) and flagged an over-broad SKILL sentence (adopted: scoped). Opus outer
  cross-surface review round 1: GAPS-FOUND (3) -- discovery could pick a field
  the app's validator rejects (adopted: `validateFieldValue`); the "no field ids"
  claim was unscoped in testing.md/RUNBOOK (adopted); three wrong RUNBOOK
  statements (WS-URL precedence, "all drivers", 3.1 on Vertex; adopted). Filed:
  `polyglot-pdf-xvoeu` (driver comments claim Agree re-creates the connection
  manager), `polyglot-pdf-nu6vm` (pre-existing RUNBOOK staleness). Also filed:
  `polyglot-pdf-zc7t4` (`apply_details_w7.py` targets the retired `reason_a`).

## Lessons

- **A local stack can be forbidden what the deployed one is allowed** -- the
  mirror of scar #7. User ADC carries no quota project, so Cloud TTS returned
  `PermissionDenied` and the `name_spellback` tool failed locally while the model
  kept trying to read the name back; the spelled-name confirm stalled and looked
  like model flakiness. `GOOGLE_CLOUD_QUOTA_PROJECT` fixed it. A local voice run
  that touches a non-Gemini Google API should check the backend log for
  `PermissionDenied` before blaming the model.
- **A target the harness picks must be one the app would accept.** Re-deriving
  the app's validation rules in an injected script is the same twin-rule drift
  as the hand-copied `groupInputs`; exposing the real validator on the dev hook
  removes the copy.
- **"Click if visible within N seconds" is not an ordering strategy.** It
  silently skips the click when the UI is slower than N; poll for the end state
  (clicked AND ready) instead.

## Doc freshness

- `docs/components/voice-ai.md`: prose updated (the inject hook's methods, incl.
  `validateFieldValue`) and stamp bumped.
- `docs/components/websocket-routing.md`, `docs/standards/voice-and-vad.md`:
  track `connection.ts`; reviewed (the hook addition does not change their
  content) and stamp bumped. `websocket-routing.md` still carries two older
  stacked stamps (pre-existing).
- `docs/standards/testing.md`: harness paragraph updated; its STALE flag comes
  from conftest/config changes on other branches, left as-is.
- Other STALE docs prep listed (auth, admin-service, schema-forms, jit-schema,
  pdf-filling, tool-call-flow, ai-models, ...) track files this branch did not
  touch: pre-existing, left.
- Prep's beads audit flagged `polyglot-pdf-h06sv` as stale in-progress -- another
  session's infra work, not this branch's; left.

## Files touched

- `tests/e2e/voice-harness/harness.js` -- discovery, seeding, validator gate, required ids
- `tests/e2e/voice-harness/driver_playwright.mjs` -- kit/target discovery flow
- `tests/e2e/voice-harness/driver_w7_desync.mjs` -- follows `lastNextField`
- `tests/e2e/voice-harness/driver_common.mjs` -- new, `agreeAndWaitForHook`
- `tests/e2e/voice-harness/driver_latin_storage{,_ru}.mjs`, `driver_ru_register.mjs` -- use the helper
- `tests/e2e/voice-harness/gen_fixtures.py` -- comment
- `tests/e2e/voice-harness/RUNBOOK.md`, `.claude/skills/voice-harness/SKILL.md` -- rewritten flow
- `frontend/src/shared/connection.ts` -- `validateFieldValue` on the dev hook
- `frontend/src/shared/voiceHarnessTargetDiscovery.test.ts` -- new
- `docs/components/voice-ai.md`, `docs/components/websocket-routing.md`, `docs/standards/voice-and-vad.md`, `docs/standards/testing.md`
