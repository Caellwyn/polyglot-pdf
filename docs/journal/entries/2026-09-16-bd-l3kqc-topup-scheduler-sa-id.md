---
date: 2026-09-16
bead: polyglot-pdf-l3kqc
title: "fix(scripts): monthly top-up scheduler service-account id exceeds the 30-char limit; pin every SA id length"
sprint: 22
tags: [hotfix, testing]
---

## Trigger

Running `scripts/setup-admin-service.sh` on 2026-09-15 to provision the
monthly firm-plan credit top-up's Cloud Scheduler identity (bd
`polyglot-pdf-0euzk`, PR #792) failed with `INVALID_ARGUMENT`:
`gcloud iam service-accounts create admin-monthly-topup-scheduler-sa`
rejects the id outright -- GCP caps a service-account id at 30
characters, and that one is 32. No test caught this before it shipped,
because every test in the suite stubs the Firebase/gcloud SDK: a mock
happily "creates" an account with an id the real API would refuse
(CLAUDE.md scar #7's shape, one layer over -- a mock proving the code
*attempts* a call cannot prove the call is *valid*, only that it's
*allowed*).

## What shipped

1. Renamed the service-account id from `admin-monthly-topup-scheduler-sa`
   (32 chars) to `admin-topup-scheduler-sa` (24 chars) at its one point
   of definition, `scripts/setup-admin-service.sh`'s
   `MONTHLY_TOPUP_SCHEDULER_SA_NAME` literal. Every consumer derives from
   that same literal (`deploy-admin.sh`'s
   `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL`, the pinning test's expected value),
   so this was a one-line rename plus updating the two places that had
   copy-pasted the old literal for their own assertions. The env VAR
   NAMES (`MONTHLY_TOPUP_SCHEDULER_SA_NAME`/`_EMAIL`) were left alone --
   only the id VALUE they carry changed; renaming the variables too would
   have been a bigger, non-bug-fixing diff.
2. `deploy/channels/admin.env` does not declare this var at all (checked;
   not present), and `admin_backend/routes/credit_routes.py` only reads
   `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL` by name via `os.getenv` at request
   time -- neither file needed a code change, just confirmation they
   carry no stale literal.
3. New `tests/test_service_account_ids.py`, per CLAUDE.md scar #8
   (enumerate the set before fixing an instance of it): rather than
   hand-listing `scripts/setup-admin-service.sh`'s four
   `service-accounts create` calls, it discovers every git-tracked `*.sh`
   file under `scripts/` (`git ls-files scripts/`, not a directory walk --
   mirrors the form-kits doctrine's "tracked is what CI actually sees"
   reasoning), regex-scans each for `gcloud iam service-accounts create`
   invocations, resolves the referenced variable back to its own literal
   assignment in the same file, and asserts every resolved id is 6-30
   characters. Found 7 create-call sites across 3 scripts
   (`setup-admin-service.sh` x4, `setup-cloud-build.sh` x1 real + 1
   dry-run echo of the same id, `setup-gcp-project.sh` x1); all now pass.
   Mutation-verified by reverting the SA name to its old 32-char value --
   the new length test goes red naming the exact file and id -- then
   restoring it.

## Lessons

A mocked SDK call cannot validate the ARGUMENT it's called with, only
that the call site exists -- the same shape as scar #7's IAM-permission
gap, but for a value-format constraint (id length) instead of a
permission grant. Where a cloud API enforces a format/length/enum rule
the mock does not replicate, the test needs to assert the STATIC VALUE
against that rule directly (as this bead's new test does), not just that
the SDK method was invoked. No standards-doc change proposed -- this is
already exactly scar #7's shape, just illustrated with a second concrete
example.

## Doc freshness

- `docs/technical_guide.md` (no freshness stamp by design): updated the
  Surface-contract-32 prose's `admin-monthly-topup-scheduler-sa` mention
  to `admin-topup-scheduler-sa`, noting the 30-char cap and this bead.
- `docs/components/admin-service.md`: reviewed, left as-is -- it refers
  to the value only by its env-var NAME (`MONTHLY_TOPUP_SCHEDULER_SA_EMAIL`),
  never spells out the literal id, so nothing there was stale.
- `docs/components/config-deployment.md`: reviewed, no mention of this
  var at all -- left as-is.
- Review outcomes recorded in the closeout ping.

## Files touched

- `scripts/setup-admin-service.sh` -- `MONTHLY_TOPUP_SCHEDULER_SA_NAME`
  literal shortened to `admin-topup-scheduler-sa`.
- `deploy-admin.sh` -- `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL`'s derived
  literal updated to match.
- `tests/test_deploy_admin_sweep_env_vars.py` -- expected-email literal
  updated to match.
- `tests/test_service_account_ids.py` -- new: enumerates and pins every
  `scripts/` service-account id to GCP's 6-30 character range.
- `docs/technical_guide.md` -- SA id literal in the Surface-contract-32
  prose updated.
