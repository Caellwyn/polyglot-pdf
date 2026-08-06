---
date: 2026-08-05
bead: polyglot-pdf-9m8h
title: "Sprint 19 plan doc + INDEX row + epic pointers (7jmy+02ye)"
sprint: 19
tags: [doctrine]
---

## Trigger

The maintainer asked for a single /plan-epic run covering both open epics
polyglot-pdf-02ye (firm tier) and polyglot-pdf-7jmy (kit lifecycle), per 7jmy's
own instruction ("Plan these together or make the seam explicit"). The SPEAR
Scope+Plan cycle ran in-session: research fan-out over the auth/firm surfaces,
the kit publish/catalogue surfaces, and the confirmation-audit trail; How
challenges surfaced; two product calls put to the maintainer and confirmed
(firm identity via firm_id custom claim only; same-kit republish always
archives + replaces, with a "replace current" control only for the cross-kit
supersede case); rubrics + bead tree approved 2026-08-05.

## What shipped

- docs/sprint_19_firm-tier-kit-lifecycle_plan.md -- the approved plan: Why,
  settled decisions, design (revision archive under <kit_id>/_archive/<marker>/,
  draft|complete|unpublished statuses, form_metadata.author_version with marker
  precedence edition_date > author_version > fingerprint, guarded hard delete
  keyed on a kit_id equality query over confirmation_events; firms/{firm_id}
  Firestore collection, firm_id custom claim, two-axis kit visibility, static
  bundle filtered to complete+public), the two exit rubrics, the bead tree, and
  the explicit out-of-scope list.
- docs/INDEX.md -- active-sprints row for sprint 19.
- Beads filed and wired (tracker, not this diff): 7jmy children w3zw ->
  6dz0 -> xzw5 -> 6x1j (serial; editor_kit_routes + confirmation_logger are
  hub files); 02ye children lo88, vccy, kkos, xwlt + deferred ugm6 (magic
  links) and ik7e (rate limits + cost ceiling); cross-epic edge 6dz0 -> vccy;
  both epics carry plan=docs/sprint_19_firm-tier-kit-lifecycle_plan.md and
  sprint=19 metadata. Ready set verified: w3zw, lo88, kkos (the three
  disjoint-surface entry points).

Fresh-eyes assess (Step 5.5): round 1 Sonnet NO-GAPS; round 2 (mandatory Opus
clearing round) GAPS-FOUND (5) -- all five adopted and fixed in the plan +
tracker: (1) the private-kit serving seam (normalize_manifest emits static
paths; vccy now owns path emission + header-carrying viewer fetches); (2)
static pipeline must filter the byte COPY, not just index.json
(copyKitsToPublic is a blanket fs.cp); (3) archive marker resolved from the
SUPERSEDED revision's own schema so fingerprint-era confirmation records stay
retrievable; (4) 7jmy rubric #5 verify step corrected to the GCS-mode gating
path (local mode is deliberately ungated -- change logged on the epic bead);
(5) guarded-delete's existence query surfaced in confirmation_logger.py
(6x1j surfaces updated, making the serialization rationale accurate). Round 3
(Opus, on the fixed diff) found 3 more consumer-trace gaps, also all adopted:
(6) the pdf-fill call derives pdf_filename from the last URL segment, so
private-kit backend-route paths would 404 the fill -- vccy now carries
pdfFiller.ts and the 02ye rubric gained a private-kit-still-works clause
(change logged on the epic); (7) the unpublished status must be threaded
through the _status_of allowlist, the KitStatusBody Literal, and the editor's
KitStatus type/bucketing, else it coerces to "unknown" and the write-lock 409
never fires -- 6dz0 surfaces widened; (8) the static-bundle filter must
exclude underscore-prefixed entries at both levels or <kit>/_archive/** ships
publicly the way _translation does today -- kkos sharpened. Round 4 (Opus)
found 6 more, all adopted: the hosted catalogue's own two-value status sites
(remoteKitStore/RemoteCatalogue -- the path rubric #5 verifies; and
form_kit_routes.py removed from 6dz0's surfaces, its gates already hide
non-complete), the pdfFile prop threading through SchemaForm +
FilledPreviewModal (three fillPDF call sites), a NEW store-level
prefix-delete primitive on FormKitStore for 6x1j, author_version in both TS
FormMetadata mirrors (compile error otherwise), the kit-card version-label
precedence slot, and the 6dz0->vccy ordering rationale restated as
behavioral. Round 5 (Opus) found 4 more, all adopted: the serving-seam
rewrite relocated from normalize_manifest (firm-agnostic, and in GCS mode the
paths are baked by deploy-all.sh into index.json) to a per-request rewrite in
list_form_kits; the pdf-view overlay (PreviewPane -> usePDFDocument raw
getDocument URL) added to vccy's seam + surfaces; two hosted-path symbol
names corrected (KitStatusResult / setRemoteStatus); and the sprint-18
coordination note widened to bd apmo (C2), with Unlock-vs-unpublished
semantics pinned (unpublished is never unlockable to draft). Round 6 (Opus)
found 1: the explicit-filename fix must land on the BACKEND (FormKitInfo
gains schema_file/pdf_file; the frontend FormKitDescriptor.pdfFile is itself
URL-derived, so pointing at it reproduced the bug) -- adopted. Nineteen
adopted gaps across rounds 2-6; nothing rejected or deferred; no
out-of-scope beads filed by the reviewers. The terminal verdict is the Opus
re-review of the final diff, recorded in the PR body and merge ping.

Research findings that shaped the design (recorded in the plan): kit storage is
single-slot per kit_id with destructive overwrite-in-place; confirmation
records carry kit_id + edition marker but no storage address; the static
Hosting bundle ships EVERY kit including drafts (no status filter in
generate-form-manifest.ts) -- the draft leak is closed by the static-scoping
bead; no rate-limiting or cost-ceiling code exists anywhere (the limits bead is
new infrastructure, deliberately deferred with magic links).

## Lessons

- Sprint 18 (epic polyglot-pdf-4qul) is concurrently reworking the /status
  promotion route (translation bake moves out). Two active sprints now touch
  editor_kit_routes.py's status transition -- the sprint-19 lifecycle beads
  carry an explicit check-4qul-state-at-claim-time note. Planning epics
  together made this collision visible before any code was written.

## Doc freshness

- docs/INDEX.md bumped (new active-sprint row). No component/standards docs
  touched -- this is a planning-only change; the docs the child beads will
  affect (auth.md, pdf-filling.md, confirmation-and-audit.md) get their bumps
  when those beads ship.
- The freshness checker flagged ~20 docs stale against tracked-file mtimes;
  those mtimes are worktree checkout times, and none of the flagged docs track
  files this docs-only branch changed -- left as-is per the
  already-stale-before-you rule.
- Beads housekeeping: no orphans; three stale in_progress beads (dft1, ggla --
  the deployment-track session's active work at 1 day; 52qm.1 at 3 days)
  deliberately left untouched -- they belong to other work streams and
  transitioning them from here risks a claim collision.

## Files touched

- docs/sprint_19_firm-tier-kit-lifecycle_plan.md (new)
- docs/INDEX.md (active-sprints row)
- docs/journal/entries/2026-08-05-bd-9m8h-sprint19-plan-filing.md (this entry)
