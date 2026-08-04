---
date: 2026-08-04
bead: polyglot-pdf-575i
title: "fix(voice): option-recital + hint-translation edge cases, and one vacuous test (bd 575i, 9tuu, thun, pjws, 5419, 35z0)"
tags: [testing, conventions]
---

## Trigger

Six beads filed as follow-ups to the prompt-tuning bundle (bd polyglot-pdf-41fi,
c2jy, 0rm1) and the f1040 line-binding fix (bd polyglot-pdf-3ave). All six were
edge cases nobody could hit on today's shipped kits -- latent, not live
regressions -- plus one test that had quietly stopped being able to fail.

The grouping is deliberate: 575i and 9tuu are two different ways the SAME `n == 2`
render branch over-claims; thun and 5419 are two different ways the SAME frontend
option-label resolver diverges from the backend's; pjws is the staleness bug that
0rm1 turned from harmless into actively wrong; 35z0 is test hygiene the maintainer
had already investigated and left notes on.

## What shipped

**575i + 9tuu -- the two-option marker is now gated on more than the count.**
The `Options (2 -- ask ONE natural question ...)` marker asserts an *exclusive*
choice between two *short* labels. Neither half held universally:

- A 2-option **multi-select** (`checkbox_group` and friends) may legitimately take
  BOTH options. The marker -- and the SI rule it triggers ("a plain yes/no
  question ... do not ask which one applies") -- forecloses that. It now falls to
  the recital branch, whose rule already says "or which ones, for a multi-select".
  Gated via `MULTI_SELECT_OPTION_TYPES`, named on the multi-select side so an
  unrecognized type is NOT assumed multi and keeps the natural ask (the mirror of
  the `ASK_DIRECTLY_OPTION_TYPES` safe-default reasoning from bd cqx6).
- A pair whose labels are too long to fold into one question. i-90
  `p7_checkbox7`'s options are ~23- and ~27-word legal declarations; its
  `spoken_name` ("Is the preparer an attorney or not") collapses them to an
  attorney yes/no and silently drops the representation-scope clause. Above
  `TWO_OPTION_MAX_LABEL_WORDS` (20) the pair recites in full.

The threshold is set from the corpus, not from taste. Across every 2-option field
in the three shipped kits the longest label of each pair runs 1,1,1,1,1,2,2,2,3,3,4,5,6
words for the plainly-either/or fields, then **17** for w7
`previously_received_itin_or_irsn`, then **27** for the i-90 declaration. The w7
case is a genuine yes/no ("Have you previously received an ITIN?") padded with the
printed-form navigation the SI already suppresses ("Yes. Complete line 6f. ..."),
so it MUST keep the natural-question marker -- any threshold at or below 17
regresses it into exactly the recital bd 41fi removed. 20 sits inside the only real gap in the data (17 to 27) with room on both
sides -- deliberately nearer the low end, so a slightly wordier genuine
either/or still asks naturally.

f1040 `fld_3c` was the other half of 575i, and it needed a different mechanism:
both its labels ("1 Line 3a" / "2 Line 3b") are *pure* printed-form navigation, so
SPEAK-THE-SUBSTANCE would strip them to nothing speakable. Fixed in SI prose (a
carve-out to the carve-out: when navigation is ALL there is, it IS the option's
identity and is spoken), not in the kit -- the class recurs on every LLM-extracted
kit, and a label edit would fix one field on one form. f1040 is a `draft` kit so
the never-edit-a-complete-kit rule did not bar an edit; it was simply the weaker
fix.

Consequently the SI and both initiating templates now key on the **marker** rather
than a bare option count ("TWO-option fields, WHEN THE GUIDANCE MARKS THEM SO",
"the guidance marks the field as having TWO options"). A count-keyed rule would
contradict the render on precisely the fields the render deliberately re-routes.
This also resolves 575i's third complaint -- that the old "TWO-option fields are
different" opener read as overriding the preceding "never summarize the list"
guard.

**thun + 5419 -- the frontend hint resolver now mirrors the backend's.** The hint
and the guidance block reach the model on the SAME turn, so any tolerance the
backend has and the client lacks resurfaces as the two-languages-at-once condition
bd 0rm1 set out to fix. `formatNextFieldHint` now accepts the BCP-47 code and its
stem alongside the canonical lowercase name, lowercases the kit's own keys, and
treats a whitespace-only value as a miss (it previously caught `''` but not
`'   '`, which would have spoken a blank). Added `kitTranslationKeys` +
`SPOKEN_LANGUAGE_BCP47` to `frontend/src/shared/languages.ts`, mirroring
`backend/utils/language_codes.py`. Legacy bare-string options (`options: ["A","B"]`
-- a supported shape that `schema_lint`, `_sanitize_options` and `optionValue()`
all handle) rendered a literal `undefined` as spoken option text; so did a dict
option missing `label`. Both now degrade to the string / the value.

thun's criterion 2 asked for a *decision*, not necessarily code: the backend's
rung-2 secretary `translate_items` fallback is deliberately NOT mirrored. Those
overrides are built per form+language at session start and never sent to the
client, so an unbaked kit's hint stays English by design rather than growing a
second, divergent translation path on the client. Recorded in the resolver comment
and in `docs/standards/si-reduction.md`.

**pjws -- the session language is now read through to persisted state.**
`changeSpokenLanguage()` persists via `SchemaFormStateManager`, which builds a NEW
state object and saves it; it never touches `WebFormConnection`'s in-memory
`this.state`. Pre-0rm1 that was harmless (the hint fell back to English). Post-0rm1
it is worse than the original bug: the hint asserts confident labels in the
language the user just switched AWAY from, beside a guidance block in the new one.
Worse still, `handleConfirmFieldRequest` ends in `save(this.state)`, so the next
confirm wrote the stale language back over the new one -- the switch survived
about one turn. Fixed with a `sessionLanguage` accessor used by all four hint
producers, plus state refreshes in the hint and confirm handlers. The accessor
reads only the LANGUAGE through to storage rather than reloading all of
`this.state`, which keeps it safe for the section-switch callers that hold
freshly-mutated unsaved state.

**35z0 -- a test that could no longer fail.**
`test_body_text_numerals_are_not_read_as_line_markers` asserted
`all(f["widget_is_on_line"] != "3" for f in findings)` over a findings list that
bd 3ave had emptied; `all()` over `[]` is `True`. The maintainer had already
investigated and left notes: a repoint to the frozen corrupt specimen is NOT a fix
(vacuous under both schemas), and the assertion never held by the rule anyway.
Reproduced both findings independently before choosing. The reason it never held is
geometric: the stray legend `'3'` (x_right 422.0) prints on only TWO rows, so it
dies to the column-SIZE rule (`_GUTTER_MIN_COL = 3`) and never reaches the
uniqueness rule the test named.

Took the maintainer's option (b) -- rebuild, not delete -- because it restores real
coverage rather than removing a dead assertion. The replacement binds a synthetic
field CORRECTLY to `c1_35`, the 4c-row checkbox sitting 5.8pt right of the legend
`'1'` (which recurs on three rows and so clears the size threshold, leaving
uniqueness as the only thing rejecting it). Baseline: silent. Mutation: the correct
binding is falsely reported as "line 1". Asserting a positive outcome under the
mutation is what makes it bite where the old absence-of-line-3 assertion could not.

**Caught in outer review -- the threshold was language-dependent.** The Opus
outer review found that the 20-word gate was measuring the TRANSLATED label:
`manifest_service._apply_label_overrides` substitutes the session-language string
into `opt["label"]` before `render_field_guidance` reads it, and word count is not
translation-invariant. Measured across all 18 baked languages, that flipped BOTH
calibration fields on shipped kits -- i-90 `p7_checkbox7` fell under the threshold
in Chinese and Korean (re-introducing the exact substance drop 575i exists to fix)
and w7 `previously_received_itin_or_irsn` rose over it in 8 languages
(re-introducing the bd 41fi recital). So the change was, in two languages, a
regression of its own bead. Verified independently before acting.

Fixed by reverse-mapping the override (it is keyed BY the English label, so no
signature change was needed) and measuring English. Pinned by a test parametrized
over EVERY language each kit bakes -- not a sample, since the two failures hit
disjoint language sets and any fixed sample would have missed one. Two smaller
findings from the same review: `label.split()` crashed the render on a non-string
option label (a regression against `origin/dev`, which measured no lengths), now
coerced and pinned; and the new `SPOKEN_LANGUAGE_BCP47` docstring claimed a guard
in `languages.test.ts` that did not exist, so the guard was written rather than the
claim deleted.

**Second outer-review round -- three more, including a vacuous test of my own.**
The re-review confirmed the three fixes above held (it re-ran the sweep over 15
fields x 17 languages against the real override-build path, and found the reverse
map has 17 real collisions in i-90 but none that can cross the threshold). It then
found three new ones:

- The `[None]` parametrization of the non-string-label test was **vacuous** --
  `opt_label or opt_value` collapses a falsy label to the value before the gate,
  so it passed with the coercion reverted. In the PR whose whole subject is a
  vacuous test. Replaced with genuinely non-coercible truthy shapes (`["x"]`,
  `{"a": 1}`), added an in-test guard asserting every parametrization is truthy
  and non-str, and split the falsy path into its own test.
- The new BCP-47 drift guard was **one-directional**: `languages.test.ts` compares
  the frontend map against a literal in the same frontend file, so both operands
  are frontend-local and a BACKEND value edit stayed green on both surfaces
  (mutation-verified: `sv-SE` -> `sv-XX` broke nothing). Since
  `language_codes.py` is the ASR-biasing map and gets edited for ASR reasons,
  that was the likelier direction. Added the backend end of the contract
  (`test_map_values_match_the_frontend_mirror`) and rewrote the docstring to say
  which suite guards which direction.
- `sessionLanguage` parsed the persisted blob a second time on the primary
  per-turn path, where the handler had already refreshed `this.state` from that
  same read. Split into `sessionLanguageFor(alreadyFresh)`; the three handlers
  that refresh at entry skip the redundant parse, and the default stays
  read-through so a non-refreshing caller is still correct.

**Third outer-review round -- two MORE vacuous cases, both mine.** Round 2's
fixes held (both directions of the BCP-47 guard bite; all five non-str
parametrizations fail). Round 3 then found the same failure mode twice more, in
tests I had written while explicitly hunting for it:

- The `''` (empty-string) case of the frontend whitespace test could not fail.
  `optionLabel` had TWO blank filters -- `v.trim()` at build time and a
  truthiness check at lookup -- so either alone caught it, and replacing the
  lookup with `key in lowered` broke nothing at all. Removed the redundancy
  rather than pinning both halves: the build-time filter is now the single
  guard (mirroring the backend's one filter), the lookup is a plain presence
  check, and all three blank cases now bite.
- `test_render_falls_back_to_value_for_a_falsy_label` did not pin the fallback
  its own docstring named. Its short-value assertion was satisfied by the
  separate `opt_strs.append(opt_value)` branch, so deleting `or opt_value` from
  the measured label left it green. Now asserts a LONG value with a falsy label,
  which only the fallback can route to the recital.

It also found a real robustness gap: the reverse-lookup map was first-wins, so
two English labels sharing one translation (i-90/Russian genuinely does this)
would make one measure the other's word count. Ambiguous entries are now dropped,
so the lookup misses and measures the translated text -- the pre-fix behavior for
that one label, never a wrong attribution. My first attempt at THAT test also
passed for the wrong reason: it depended on dict insertion order, and with the
short label inserted first, first-wins happened to pick correctly. Both orders
are now asserted.

Plus documentation corrections this review caught: a stale `spoken_labels`
reference (renamed `measured_labels`), an understated new-test count, and
the claim that 20 is the "midpoint" of the 17-to-27 gap (it is not; the wording
now says what it actually is and why it leans low). The close reason on bd
polyglot-pdf-semp described the pre-round-2 test, so it carries a correcting
comment.

**Deferred:** `SchemaForm.previewEdit.test.tsx` fails in full-suite runs but passes
in isolation. Verified pre-existing and not caused by this branch (reproduced on
clean dev with the branch stashed: 1198 passed / 1 failed). The failing count
varies between runs (1 vs 4 of the same file), pointing at ordering/timing. Filed
as **bd polyglot-pdf-6j0m**; not investigated further as it gates nothing here.

## Lessons

**A test that passes is not a test that works.** Every new test in this change was
mutation-verified individually, and that caught a real problem in my own work: the
pjws pins looked fine and were quietly redundant. The per-handler state refresh and
the read-through accessor BOTH fix the primary hint path, so removing either one
alone left the end-to-end test green -- only removing both turned it red. Each
mechanism is now pinned on its own (the accessor via a direct assertion and the
second hint producer; the handler refresh via a confirmed-elsewhere field that must
not be re-offered). The clobber test had the same flaw in a different shape: it
initially persisted the fill without putting it in memory, so the handler bailed at
the no-usable-value loop-breaker and never reached the `save()` the test was about
-- it passed for the wrong reason until the setup was reordered to the real
sequence (fill, then switch, then confirm).

That is the same failure mode as bd 35z0 itself, arrived at from the opposite
direction: 35z0's assertion was vacuous because the data went empty underneath it;
mine were vacuous because a redundant code path held them up. **Redundancy is a
virtue in the product and a defect in the pins.** Worth doing on any change where
two mechanisms both plausibly satisfy the same assertion.

**Redundant guards cannot be tested -- so remove the redundancy, do not pin
both halves.** This PR shipped THREE vacuous cases across three review rounds,
and every one had the same shape: two mechanisms both satisfied the assertion, so
reverting either left the test green. The pjws pins (a handler refresh AND a
read-through accessor), the frontend blank filter (`v.trim()` at build AND a
truthiness check at lookup), and the falsy-label fallback (`or opt_value` AND the
separate `opt_strs` branch). I caught the first myself, then wrote the next two
while explicitly watching for it -- which says the instinct to add a belt-and-
braces guard is stronger than the instinct to check whether the braces are
reachable.

The durable fix differs by case. Where BOTH mechanisms are genuinely wanted (the
pjws pair covers different callers), pin each separately and say why in the test.
Where one is redundant (the blank filter), DELETE it -- a guard that cannot fail
a test is not defense in depth, it is an untestable branch that will be
"simplified" later by someone who cannot tell which half mattered. Preferring the
second reading more often would have avoided two of the three.

**Watch for tests that pass by insertion order.** My first collision test built
an override dict with the short label first, so a first-wins reverse map happened
to pick the RIGHT label and the mutation stayed green -- correct outcome, wrong
reason, and dependent on nothing but dict ordering. When a test's subject is
"which of two colliding entries wins", assert BOTH orders; ordering is exactly
the variable under test.

**Mutation-verify per PARAMETRIZATION, not per test.** I mutation-verified the
non-string-label test and watched it go red -- but only three of its four cases
actually failed, and I read the red as "the test bites" and moved on. The
`[None]` case passed because a falsy label is collapsed to the value upstream and
never reaches the gate at all. A parametrized test is N tests; a mutation that
kills SOME of them says nothing about the rest. Shipping a vacuous case into the
PR whose entire subject is a vacuous test is the sharpest possible reminder that
"the suite went red" is the wrong granularity to check at. The guard I added
(asserting each parametrization is truthy and non-str) encodes the precondition so
the next person cannot add a silently-collapsed case.

**A mirror needs a guard at BOTH ends, or it guards nothing in the likely
direction.** The BCP-47 map guard I wrote compared the frontend map against a
literal in the frontend test file -- both operands frontend-local, so it could
only catch an edit to the side it lived on. The realistic drift was a backend edit
(that file exists for ASR biasing and is maintained for ASR reasons), which stayed
green everywhere. When two files must agree, ask which one is more likely to
change, and make sure THAT edit is what fails a test. Both ends now hold a literal
copy of the contract.

**A threshold calibrated on one representation must be APPLIED to that
representation.** The 20-word cutoff was measured on English labels and then
applied to whatever string happened to be in `opt["label"]` at render time --
which, in a translated session, is not English. The gate was meant to describe the
FIELD (are these labels too long to fold into one question?) but silently became a
property of the SESSION. The tell was available and I did not look for it: the
render takes an `option_label_overrides` parameter, so "what is in this string by
the time I measure it?" was answerable from the signature. Any comparison against
a tuned constant should state which representation it assumes and enforce it,
because the calibration and the application can drift apart without either side
looking wrong.

Corollary for tests: when a value varies over a dimension (here, 18 languages),
parametrize over the WHOLE dimension rather than a sample. The two failures here
hit disjoint language sets -- Chinese/Korean vs 8 European/South-Asian languages --
so any plausible 2-3 language sample would have caught one and missed the other,
and a one-language spot check would have caught neither.

**Prefer a positive assertion under mutation to an absence assertion.** `assert not
any(bad)` is one data change away from vacuous. `assert this specific correct thing
is not flagged` keeps failing for the right reason. This is now the shape of the
35z0 replacement, and it is why the old test survived a kit fix that should have
invalidated it.

**Set a threshold from the corpus and record the measurement.** The 20-word cutoff
is only defensible because the shipped kits show a gap between 17 and 27, and the
17 is a case that must land on the permissive side. Both the constant's comment and
a dedicated test carry that reasoning, so a future nudge has to confront the w7
field rather than just moving a number.

## Doc freshness

- **Bumped `docs/standards/si-reduction.md`** -- the one doc whose `Tracks:` globs
  cover the changed files (`backend/config.py`, `backend/services/ai_context.py`).
  Updated the option-marker section for the new n==2 gating, the marker-not-count
  keying, the all-navigation carve-out, the mirrored frontend resolver, the
  bare-string option shape, and the read-through session language; stamped
  2026-08-04. The checker now reports it OK.
- **Reviewed and left:** roughly twenty other tier-2 docs the freshness checker
  flags as STALE (`terminology.md`, `testing.md`, `voice-and-vad.md`,
  `ws-protocol.md`, `technical_guide.md`, the `components/*` set, and others).
  They track files this branch did not change and were stale before it; per the
  closeout rule they are left alone and noted here.
- No CLAUDE.md changes.

## Files touched

- `backend/services/ai_context.py` -- `MULTI_SELECT_OPTION_TYPES` +
  `TWO_OPTION_MAX_LABEL_WORDS`; the n==2 branch gated on both; `measured_labels`
  collected undecorated so the length rule never measures the `(use value: v)`
  wrapper.
- `backend/config.py` -- PRESENTING OPTIONS two-option rule re-keyed to the
  guidance marker + the all-navigation carve-out; WORKFLOW step 1 and both
  initiating templates re-scoped to match.
- `backend/tests/unit/test_dti_si_voice_rules.py` -- 12 new test functions (substantive
  pair, threshold boundary + the w7 admit case, multi-select and its spellings,
  fld_3c, the two SI-prose pins); 3 existing contract tests updated.
- `frontend/src/navigation.ts` -- resolver mirrors the backend (key tolerance,
  whitespace-as-miss, bare-string + missing-label shapes).
- `frontend/src/shared/languages.ts` -- `SPOKEN_LANGUAGE_BCP47` +
  `kitTranslationKeys`, mirroring `backend/utils/language_codes.py`.
- `frontend/src/__tests__/navigation-hint.test.ts` -- 7 new it()/it.each() blocks (16 cases, up from 9) for the key
  forms, blank values, the unbaked-kit fallback, and the option shapes.
- `frontend/src/webFormConnection.ts` -- `sessionLanguage` read-through accessor
  wired into all four hint producers; state refresh in the hint and confirm
  handlers.
- `frontend/src/__tests__/hint-language-freshness.test.ts` -- new; 6 cases pinning
  each mechanism independently.
- `tests/test_check_line_binding.py` -- vacuous test replaced with the synthetic
  legend-row case; the sibling's stale cross-reference updated.
- `docs/standards/si-reduction.md` -- see Doc freshness above.
