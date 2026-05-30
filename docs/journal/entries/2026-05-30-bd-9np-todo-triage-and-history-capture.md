---
date: 2026-05-30
bead: polyglot-pdf-9np
title: "Triage TODO.md into work beads + capture pilot/business history"
tags: [conventions]
---

## Trigger

`bd polyglot-pdf-9np` (child of `polyglot-pdf-ee5`, "Beads bootstrap + TODO.md
triage"). `planning_documents/TODO.md` (last updated **November 20, 2025**)
predates beads and had drifted: it mixed already-shipped work, obsolete
cleanups, operational/pilot logistics, and genuinely-live engineering
workstreams in one flat checklist. The bead's scope note warned against blind
transcription — many items were already done or already owned by other beads,
so this needed an **item-by-item audit against current code** plus
**history preservation** before TODO.md could drop to historical.

## What shipped

An audit pass (every TODO item verified against current `main`), **15 new work
beads** for the live items, corrected dependency edges, and this history-capture
entry. TODO.md is marked superseded with a header pointing at the beads, keeping
its business/pilot context in place.

### Audit verdicts (TODO item -> disposition)

| TODO item | Verdict | Evidence (verified 2026-05-30) |
|---|---|---|
| Field validation, confirmation system, native-language disclaimer, print/PDF fill | DONE | All four marked complete Nov 18-20 2025; confirmed live. |
| `getFieldBySpokenName()` part->section fix | DONE | `schemaFormState.ts:654` uses `currentSectionId`/`completedSections`; no `currentPartId`/`completedParts`. |
| TECHNICAL_GUIDE.md v4.0 update | DONE | Marked complete. |
| Logging Phase 1 (token tracking) | DONE | `structured_logger.py`, `dev_file_logger.py`, `log_schemas.py` present; usage_metadata extraction at `live_ai_gemini.py:1137-1150`. |
| PII clears on close / clear-form | DONE | `schemaFormState.ts:403` `clear()` removes the storage key; `handleClearForm()` in `VoiceOverlayMobile.tsx`. Backend stateless. |
| Deprecated demo components (`adult_intake_demo.html`, `GreetingCarousel`, legacy auth) | OBSOLETE | None present in repo — already removed. |
| Parts/sections terminology + `current_part_id` rename | LIVE, **already owned** | Backend holdouts still exist (`live_ai_gemini.py` etc.) but the rename is tracked by `polyglot-pdf-gfb.4` and canon by `polyglot-pdf-m3f`. No new bead — dedup. |
| Planning-doc archival (IMPLEMENTATION_PLAN, GATED_DISCLAIMER, etc.) | LIVE, **already owned** | Covered by `polyglot-pdf-4p0` (archive canonical + stale docs). No new bead. |
| E2E testing pass | LIVE | -> `polyglot-pdf-277`. |
| JIT live validation (`USE_JIT_SCHEMA`) | LIVE | -> `polyglot-pdf-7ds`. Flag defaults `false` at `config.py:46`; JIT unit suite is `test_jit_schema_loading.py` with **12** tests (TODO claimed 33). |
| console.log cleanup | LIVE | -> `polyglot-pdf-tp3`. Actual count **429** (`335 log / 64 error / 30 warn`), not the ~268 claimed. |
| Highlight timing 1500 vs 2000ms | LIVE | -> `polyglot-pdf-nxb`. `webFormConnection.ts:1336` = 1500ms, `SchemaForm.tsx:129` = 2000ms. |
| Future forms I-589 / I-485 / I-765 / N-400 | LIVE | -> `zmg` / `8t6` / `p7y` / `dqg`. Only `form-kits/i-90/` ships today. |
| Logging roadmap Phases 2-6 | LIVE (partial/none) | -> `g0e` / `3ae` / `ytf` / `0bs` / `yqg`. Phase 2 partial (`form_session_id` tracked, no session events); Phase 4 partial (`log_field_voice_attempt()` exists, frontend/section-nav missing); Phases 3/5/6 absent. Home doc is `docs/standards/logging-and-cost.md` (`m8s`); this bead files the *work*, per m8s's own note. |
| Perf monitoring dashboard | LIVE | -> `polyglot-pdf-nt0` (depends on logging Phase 5). |
| Digital save / cloud-resume | LIVE (future) | -> `polyglot-pdf-57d`; must reconcile with the stateless-backend + PII invariants. |
| Pilot logistics: paper waivers, earbuds/mics, tablet hardware testing | NON-CODE | Operational, not engineering. Captured below; no bead. |

### Dependency wiring

- `7ds` (JIT validation) depends on `277` (E2E) — JIT can't be validated without
  a working end-to-end baseline.
- Logging phases chained `g0e -> 3ae -> ytf -> 0bs -> yqg`; `nt0` (dashboard)
  also depends on `0bs` (its BigQuery data source).
- All 15 new beads carry a `discovered-from` edge to `9np`.
- **Gotcha:** `bd create --deps <id>` silently dropped the edge for several
  beads (no error). The reliable path was a separate `bd dep add <id>
  --depends-on <dep>`. Verify with `bd ready` / `bd blocked` after creating a
  chained set — don't trust create-time `--deps`.

## History preserved (lived only in TODO.md)

The following context was **only** in TODO.md and is recorded here before that
file drops to historical:

**Pilot setup (ESC nonprofit, target week of Nov 25 2025):**
- Location: ESC nonprofit office. First form: **I-90** (Green Card Renewal).
- Hardware: 8-inch **Amazon Fire HD 8** tablets; **60 disposable earbuds + 2
  lapel mics**; HTTPS required for mic access.
- Operational checklist (non-code, not beaded): print ~20 paper consent waivers;
  test audio quality + mic on hardware arrival; validate UX on actual tablets.

**Business context:**
- LLC established; E&O insurance active; Cyber insurance active.
- Cost per form ~$5 (Gemini API); target price **$20-50/form**. Gemini token
  cost per session dominates hosting cost (hosting is not the cost lever — see
  the keep-classic architecture decision).
- Measured cost ~$0.20 for a 9-12 field session.

**Logging roadmap design** (the full Phase 2-6 plan, key metrics, and the
NEVER-LOG / ALWAYS-LOG compliance split) now lives in
`docs/standards/logging-and-cost.md` (`m8s`); the per-phase *work* is the
`g0e..yqg` bead chain.

**Already-completed-work rationale** (Nov 2025): field-validation hardening,
the confirmation/liability system, the gated native-language disclaimer (18
languages), PyMuPDF print, and the tablet push-to-talk stuck-recording fix
(Dec 3 2025, 5 safety mechanisms) are all shipped and live — preserved in the
table above so the "why" survives the file's retirement.

## Why this matters

Blind transcription would have filed dead beads (terminology + doc-archival are
already owned; demo cleanup is already done) and lost the pilot/business context
that justifies the product's cost model and compliance posture. The audit also
corrected three stale TODO numbers (JIT 33->12 tests, console.log 268->429, and
the parts/section claim that's only *partly* done on the backend).

## Pointers

- Superseded file: `planning_documents/TODO.md` (header now points here + at the
  beads).
- Logging roadmap home: `docs/standards/logging-and-cost.md` (`m8s`).
- Terminology canon / rename: `m3f` / `gfb.4`. Doc archival: `4p0`.

## Doc freshness + tests

`check_doc_freshness.py`: no docs to check (`docs/components/` + `docs/standards/`
still empty under the gfb epic). This entry is tier-3 (not freshness-tracked).

Test suite (`backend/tests/`): **148 passed, 2 skipped, 4 failed**. This branch
touches only `planning_documents/TODO.md` and this journal `.md` — **zero Python**
— so the 4 failures are pre-existing, not introduced here: 3 are the
`WS_IDLE_TIMEOUT_SEC` 120-vs-60 mismatch already tracked by `polyglot-pdf-od1`,
and 1 is `test_live_ai_gemini_real_connection`, a contract test needing a live
Gemini API connection.
