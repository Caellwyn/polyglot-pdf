---
date: 2026-09-09
bead: polyglot-pdf-t86oz
title: "feat(telemetry): E3.3 text (secretary/validator/translation) + TTS usage events with cost, session_ctx per call"
sprint: 22
tags: [conventions, testing]
---

## Trigger

Epic 3 bead 3 of the admin-console program (`docs/sprint_22_admin-console_plan.md`,
Epic 3 "Usage event v2", text and TTS paths). Bead `polyglot-pdf-wio6m` (E3.1)
shipped the usage-event v2 CONTRACT (`log_text_ai_usage`, `log_tts_usage`, the
closed `usage_kind` set, `TEXT_GENERATION_PRICING` / `TTS_PRICING_USD_PER_CHAR`)
and bead `polyglot-pdf-cjifh` (E3.2) wired the live-voice path, but the text
adapter's `_log_usage` and the three TTS synthesize functions still emitted
only the old plain `structlog` line -- the schema had the columns, nothing
called the new wrappers. `backend/tests/test_usage_event_coverage.py` pinned
this gap explicitly: the text and TTS allowlist entries were
`xfail(strict=True)` naming this bead by id.

The bead's harder constraint: `TextAIGemini` is a per-process SINGLETON
(`backend/dependencies.py`), unlike `LiveAIGemini` (one per WebSocket
connection). Storing session ids on `self` -- the pattern E3.2 used for the
live adapter -- would leak one session's firm/employee/link/kit ids into a
concurrent session's usage event on the shared singleton.

## What shipped

**Text side** (`backend/adapters/text_ai_gemini.py`): `_generate` gains
optional `usage_kind` + `session_ctx` kwargs, threaded from `validate()`
(`usage_kind="text_validator"`), `ask()` (`"text_secretary"`),
`translate_labels()` / `translate_items()` (both `"text_translation"` -- one
product, two request shapes). `_log_usage` now does two things: the
pre-existing plain `text_ai_usage` structlog line (unchanged), and, only when
a caller supplied `usage_kind`, a `log_text_ai_usage(...)` call with a
computed `cost_estimate_usd` from `TEXT_GENERATION_PRICING` (uncached-input +
cached-input + output token costs; `None` for an unpriced model rather than a
guessed number). `ITextAI` (the port) gained the matching optional parameter
on the same four methods so it stays an honest description of the concrete
adapter.

Callers build `session_ctx` (`{firm_id, employee_id, link_jti, kit_id,
channel, form_session_id}`) from their OWN session state and pass it on the
call -- never stored on the singleton. `ValidatorService.validate()` forwards
it straight through. `FormFillingService` (which already holds `self._kit_id`
/ `self._firm_id` / `self._link_jti` / `self._employee_id` from bd
polyglot-pdf-cjifh's live-plumbing work, since IT is per-connection) gained a
`_text_ai_session_ctx()` helper reused at all four of its `text_ai` call
sites (ask_secretary, the per-window validator, the whole-form pro pass).

**TTS side**: `spellback_tts.py` gained `_tts_cost_estimate_usd` and a
shared `_log_tts_usage_event` helper, called by `synthesize_spellback`,
`synthesize_notice`, and `synthesize_intro` after an ACTUAL synthesis
(character count from the SYNTHESIZED text, not the raw caller value) with
their own `usage_kind`. `notice`/`intro` both cache by `(language, key)`, so
a cache hit -- which calls Cloud TTS zero times -- emits ZERO usage events;
emitting on a hit would record cost that was never billed.
`backend/routes/tts_routes.py` gained `_usage_session_ctx(claims)`, building
the context dict from the route's auth-dependency claims (mirroring the
staff-uid-as-`employee_id` fallback bd cjifh used for the WS route's
non-link sessions), forwarded at all three route handlers.

**Removed the two `xfail(strict=True)` markers** in
`test_usage_event_coverage.py` -- both `ALLOWED_SITES` entries are now
`emit_wired: True`, and the strict markers would have failed the suite
(XPASS) the moment the emit landed, forcing this cleanup rather than letting
it slip.

**Cross-surface ripple, found by grepping the whole set rather than one at a
time** (CLAUDE.md scar #8): widening `ITextAI.validate`/`ask`'s real
signature broke every existing test double whose `validate(self, payload)` /
`ask(self, query, context)` had no matching parameter, plus
`TextAIClaudeCli._generate`'s override (the free local-CLI authoring
adapter, which now needed to accept-and-ignore the two new kwargs -- it has
no Google Gemini billing to attribute). Thirteen sites across seven test
files plus one probe script, fixed in one pass rather than one review round
each: `test_validator_service.py` (4 stub classes), `test_validator_windows.py`
(6 closures), `test_validator_steering.py` / `test_form_complete_pro.py` (1
each), `test_ask_secretary_handler.py` (8 closures -- `ask()` now takes a
third positional arg), `test_spellback_tool.py` (2 route-level fakes),
`probe_validator_rail.py` (1, out of test-coverage scope but real code).

**Scope call:** `backend/services/option_translation.py` (the authoring-time
translation bake and the runtime option-override build) is NOT in this
bead's declared surfaces and was left untouched. Its `translate_items` calls
still emit a usage event -- `TextAIGemini.translate_items` always passes
`usage_kind="text_translation"` into `_generate` regardless of whether the
caller supplied `session_ctx` -- but with every context key null, because
`option_translation.py` does not pass `session_ctx`. Same shape as any other
unmigrated caller, not a bug: unfinished attribution the bead's Surfaces
list did not ask for.

## Lessons

**A synchronous/instant async mock does not prove a concurrency guarantee.**
The first version of the singleton-leak mutation test used a plain
`AsyncMock(side_effect=[response_a, response_b])` for the two concurrent
`validate()` calls -- and it PASSED even after I deliberately introduced the
exact leak bug (`self._leaked_session_ctx = session_ctx` in `_generate`, read
back in `_log_usage`) the test was supposed to catch. The reason: an
`AsyncMock` with an instant `side_effect` resolves within one event-loop
tick, so `asyncio.gather`'s two coroutines never actually interleave AT the
critical section -- each one runs its "set on self, then read back" sequence
uninterrupted, coincidentally correct even with the leak in place. The fix
was a `side_effect` function that genuinely `await asyncio.sleep(...)`s (the
FIRST/slower call sleeps longer, so it is the one suspended-then-resumed
after the second call has already overwritten `self`), which made the
mutation test go red as expected. Mutation-testing scar #9 says "prove a new
test can fail"; this is the sharper version for concurrency tests
specifically -- an instant mock can make two coroutines run sequentially in
disguise, and a test built on one proves nothing about the race it claims to
guard.

**A widened port method signature is a cross-surface change even when the
production callers are all correct.** The production diff here was small and
correct on the first pass (four adapter methods, two service call sites); the
thirteen test-double breakages were not bugs in my design, they were the
mechanical, enumerable consequence of one interface change ("any existing
`ITextAI` implementer without the new optional kwarg now raises TypeError the
moment a real caller passes it"). Grepping for every `async def validate(self,
payload)` / `async def ask(self, query, context)` shape across the repo BEFORE
declaring done (rather than running the suite once, fixing whatever failed,
and calling it complete) turned a potential multi-round review cycle into one
pass -- the enumerate-the-set discipline (scar #8) applies to test fixtures
just as much as production call sites.

## Doc freshness

Updated three tier-2 docs whose `**Tracks:**` lines cover the changed files
and whose CONTENT was made stale by this change:
`docs/technical_guide.md` (Surface contract 20's call-site-coverage bullet,
plus the doc's own per-bead changelog line at the top, following the
wio6m/cjifh precedent), `docs/standards/logging-and-cost.md` (the same
call-site-coverage paragraph, plus widened its Tracks line to the four files
it now describes and bumped the stamp), and `docs/standards/
validation-delegation.md` (a new bullet under Frozen contract 5 documenting
the `session_ctx` kwarg on the `ITextAI` port). Deliberately did NOT bump
`validation-delegation.md`'s own `*Last updated*` stamp: its existing note
(bd polyglot-pdf-6dn2n) says the date is frozen on purpose pending a real
content re-verification the doc still needs, and a bump from this narrow
bead would clear that signal for an unrelated future auditor.

Six other tier-2 docs flag STALE in `check_doc_freshness.py` because they
track `form_filling_service.py` or `text_ai_gemini.py` (files this bead
edited): `context-compression.md`, `hipaa-pii-policy.md`, `risk-rating.md`,
`schema-key-visibility.md`, `section-reset-deprecation.md`,
`stateless-architecture.md`. Checked each against this diff's actual content
(not just its Tracks line, per bd cjifh's journal precedent): none describes
the `ITextAI` session-context plumbing, the usage-event call sites, or the
`_text_ai_session_ctx()` helper -- their claims are unaffected. Left
un-bumped for a dedicated docs-audit pass rather than acked here as a side
effect of a plumbing bead.

Review outcomes recorded in the closeout ping.

## Files touched

- `backend/adapters/text_ai_gemini.py` -- `_generate` + `_log_usage` gain
  `usage_kind`/`session_ctx`; `validate`/`ask`/`translate_labels`/
  `translate_items` thread them through and pass their own `usage_kind`.
- `backend/adapters/text_ai_claude_cli.py` -- `_generate` override accepts
  (and ignores) the two new kwargs.
- `backend/ports/text_ai_port.py` -- matching optional `session_ctx` param
  on `validate`/`ask`/`translate_labels`/`translate_items`.
- `backend/services/validator_service.py` -- `ValidatorService.validate()`
  gains + forwards `session_ctx`.
- `backend/services/form_filling_service.py` -- new
  `_text_ai_session_ctx()` helper, used at the ask/validate/pro-pass call
  sites.
- `backend/services/spellback_tts.py` -- `_tts_cost_estimate_usd`,
  `_log_tts_usage_event`; `synthesize_spellback` gains `session_ctx` and
  emits.
- `backend/services/notice_tts.py`, `backend/services/intro_tts.py` --
  `synthesize_notice`/`synthesize_intro` gain `session_ctx` and emit (never
  on a cache hit).
- `backend/routes/tts_routes.py` -- new `_usage_session_ctx(claims)`,
  passed at all three TTS route handlers.
- `backend/scripts/probe_validator_rail.py` -- stub signature fix.
- `backend/tests/test_usage_event_coverage.py` -- both allowlist entries
  flip to `emit_wired: True`; xfail markers removed; docstring updates.
- `backend/tests/unit/test_usage_event_text_tts.py` (new) -- the emit-proof
  + concurrency tests (see What shipped / Lessons).
- `backend/tests/test_validator_service.py`,
  `backend/tests/unit/test_validator_windows.py`,
  `backend/tests/unit/test_validator_steering.py`,
  `backend/tests/unit/test_form_complete_pro.py`,
  `backend/tests/unit/test_ask_secretary_handler.py`,
  `backend/tests/unit/test_spellback_tool.py` -- test-double signature
  fixes for the widened `ITextAI` contract.
- `docs/technical_guide.md`, `docs/standards/logging-and-cost.md`,
  `docs/standards/validation-delegation.md` -- current-state prose updates
  (see Doc freshness).
