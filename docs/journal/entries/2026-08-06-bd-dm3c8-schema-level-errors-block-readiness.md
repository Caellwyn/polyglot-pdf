---
date: 2026-08-06
bead: polyglot-pdf-dm3c8
title: "a schema-level lint ERROR must block readiness (the C2 trap)"
sprint: 18
tags: [schema-editor, review]
---

## Trigger

Found by the Opus outer review on sprint-18 C4 (bd polyglot-pdf-g687), and
deliberately NOT fixed there: C4's exit criterion 2 had been amended so the
/status GATE wiring belongs to C2 (bd polyglot-pdf-apmo). Filed instead, and
wired as a HARD BLOCKER on C2 -- because C2 is exactly where the defect goes
live.

`publish_readiness` built its verdict from FIELD-anchored findings only.
`_bucket_by_field` skipped any finding whose path yielded no field id, and
`is_counted_reviewed` only ever saw a field's own bucket. So a lint ERROR that
no field row can carry demoted nothing, and `ready = total > 0 and to_review
== 0` read True.

The /status gate meanwhile refuses on ANY lint ERROR regardless of anchoring.
So a fully-reviewed kit could stamp `ready: true, 100%` and then 409 at
publish -- the confident-then-refused shape this whole epic exists to end,
relocated into the stamp. Latent only because nothing read `ready` yet; C2's
stated purpose is to start reading it.

## What shipped

Two reachable ERROR classes now block, both pinned:

- `to-review-pending` at `sections[i] (id=sec_to_review_x)` -- the holding-
  section leftover-ids ERROR. This is the SUBTLE one: its path *does* carry an
  `(id=)` token, so a rule keyed on "has an id token" treats it as field-owned
  and skips it. The token names a SECTION. `_schema_level_errors` therefore
  tests `fid in field_ids` -- "resolves to a REAL field" -- mirroring the rule
  the client already uses (`lintFindings.formLevelFindings` keys on "resolves
  to no field in fields[]", not on "has no id token").
- `dump-widget-multiclaim` at `widget '<name>'` -- no id token at all.

They land on their OWN verdict field (`blocking_schema_errors`), not in the
counts. `reviewed + to_review == total` counts FIELDS and is a test-pinned
invariant, so a finding belonging to no field cannot inflate a field tally
without breaking it. The consequence is deliberate and worth stating: a
fully-reviewed kit carrying a schema-level ERROR still reports **100%
reviewed** -- which is TRUE, the humans really did review every field -- while
`ready` is False. The percentage answers "how much has a person reviewed?";
`ready` answers "may this publish?". Conflating them would have made the
percentage lie to protect the gate.

Each blocker is named as `<rule> at <path>` (exit criterion 2). A gate that
refuses without saying what to fix is unactionable, and C2 surfaces this list
to a human.

Fixed while here: the `lint_findings` parameter is typed `Iterable` and the
verdict now consumes it twice (bucket per field, then scan for schema-level
ERRORs), so a generator would have arrived exhausted at the second pass.
Materialized once, with its own test.

Mutation-verified: dropping the schema-error clause from `ready` reddens 3
tests; making `_schema_level_errors` treat any id token as field-owned reddens
exactly the section-ERROR parametrization -- the case the bead named as subtle;
keeping only the last collected error reddens the both-classes test; refusing
silently on an unmeasurable schema reddens its own test.

**A correction worth recording.** The first draft ALSO filtered inside
`_bucket_by_field`, and this entry originally credited that filter as what made
the section-anchored ERROR block. It was dead code: `by_field` is only ever
read by a real field's own id, so a bucket keyed on a section id is never
consulted. The Opus fresh-eyes round proved it two ways -- deleting the filter,
and reverting the call site -- each leaving all 58 tests green. It also caught
that the mutation I had recorded as verifying that filter actually exercised
`_schema_level_errors`, a different function. The filter is gone, and
`_bucket_by_field` now carries a note saying why it is not there, so the next
reader does not re-add it for the same plausible reason.

Verified end-to-end against the real C2 scenario, not just the units: for a
fully-reviewed kit with a holding-section ERROR, the gate's own refusal
predicate and the verdict now AGREE, and the refusal carries the rule and path.

backend 1697 passed (from 1692 -- 5 added, zero regressions).

## Lessons

- **A "latent" defect in a shared definition is worth fixing BEFORE its
  consumer lands, not after.** Nothing read `ready`, so this could have waited
  for C2 to discover it. But C2's whole job is to wire the gate to this
  verdict, so the discovery would have happened as "the gate and the stamp
  disagree" mid-implementation -- expensive to diagnose from that end, and
  easy to "fix" by making the gate stop refusing. Blocking C2 on it made the
  ordering explicit instead of relying on someone noticing.
- **Two anchoring rules that look equivalent are not.** "Has an id token" and
  "resolves to a real field" differ on exactly one shipped ERROR -- and that
  ERROR is the one that blocks publication. The client had already learned
  this and encoded it; the backend mirror silently used the weaker rule. When
  mirroring a predicate, mirror the REASON, not just the shape.
- **A defensive change that no test can pin is a claim, not a fix.** The dead
  `_bucket_by_field` filter looked exactly like the load-bearing change -- it
  sat in the obvious place, its comment cited the real client rule, and the
  suite was green around it. What exposed it was the reviewer asking for a
  mutation that reddens, and finding none existed. If a change cannot be made
  to fail, either write the test that fails or delete the change; keeping it
  buys nothing and misdirects the next reader.
- **Check WHICH function a mutation actually hit.** I recorded a mutation as
  verifying the bucketing filter when it had exercised a different function
  entirely. Both were in the diff and both plausibly related, so the record
  read as complete. A verification claim naming the wrong target is worse than
  no claim -- it converts an unpinned change into an apparently-pinned one.

## Doc freshness

No tier-1/2 doc names the readiness verdict's shape. The freshness checker's
verdict at closeout governs.

## Files touched

- backend/services/publish_readiness.py -- schema-level ERROR collection,
  field-id-aware bucketing, the new verdict field, one-shot-iterable fix
- backend/tests/unit/test_publish_readiness.py -- 5 tests (both ERROR classes
  parametrized, the WARNING non-case, the no-double-count case, the generator
  case)
