---
date: 2026-09-14
bead: polyglot-pdf-62o4d
title: "feat(alerts): firm-scoped alerts route + FirmAlertsBanner on the mint and link-history pages (no email)"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 3 follow-up from the maintainer's 2026-09-14 alerts decision: no
outbound email for now; alerts appear (a) in the firm's own console where
staff generate links and (b) in the admin console's firm detail. Half (b)
already shipped with bd polyglot-pdf-mpebj (E3.11a)'s `AlertsPage.tsx` over
the operator-wide `GET /admin/alerts`. This bead is half (a): give a firm's
own manager/employee console a view of their own firm's unacknowledged
alerts, with acknowledge for managers only.

## What shipped

Two changes to the already-shipped `admin_backend/routes/alert_routes.py`
(bd mpebj), plus one new frontend component:

1. A NEW route, `GET /admin/firms/{firm_id}/alerts`, the firm-console
   counterpart of the operator-wide list. Same `alerts/{id}` collection,
   filtered server-side to one firm, behind
   `require_app_admin_or_owning_manager_or_employee` (the fifth gate bd
   scaig introduced for link listing) rather than the operator-wide
   route's `require_app_admin`. Its response allowlist is deliberately
   NARROWER: `id, kind, level, ts, context, acknowledged_at` -- never
   `firm_id`, `acknowledged_by`, or `emailed_at`. `?channel=` is accepted
   and ignored: alerts carry no channel field at all, but the frontend's
   `adminFetch` helper appends `?channel=` to every firm-scoped call
   unconditionally, so the route must tolerate it rather than 422.
2. `PATCH /admin/alerts/{alert_id}/acknowledge`'s gate widens to the same
   composite, so a manager can acknowledge their own firm's alert (404 for
   another firm's, mirroring the existing `_require_owning_firm` shape
   from `link_routes.py`, re-implemented here rather than imported since
   it is a two-line rule over an already-shared predicate, not a rule
   worth a cross-module dependency). An EMPLOYEE actor, though the shared
   dependency lets them through (it must, to serve the read-side route
   above), is refused with a 403 INSIDE THE ROUTE BODY before the
   Firestore transaction runs -- a deliberate route-body check rather than
   a sixth, narrower dependency, since acknowledge's actor set has no
   existing two-actor dependency to fall back to the way link revoke could
   reuse `require_app_admin_or_owning_manager`.
3. `frontend/src/console/FirmAlertsBanner.tsx`, a shared component mounted
   at the top of `MintLinkPage.tsx` and `LinkHistoryPage.tsx`. Reads role
   and firm id from the verified token's claims (mirroring
   `LinkHistoryPage.tsx`'s own resolution); renders a CLOSED kind ->
   plain-language message map (the bead's own three sentences verbatim)
   instead of the raw `context` object, with a generic fallback sentence
   (no interpolation) for an unrecognized kind; is silent (renders `null`)
   on every failure mode named in the bead (no firm claim, a non-200
   response, a thrown fetch, zero alerts) rather than showing an error --
   deliberately unlike the two host pages' own fetches, which do surface
   errors, because a peripheral notice must not compete with a page's real
   error state. Acknowledge is manager-only (client-side affordance; the
   real boundary is the route's own 403), fires one call then re-fetches
   rather than patching the row locally. `MintLinkPage.tsx` bumps a
   `refreshSignal` number prop on a 402 (insufficient credits) so the
   banner re-fetches without a page reload -- a plain prop bump rather
   than an imperative ref API, since no ref-based pattern exists elsewhere
   in this codebase to follow.

The operator-wide `GET /admin/alerts` and its own full allowlist are
UNCHANGED (still `require_app_admin`, still the complete `ALERT_FIELDS`
set) -- the new narrower view is a separate function, not a parameter on
the shared one, so the two allowlists cannot drift together by accident.

## Lessons

Reusing an established composite-gate pattern (bd scaig's
`require_app_admin_or_owning_manager_or_employee`, and `link_routes.py`'s
`_require_owning_firm` shape) made the new route's authorization
straightforward to reason about and test -- but a WRITE route sharing a
READ-oriented composite gate needs its own explicit in-body refusal for
the actor kind that should read but not write, since the gate itself
cannot express "let X through here but not there" across two different
routes sharing one dependency. This is not a new pattern worth its own
doctrine note; it is the same shape link_routes.py's revoke/list split
already demonstrates, just solved with a body check instead of a second
dependency because acknowledge's actor set has no existing narrower
dependency to fall back to.

Existing page-level tests (`MintLinkPage.test.tsx` was unaffected;
`LinkHistoryPage.test.tsx` needed two fixes) that assert on a fetch mock's
FULL call list broke the moment a new fetch-triggering component was
mounted into the page -- a reminder that a shared component's own
independent side effects (here, an unconditional alerts fetch on mount)
are a real integration surface even when the component itself is
separately unit-tested. Fixed by routing the mock by URL path rather than
by call order/count.

## Doc freshness

- `docs/technical_guide.md`: new routes-table row for `GET
  /admin/firms/{firm_id}/alerts`; the `PATCH .../acknowledge` row rewritten
  for the widened gate; new Surface contract 32.
- `docs/components/admin-service.md`: alert-routes paragraph extended for
  the new route + widened gate; `*Last updated:*` bumped to 2026-09-14.
- No `frontend/src/console/*` file this bead changed is named by any tier-2
  doc's Tracks line individually; none touched (the bead's own doc
  surfaces are `docs/components/admin-service.md` and
  `docs/technical_guide.md` only).
- A pre-existing, unrelated set of stale docs (`docs/standards/*.md`
  tracking backend/frontend files touched by OTHER beads) was reviewed via
  `scripts/check_doc_freshness.py` and left as-is -- none of them track
  any file this bead changed.

## Cross-surface review round (2026-09-14)

The Opus outer cross-surface review found the contract trace clean except
for one blocker-tier doc gap: this bead's own diff to
`docs/components/admin-service.md` bumped the doc's stamp and rewrote the
E3.11 prose paragraph but left the per-route gate table and the fifth-gate
subsection untouched, so three sentences in that doc went stale the moment
this bead shipped -- no `GET /admin/firms/{firm_id}/alerts` table row; the
acknowledge row still named `require_app_admin` and called it "The ONE
mutating route"; and the fifth-gate subsection still called itself the
ONLY gate on `GET /admin/firms/{firm_id}/links` and "pinned directly on
its one route", both now false with two more routes on the same gate.
`docs/technical_guide.md`'s equivalent table was already correct, so this
was an omission in one doc, not a doc-vs-plan disagreement.

Adopted (fixed in this round): the blocker above -- added the missing
route-table row, corrected the acknowledge row's gate name and rewrote its
"ONE mutating route" line to explain the employee refusal instead of
implying app-admin-only, and rewrote the fifth-gate subsection (both its
"COMPLETE route set" lead-in and its own heading paragraph) to describe
three routes on the shared gate instead of one. While enumerating that
same false "one route" framing (CLAUDE.md scar #8), found and fixed one
more instance of it in `docs/technical_guide.md`'s `/health` row parenthetical
(same claim, different file; not raised by the reviewer but the same class
of falsehood).

Deferred (already filed as beads by the reviewer, not touched here): the
402-refresh comment's incorrect justification (`polyglot-pdf-vhwyr`);
`MintLinkPage.test.tsx`'s untested 402->banner-refresh wiring
(`polyglot-pdf-f9hu7`); three `admin_auth.py` docstrings still calling the
fifth gate a one-route gate (`polyglot-pdf-fz1lk`) -- code comments, not a
tier-1/2 doc, so filed rather than fixed inline.

Rejected: none -- every reviewer finding was either the blocker (fixed) or
an already-filed nit (left for its own bead).

Full backend, admin_backend, and root suites re-run after the doc fix:
538 (admin_backend) + 3837 (backend, 67 skipped, 1 xfailed) + 1691 (root,
46 skipped) all green. No test code changed in this round (docs-only fix),
so no new mutation-verification was needed.

## Files touched

- `admin_backend/routes/alert_routes.py` -- new firm-scoped list route,
  widened acknowledge gate + employee refusal, narrower response allowlist.
- `admin_backend/tests/unit/test_alert_routes.py` -- rewritten: kept the
  operator-wide list/acknowledge pins, added firm-scoped list tests
  (404-not-403 scoping, narrow allowlist) and acknowledge gate tests
  (manager success + audit, employee 403, cross-firm 404, firm-less alert,
  app admin any firm), all mutation-verified.
- `admin_backend/tests/unit/test_admin_route_auth.py` -- registered route
  set gains the new path; fifth-gate carrier test widened to three routes;
  new gate-pin test for the two alert routes; module docstring updated.
- `frontend/src/console/FirmAlertsBanner.tsx` -- new shared banner
  component.
- `frontend/src/console/FirmAlertsBanner.test.tsx` -- new test file
  (silence on every failure mode, message mapping, no-raw-context,
  manager-only acknowledge, one-call-then-refetch, refreshSignal).
- `frontend/src/console/MintLinkPage.tsx` -- mounts the banner; bumps
  `alertsRefreshSignal` on a 402.
- `frontend/src/console/LinkHistoryPage.tsx` -- mounts the banner.
- `frontend/src/console/LinkHistoryPage.test.tsx` -- mock-fetch helper and
  two tests updated so the banner's own independent fetch does not corrupt
  existing call-count/sequencing assertions.
- `frontend/src/console/styles/console.css` -- `.firm-alerts-banner*`
  rules.
- `docs/technical_guide.md`, `docs/components/admin-service.md` -- see
  Doc freshness above.
