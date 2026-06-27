---
date: 2026-06-27
bead: polyglot-pdf-fu1h
title: "Audit naive/JIT/DTI arm coexistence -- conflicts + gotchas before finishing the static-SI epic"
tags: [review, doctrine]
---

## Trigger

Maintainer-requested intermediate bead in the static-SI epic (polyglot-pdf-13w7).
After 1ac3 + j748 merged (DTI SI static + field-1 via injection), the maintainer's
gut said: the form-context/SI architecture now runs three parallel arms
(naive/legacy, JIT, DTI) that share surfaces, it has iterated heavily, and DTI is a
major overhaul only half-landed -- audit for future conflicts BEFORE uogm (C) and
h1bn (D) build more on the shared surfaces. Filed fu1h as a blocker of uogm + h1bn
so the audit gates the remaining epic work.

## What shipped

A findings doc, `docs/audits/2026-06-27-naive-jit-dti-arm-coexistence.md`, with 8
findings -- each VERIFIED against the cited code (not inferred from a subagent
summary), severity-tagged (BLOCKER-FOR-C/D / LATENT / BENIGN), with file:line + the
triggering scenario. Method: two parallel Explore agents mapped the backend
handshake/routing and the frontend mode-persistence/opener; I then re-read the
load-bearing paths myself and verified every high-severity claim before writing it
up (the subagents over-stated some -- see below).

Headline findings:
- **F1 (BLOCKER-FOR-C):** a manual section switch sends the full section fields with
  NO manifest, so the DTI branch's manifest read is empty after a switch. Benign
  today (the static SI discards progress), but it dictates HOW uogm must build its
  metadata block: source it from the section_metadata the switch carries
  (section_number/label/total/previous_spoken_names), NOT from schema["manifest"],
  or the progress/section header is empty on sections 2..N.
- **F3/F4 (LATENT):** the first handshake after a flag flip uses the stale persisted
  mode (handshake sent before session_ready reports the real flags); dtiModeEnabled
  is in-memory only so a reload-before-session_ready window omits the next-field
  schema. Both partly mitigated, both added to h1bn's edge-case list.
- **F2/F5/F6/F7 (BENIGN/by-design):** DTI field-guidance resolution is CORRECT today
  at both session start AND section switch (verified -- confirms j748 holds across
  arms); JIT manifest-loss-at-switch is an out-of-epic JIT-arm quirk; both-flags-on
  is precedence-safe; the disclaimer template is unaffected by j748.

Correcting the subagents (why I verified): the backend Explore framed F1 as a
HIGH-severity bug across JIT+DTI. On reading the code, the DTI section-switch path
actually resolves field guidance correctly (the switch carries the full section
fields + a hint with the field_id, which `_resolve_hint_field_schema` finds), so the
real DTI issue is narrower -- the progress/metadata channel, which is C's surface,
not a shipped defect. The JIT manifest-loss is real but out-of-epic.

Go/no-go: **GO for both uogm and h1bn**, with the F1 design constraint on C. No
shipped-code defect found.

Disposition of findings (decision defended below): no orphan beads filed. Every
actionable item is a constraint on an upcoming epic child, so it was recorded on the
bead that will act on it -- F1 -> uogm notes; F3+F4 -> h1bn notes -- rather than as a
standalone bead that would duplicate the child. Benign items are marked in the doc so
they are not re-investigated.

Exit-criteria scorecard (this is an investigate/document bead):
1. Findings doc enumerates every conflict, severity-tagged, file:line + scenario --
   PASS (`docs/audits/2026-06-27-naive-jit-dti-arm-coexistence.md`, 7 findings).
2. Real must-fix items recorded (here: on the acting beads) + benign items marked --
   PASS (F1->uogm, F3/F4->h1bn notes; F2/F5/F6/F7 marked benign).
3. Clear go/no-go for uogm + h1bn -- PASS (GO for both, F1 constraint on C).

Fresh-eyes adversarial assess (Sonnet): verified the audit's CLAIMS against the code
(the right test for a document-deliverable bead) -- all substance holds: every
finding's claim accurate, severity labels correct, F1 (the only blocker) verified,
go/no-go correct, all 3 exit criteria PASS. Found 2 cite-accuracy GAPS in the doc
itself (`SYSTEM_INSTRUCTION` mis-cited as ~427, actual :372; a reversed
`368-348` range) + 2 completeness suggestions (F1 should also cite the
`manual_section_switch` payload path; a 6th shared surface -- the USE_DTI-gated
compression-window derivation). ADOPTED all 4: fixed both cites to the verified line
numbers, added the manual-switch evidence to F1, and added F8 (compression
derivation, BENIGN). Re-spawn not needed -- the substance was already NO-GAPS; the
adopted items are doc-accuracy fixes I verified against the code directly. Adopt: 4.
Reject: 0. Defer: 0.

## Lessons

Verify subagent findings against the code before writing them into a durable doc.
Both Explore agents produced rich, useful maps, but the backend one labeled the DTI
section-switch path a HIGH-severity bug; reading the actual switch payload
(extractSectionFields = full fields + a hint carrying the field_id) showed DTI
resolves correctly there -- the real issue is the narrower progress/metadata channel.
An audit that shipped the subagent's framing verbatim would have mis-scoped C's work.
(Reinforces the existing "verify claims against code, not the brief" scar.)

## Doc freshness

This branch changed ONLY `docs/audits/2026-06-27-naive-jit-dti-arm-coexistence.md`
(a new file). The freshness checker flagged ~20 tier-2 docs as stale, but every one
is stale because of THIS-MORNING's j748/1ac3 code commits (config.py, ai_context.py,
form_filling_service.py, websocket_routes.py) -- files this audit branch did not
touch. A pure-docs branch cannot have made a tracked code doc stale, so all are
reviewed-and-left. (Note: `docs/components/websocket-routing.md` now reads OK -- j748
already bumped it.) The natural owner of refreshing the SI-shape contract docs
(si-reduction.md etc.) to cover the now-static DTI arm is the static-SI epic, tracked
implicitly by uogm/h1bn.

## Beads housekeeping

No orphans. Three stale in_progress beads (hrn, jf6w, ue5s) are pre-existing,
unrelated to this branch, owned by the maintainer / long-running epics -- not this
bead's to transition. Noted and left.

## Files touched

- `docs/audits/2026-06-27-naive-jit-dti-arm-coexistence.md` -- NEW: the arm-coexistence audit findings doc.
- (bead notes, not files) `polyglot-pdf-uogm` + `polyglot-pdf-h1bn` got the F1 / F3+F4 constraints appended.
