---
date: 2026-09-03
bead: polyglot-pdf-ybwjw
title: "docs(plan): commit sprint 22 admin-console program plan + INDEX row"
sprint: 22
tags: [doctrine, security]
---

## Trigger

The maintainer asked for a plan for an admin console to replace the growing
set of hand-run bash scripts: deploys to every target, form-kit commercial
management, firm/user/credit management with promotional credits and later
Stripe, and monitoring (usage and cost by firm, form and employee; errors;
credit alerts; cost versus income including Cloud Run hosting). The planning
session ran in plan mode on `claude/admin-console-planning-dfe9bf`: three
Explore inventories (deploy scripts, firm/link/credit code, telemetry), a
thoughts-and-questions round that settled four product decisions (separate
admin service + console; Cloud Build from git; debit-at-mint credits with
refund on unopened expiry; Foundations-first order), three design passes, then
two maintainer review rounds the same day.

## What shipped

`docs/sprint_22_admin-console_plan.md`, the program plan of record for six
epics, plus its row in `docs/INDEX.md`. The plan fixes the architecture and
the cross-epic contracts, and carries a rubric per epic. The maintainer's two
review rounds changed the design materially and are folded in:

- credit reserved BEFORE the token is signed, and `/api/links/open` requires
  a mint record (which also gives the console link revocation);
- audit rows written inside the mutation's Firestore transaction (or a
  pending-then-committed pair for Auth and build calls), so a retried 500
  cannot double-grant;
- the refund guard reads the authoritative redemption doc, never the
  best-effort status mirror;
- a staging tier for the channel-less admin service: tagged no-traffic Cloud
  Run revisions plus a second permanent candidate Hosting site (preview
  channels would churn Auth authorized domains and CORS);
- enforcement behind a `CREDITS_ENFORCED` runtime flag plus an operator CLI,
  so existing firms are never locked out before seeding;
- the staging-before-demo gate as a build step, and every build from git via
  the connected repo (tarball uploads exclude the site directories, and a
  dirty tree would deploy under a clean SHA);
- explicit `channel` arguments on the shared link helpers; `usd_amount` and
  `firm_kind` snapshots on ledger entries so income filters on the firm's
  kind, not on a channel the admin service does not have;
- no Docker build args (`gcloud builds submit --tag` cannot pass them);
  runtime `APP_MODULE` and `GIT_SHA` env instead;
- exception logging emits type and frames, never the message (the P0 PII
  decision from bd `polyglot-pdf-p84m`).

Beads filed from the plan, all pushed: program epic `polyglot-pdf-4uvh2`;
epics `b66pb` (E1), `e374w` (E2), `43c99` (E3), `nacfo` (E4), `m5exr` (E5)
with `plan:`/`sprint:` metadata; Epic 1 children 1.1-1.8 (`pnoik`, `7w17m`,
`3l2vp`, `li9x0`, `bg313`, `9hzod`, `b6943`, `2cwja`); Epic 2 Track A A1-A6
(`4rkrx`, `vnxew`, `jecrl`, `ah5d3`, `1op3g`, `d4wdi`); this bead. Ordering
edges leave only 1.1 and this bead ready. Epics 2 (Tracks B/C), 3, 4 and 5
still get their own `/plan-epic` pass.

Fresh-eyes and docs-review outcomes are recorded in the closeout ping.

## Lessons

- **Verify a subagent's claim about a guard's SCOPE by reading its anchor
  line.** The platform design pass asserted the IAM envelope test walks the
  repo root and proposed a carve-out for the new package; the test's root is
  `parents[2]` of a file under `backend/tests/unit/`, which is `backend/`
  itself, so a sibling package is outside it by construction. One line of
  code settled a whole section of the design.
- **A reviewer's "it works today" needs the mechanism named.** Two
  plan-level assumptions (Docker build args under `--tag`; preview channels
  for a signed-in app) were each wrong for a concrete tooling reason the
  maintainer supplied. When a plan leans on a tool feature, cite the flag or
  page that provides it.
- **Very long heredoc commands hit the process spawn limit.** A single Bash
  call writing twenty-one bead bodies failed with `ENAMETOOLONG`; splitting
  the same content across several calls worked. Write big batches in chunks.

## Doc freshness

`docs/INDEX.md` stamped 2026-09-03 with the new sprint row. No tier-2 doc
tracks the plan file. `check_doc_freshness.py` reports the sprint-archive
protocol, conventions and citations clean; its STALE warnings
(`voice-and-vad.md`, `ws-protocol.md`, `technical_guide.md`) track files this
branch did not touch and were left as they were.

## Files touched

- `docs/sprint_22_admin-console_plan.md` (new)
- `docs/INDEX.md`
- `docs/journal/entries/2026-09-03-bd-ybwjw-admin-console-program-plan.md` (this entry)
