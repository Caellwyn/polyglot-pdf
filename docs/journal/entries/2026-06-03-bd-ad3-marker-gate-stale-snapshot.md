---
date: 2026-06-03
bead: polyglot-pdf-ad3
title: "Hydration marker closes the stale-snapshot gap in remote beads bootstrap"
sprint: 1
pr: "ad3"
tags: [harness, doctrine]
---

## Trigger

Immediately after p68/#62 (self-healing remote beads bootstrap) merged, a fresh
remote session **still** reported the bug — but in a more insidious form. Instead
of failing to open, it loaded the committed `.beads/issues.jsonl` **backup
snapshot** (5 days stale: 30 issues / 9 ready) and presented it as the current
tracker. The live `refs/dolt/data` store had 117 issues / 34 ready.

## Why p68 missed it

p68 keyed "is beads hydrated?" off `summary.total_issues > 0`. That catches the
*empty* DB that `bd prime` auto-creates, but **not** a populated-but-stale one:
the JSONL snapshot (enabled by an earlier session's `issue-prefix` change so bd
rebuilds from it on fresh clones) makes bd report 30 issues, so both the
bootstrap's idempotency check **and** the `bd_prime` banner concluded "all fine"
and the session ran on stale data. Worse than failing loudly.

## Fix

A per-container **hydration marker** (`.beads/.cache/.hydrated`), written *only*
after a successful hydrate from `refs/dolt/data`:

- **`beads_remote_bootstrap.py`** — idempotency check is now `marker exists AND
  populated`; the marker is written after hydrate/repair. Also added an
  `is_remote_container()` guard (detected via the `local_proxy` origin) so the
  destructive wipe-and-clone refuses to run on a real local checkout.
- **`bd_prime.py`** — in a remote container, `_beads_unhydrated()` returns true
  whenever the marker is absent, **regardless of issue count**; elsewhere it falls
  back to the empty/unopenable check so a populated local never trips the banner.
  Banner reworded to name the stale-snapshot case.

Proven: with bd populated (117) but the marker deleted, the old empty-check says
"looks fine" while the new gate fires the banner and re-hydrates.

## Scar tissue

- **A committed JSONL snapshot is a *backup*, never a source of truth in a remote
  session.** Any "is beads current?" check in an ephemeral container must verify
  the live `refs/dolt/data` was hydrated (the marker), not merely that bd opens
  with some rows — a stale snapshot is the most dangerous state because it looks
  healthy.
