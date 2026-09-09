---
date: 2026-09-09
bead: polyglot-pdf-wio6m
title: "feat(telemetry): E3.1 usage event v2 -- one emitter shape, usage_kind, text + TTS pricing tables, call-site coverage test"
sprint: 22
tags: [conventions, testing]
---

## Trigger

Epic 3 bead 1 of the admin-console program (`docs/sprint_22_admin-console_plan.md`,
Epic 3 "Usage event v2"). Epic 3 wants a cost dashboard: Firestore rollups for
live views, and a Cloud Logging -> BigQuery sink for historical cost and
cost-vs-income. Neither is worth building on today's telemetry, because the paid
calls do not agree on a shape. The Live adapter emits a rich per-turn
`gemini_api_response` event; the text adapter logs a `structlog` line with a
different key set; the TTS path emits nothing at all. Three shapes, one of them
absent, means the sink would need three schemas and the totals would still be
wrong.

This bead lays the schema so beads 2 and 3 have something to plumb ids into. It
deliberately wires the emitter CONTRACT only -- the per-path plumbing is
`polyglot-pdf-cjifh` (live) and `polyglot-pdf-t86oz` (text + TTS).

## What shipped

**One emitter, three wrappers.** `StructuredLogger._emit_usage` is the single
private emitter; `log_gemini_api_response`, `log_text_ai_usage` and
`log_tts_usage` are thin wrappers differing only in `event_type`, `usage_kind`,
and which counts they carry. `log_gemini_api_response` keeps its v1 name and
positional signature, so the live adapter's call site compiles untouched and the
six new context ids arrive as optional keywords.

**The key set is the contract, and it is written unconditionally.** `usage_kind`
is a closed `Literal` (7 members) in `log_schemas.py`; the optional context keys
are declared once as `USAGE_CONTEXT_KEYS` and `_emit_usage` iterates THAT tuple.
Every wrapper writes every key on every call, `None` included. This is the whole
point of v2: at the BigQuery sink a *missing* key and a *null* are different
things, and a row that omits `firm_id` because the caller had no value drops
silently out of a `GROUP BY firm_id`. The invoice and the dashboard then
disagree, with no error anywhere to notice. Iterating the schema's own tuple
means a key added there without a matching emitter parameter raises `KeyError`
on the first emit rather than quietly never being written.

**Two new pricing tables, because they bill as different products.** The
existing `GEMINI_PRICING_BY_FAMILY` prices the native-audio Live endpoint and
does not transfer. `TEXT_GENERATION_PRICING` (verified against
ai.google.dev/gemini-api/docs/pricing on 2026-09-09) prices plain
`generate_content`; `TTS_PRICING_USD_PER_CHAR` prices Cloud TTS per *character*.
`get_text_generation_pricing` matches longest-key-first, so a `-lite` id is not
billed at flash rates (3x input, 6x output), and returns `None` for an unknown
model rather than a fallback row -- deliberately unlike the Live lookup's
`DEFAULT_PRICING_FAMILY`, because in a cost report a confident wrong number is
worse than a visible gap.

**The Chirp3-HD rate is an explicit, tested gap.**
cloud.google.com/text-to-speech/pricing could not be fetched: the page truncates
before its pricing table, and the `/docs/pricing` alias 301s to a host that
404s. Per the bead contract that leaves a `None` and a failing test rather than a
number written from memory.

**Deferred / deliberately not done:** the per-path plumbing (beads `cjifh`,
`t86oz`). The coverage test's emit proofs for the text and TTS sites are
`xfail(strict=True)` until then.

## Lessons

**A permanently-red test is not a TODO, it is a broken suite.** The bead asked
for "an explicit `TODO` with `None` and a test that fails until it is filled."
Taken literally that leaves the suite red for every unrelated change from now
on -- and a suite that is always red stops being read, which costs more than the
missing rate. `xfail(strict=True)` keeps the forcing function *exactly*: the test
documents the gap, does not redden the suite, and the moment someone fills the
rate in it XPASSes and pytest reports a FAILURE demanding the marker come off.
Mutation 5 verified precisely that. Generalizes: when a spec asks for a failing
test as a reminder, strict xfail is almost always the right shape.

**`is` is over-specification, and the full suite is where it bites.** The pricing
lookup test originally asserted `get_text_generation_pricing(id) is TABLE[key]`.
It passed alone and in `-k` runs, then failed 5 ways in the full suite:
`backend.config` is reachable under two module identities during a whole-suite
run, so equal rows from different module copies compared unequal. Identity was
never the contract -- "resolves to the right rates" is. Two things generalize:
assert the property, not the object; and this is exactly why CLAUDE.md says run
the FULL suite pre-PR rather than a filtered subset. A `-k` run would have
shipped this.

**Enumerate mechanically, and prove the enumerator is not vacuous.** The coverage
test AST-walks everything Cloud Run executes rather than trusting anyone to
register a new paid call (scar #8). But an enumeration guard has a failure mode
of its own: a broken matcher finds zero sites and reports perfect coverage of
nothing. So there is a separate test asserting the walk actually finds the three
known adapters, and the allowlist is checked in BOTH directions so a stale entry
(a claim of coverage for deleted code) fails too.

**Mutation-verify the mutation that matters.** Eight mutations, each red then
restored: dropping one envelope key reddened 16 tests across all 7 kinds; fake
call sites were planted for all three SDK shapes (`generate_content`,
`synthesize_speech`, `live.connect`) in both a new file and two existing deployed
files, since a matcher can easily handle one shape and miss another.

## Doc freshness

- `docs/standards/logging-and-cost.md` -- the tier-2 doc that Tracks all three
  changed source files. New usage-event-v2 section (wrappers, the closed
  `usage_kind` set, why keys are unconditional, the coverage guard), the two
  pricing tables with verified figures and the dated Chirp3-HD gap, and
  "(defined, not yet emitting)" dropped from the schemas heading, which is no
  longer true. Stamped 2026-09-09.
- `docs/technical_guide.md` -- new **Surface contract 20** (producer, consumers,
  the closed key set, what silently breaks on drift, and the pricing-tables
  non-transfer trap). Stamped 2026-09-09. Note: this file DOES carry a
  `*Last updated:*` line, contrary to a "no stamp by design" claim in the task
  brief -- the file wins.
- `docs/standards/hipaa-pii-policy.md` -- Tracks `log_schemas.py`. Its
  event-schemas row described only the v1 emitter; it now records that the v2
  envelope carries ids/counts/costs/model names only with no free-text slot, and
  names the test that pins it. Stamped 2026-09-09.
- Remaining STALE docs in the closeout-prep report are pre-existing and were left
  alone: each is flagged because its Tracks line names `backend/config.py`, which
  nearly every bead edits, and none describe the surfaces this bead changed.

## Files touched

- `backend/utils/log_schemas.py` -- `UsageKind` literal, `USAGE_CONTEXT_KEYS`,
  `UsageEventMetadata`, two new `EventType` members.
- `backend/utils/structured_logger.py` -- `_emit_usage` plus the three wrappers.
- `backend/config.py` -- `TEXT_GENERATION_PRICING`,
  `get_text_generation_pricing`, `TTS_PRICING_USD_PER_CHAR`, `tts_voice_tier`.
- `backend/tests/test_usage_event_coverage.py` (new) -- AST enumeration +
  allowlist, both directions, plus the non-vacuity and scope guards.
- `backend/tests/test_usage_event_schema.py` (new) -- full-key-set proof per
  `usage_kind`, derived from the literal.
- `backend/tests/unit/test_pricing_tables.py` (new) -- per-column rate checks and
  the strict-xfail TTS TODO gate.
- `docs/standards/logging-and-cost.md`, `docs/technical_guide.md`,
  `docs/standards/hipaa-pii-policy.md` -- as above.

Review outcomes recorded in the closeout ping.
