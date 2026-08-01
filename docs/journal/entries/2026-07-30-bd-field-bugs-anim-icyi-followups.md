---
date: 2026-07-30
bead: polyglot-pdf-hii0, polyglot-pdf-stkz, polyglot-pdf-g5vj, polyglot-pdf-2hxu, polyglot-pdf-r5q1, polyglot-pdf-l7u0, polyglot-pdf-79tz
title: "Eight follow-ups from the anim + icyi closeouts: the gate's blind spots, the painter's all-or-nothing rect, and a once-mock that leaked"
tags: [editor, extractor, guidance, testing, postmortem]
---

## Trigger

The `bd polyglot-pdf-anim` (guidance staleness gate) and `bd polyglot-pdf-icyi`
(deterministic positions) closeouts each filed a cluster of out-of-scope
follow-ups. The maintainer handed over eleven and asked for as many as could be
done independently, skipping anything blocked on their decision. Eight were
actionable; three were not (see "Left open" below).

## What was wrong

Three of the eight share one shape: **a rule was enforced in one place and
silently absent in another**, so two surfaces disagreed about the same field.

- **hii0** -- the "Why this field is flagged" banner built its warning list
  straight from the raw findings array. After a reviewer ticked the
  acknowledgment checkbox two inches below it, every other surface agreed the
  field was clear (green row, no amber ring, counted complete) while the banner
  still demanded the confirmation the human had just given. The reviewer could
  not tell whether their click had registered -- which trains precisely the
  click-through-the-gate habit the feature's own docstrings say to avoid.

- **l7u0** -- `FieldOverlay` derived status from the field alone, so the PDF
  canvas ignored both backend lint ERRORs (pre-existing, documented in its own
  comment) and the guidance gate (added by anim). It could paint green over a
  field the list showed amber, contradicting the "review sign-off agrees across
  surfaces" contract its own docstring claims.

- **2onl / l7u0's shared root** -- both are instances of "a derived signal
  reached one consumer and not another."

The other five:

- **stkz** -- `identity_payload` hashed name, spoken_name and option bindings,
  but NOT `type`. A `text -> date` change rewrites the expected ANSWER SHAPE
  while leaving every hashed key byte-identical, so the hash never moved and the
  gate stayed silent on guidance that no longer fit the field.

- **g5vj** -- `currentIdentity`'s regex was unanchored. Because the backend
  interpolates the field id AHEAD of the identity token, a field id containing a
  literal `[identity:<hex>]` would parse the id's embedded hex instead of the
  real trailing hash -- pinning the ack to a string that can never change, i.e.
  a permanent waiver, the exact hole current-identity pinning exists to close.

- **u4r0** (COLLISION -- fixed independently by PR #514 mid-review, which
  closed the bead; this PR does NOT close it) -- the position pass ran BEFORE
  `_complete_grouped_families`, which appends missing family members carrying
  only `{value, label, pdf_field_name}`. Those options shipped positionless.
  Not cosmetic: the runtime option-rect painter is ALL-OR-NOTHING
  (`valuePainting.ts` returns `[]` for the WHOLE field if ANY selected option
  lacks a usable rect), so one completed option silently disabled per-option
  marks for the entire choice field. Both fixes re-ran the position pass after
  completion; #514's adds an explicit `normalize_pages=False` parameter so the
  one non-idempotent part of the pass (the one-shot page-base shift) cannot
  run twice -- the maintainer chose that implementation, and this PR keeps it,
  layering the 2hxu provenance renames and the r5q1 guard on top. This PR's
  surviving u4r0-adjacent contribution is `test_provenance_counts_reflect_
  BOTH_position_passes` (the two-pass provenance wiring pin) plus the stage-
  order unit tests, which complement #514's end-to-end tests rather than
  duplicate them.

- **2hxu** -- since icyi made the deterministic rect win unconditionally,
  `positions_filled` counts DERIVATIONS ("did it run?") rather than REPAIRS
  ("was it needed?"), making it ~= the field count on any AcroForm. The
  `positions_filled: 0` alarm the 5f41 journal records as a missed signal can
  never fire again.

- **r5q1** -- the real-kit position guard resolved expected rects only via a
  field-level `pdf_field_name`, so it skipped all 32 consolidated-choice fields
  and never inspected `options[]` at all, leaving 112 committed option rects
  unverified. The existing non-vacuity floor could not catch this: it asserts
  `compared > 0` per kit, and the top-level-named text fields keep it non-zero.

## The one that was a real mystery: 79tz

Filed as "seen once in a full run, passed in isolation and on re-run." Root
caused rather than papered over.

`afterEach` used `vi.clearAllMocks()`, which wipes call history but does **not**
drain QUEUED ONE-TIME implementations. An unconsumed `mockRejectedValueOnce` is
also not overwritten by the `beforeEach` `mockResolvedValue`, because once-values
are consumed ahead of the persistent one. So any test that queues a one-time
rejection and fails to spend it -- an early assertion failure, a save the UI
coalesces, a timing-dependent second click -- leaks that rejection into whichever
test runs next, where it fires on the FIRST call.

That is exactly the reported failure: `a later successful save clears a lingering
failure banner` queues one rejection and expects the SECOND save to resolve, so
an inherited rejection makes the banner never clear.

Verified directly, both ways: with a deliberately-leaked once-mock, the
following test fails under `clearAllMocks` and passes under `resetAllMocks`. The
probe was kept as a permanent regression pin.

## Decisions taken (and why they were not escalated)

**stkz: hash `type` rather than document it as excluded.** The bead offered
either. The payload's own docstring justifies its exclusions with "changing
those does not make authored guidance wrong" -- and a type change plainly does:
`type` is one of the seven inputs the authoring model is shown
(`enrich_instructions.field_digest`), and CONTRACT_TEXT names answer format an
explicit content priority. So the stated test selects hashing. Decisive
measured fact: **no shipped kit carries a baked `identity_sha1`** -- 0 of 44
provenance records across all three committed kits -- so the formula window the
bead flagged as closing on the first re-bake is still fully open, at zero
migration cost. Appended to the positional payload so existing elements keep
their indices.

**r5q1 vs ks1y: an enumerated shrink-only ledger.** Strengthening the guard
surfaces exactly 8 mismatches, all i-90 consolidated-choice fields, all owned by
`bd polyglot-pdf-ks1y` -- which is scoped to a PARALLEL `i-90_v2` extraction
because the live demo serves `form-kits/i-90` and it must stay byte-identical.
Rather than leave the guard switched off for all 32 fields, the 8 are enumerated
in `_KS1Y_FIRST_OPTION_DIVERGENCE`, still counted as compared, and asserted to
only ever SHRINK: a field that stops diverging fails the test until it is
removed from the list. This turns on verification for the other 24 now without
touching the demo kit.

**Bundling eight beads into one PR.** Each is individually too small to justify
a full review cycle; the repo contract explicitly permits one PR closing several
whole beads.

## Verification discipline

Every fix was checked for NON-VACUITY by reverting it and confirming the new
tests actually fail:

- g5vj: both new tests fail on the unanchored regex.
- hii0: exactly the 3 positive-suppression assertions fail; the 3 negatives
  (no ack / superseded ack / other-field scoping) stay green.
- u4r0: removing the re-run reproduces `option 1 has no pdf_position`.
- r5q1: breaking option resolution fires the new per-class floor
  (`f1040: 24 option(s) carry a pdf_position but NONE resolved`); adding a
  non-diverging field to the ledger fires the shrink assertion.
- l7u0: exactly the 4 disagreement cases fail; control + acked + degradation
  stay green.
- 79tz: reproduced and fixed in both directions (see above).

Final: backend **2364 passed / 2 skipped**; schema-editor **956 passed**, stable
across **three consecutive full runs** (the flake's own bar); typecheck clean.

## Doc-freshness review (closeout requirement)

`closeout_prep.py` reports a set of stale tier-2 docs. Reviewed and
deliberately NOT updated: every one is a backend/voice-path doc
(`hipaa-pii-policy`, `voice-and-vad`, `ws-protocol`, `stateless-architecture`,
`terminology`, ...) drifting against files this PR never touches. None of the 17
changed files appears as a staleness trigger. Updating them would be scope creep
on unrelated surfaces.

One near-miss worth recording: `docs/components/pdf-view.md` tracks a
`FieldOverlay.tsx` and looked invalidated by l7u0. It is a DIFFERENT component --
`frontend/src/pdf-view/FieldOverlay.tsx` (the voice-app preview) vs
`schema-editor/src/components/FieldOverlay.tsx` (the authoring editor). Two
files, two trees. The doc remains accurate.

`bd` reports one stale in_progress bead (`polyglot-pdf-btbi`, W-7 require_if).
Pre-existing, unrelated to this diff, and owned by other in-flight work -- not
transitioned here.

## Left open (maintainer decisions)

- **ks1y** -- exit criterion 1 requires human eyes on a rendered overlay to
  decide which of two real widget rects is correct. No `i-90_v2` exists yet.
- **2onl** -- catalogue % is blind to the gate. The card is computed from a
  directory scan; the gate lives in lint findings the scan never runs, so the
  card structurally cannot see it. The maintainer proposed a better direction
  than any in the bead: store the percentage in schema metadata and recompute
  on save. Two riders: the trigger must be "on save," not "on status change"
  (staleness is a cross-field hash comparison -- editing field A's labels can
  invalidate field B's sign-off with no status change anywhere), and a stored
  derived value is a documented exception to the no-persisted-derived-state
  convention.
- **ug5n** -- repair-all's value re-mint raises the gate on untouched fields.
  The candidate fix has `schema_repair.py` refresh provenance `identity_sha1`,
  i.e. a machine writing the gate's own comparison basis. How much the gate
  trusts automation is a product call.

## Filed

`polyglot-pdf-kas0` -- `usePDFDocument.test.ts` carries the identical once-mock
hazard (module mock + `clearAllMocks`). Out of scope for 79tz and no flake
observed there yet, so filed rather than folded in.
`remoteKitStore.test.ts` was checked and is NOT affected -- it builds a fresh
`fetchMock` every `beforeEach`.

## Lessons

1. **When a gate is added, sweep every surface that renders the gated thing.**
   anim added the staleness gate to the row and the counters; the banner
   (hii0), the canvas (l7u0), and the catalogue (2onl) each kept their old
   answer. Three separate beads, one omission.
2. **A guard that resolves its expectation more narrowly than the code it
   guards is decoration.** r5q1 is the second instance of exactly this shape in
   the same test (the first was exact-vs-suffix matching, which had already
   blanked 132 i-90 fields). A whole-kit non-vacuity floor cannot catch a
   regression confined to one class -- floors must be PER-CLASS.
3. **`clearAllMocks` is not `resetAllMocks`.** The difference is invisible until
   a once-mock goes unconsumed, and then it presents as an unrelated test
   failing intermittently. Prefer `resetAllMocks` in any file that uses
   `*Once` mocks with module-level defaults.
4. **"Is it spoken?" was the wrong test for the identity hash.** The right one,
   already implicit in the docstring's own exclusions, is "does changing it make
   the authored guidance wrong?" -- which is what admitted `type`.
