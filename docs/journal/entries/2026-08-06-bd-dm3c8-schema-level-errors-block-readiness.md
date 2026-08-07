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
  `(id=)` token, so a bucketing rule keyed on "has an id token" files it under
  a field that does not exist and silently drops it. The token names a
  SECTION. The client already drew this distinction for the same reason
  (`lintFindings.formLevelFindings` keys on "resolves to no field in fields[]",
  not on "has no id token"); the backend now does too -- `_bucket_by_field`
  takes the set of ids that really exist in `fields[]`.
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
tests; making the scan treat any id token as field-owned reddens exactly the
section-ERROR parametrization -- the case the bead named as subtle.

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

## Doc freshness

No tier-1/2 doc names the readiness verdict's shape. The freshness checker's
verdict at closeout governs.

## Files touched

- backend/services/publish_readiness.py -- schema-level ERROR collection,
  field-id-aware bucketing, the new verdict field, one-shot-iterable fix
- backend/tests/unit/test_publish_readiness.py -- 5 tests (both ERROR classes
  parametrized, the WARNING non-case, the no-double-count case, the generator
  case)
