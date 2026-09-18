---
date: 2026-09-17
bead: polyglot-pdf-e1l5f
title: "docs(components): collapse the stacked Last-updated stamp chains in admin-service.md (18) and config-deployment.md (8), and teach check_doc_freshness.py that shape"
sprint: 22
tags: [conventions, refactor, testing]
---

## Trigger

Noticed during the outer cross-surface review of bd polyglot-pdf-cvck9
(tracing the `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL` contract into the docs
that restate it). `docs/components/admin-service.md` carried EIGHTEEN
stacked `*Last updated:*` stamps, each a parenthetical paragraph
narrating what one bead changed, and `docs/components/config-deployment.md`
carried EIGHT -- versus one or two on every peer surface doc. That is a
chronological narrative threaded through a tier-2 doc's prose, which
`docs/doc-architecture.md` section 3 makes current-state-only. Neither
`scripts/check_doc_freshness.py`'s existing checks (a `Previously:`/
`Prior:`/`Earlier:` chain, or an `## Update history` heading) could see
this shape: a doc that instead grows a NEW `*Last updated:*` paragraph
per bead and never removes the old ones is a third violation shape,
distinct from both.

## What shipped

**The two named docs.** Both collapsed to exactly one `*Last updated:*`
stamp. `config-deployment.md`'s body prose was already fully current-state
(everything the eight stamps narrated -- the deploy-wrapper thinning, the
`MONTHLY_TOPUP_SCHEDULER_SA_EMAIL` move into `admin.env`, the staging gate,
the CSP/security-headers work -- was already stated in the body below the
stamps), so this was a pure deletion. `admin-service.md` needed real content
work first: two of its eighteen stamps described routes that had NEVER
been added to the Routes table -- the firm-plan + monthly credit top-up
routes (`PATCH /admin/firms/{firm_id}/plan`, `POST
/admin/credits/monthly-topup`, bd polyglot-pdf-0euzk) and the whole
deploy-trigger surface (`POST`/`GET /admin/deploys`, `GET
/admin/deploys/{deploy_id}`, `GET /admin/deploys/targets`, `GET
/admin/deploys/promotable`, `POST /api/deploys/webhook`, bd
polyglot-pdf-tb3kp / polyglot-pdf-ryx86). Added seven new table rows for
those, and replaced a dangling "see the top dated block above" reference
in the console-pages bullet (which pointed at a stamp paragraph about to
be deleted) with an actual current-state description of `DeploysPage.tsx`.
Every other fact the eighteen stamps carried was already present as body
prose, so the rest of the collapse was deletion, not addition.

**The checker.** `check_doc_conventions()` in
`scripts/check_doc_freshness.py` gained a third check: any tier-1/tier-2
doc carrying more than one `*Last updated:*` line is now flagged, naming
every stamp's line number. This is generic across the whole corpus, not
scoped to the two docs above.

**Scope decision (see "Autonomous decisions" below).** Running the new
generic check against the real repo surfaced EIGHT more docs with the
same violation (`docs/technical_guide.md`, `docs/components/auth.md`,
`docs/components/websocket-routing.md`, `docs/standards/ai-models.md`,
`docs/standards/hipaa-pii-policy.md`, `docs/standards/logging-and-cost.md`,
`docs/standards/testing.md`, `docs/standards/ws-protocol.md`) --
`docs/technical_guide.md` is a special case, since it is documented
(bd polyglot-pdf-abn4o) to carry NO stamp at all, so its four lines are a
regrowth of the exact pattern abn4o already removed once. Fixing all
eight is a real multi-file content pass, well beyond this docs-nit bead's
named surfaces. Filed bd polyglot-pdf-4iyi6 with the exact enumerated
list and line numbers, and added a temporary, explicitly-commented
`KNOWN_STACKED_STAMP_DOCS` allowlist to
`tests/test_doc_freshness.py::TestCurrentRepoIsCleanOfChainsAndHistorySections`
so the new generic check does not turn CI red on every other branch that
happens to touch those eight files in the meantime. The allowlist only
suppresses the "stacked" finding for those exact eight paths -- a NINTH
stamp on any of them, or a stacked-stamp violation on any doc NOT listed,
still fails the test. bd 4iyi6's own exit criteria require the allowlist
to end up empty.

## Lessons

A doc-convention checker built against two known violation shapes
(`Previously:` chains, history-section headings) can still miss a THIRD
shape that produces the identical outcome (chronological narrative baked
into a current-state doc) through a different mechanical signature (a
repeated structural marker rather than a keyword). When auditing a
convention for compliance, grep for the STRUCTURAL PROPERTY the rule
actually cares about (here: "more than one occurrence of the marker
line"), not just the keyword patterns an earlier fix happened to name.

Landing a newly-generalized checker against a real corpus can surface a
population of pre-existing violations far larger than the bead that
motivated the checker. The right move is not to either (a) silently fix
the whole population inside an unrelated docs-nit bead, or (b) narrow the
checker's logic to dodge them -- (a) blows the bead's scope and turns a
mechanical cleanup into an open-ended content audit, and (b) reintroduces
exactly the blind spot the new check exists to close. The move that keeps
both properties is: keep the check fully generic, file one bead
enumerating every violation it surfaces (CLAUDE.md scar #8), and give the
CI-gate TEST (not the production check) a narrow, explicitly-commented,
provably-temporary allowlist naming exactly that enumerated set -- so the
new rule still catches every OTHER doc immediately, the pre-existing
population gets a tracked, boundaried follow-up instead of open-ended
scope creep, and the allowlist itself is the signal that closes it out
(it must be empty when the follow-up bead closes).

## Doc freshness

`docs/components/admin-service.md` and `docs/components/config-deployment.md`
both re-stamped `2026-09-17` with the collapse noted. No other tier-2 doc
in this bead's declared surfaces needed a bump.

## Files touched

- `docs/components/admin-service.md` -- collapsed 18 stamps to 1; added 7
  Routes-table rows for the plan/topup and deploy-trigger routes; replaced
  a dangling forward-reference in the DeploysPage console-pages bullet.
- `docs/components/config-deployment.md` -- collapsed 8 stamps to 1 (pure
  deletion; body was already current).
- `scripts/check_doc_freshness.py` -- `check_doc_conventions()` gained
  Check 3 (stacked-stamp detection).
- `tests/test_doc_freshness.py` -- five new tests for Check 3
  (mutation-verified: removing the check reddens three of the five; the
  other two correctly pin the negative/no-violation case), plus the
  temporary `KNOWN_STACKED_STAMP_DOCS` allowlist on the CI-gate test.
