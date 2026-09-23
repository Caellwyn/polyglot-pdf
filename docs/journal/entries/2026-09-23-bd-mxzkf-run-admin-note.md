---
date: 2026-09-23
bead: polyglot-pdf-mxzkf
title: "docs(config-deployment): note run.admin is project-wide, mirroring nacfo.1's script comment"
sprint: 22
tags: [conventions]
---

## Trigger

docs/components/config-deployment.md documents scripts/setup-cloud-build.sh's
PROJECT_ROLES grants in one prose paragraph, then a following paragraph
("actAs, not just run.admin") explicitly explains why the actAs bindings are
resource-scoped rather than project-wide. The run.admin mention itself never
noted that IT is project-wide, or why -- the same shape as a nit already
fixed inside the script itself by bd polyglot-pdf-nacfo.1 (which added a
comment to PROJECT_ROLES explaining that Cloud Run IAM has no role narrower
than run.admin for managing revisions across multiple named services). This
bead mirrors that same rationale into the doc so the two don't drift apart.

## What shipped

One clause added to the run.admin mention in
docs/components/config-deployment.md's "The build's own identity,
polyglot-cloudbuild-sa" paragraph: it now states the grant is PROJECT-WIDE
and why (no narrower Cloud Run role exists for managing revisions across
multiple named services), explicitly contrasted with the resource-scoped
actAs bindings described two paragraphs later. No code, script, or IAM
change -- scripts/setup-cloud-build.sh already carries this rationale as a
comment; only the doc was missing it.

## Lessons

Docs-prose nits that mirror a comment already fixed in code are cheap to
close as their own tiny bead rather than folding into the original
code-fix bead -- keeps the code-fix diff minimal and the doc-fix
independently reviewable (Haiku docs-reviewer arm, not the Opus
cross-surface gate).

## Doc freshness

Bumped docs/components/config-deployment.md's *Last updated:* stamp to
2026-09-23. closeout_prep's doc-freshness pass also flagged a large set of
OTHER tier-2 docs as stale (admin-service.md, auth.md, technical_guide.md,
and about 20 more) against files this bead never touched (admin_backend/*,
backend/services/credit_ledger.py, backend/config.py, etc.) -- those are
churn from other concurrent admin-console-program work landing on dev, not
caused by this change. Reviewed and left as-is per the closeout triage rule
(stale docs not touched by this bead are noted, not fixed here). Same for
the pre-existing stacked-*Last-updated*-stamp violations the prep run
flagged on technical_guide.md, auth.md, websocket-routing.md,
ai-models.md, hipaa-pii-policy.md, logging-and-cost.md, testing.md, and
ws-protocol.md -- none of these files are in this bead's scope.

## Files touched

- docs/components/config-deployment.md -- added the project-wide clause to
  the run.admin mention; bumped the *Last updated:* stamp.
