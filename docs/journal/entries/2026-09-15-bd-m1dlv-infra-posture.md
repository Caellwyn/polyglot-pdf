---
date: 2026-09-15
bead: polyglot-pdf-m1dlv
title: "audit(infra): D -- the read-only live posture runbook, and what its first run found"
tags: [security-audit, deploy, iam, audit-scripts]
---

## Trigger

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream D, threat actors T1,
T3 and T4. The repo pins what the deployed identities SHOULD hold
(`test_deployed_iam_envelope.py`, `test_admin_sa_iam_envelope.py`) and what
the deploy scripts SHOULD set; nothing read the live project back and
compared. PF-12 (a project-wide bucket viewer role, no public-access
prevention, no gitignore for key files) was a paper finding until
something could check it. Built by a Sonnet builder in an isolated
worktree over four rounds plus one orchestrator fold-in; the orchestrator ran the review loops and
closeout.

## What shipped

`scripts/audit/infra_posture.sh --project <id>`: 78 read-only checks under
the operator's ADC, each ending PASS, FAIL or `N/A: <reason>`, continuing
past permission errors, exit code always 0 (the counts are the signal).
Project IAM (human Owner/Editor flagged); the backend, admin and Cloud
Build service accounts' roles against the pinned lists, including the
Cloud Build identity's scoped grants (the bucket role, its actAs on both
runtime identities with a not-project-wide check for each, the Pub/Sub
token-creator grant) -- the script's copies are drift-guarded by
`tests/test_infra_posture_script.py` against the three envelope tests and
`setup-cloud-build.sh`; every Cloud Run
service and revision (secret-shaped env values reported by NAME plus a
verdict, forbidden flags, verbosity knobs, secret bindings, ingress,
scaling, runtime identity, and a FAIL when an expected service is
missing); the scope guards read the exit status, so a failed policy read
is N/A, never a PASS; Secret Manager; the kit bucket; the ACTIVE Firestore ruleset via
the Rules API compared to the repo file by hash after newline
normalisation; TTL, PITR and backups; Cloud Logging retention,
sinks, exclusions and audit config; BigQuery; Firebase Auth via the
Identity Toolkit API; Hosting headers per site following redirects;
container scanning and base-image age; Cloud Build log content as COUNTS
of secret-shaped assignments and JWT prefixes over the first 20 000
lines; and the T4 processor settings. The check list is pinned as shipped
text, the way `setup-monitoring.sh` is.

## What the first runs found (2026-09-15, redacted; the full table is on the bead)

Final run: 78 checks, 55 PASS, 8 FAIL, 15 N/A.

- Two human accounts hold project Owner -- a maintainer decision, likely
  accepted risk on an owner-operated project.
- `polyglot-cloudbuild-sa` does not exist on the project: `setup-cloud-build.sh`
  (PR #784) has never been run there. A provisioning ask, not a tightening.
- The kit bucket's public-access prevention is `inherited`, not
  `enforced` (PF-12). One live command fixes it; a maintainer ask.
- All five Hosting sites lack CSP, X-Frame-Options and Referrer-Policy --
  PF-4, owned by E2; the script now verifies it live.
- Everything the earlier work claimed is confirmed live: both service
  accounts' roles equal their pinned lists, no revision carries a secret
  value, a bypass flag or a verbosity knob, the B0 exclusion
  `ws-token-in-url` is present, Cloud Build logs contain no secret-shaped
  text, the admin SA's BigQuery viewer is dataset-scoped.
- N/A with reasons: the operator identity lacks Identity Toolkit read
  (Firebase Auth settings), no API exists for per-user MFA or the TTS
  data-use setting, the Vertex opt-out is console-only and the
  Organization Policy API is disabled, container scanning is OFF (an ask
  to enable), no default BigQuery expiration (workstream A's retention
  bead), and the Cloud Build identity's scoped grants (absent with the
  identity itself). The deployed Firestore ruleset equals the repo file.

## Review record

**Fresh-eyes (sonnet): two rounds.** Round 1 GAPS-FOUND (2): the admin
service-account list was the one of three with no drift guard against its
source test (now imported and compared), and two comments described a
mechanism the script does not have (per-check subshells; a `run_check`
function). Nits adopted: the per-secret check says access is via the
project role rather than printing an empty accessor list; Hosting follows
redirects and reports the final hop; the build-log scan is bounded and
announces itself. The reviewer reproduced the builder's live counts
exactly before the round-2 re-run.

**Opus cross-surface review: two rounds.** Round 1 GAPS-FOUND (3), all
adopted: the Cloud Build identity's scoped grants had no checks at all, so
a project-wide actAs widening would have passed; the rules parity check
could never pass (wrong release name, a missing quota-project header, and
CRLF doubled through bash and python text mode -- now one python
invocation comparing hashes after newline normalisation, and it passes
live); and two repo files were read relative to the caller's directory,
so running from elsewhere produced a confident false FAIL on the deployed
rules. Nits adopted: a dead variable, a FAIL for a missing expected Cloud
Run service (which exposed a newline-vs-space bug in the live service
list), the doc's mention of a `firebase` CLI the script never calls. The
reviewer filed `dk5ok`, `zsr2h`, `hm0cw`, `ugbda` for these before they were
routed back into this PR. Round 2 GAPS-FOUND (2), both
adopted in round 4: the actAs loop's early `continue` silently dropped the
not-project-wide sibling when a policy read failed (the exact silent-skip
shape the header forbids), and the three not-project-wide checks recorded
PASS on empty output without reading the exit status, so a failed policy
read would have passed the scope guard; nit: the project-wide actAs query
ran once per target and now runs once. Round 2 also verified live that the
rules chain fetches the ACTIVE release and that the normalisation masks
only CRLF-vs-LF. Round 4 moved the project-wide
scope check out of the per-target loop entirely (a structural test pins
one record per loop iteration) and made all three not-project-wide
checks branch on the exit status (a parametrized test pins each); the
live totals were unchanged, with the three checks now passing for a real
reason. Round 3 NO-GAPS (the
structural and parametrized pins each reddened under exactly the mutation
that matters, including moving the scope check back into the loop under
its literal name); its one nit -- the literal check list was pinned as a
subset only -- was folded in as a set-equality test, and two shipped
comments that narrated review rounds were reduced to their rationale.

**Housekeeping reviewed and left:** other sessions' in-progress beads; the
stale-doc flags for files this branch did not touch. Prep suite: 6059
passed.

## Lessons

- **A pin without a live read is a hope.** Two roles pinned in tests and
  "provisioned" by a merged script were never applied to the project; the
  first read-back found it in seconds.
- **Bash builds its own traps on Windows.** CRLF in gcloud output broke
  every set comparison, `PIPESTATUS` after a command substitution read the
  wrong exit code, a heredoc silently won over a here-string, and a broken
  `bq` exited 0 while printing an error. Each became a guard in the script.
- **Say why a check is N/A, every time.** Twelve checks could not run;
  each names the permission, the missing API, or the fact that no API
  exists, so the posture doc can say what is unknown rather than what is
  unchecked.

## Doc freshness

Bumped: `docs/components/config-deployment.md` (a "Live infrastructure
posture (read-only)" section, the Tracks line, one stamp line).

## Files touched

- scripts/audit/infra_posture.sh -- the runbook (new)
- tests/test_infra_posture_script.py -- shipped-text pin + drift guards (new)
- docs/components/config-deployment.md -- section + stamp
- docs/journal/entries/2026-09-15-bd-m1dlv-infra-posture.md -- this entry
