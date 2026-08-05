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
nowhere; those now fall to the banner. Round 4 (Opus) CLEARED the rubric
(all three exit criteria PASS, zero rubric gaps, round-3 fixes verified
holding) with three non-rubric findings: the HostedGuide's stale
"Validation & Progress panel" copy (the reviewer filed bd
polyglot-pdf-hnce; fixed inline in this PR, which closes it), and two
true nits deferred to bd polyglot-pdf-z5r6 per the nit convention -- the
strip's form-wide jump vs the list's search lens, and the local-mode
double lint while the folder handshake resolves. Rejected: none.

Opus outer review, primary pass 1: 6 findings, all adopted. (1) Lint
findings were not per-form state: kit A's findings left in App's mirror
resolved to no field in kit B and were PROMOTED onto B's Form row -- and
dismissing one wrote A's fingerprint into B's schema; the per-form reset
now clears the mirror, and the strip + field list are keyed per form so
their internal state (last report, Form-row expansion, search) resets on
switch. (2) The Form row's auto-expand was a once-per-lifetime latch; it
now re-opens whenever the ERROR count changes to non-zero. (3)
field-claim-unresolvable's " option[j]" path spelling (space, singular)
never matched the option-anchor regex, sending the per-option mapping
ERROR to the generic banner; the regex now accepts both spellings. (4)
The re-lint fired per keystroke against the kit-scoped route (a store
dump read each time on hosted); re-lints are now debounced 400ms with the
first lint per form instant. (5) The findings-bucketing loop existed as
two hand-copies (App + strip); extracted to one shared
bucketFindingsByField. (6) The uncovered-structural-error clause now also
covers a field with no id/type, and the disabled jump tooltip says
"reviewed" instead of "complete". Regression tests for 1-4 and 6.

Opus outer review, primary pass 2 (re-run on the fixed diff): 3 findings,
all adopted. (1) Local mode offers Mark complete on EVERY card (hosted
gates it to the open kit), so a refusal about kit B mirrored onto open
kit A's strip -- and its Go-to links, via the rename-recovery re-point,
could silently select an unrelated field of A; the mirror is now scoped
to the open kit (a non-open kit's refusal stays on its card). (2) The
kit-scoped lint's existence check used _load_meta_or_404, whose
list_kit_files lists EVERY blob under form-kits/ on GCS -- a whole-bucket
LIST per lint on the editor's hottest route; replaced with two direct
reads (metadata + dump; both absent = 404). (3) The kitId transition
(undefined -> id when the local folder handshake resolves) rode the
debounce, leaving the strip dump-blind for the window; a kit change now
lints instantly. The reviewer also filed bd polyglot-pdf-kk74
(EDITOR_GUIDE.md still documents the removed pane -- out of scope, bd
hnce covered only HostedGuide).

Opus outer review, primary pass 3: 1 finding, adopted -- the pass-2
refusal-mirror gate was applied only to the LOCAL catalogue; the hosted
catalogue's EXPANDED card grid also offers Mark complete on every card
(only its compact selector is open-kit-gated), so the same cross-kit
refusal leak existed on the production path. The identical open-kit gate
now guards both catalogues, mutation-verified. The reviewer filed bd
polyglot-pdf-ytfx (refusal Go-to links can name a SECTION id from
to-review-pending's 409 text -- narrower, separable, out of the rubric).

Opus outer review, primary pass 4: 3 findings, all adopted. (1) The
review filter did not force-expand sections, so a stale collapse hid the
filter's own targets under the "showing only fields needing review" note
-- search and the review filter now share the force-expand/guard/badge
behavior. (2) The guidance verify-loop flags (instructions-rectified /
-ungrounded-dropped / -enrich-unavailable) write a bare ".help" path and
fell to the banner; propertyAnchor now anchors bare .help at the
Instructions box (the client half of bd z9u7, which stays open for the
writers to emit precise paths). (3) A transient acroform.json read
failure silently downgraded the kit-scoped lint to a dump-blind 200; the
route now 502s on a FAILED dump read (missing dump still degrades
legitimately), so the strip shows its honest degraded state. The
reviewer filed bd polyglot-pdf-caed (a field with section_id set but
listed in no section renders in no list yet counts as a review target --
pre-existing, made visible by the count-as-control).

Opus outer review, primary pass 5: 1 correctness gap + 2 stale comments,
all adopted. The gap: the timeliness rule counted the guidance-staleness
finding, but the ack writer preserves seen_fingerprints -- so
sign-off-then-drift-then-ack (the anim gate's core scenario) dead-ended
permanently amber with no control able to clear it. The staleness rule
is now EXCLUDED from the timeliness comparison (the ack gate is its sole
owner, matching the three rendering surfaces), mutation-verified with
the reviewer's exact reproduction as the test. Comments: remoteKitStore's
flags doc and FieldEditor's lintFindings prop doc still described the
removed pane/banner; both reworded.

Opus outer review, primary pass 6: 2 findings (both the refusal line's
Go-to links -- bd ytfx re-derived as in-scope), adopted inline: the links
now render only for ids that resolve to a real field (a section-anchored
to-review-pending token silently re-selected an unrelated field via the
vanish-recovery), and the raw parse widened to the backend's own token
width so the filter, not a narrower regex fork, is the gate. This PR
therefore closes bd ytfx too. Mutation-verified.

Opus outer review, primary pass 7: 2 findings, both adopted and
mutation-verified. (1) In the no-backend fallback every finding on a
field shared one fingerprint (rule '' + a bare field-id path, message
excluded), so fixing error A and getting error B on the same field never
re-raised the timeliness demotion -- the field stayed signed-off green.
The fallback path now carries an ordinal, keeping each finding distinct.
(2) help-instructions-missing is a schema-level AGGREGATE (one finding
per schema at $.fields, rendered on the Form row), but its remedy read
"Write spoken instructions for this field" -- naming a field that does
not exist on that row; reworded to address the listed fields.

Opus outer review, primary pass 8: 3 findings, all adopted. The two
correctness ones share a root cause -- POSITION leaking into finding
identity. (1) The backend path embeds the field's array index
(`fields[3] (id=x)`), so ignoring or reordering any earlier field shifted
every later index and falsely demoted every later signed-off field: the
mass re-review wave the message-exclusion rule exists to prevent,
re-entering through the path. The fingerprint now normalizes
`fields[]/sections[]/parts[]` indices away (the `(id=X)` token beside
them IS the identity); `options[i]` is deliberately kept, being the only
thing that identifies which choice a finding is about. (2) Pass 7's
fallback ordinal was GLOBAL, so fixing an unrelated finding shifted every
later one (false demotion) and let a new finding inherit a retired
ordinal (missed demotion -- the original bug still reachable); the
discriminator is now content-derived (a hash of the message) plus a
per-(field,message) occurrence counter for genuinely duplicated
messages. Mutation-verified with the reviewer's own scenarios, including
re-deriving after an edit -- the step the pass-7 test omitted, which is
why it passed a broken implementation. (3) stripIdentitySuffix was
end-anchored (a silent-failure shape this repo has shipped before); it
now matches the token anywhere.

Opus outer review, primary pass 9: confirmed the pass-8 identity fixes hold
(it specifically tried to make position leak back and could not). Six
findings; four fixed inline, two filed. Fixed: (1) THE DEAD END -- the
timeliness demotion never writes, so the stored status stays
reviewed_correct and the review dropdown already reads "Reviewed -
correct"; re-picking it fires no change event in a real browser, and that
dropdown was the only caller that re-stamps. A field demoted by a new
finding was therefore permanently amber with no control able to clear it
-- the same trap the ack gate had, one layer up. There is now an explicit
"I have seen these -- still reviewed" control that re-stamps with what is
on screen. (2) option-value-duplicate carries the offending value only in
its MESSAGE at a bare field path, so a different duplicate defect
inherited the old sign-off; a per-rule content discriminator (that one
rule only) fixes it while every other rule keeps the message-independent
fingerprint C12 depends on. (3) stripContainerIndices could rewrite
indices inside a PDF WIDGET NAME (PDF-controlled data, not our path
grammar), collapsing two widgets into one fingerprint; widget paths are
now left alone. (4) The review filter was reachable only by right-click --
unreachable by keyboard (Enter/Space fire click) and absent on touch --
for the overview the pane removal promised; there is now a real toggle
button with aria-pressed, right-click kept as the shortcut. Also moved
the findings-mirror clear from the top of the open handlers to the
success path, so a FAILED open no longer blanks the rows' findings while
the strip keeps counting them. Filed by the reviewer: bd
polyglot-pdf-b97k (the catalogue scans still use getCompletionStats while
liveStats uses reviewCounts -- two definitions of one number, with
comments asserting the opposite), bd polyglot-pdf-18uh, bd
polyglot-pdf-0f4s.

A note on the test that did NOT catch the dead end: the unit test called
withReviewStatus directly and the UI test started from an unreviewed
field, so neither drove the real control. Attempting to pin the trap
itself is not possible in jsdom (fireEvent.change dispatches
unconditionally, unlike a browser's no-event-on-unchanged-value), so the
test pins the precondition plus the new control instead.

Opus outer review, primary pass 10: ALL THREE rubric criteria PASS, all
five pass-9 fixes verified holding (the reviewer executed the fingerprint
and anchor logic against the real backend emission paths). One finding,
filed by the reviewer as bd polyglot-pdf-uzf4 and fixed here rather than
deferred: the pass-9 re-confirm button had no severity filter, so it also
rendered on fields carrying a lint ERROR -- where red wins over the
timeliness clause in both effectiveStatus and isCountedReviewed, making
the click a success-shaped no-op. The control is now offered only when no
ERROR is anchored to the field (an error is fixed, never confirmed away).
This PR therefore also closes bd uzf4.

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
