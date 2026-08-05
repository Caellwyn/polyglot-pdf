---
date: 2026-08-05
bead: polyglot-pdf-o7y9
title: "s18 C1: embedded findings + one-truth strip (warnings pane removed)"
sprint: 18
tags: [schema-editor, refactor, testing]
---

## Trigger

Second child of the sprint-18 editor-UX epic (polyglot-pdf-4qul, plan
docs/sprint_18_editor-ux-overhaul_plan.md, decisions 1-3, rubric 1), after
C12 stabilized every lint message. The maintainer's hands-on sessions
established that a SEPARATE warnings surface is itself the bug: it eats
workspace, holds a second copy of per-field truth that drifts from the
field statuses ("0 need review" beside "7 to review"), and invites bulk
shortcuts that defeat review.

## What shipped

The ValidationPanel's findings LIST is gone; the component survives as a
one-line strip owning its four non-display responsibilities (the lint
round-trip with the monotonic staleness guard, the onReport mirror,
Repair-all, the degraded-mode notices) plus a refusal/error line from
birth -- both catalogues now mirror a Mark-complete refusal up to App,
which homes it on the strip with click-to-focus links for any "(id=x)"
the gate names.

Findings render at their fields: FieldEditor buckets each finding by the
property its path names (help.instructions / help.details / options[i] /
show_if-require_if / the field itself) and renders it under that control
with the C12 remedy line (RULE_REMEDIES is now consumed, as staged); a
header chip scrolls to the first finding. FieldList rows carry a count
chip; ONE pinned Form row at the top holds schema-level (field-less)
findings and is the only standalone-dismiss surface -- WARNINGs only,
stored as fingerprints on schema._form_review.dismissed_fingerprints;
ERRORs are never dismissible (they block the gate regardless).

The count predicate is pinned (decision 2): reviewed = _review.status ==
reviewed_correct, not demoted by the ack gate or the timeliness rule, and
no lint ERROR anchored to the field. reviewStatus.isCountedReviewed is the
one definition; the strip's counts, the live catalogue bar (liveStats),
and the review-target set (jump + filter) all derive from it, so "M to
review" and the jump agree by construction. checkFieldComplete left the
count and stays the advisory WHY-list/icon input -- the named corner (a
signed-off field red for a client-only reason counts reviewed while its
icon stays red) is accepted with the pinning.

seen_fingerprints landed as the fourth _review slot: fingerprint = rule +
field + path-sans-identity-suffix, message EXCLUDED (C12's rewording can
never mass-demote); the STATUS writer owns the slot (sign-off stamps the
current findings' fingerprints -- empty set when no report is in hand --
and any transition away clears it), the note/ack writers preserve it via
one shared rebuildReview helper. A finding newer than the sign-off demotes
the field to needs-review as an effective-status derivation, exactly like
the ack gate. Pre-slot sign-offs are grandfathered (no fingerprints
recorded -> no demotion) instead of mass-demoting every existing kit on
ship.

The strip lints with the SAME inputs as the publish gate: new backend
route POST /api/editor/kits/{kit_id}/lint lints the POSTED (possibly
unsaved) schema WITH the kit's persisted acroform.json, so the two
dump-gated rules are visible live; the dumpless /lint remains for
schemas with no kit identity. The frontend passes the kit id only when
server actions are trusted for the folder (same-folder handshake), so a
mismatched local folder can never pull another copy's dump into the
findings. This retired C1's original "NO backend changes" claim per plan
v11. RULE_LABELS/RULE_REMEDIES moved to utils/lintFindings.ts and the
backend parity test follows them there.

Verification: full backend suite 1561 passed; full schema-editor suite
1090 passed; five mutation checks (drop the demotion, key the fingerprint
on the message, drop the lint-ERROR clause from the count, drop the kit
id from the strip's lint call, drop slot preservation from a writer) each
reddened the tests that pin them. One fixture was strengthened during
mutation testing: the strip's hand-tally test now stamps the ERROR's
fingerprint into the signed-off field so the ERROR clause -- not the
timeliness rule -- is what it pins.

Deferred/known-corner notes: the live-browser drive was skipped (port
3001 held by a non-preview process on this machine); behavior is covered
by the component/App suites, and the epic's later children (C4/C2) drive
the same surfaces.

Fresh-eyes assess loop: round 1 (Sonnet) found 2 gaps, both adopted --
the FieldEditor chip's error count was not scoped to its field
(regression test added), and the onStatusRefusal producers had no tests
(added to both catalogue suites). Round 2 (Opus) found 3 gaps + 1
consistency finding, all adopted: (1) propertyAnchor assumed options[N]
holds an index, but the translation-flag writers put the option VALUE
there -- numeric values (real on i-90/f1040) anchored flags at the wrong
option row; fixed with a rule-aware resolveOptionIndex. (2) A finding
whose field_id names a NON-field (the publish-blocking to-review-pending
ERROR carries a section id) rendered nowhere; formLevelFindings now keys
on "resolves to no field", homing those on the Form row. (3) The pinned
predicate could read 100% beside a red row for an unmapped CHOICE field
(no field-level name, unmapped options) because NO backend lint rule
covers that class -- the plan's C12-promotion precondition never
happened; a narrow schema-derived stand-in clause excludes it from the
count, and bd polyglot-pdf-xuub is filed to promote the real backend rule
and retire the clause. (4) The FieldList row badge counted the staleness
finding while the FieldEditor chip excluded it; both now exclude it (the
ack-gate box is its rendering). The round-2 reviewer also filed two
out-of-scope beads itself: polyglot-pdf-2dlb (strip jump dead-click for a
field whose section_id names no section) and polyglot-pdf-z9u7
(instructions-rectified/-ungrounded-dropped use a bare .help path).
Round 3 (Opus) found 4 more, all adopted: (1) the refusal line and the
review filter were per-form state that survived a kit switch -- a refusal
naming form A's fields (with dead links) sat on form B's strip; every
open/close path now resets both (resetPerFormReviewUi). (2) The header
chip's scroll used a combined document-order selector, so it always
landed on the advisory banner instead of the property anchor; it now
prefers [data-embedded-finding], banner as fallback, and the test asserts
WHICH element scrolled. (3) A shipped RemoteCatalogue notice still told
authors "the validation panel lists them"; reworded to the flagged
option rows, with the old phrase pinned absent. (4) An options[]-anchored
finding on a field whose type never renders the Options block (backend
lint checks options on every field) was counted by the chip but rendered
nowhere; those now fall to the banner. Rejected/deferred: none rejected.

## Lessons

- A mutation that reddens a test can still be masked by an ADJACENT rule:
  the count's lint-ERROR clause mutation stayed green at the strip level
  because the fixture's empty seen_fingerprints let the timeliness rule
  demote the same field. Pin a clause by constructing the fixture so ONLY
  that clause distinguishes pass from fail (mutation-verify-per-clause,
  the parametrization memory one level down).
- vitest 4 on this worktree wedges on many-file parallel runs (fork
  startup timeouts) but is reliable with --fileParallelism=false;
  single-file runs are unaffected.

## Doc freshness

docs/technical_guide.md bumped: its route table gained the editor lint
pair (/api/editor/lint + the new kit-scoped /api/editor/kits/{id}/lint)
since it tracks backend/routes/*.py and this branch changed
editor_kit_routes.py. The freshness checker's other two STALE flags
(standards/voice-and-vad.md, standards/ws-protocol.md) track files this
branch did NOT touch -- pre-existing staleness, reviewed and left. No
components/ doc tracks the schema-editor surface (no
docs/components/schema-editor.md exists); docs/INDEX.md and the sprint-18
plan already describe this child and were left as-is.

## Files touched

- backend/routes/editor_kit_routes.py -- kit-scoped lint route (+ dumpless-route docstring)
- backend/tests/unit/test_editor_kit_routes.py -- 4 kit-scoped lint tests
- backend/tests/unit/test_lint_rule_parity.py -- parity source moved to lintFindings.ts
- schema-editor/src/utils/lintFindings.ts (+ test, new) -- labels/remedies, fingerprints, anchors, Form-row dismiss
- schema-editor/src/utils/reviewStatus.ts (+ test) -- rebuildReview, seen_fingerprints, timeliness rule, pinned count predicate
- schema-editor/src/utils/remoteKitStore.ts -- lintSchema(schema, kitId?)
- schema-editor/src/types/schema.ts -- FieldReview.seen_fingerprints, FormSchema._form_review
- schema-editor/src/components/ValidationPanel.tsx (+ test rewrite) -- the one-line strip
- schema-editor/src/components/FieldList.tsx (+ FieldList.formrow.test.tsx, new) -- Form row, row flags, review filter
- schema-editor/src/components/FieldEditor.tsx (+ FieldEditor.embedded.test.tsx, new) -- property-anchored findings, chip, sign-off stamping
- schema-editor/src/components/FieldEditor.{guidanceack,review,ignore}.test.tsx -- re-pinned to the new homes
- schema-editor/src/components/FormCatalogue.tsx / RemoteCatalogue.tsx -- onStatusRefusal mirror
- schema-editor/src/App.tsx (+ App.hosted.test.tsx) -- jump/filter/refusal/form-findings wiring; liveStats on the pinned predicate
