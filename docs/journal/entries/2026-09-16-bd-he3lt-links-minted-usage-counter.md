---
date: 2026-09-16
bead: polyglot-pdf-he3lt
title: "feat(telemetry): links_minted usage counter written at mint; Usage page shows it and a clearer empty state"
sprint: 22
tags: [testing, conventions]
---

## Trigger

Maintainer observation on 2026-09-15, right after the first live mint on
staging: "usage was not updated." Correct by design at the time -- the
Epic 3 bead E3.4 usage rollups (`firms/{firm_id}/usage/{YYYY-MM}`,
`kits/{kit_id}/usage/{YYYY-MM}`) are written at voice-session END
(`record_session_end`, from the websocket teardown block), with
`links_opened` from the client's open path and `links_completed` from
`complete_link`. A mint itself touches none of those write sites, so the
Usage page stayed on "no data" until a client actually opened the link and
a session later finished -- for a firm that had just paid for and minted a
link, this reads as a broken feature, not a quiet month. This bead is a
reactive fix, not a planned Epic 3 line item; it traces directly to the
maintainer's own bug report rather than a pre-existing plan section.

## What shipped

**Backend (`backend/services/usage_rollups.py`, `backend/routes/
link_routes.py`).** New `record_link_minted(*, firm_id, kit_id,
employee_id, channel, now=None)`, the third entry point into the same
rollup documents E3.4 established. Called from `mint_link` right AFTER
`_reserve_mint`'s reservation transaction has already committed the debit,
the ledger entry, and the `links/{jti}` mint record -- never inside that
transaction, so a rollup write can never slow down or fail a reservation
it merely observes. Writes ONE BATCHED update, the same "both docs or
neither" shape `record_session_end` uses:
`firms/{firm_id}/usage/{month}.links_minted` +
`.by_employee.{employee_id}.links_minted`, and
`kits/{kit_id}/usage/{month}.links_minted`. `by_employee` here keys on the
minting employee's uid unconditionally -- every mint is a staff action by
definition, so there is no link-vs-staff attribution ambiguity the way
`record_session_end`'s own `by_employee` has to resolve.

The route call site wraps the call in its OWN try/except, on top of
`record_link_minted`'s internal never-raises contract -- defense in depth,
mirroring the existing `record_session_end` call site in
`websocket_routes.py`. This was caught by a mutation test: patching
`record_link_minted` itself to raise (rather than going through its
internal guard) surfaced that the route had no protection of its own
before this bead: an exception raised before the callee's try/except is
even reached would have 500'd an otherwise-successful mint.

**Read side (`admin_backend/routes/usage_routes.py`).** `_FIRM_USAGE_KEYS`
and `_KIT_USAGE_KEYS` -- the explicit response allowlists -- gain
`links_minted`. Without this, the new field would have been written to
Firestore but silently dropped from the console's response by the
existing allowlist discipline (the same "no `**doc`, everything named by
hand" rule that already protects this route from accidentally exposing an
internal field).

**Console (`admin-console/src/pages/UsagePage.tsx`).** Renders
`links_minted` in the summary stats row and as a fourth column on the
by-employee breakdown table only (`by_kit`/`by_language` never carry it,
so their tables gained no column). Also: when the usage rollup doc comes
back all-null, the page now makes a SECOND, best-effort check -- a
`getFirm(firm_id)` call (the same route `FirmDetailPage.tsx` already
uses) checking whether any of the firm's ledger rows fall in the selected
month (UTC, matching `_month_key`'s own convention). A mint's ledger entry
commits synchronously in the SAME transaction as the debit, so it is a
reliable "something happened" signal even in the (rare, best-effort) case
where the rollup write itself did not land. When found, the page shows
"no sessions yet this month" instead of the bare "no data"; a failed or
empty ledger check silently degrades to the plain message -- never a
second error banner, never a wrong claim of activity.

**Deferred / not touched:** `credit_ledger.py` and a hypothetical new
backend route for "ledger activity by month" were considered for the
empty-state check and rejected in favor of reusing `getFirm`'s existing
paginated ledger field entirely client-side -- no new backend surface, no
IAM change, and the bead's declared surfaces did not include either of
those files. This is noted as a defended decision in the merge report, not
filed as a follow-up bead (the existing `getFirm` page size, default 50,
is more than sufficient for the recent/current month this page defaults
to).

## Lessons

**A route's own defense-in-depth wrapper is a separate, testable
guarantee from its callee's never-raises contract, and only a mutation
test that patches the CALLEE (not the internal exception path) can tell
them apart.** The existing test suite's own established pattern for this
distinction -- test_usage_rollups.py's `test_NO_firm_id_writes_NOTHING_...`
docstring calling out exactly this "outward behavior looks identical
either way, only a spy distinguishes them" trap -- generalizes directly:
copied that spy-on-`_get_db` technique for the new `record_link_minted`
guard tests, and it is the same class of gap that caught the missing
route-level try/except in `mint_link` (a mutation replacing
`record_link_minted` outright, not just breaking something inside it, is
what a callee's own internal guard cannot protect against). Already
documented in `docs/standards/testing.md#test-the-tests`; no new doc
needed, just another instance proving the existing rule.

## Doc freshness

- `docs/technical_guide.md` Surface contract 26 (session-end usage
  rollups) updated: title now credits the extending bead, "two entry
  points / three call sites" becomes "three entry points / four call
  sites", and a new bullet documents `record_link_minted`'s full
  field-level contract (mirroring the existing bullet style for
  `record_link_opened`/`record_link_completed`). The mint route's own
  table row gains one sentence noting the new rollup write. (No
  `*Last updated:*` bump on this file -- by design; it has none.)
- `docs/components/admin-service.md` and `docs/components/auth.md` each
  get a new dated entry at the top of their append-log describing the
  current shape; both are `OK` per `scripts/check_doc_freshness.py` after
  the bump.
- Reviewed and left as-is (not touched by this bead, staleness pre-dates
  it): `docs/components/config-deployment.md` (flagged stale only because
  it tracks the whole `admin-console/` directory by prefix; its own
  subject -- build/deploy mechanics -- is unrelated to a page-content
  change), `docs/components/schema-forms.md`, `docs/components/voice-ai.md`,
  `docs/components/websocket-routing.md`, `docs/components/
  context-compression.md`, `docs/components/jit-schema.md`,
  `docs/components/tool-call-flow.md`, and most of `docs/standards/*.md`
  -- all flagged by `check_doc_freshness.py` against files this bead never
  touched (config.py, live_ai_gemini.py, schemaFormState.ts, and similar).
  `scripts/check_doc_freshness.py` exits 0 (warn-only) for exactly this
  reason.
- Beads: `bd stale` flags two pre-existing in-progress beads
  (`polyglot-pdf-0dsv4`, `polyglot-pdf-ih428`) not updated in 1+ days --
  neither belongs to this bead's work; left for the orchestrator per
  standing instruction.
- Review outcomes recorded in the closeout ping.

## Files touched

- `backend/services/usage_rollups.py` -- new `record_link_minted()`.
- `backend/routes/link_routes.py` -- calls `record_link_minted` after the
  reservation commits, wrapped in its own try/except.
- `backend/tests/unit/test_usage_rollups.py` -- `record_link_minted` unit
  tests (batched commit, accumulation, firm/kit/employee guards,
  channel-partitioning, never-raises), all mutation-verified.
- `backend/tests/unit/test_link_routes.py` -- integration tests proving
  the route wiring: a real mint bumps the rollup doc; a broken rollup
  write leaves the mint successful.
- `backend/tests/unit/_fake_firestore.py` -- new `_WriteBatch` /
  `db.batch()` support (this shared fake previously modelled only
  `.transaction()`).
- `admin_backend/routes/usage_routes.py` -- `links_minted` added to both
  response allowlists.
- `admin_backend/tests/unit/test_usage_routes.py` -- allowlist
  pass-through tests for the new field on both the firm and kit routes.
- `admin-console/src/utils/adminApi.ts` -- `FirmUsageRollup` type gains
  `links_minted` (top-level and nested under `by_employee`).
- `admin-console/src/pages/UsagePage.tsx` -- renders `links_minted`; adds
  the ledger-activity empty-state check.
- `admin-console/src/pages/UsagePage.test.tsx` -- new tests for the
  `links_minted` display and both empty-state branches, mutation-verified.
- `docs/technical_guide.md` -- Surface contract 26 extended.
- `docs/components/admin-service.md`, `docs/components/auth.md` -- new
  dated entries.
