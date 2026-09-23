---
date: 2026-09-23
bead: polyglot-pdf-uijam
title: "audit(sprint 23): the closing snapshot -- demo deployed, posture run 66/2/11, one deploy outstanding"
tags: [security-audit, deploy, audit-scripts]
---

# Sprint 23 closes: what is live, what the closing run found, what is left

The security audit epic (`docs/sprint_23_security-audit_plan.md`) ended
with every child merged and, today, the demo deploy that its fourth exit
criterion waited on. This entry is the closing snapshot the criterion asks
for; the findings register itself is in
`2026-09-16-bd-vzrbc-security-posture-g.md`.

## What went live today

The demo channel deployed dev `b91fad5bb` (backend revision 00099,
frontend, and -- for the first time through the Cloud Build path -- the
Firestore rules). Checked in-process afterwards, redacted:

- The active Firestore ruleset is byte-equal to the repo's `firestore.rules`
  and carries C3's denies (`authorized_emails` and `confirmation_events`
  unreadable and unwritable from the web).
- The backend runs the deployed commit with `max-instances=10`; no
  secret-shaped value in its environment; `/health` answers the trimmed
  shape (three keys).
- The demo app site serves the report-only CSP, HSTS, Referrer-Policy and no
  `X-Frame-Options` (frame-ancestors lives in the CSP), as E2 shipped.
- On staging, the same commit's limiter refused a hosted burst from the 31st
  call with a two-hop forwarded chain on every refusal, which settled the
  one premise the rate limiter had rested on (`ckceh`; PR #876).

## The closing posture run

`infra_posture.sh --project polyglot-demo-aa709`, run by the maintainer
from their own terminal at 23:13Z: 79 checks, 66 PASS, 2 FAIL, 11 N/A
(2026-09-15's first run: 55 / 8 / 15). Six of the first run's eight FAILs
cleared: the Cloud Build identity now exists with its pinned roles, the
bucket's public-access prevention is enforced, and four of the five Hosting
sites serve the headers; container scanning, N/A then, now reads PASS.

- FAIL, accepted: two human accounts hold Owner -- the sole operator's two
  accounts, accepted in writing on 2026-09-17 (the posture doc's decisions
  table). The script cannot know an acceptance, so this row stays red by
  design.
- FAIL, one deploy away: the schema-editor Hosting site still serves only
  HSTS. It deploys through `deploy-editor.sh`, not the demo channel, and has
  not been deployed since E2 merged; its next deploy carries the headers.
- N/A, the script's own fault (seven checks; bd `kz7rv`): the four Firebase
  Auth reads fail because the script's request carries no quota-project
  header -- the same read succeeds in-process under the same credentials --
  and the three BigQuery reads shell out to the `bq` CLI, whose Python is
  broken on the operator machine (the telemetry code already left `bq`
  behind in `vm2fu`).
- N/A, no readable form (four checks): per-user MFA, Auth export, the Vertex
  org policy, TTS data use -- as documented on 2026-09-15.

The closing log sweep (`log_pii_sweep.py`, 30 days, in-process):
the BigQuery views clean; the request-log rows (70 + 73 on demo, 13 + 14
on staging) are the pre-fix residue dispositioned on 2026-09-15, unchanged
(newest 2026-09-14T19:29Z, the exclusion's propagation lag), aging out by
2026-10-14; and one NEW family -- 46 admin-service lines carrying an email
under `actor_email` / `caller_email`, from three log calls that pass the
Google OIDC caller's address (the scheduler's and Pub/Sub's service
accounts; a staff address when a human runs the route). Not client data;
filed as `4ffib` (use the subject, pin the `*_email=` shape).

## Exit criteria, scored

1. Inventory complete and live-verified: met on 2026-09-15 (A, `uaxt5`).
2. No credential or field value in Logging or BigQuery after the fix: met
   (B2 `v8l6m`; today's sweep above).
3. Every route classified and cross-tenant-tested by a set-derived matrix:
   met (C1 `fr20a`, C2 `bwevj`).
4. Live posture equals the repo: met except the editor site's headers, which
   is one `deploy-editor.sh` run; the Owners row is an accepted risk.
5. Every finding dispositioned, scanning recurs: met -- the register lists
   PF-1..16 with severity; every P0/P1 merged; every P2/P3 has a bead; the
   informational security job ran on every PR this week.

## What the week also taught

- **Deploy the staging-verified commit, not HEAD.** Three demo deploys
  failed on the two gates because dev moved between the staging deploy and
  the demo deploy; the fix was a detached checkout of staging's commit. The
  wrapper should do that itself (`6s0ut`) and say which step failed
  (`x3scz`).
- **Grouped Dependabot bumps broke dev twice** (#816-#822, then
  #862-#865): a pip set that does not resolve, invisible to CI because the
  CI job installs a different requirements file than the image. Merge path
  doctrine raised to P1 (`g4p1j`); #867 reverted the bumps and #878
  (`lwka0`) keeps the deploy-sensitive packages out of grouped bumps and
  makes CI install the runtime requirements file.
- **Google refused the Vertex abuse-monitoring opt-out** (no company
  website yet); recorded as a dated accepted risk, re-apply after launch.

## Files

`docs/standards/security-posture.md` (the processor intro, the Firebase
Auth row, the runbook and sweep rows, the stamp); this entry.
