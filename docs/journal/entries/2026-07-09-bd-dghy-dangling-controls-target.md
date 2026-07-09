---
date: 2026-07-09
bead: polyglot-pdf-dghy
title: "Migration reports a dangling controls_fields target instead of dropping it"
tags: [migration, testing]
---

## Trigger

Round-3 fresh-eyes on the P6.2 flip (bd h76m.16) noticed a latent reporting gap in
`migrate_schema_v2.py`'s controls_fields->show_if/require_if mirroring (Pass 4):
when a `shows`/`makes_required` target id resolved to no field (a dangling/typo'd
reference), the loop just `continue`d without touching any counter -- so if the
edge ALSO had no unconverted actions, it was dropped from the audit trail with
ZERO trace (no `controls_fields_dropped`, no `unmirrored_controls` entry). None of
the 4 shipped kits has a dangling target, so it was never a live regression -- but
a future kit with a typo would silently lose that edge.

## Fix

Pass 4 now collects dangling targets (`<tid>.<key>`) into a new report key
`dangling_controls_targets` AND, per-edge, a `dangling_targets` field on the
`unmirrored_controls` entry -- so a dangling ref is always surfaced, never silently
dropped. It is also excluded from the "clean drop" accounting (a dangling edge is
not a no-op). The CLI `main()` prints a WARNING listing dangling targets alongside
the existing unconverted-action warning. A unit test constructs an edge whose
`makes_required` target does not exist and asserts it appears in the report and is
NOT miscounted as a clean drop.

## Verification

`tests/test_migrate_schema_v2.py` 21 passed (incl. the new dangling test). All 4
shipped kits re-migrate with `dangling_controls_targets == []` and unchanged mirror
counts -- no behavior change for them. Scope was `scripts/migrate_schema_v2.py`
only (+ its test), matching the bead's surfaces.
