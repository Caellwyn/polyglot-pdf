---
date: 2026-09-01
bead: polyglot-pdf-2sli8
title: "bug(schema-repair): mixed atom+bucket condition silently dropped the bucket with no log entry"
tags: [backend, schema-forms]
---

## Trigger

`backend/services/schema_repair.py`'s `_rewrite_condition()` has three
shape branches: a pure composite group (bucket keys present, no
field/operator keys), the `or`/`and` pseudo-group, and a fallthrough that
treats the whole `cond` dict as a single plain atom via `_rewrite_atom`.

A condition dict carrying BOTH atom keys (`field`/`operator`) AND a
`ConditionGroup` bucket key (e.g. `any_of`) -- exactly the malformed
shape `schema_lint.py`'s composite-depth ERROR rule exists to catch
("this condition mixes a single rule with a group of rules") -- failed
the pure-composite-group branch's guard and fell through to
`_rewrite_atom(cond, ...)`, which reads only the top-level
field/operator/value keys and silently discarded the bucket entirely.
No repair log entry was ever recorded (`repairs` stayed empty).

Every OTHER drop path in this module (unknown operator, unresolvable
reference, unresolvable value, dangling `controls_fields` target) logs a
`drop-condition` entry with `error: true`, per the module's own stated
fail-open contract. This one was silent data loss worse than fail-open --
a re-lint of the repaired schema wouldn't catch it either, since the
surviving bare atom lints clean.

## Fix

Added an explicit check at the top of `_rewrite_condition`: if both a
`CONDITION_GROUP_BUCKETS` key and `field`/`operator` are present, drop
the condition entirely (matching every other malformed-shape drop
path's contract) with a `drop-condition` / `error: true` entry naming
which bucket(s) were present.

Chose "drop entirely" over "repair by folding" (the exit criteria's
other option): folding the atom into the bucket, or discarding the
bucket and keeping the atom, both require GUESSING which relationship
the original author intended -- the same never-guess principle this
module's own `option_id`/alias-collision resolution already follows
elsewhere (never silently pick a plausible-but-unverified interpretation).

## Testing

New test `test_mixed_atom_and_bucket_condition_is_dropped_with_recorded_error`
in `tests/test_schema_repair.py`, mirroring the existing
`test_unknown_operator_is_dropped_with_recorded_error`'s pattern exactly:
drives the real `repair()` entry point end-to-end (not just
`_rewrite_condition` in isolation), asserts the field's `show_if` is
gone entirely, asserts exactly one `drop-condition` entry with
`error: True`, and asserts the repaired schema still lints clean.

Mutation-verified: removing the new guard reddens the test with exactly
the pre-fix bug reproduced (the mixed shape silently repairs to a bare
atom, `any_of` gone, zero repairs logged). Restored. Full
`tests/test_schema_repair.py` (94 tests) and `backend/tests/test_schema_lint.py`
(107 tests) both green.
