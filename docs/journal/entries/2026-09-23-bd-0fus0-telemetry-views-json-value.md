---
date: 2026-09-23
bead: polyglot-pdf-0fus0
title: "fix(telemetry): views reference sink-inferred jsonPayload columns directly, so a field null in the first rows (channel on the admin's grant) blocks view creation -- read fields via JSON_VALUE"
sprint: 22
tags: [hotfix, testing]
---

## Trigger

LIVE 2026-09-23, with both Cloud Logging -> BigQuery sink tables finally
populated on the demo project: creating `income_month` from
`sql/telemetry_views.sql` failed with "400 Field name channel does not
exist in STRUCT<firm_id STRING, timestamp STRING, level STRING, ...> at
[13:15]". The stderr table's very first row was a `subscription_grant`
top-up written by the admin service (which serves both channels and so
writes `channel=None` by design), and a Cloud Logging -> BigQuery sink
infers each destination table's `jsonPayload` STRUCT columns from the rows
it has actually received, skipping any field that was null in every row so
far -- so `jsonPayload.channel` did not exist as a struct field at all, and
any view referencing it directly could not be created.

This traces to the admin-console program plan
(docs/sprint_22_admin-console_plan.md, "BigQuery" section) and directly
supersedes bd polyglot-pdf-vqgkj (2026-09-09), which had moved the same
views FROM `JSON_VALUE` TO plain struct dot-access, reasoning correctly
about the sink's STRUCT materialization but unable to verify the fix
against a live table -- neither sink table existed anywhere yet at the
time. The dot-access fix was right about the STRUCT shape and wrong about
the trap that shape carries: schema INFERENCE, not the STRUCT type itself,
is what blocks CREATE VIEW.

## What shipped

`sql/telemetry_views.sql`: the four sink-backed views (`cost_by_firm_month`,
`cost_by_kit_month`, `cost_by_employee_month`, `income_month`) now read
every `jsonPayload` field via
`JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.path')` instead of struct
dot-access. `TO_JSON_STRING(jsonPayload)` re-serializes the struct's
CURRENT fields to a JSON string every time (always succeeds, regardless of
which fields the sink has inferred so far), and `JSON_VALUE` then returns
the path's value or NULL if the path is absent -- schema-independent by
construction, and the accessor shape the epic's own ad-hoc verification
queries already used successfully against both live tables.
`hosting_cost_by_service_month` is untouched: it reads the Cloud Billing
export, a fixed, Google-published-schema table, not a sink-inferred one, so
its direct `service.description` / `resource.name` struct access was never
the bug this bead fixes.

The file's header comment carries the full mechanism -- the live error
text, why dot-access fails at CREATE time (a hard schema error) rather than
the silent-NULL failure mode JSON_VALUE-on-a-STRING would cause (which is
what bd polyglot-pdf-vqgkj's comment had correctly warned against, for a
different call shape than the one used here), and why
`TO_JSON_STRING(jsonPayload)` sidesteps both problems.

`backend/tests/unit/test_telemetry_views.py`: replaced
`test_no_view_wraps_a_jsonPayload_accessor_in_JSON_VALUE` (pinning the
now-superseded dot-access rule) with
`test_sink_backed_views_read_jsonPayload_only_via_JSON_VALUE_on_TO_JSON_STRING`,
asserting no sink-backed view body contains bare `jsonPayload.<field>`
dot-access and that each does use
`JSON_VALUE(TO_JSON_STRING(jsonPayload), ...)`; a new
`test_hosting_cost_view_keeps_direct_struct_access` pins that the one
non-sink-backed view is untouched. Every other test's column-provenance and
filter regexes were rewritten to extract the JSONPath string argument
instead of a dotted struct accessor.

`backend/tests/unit/test_credit_ledger.py::test_export_line_carries_every_column_income_month_reads`:
its `jsonPayload\.(\w+)` regex matched ZERO columns against the new SQL
(there is no bare `jsonPayload.` substring left in `income_month`'s body) --
a vacuous pass, not a real pin, caught only by re-checking rather than
trusting the green run. Rewritten to extract the JSONPath argument the same
way as the views test.

Every rewritten/added assertion mutation-verified: reverted a view's
accessor back to dot-access (both the first occurrence in a view body and a
non-first one, to rule out an accidental first-match-only check), added an
unlisted column reference to a usage view and separately to `income_month`
-- each confirmed red, then restored and re-verified green. Full backend
suite (3891 passed) and root suite (2054 passed) both green with no other
regressions; `closeout_prep.py`'s combined run: 6675 passed.

## Lessons

A prior bead reasoning correctly about a live system's behavior from
documentation alone, with an explicit note that it could not verify against
a real deployment, is a hypothesis, not a closed loop -- bd
polyglot-pdf-vqgkj said so itself ("The live-evidence verification step is
a first-deploy operator task... not something completable before then").
This bead is that verification landing, two weeks later, and it surfaced a
real gap: the STRUCT-materialization reasoning was right, but a second,
independent failure mode (schema INFERENCE skipping null-valued fields) sat
underneath it, invisible until a real row landed. No new standards-doc
addition beyond the current-state accessor-shape sentence already folded
into `docs/standards/logging-and-cost.md`'s Views paragraph and
`docs/technical_guide.md`'s Surface contract 25 -- this bead's own body and
`sql/telemetry_views.sql`'s header carry the full reasoning already, and
duplicating it a third place would just be another site to keep in sync.

## Doc freshness

`docs/standards/logging-and-cost.md` and `docs/technical_guide.md` (both
named in the bead's Surfaces list) had their Views/Surface-contract-25 prose
updated in place to state the current JSON_VALUE accessor shape and why it
is schema-independent where dot-access was not. Neither file got a new
`*Last updated:*` stamp -- both already carry a pre-existing
stacked-stamp violation flagged by `scripts/check_doc_freshness.py`'s
`[doc-conventions]` check ("a doc must carry exactly ONE"), and collapsing
years of accumulated per-bead history into the canonical single-stamp form
for all 8 affected docs repo-wide is out of this bug-fix bead's scope --
filed separately as bd polyglot-pdf-lpmj9.

`closeout_prep.py`'s doc-freshness pass flagged 27 of ~29 tracked docs
STALE, including both docs I touched, but every flagged file's cited
trigger is a source file whose mtime moved because `git worktree add`
refreshed the whole checkout's file timestamps, not a genuine content
change my 5-file diff made -- confirmed by counting how many docs it
flagged (nearly all of them) and by checking that most of the cited
"changed" files (`admin_backend/main.py`, `backend/routes/websocket_routes.py`,
etc.) are files this bead never touched. Reviewed and left as-is; review
recorded here per the triage instructions rather than bumped.

## Files touched

- `sql/telemetry_views.sql` -- accessor shape for the four sink-backed views.
- `backend/tests/unit/test_telemetry_views.py` -- accessor-shape pin
  rewritten + regex updates for the new call shape.
- `backend/tests/unit/test_credit_ledger.py` -- column-extraction regex
  updated to match the new call shape (was silently vacuous otherwise).
- `docs/standards/logging-and-cost.md` -- Views paragraph, current-state
  accessor fact.
- `docs/technical_guide.md` -- Surface contract 25, current-state accessor
  fact + corrected "BigQuery never errors" claim.
