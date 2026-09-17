---
date: 2026-09-17
bead: polyglot-pdf-8e812
tags: [deploy, iam, cloud-build, hotfix]
surfaces: [scripts/setup-cloud-build.sh, scripts/audit/infra_posture.sh, admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py]
---

# The Cloud Build identity could not read the Firestore API's enablement; the rules target 403'd

The first demo deploy through the thin Cloud Build wrappers (bd `oqtm7`,
#836) failed at the `firestore-rules` target: `npx --yes firebase-tools
deploy --only firestore:rules` opens with "ensuring required API
firestore.googleapis.com is enabled", a `serviceusage.services.get`, and
`polyglot-cloudbuild-sa` got HTTP 403 "Permission denied to get service".
None of its seven pinned roles carries that permission. The runner stops
at the first failed target, so the rules (C3's denies) and every target
after them did not deploy. The mock-cannot-tell-you-the-real-dependency
scar (#7) in a new costume: the envelope tests pinned the role list
against itself and against the build's commands, and the pre-flight call
the tool makes before its command was invisible to both.

## What changed

`roles/serviceusage.serviceUsageViewer` -- the narrowest predefined role
carrying `serviceusage.services.get` -- joins the identity's role list in
all six copies (scar #8: `scripts/setup-cloud-build.sh` PROJECT_ROLES,
`scripts/audit/infra_posture.sh` CLOUD_BUILD_SA_EXPECTED_ROLES, the
envelope pin `EXPECTED_BUILD_SA_PROJECT_ROLES`, and the three docs that
enumerate the roles), each with the reason. The envelope test's
step-to-role table gains two rows keyed on the rules and indexes deploy
lines, since both run the same pre-flight. The two docs that carry the
"a NEW grant is not live until the script is re-run" note for
`datastore.indexAdmin` now say the same for this role.

The live grant is a separate per-instance ask. While reading the live
policy for it, the identity was also found to lack `datastore.indexAdmin`
(the setup script gained that role after it was last run), so both are
asked for together.

## Verification

- `test_cloud_build_sa_iam_envelope.py`, `test_infra_posture_script.py`,
  `test_setup_cloud_build_script.py`: green. Dropping the role from the
  setup script alone reddens four pins; from the posture script alone,
  one (the drift guard).
- Fresh-eyes (Sonnet): two gaps -- the indexes half's pre-flight had no
  row in the step-to-role table; the docs lacked the re-run note the
  sibling role carries. Both fixed. Unverified by execution: that the
  viewer role is the narrowest carrying the permission (Google's role
  reference; consistent with both reviewers' knowledge).

## Lessons

- **A tool's pre-flight is a permission the command line does not show.**
  The envelope test keys on `firebase-tools deploy --only firestore:rules`
  and mapped it to the rules role; the tool's first API call was a
  different permission entirely. Read a tool's first failure line on a
  fresh identity before trusting a role table derived from its commands.

## Files

`scripts/setup-cloud-build.sh`, `scripts/audit/infra_posture.sh`,
`admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py`,
`docs/components/config-deployment.md`, `docs/doctrine/promotion-tiers.md`,
`docs/technical_guide.md`.
