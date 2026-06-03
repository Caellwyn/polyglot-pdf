---
date: 2026-06-03
bead: polyglot-pdf-p68
title: "Self-healing beads bootstrap for remote/web sessions (refs/dolt/data + wisp clone bug)"
sprint: 1
pr: "p68"
tags: [harness, doctrine]
---

## Trigger

Beads was unusable in Claude Code remote/web sessions: a fresh container clones the
code but not the issue store, and `bd ready` / `bd show` / `/closeout` all need it.
The goal was to make future remote sessions able to use beads **durably**, without
per-session flailing.

## Diagnosis (three independent blockers)

The store lives in the Dolt ref **`refs/dolt/data`**, not the git working tree. A
naive `bd bootstrap` in a remote container fails three ways:

1. **The prime hook lies.** Generic `bd prime` prints *"No git remote configured —
   issues are saved locally only."* False here — beads syncs through
   `refs/dolt/data` over the same git origin as the code.
2. **Credentials.** `sync.remote` is the public `github.com` URL, so `bd bootstrap`
   attempts a Dolt-native clone of github.com, which has no credentials in the
   sandbox. Git only works through the session's authenticated local proxy origin
   (`git+http://local_proxy@127.0.0.1:<port>/…`). Neutralising `sync.remote` makes
   bootstrap fall back to the git origin, which works.
3. **The dolt-ignored `wisps` tables.** `wisps` / `wisp_*` are in `dolt_ignore`
   (so per-clone wisp state can't merge-conflict) and therefore absent from
   `refs/dolt/data`. On a fresh clone bd migrates forward, but migration
   `0047_recompute_mixed_is_blocked` references `wisps` → `table not found: wisps` →
   bd cannot open the DB at all. A long-lived local checkout never hits this because
   it only ever *pulls* into a DB that already has the local wisp tables; only a
   fresh clone trips it. Upstream beads fresh-clone bug.

The whole diagnosis had to be done with a standalone `dolt` CLI querying the cloned
store directly, because `bd` itself wouldn't open.

## Fix

- **`scripts/beads_remote_bootstrap.py`** — idempotent hydrate + self-repair. Clone
  over the proxy (`sync.remote` neutralised then restored), then recreate the wisp
  tables using the **exact schema of the installed bd version**, sourced from a
  throwaway `bd init` (no hand-written DDL to rot); bd then runs its last migration
  and opens. Acquires a `dolt` CLI on demand (PATH → cached → release download → `go
  install`), cached under gitignored `.beads/.cache/`. Never pushes.
- **`scripts/bd_prime.py`** — SessionStart hook now prints an actionable bootstrap
  banner whenever the store is un-hydrated **or empty**, instead of the false
  "no remote" line. The empty check is load-bearing: `bd prime` auto-creates an
  *empty but openable* DB, so keying off "does bd open?" is a false positive that
  strands the session on zero issues — we key off `total_issues` instead.
- **`docs/components/beads-remote-bootstrap.md`** (+ INDEX row) — the runbook.

Proven end-to-end in this remote container: cold start → `bd ready` lists the real
33 ready beads (117 total).

## Scar tissue

- **`bd prime` auto-creates an empty, openable DB.** Any "is beads ready?" check
  must verify the store is *populated* (`total_issues > 0`), not merely that bd
  opens — otherwise a session silently runs against an empty tracker.
- **Schema-version gap on push.** Remote sessions run bd `@latest` (schema 47) vs.
  the maintainer's level-40 canonical. Reading/local-writes are fine, but the first
  `bd dolt push` from a remote session bumps the canonical schema (and carries the
  recreated wisp tables into `refs/dolt/data`); the local `bd` must be upgraded to
  `@latest` to keep reading it. Sequence the local upgrade before/around that first
  push. See the component doc's "schema version on push" section.
