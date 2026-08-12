---
date: 2026-08-05
bead: polyglot-pdf-oagt
tags: [legal-invariant, pdf-filling, liability, denylist, testing]
surfaces: [backend/routes/pdf_fill_routes.py, backend/services/certification_denylist.py]
---

# The tool must be unable to fill a preparer block

## Why this is structural and not a disclaimer

Our position is that we are not the preparer of any form: the client
self-prepares with a typing aid, and the reviewing firm takes professional
responsibility with the client present. The asserted version of that claim is a
sentence in a contract. The structural version -- **the software cannot fill the
preparer block** -- is a fact anyone can verify by inspecting the code or the
output.

USCIS I-90 Part 6 is the Interpreter's Certification and Part 7 the Preparer's
Declaration; both are signed under penalty of perjury. Form 1040 has an
equivalent "Paid Preparer Use Only" block. Writing into any of them would have
the software assert, inside a signed government filing, that a specific human
performed a professional act.

## Both of the bead's premises were false

The bead was written expecting a small defense-in-depth addition. Neither
assumption held, and both errors pointed the same way -- toward more exposure,
not less.

**"Parts 6/7 are set to ignore."** They are not. All 37 interpreter/preparer
fields on the shipped I-90 kit are live and writable today, as are F1040's three
paid-preparer fields plus its firm block. The two signature fields carry
`read_only`, but the filler has a deliberate read-only UNLOCK feature
(`test_pdf_fill_readonly_unlock.py`), so the flag is not protection.

**"A denylist would be defense in depth."** It is the only defense.
`/api/fill-pdf` builds its field map from `request.form_schema` -- the schema in
the REQUEST BODY -- and never loads the kit's stored `schema.json`
(`pdf_fill_routes.py:101-132`). The editor's `_ignored_fields` quarantine only
removes a field from the client's copy of the schema. A stale bundle, a buggy
build, or a hostile caller that sends the field anyway gets it written. So
marking Parts 6/7 as ignored would have produced the appearance of protection
with none of the substance.

That reframes the work: the schema convention is the ergonomic layer, and the
server-side refusal is the legal one.

## What shipped

`backend/services/certification_denylist.py` -- a pattern list checked against
BOTH the schema field id and the PDF field name (the client controls both, so
neither alone suffices). It lives in its own module so the patterns read as a
reviewable legal artifact rather than route logic.

Two independent guards on the write path:

1. **The dispatch loop** (`pdf_fill_routes.py`), by schema field id, placed
   before the schema lookup so a denylisted field is refused even when the
   client omits it from the schema it sent. Every write branch -- text, radio,
   checkbox, checkbox_group -- is downstream of this loop.
2. **`fill_widget`**, by the name on the REAL widget in the PDF, which no
   client-supplied schema can misrepresent. Plus the shared-field radio's direct
   xref surgery, which bypasses `fill_widget` entirely and needed its own check.

Matching is deliberately broad because the error costs are asymmetric: a false
positive leaves a preparer field empty, which is the correct outcome anyway
since a human completes that block by hand; a false negative fills a perjury
attestation.

The allowlist is **empty**, and that is measured rather than assumed: across all
three shipped kits the patterns catch 37 I-90 fields and 3 F1040 fields, and
zero W-7 fields (the W-7 has no preparer block at all). Its birth-certificate
and certified-translation mentions live in help text, which is never matched --
only ids and PDF field names are.

## Three problems the tests caught in my own work

Each was found by a test I wrote, before review -- worth recording because the
common factor is that the tests enumerate reality instead of trusting a list I
typed.

1. **A pattern bug.** `\bfirm[_-]?(name|ein)` does not match inside
   `fld_firm_name` -- `\b` finds no boundary between `fld_` and `firm`. Four
   F1040 preparer-firm fields were escaping. Caught because
   `test_f1040_paid_preparer_block_is_refused` enumerates the block from the
   shipped schema rather than checking the handful of ids I had in mind.

2. **A vacuous parametrized case.** I listed `p7_line1a_preparersfamilyname`,
   which does not exist in the schema (the real id is `p7_line1a_familyname`).
   Asserting a widget is EMPTY passes trivially when the field id is fictional,
   and it passed with BOTH guards disabled -- testing nothing at all.
   `test_each_target_is_a_real_writable_field` now bypasses the denylist and
   requires each target to actually fill, so a fictional id cannot hide again.

3. **An unpinned guard.** With both layers live, disabling either one left every
   test green: the survivor silently covered for it. Redundancy is right for a
   perjury attestation, but it hides regressions, and a refactor could have
   deleted the loop check with the suite staying green until the day
   `fill_widget` was also touched. `test_each_guard_layer_refuses_on_its_own`
   disables each layer in turn and requires the other to hold the line alone.

## Fresh-eyes round 1 (Opus): criterion 2 FAILED

The reviewer scored criterion 1 PASS and criterion 2 **FAIL**, and was right.

**The W-7's "Acceptance Agent's Use ONLY" block was completely unprotected** --
nine live fields including the agent's own PTIN and EIN. An IRS Acceptance Agent
signs the W-7 certifying they reviewed the applicant's ORIGINAL identity
documents: the same third-party professional attestation as a preparer's
declaration, on a deployed kit. The reviewer filled the whole block through the
real route. My denylist matched none of it.

Two of my own errors combined to hide it:

1. **The same `\b` bug, three times in one bead.** `r"\bptin"` never matches
   `agent_ptin` -- there is no word boundary between `_` and `p`. I had already
   found this exact bug in `firm`, fixed it, and written it up as a lesson in
   this very entry, then left its twin three lines away with a comment claiming
   it worked. It was the single pattern that would have caught the W-7 block.
   Deleting it left all 19 tests green. A third instance (`\bdelegate` vs
   `name_of_delegate`) surfaced while fixing the second.
2. **A test that pinned the gap as correct.** My false-positive guard asserted
   "nothing on the W-7 matches," which passed BECAUSE of the hole and would have
   blocked the fix. Now split: the agent block MUST match, and the applicant's
   own fields must NOT.

Other adopted findings:

- **`r"certif"` was too broad** -- it would refuse `birth_certificate_number`,
  `certificate_of_naturalization_number`, `marriage_certificate_date` on kits we
  have not authored yet. An applicant's own DOCUMENT is not a third party's ACT
  of certifying. Narrowed to `certification` / `certifies` / `certifying`.
- **The allowlist was structurally inoperative.** It was checked against
  `field_id` only, but two of the three guards call the predicate with
  `field_id=""` and a widget name -- so a carve-out would pass its own test and
  still be refused. Now checked on either identifier.
- **A fourth guard**: `apply_field_flag_changes` must not UNLOCK a certification
  widget. Clearing the read-only bit is itself a write that persists into the
  emitted PDF; several call sites run it before the value-write guard.
- **The shared-radio guard was unreachable in tests**, so deleting it left
  everything green. Now exercised by a synthetic v2 shared-radio kit, with the
  dispatch-loop layer suppressed so layer 3 actually runs.

**One test I wrote and then deleted.** The first unlock test drove the real route
and asserted the read-only bit survived -- and passed with the guard DELETED,
because every I-90 signature has `conditional_logic: null` and the unlock returns
early on its own. It was describing the status quo. Replaced with a direct test
of the guard's decision, plus an assertion that the ordinary applicant unlock
(bd 7a9.16) still works.

## Fresh-eyes round 2 (Opus): the DESIGN was wrong, not just the patterns

Round 1 fixed my patterns. Round 2 showed a flat pattern list cannot express
this invariant at all.

**`\bp6[_-]` is an I-90 fact wearing a global costume.** On the I-90, Part 6 IS
the Interpreter's Certification. On the N-400, Part 6 is "Information About Your
Employment and Schools" and Part 7 is "Time Outside the United States" -- the
applicant's own answers. Measured against the shipped predicate,
`p6_line1_employer_name`, `p6_school_name`, `p7_line1_country_visited`,
`are_you_self_employed` (the N-400 asks the applicant directly),
`declaration_of_intent_number`, `agent_orange_exposure` and `travel_agent_name`
were **all refused**. A client would have answered each aloud, confirmed it, seen
it on screen -- and watched it silently vanish from the printed form.

That is the failure mode the module's own docstring names as the one to avoid,
and I had built it in while writing that docstring.

The same flat list also MISSED `attorney`, `accredited_representative`, `notary`,
`civil_surgeon` and the G-28 block -- third-party attestations on kits that are
plausibly next.

**Fix: two tiers.** Tier 1 is global and holds professional ROLES that are never
the applicant on any form. Tier 2 is keyed on `kit_id` and holds form-specific
facts (`p6_`/`p7_` for the I-90; `firm`/`self_employed` for F1040;
`agent`/`delegate` for the W-7). `kit_id` is optional and threaded through all
four guards: omitting it applies the global tier only, so a caller that cannot
supply it still gets full role coverage, and an unknown kit is safe rather than
silently unprotected. Adding a kit now means reading that form -- the correct
amount of friction. Coverage on the shipped kits is unchanged: 37 / 7 / 9.

Also adopted:

- **9 of 16 patterns were pinned by nothing** -- each could be deleted with the
  whole suite green. Worst: `r"ptin\b"`, the pattern round 1 was fixed FOR, was
  STILL dead against every shipped kit (`agent_ptin` is caught by `agent[_-]`,
  `fld_preparer_ptin` by `preparer`). So the round-1 fix was never verified by
  the suite, and the same `\b` bug could recur unseen. Every global pattern now
  has a test only it can satisfy.
- **The fourth guard was completely unpinned.** Deleting it left all 27 tests
  green. My test asserted only what the predicate RETURNS -- never that
  `apply_field_flag_changes` consults it -- and the per-layer harness splits
  layers on `bool(field_id)`, which this guard does not distinguish. It now
  records the route's actual calls and identifies that guard by its distinctive
  argument shape (a field id PLUS a fully-qualified widget name). My first
  attempt at that fix ALSO passed with the guard deleted, because the dispatch
  loop satisfies "non-empty id + some widget name" too.
- **The measured counts were wrong in three places.** "37 I-90 + 3 F1040 + ZERO
  W-7" was true only while the acceptance-agent block was unprotected, and it
  survived the fix. A future reader would have concluded the W-7 has no
  third-party block and could have deleted the very patterns that closed round
  1's hole. Corrected to 37/7/9 and pinned by a test.
- **pdf-filling.md claimed "Two independent guards"** when there are four, and
  misattributed which test pins which.

## Deliberately not done

**bd `polyglot-pdf-sxyp` (P1, filed from round 1's finding 8).** The refusal is
server-side only, and nothing upstream knows about it: a client can still be
voice-walked through all 37 I-90 Part 6/7 fields and all 9 W-7 agent fields, see
them filled on screen, confirm each aloud, get a confirmation audit record --
then download a PDF where every one is blank, with no message. None is marked
required, so nothing stalls; the divergence is silent. Worse, the confirmation
trail then positively asserts something FALSE, and that trail is the liability
record. Filed rather than folded in because the fix contains a real product call
(skip the fields entirely vs. label them vs. surface a skipped-field manifest)
about what a client SEES on a legal form.

The bead's step 4 -- the editor flagging certification blocks at authoring time
-- is filed as `polyglot-pdf-zerz`. It is a different surface (schema-editor),
it carries a real severity decision (ERROR blocks publishing; the maintainer
overruled exactly that in bd `47r3` because it would have blocked firms with
proprietary forms), and the runtime guard does not depend on it. Neither exit
criterion requires it.

## Recovery + closeout (2026-08-12)

This work was written earlier and then ABANDONED on a never-pushed local
branch (`claude/certification-denylist`) with three beads tangled on it: bd
47r3 (already merged separately via PR #545), bd 89mt (a cost-measurement
spike whose bead is CLOSED and whose artifacts the maintainer declined to
ship), and this one. Only the five oagt files were cherry-picked onto a clean
branch off current dev; the 89mt artifacts are stranded on that local branch
and their inventory is recorded on bd 89mt in case they are ever wanted.

Re-verified against TODAY's dev rather than trusted from the branch (it was
27 commits behind): 85 denylist tests pass, the full both-roots suite is
green at 3122, and all FOUR is_certification_field enforcement sites in
pdf_fill_routes.py are INDEPENDENTLY mutation-verified -- disabling any one
alone reddens a distinct test. That per-site check matters here: one test
covering several guards would have let a deleted guard ship green, which is
exactly the failure this file's own round-2 note records.

BASE-DRIFT BUG CAUGHT AT REVIEW: the branch's `pdf-filling.md` edit was
written against the stale base, so cherry-picking it DELETED a still-accurate
~65-line revision-archive / guarded-delete section added by three PRs (w3zw,
xzw5, 6x1j) that merged after that base, and reverted the file's date stamp
backwards. Fixed by rebuilding the doc from dev's current copy and splicing
only the new certification section in. The general lesson: when recovering an
abandoned branch, a DOC edit is the dangerous part -- code conflicts announce
themselves, prose silently reverts whatever landed meanwhile.

SECOND BASE-DRIFT CASUALTY, caught by the outer review and fixed inline: this
diff adds 67 lines to pdf_fill_routes.py, which SHIFTED ten line citations in
`docs/technical_guide.md` -- the tier-2 map CLAUDE.md calls "the blast-radius
reference for reviews". They were accurate on dev and wrong here, which is a
wrong claim about the code in a current-state doc. Re-anchored all 22 cited
line numbers by DERIVING each from the current file (match dev's line CONTENT,
find where it now lives) rather than adding an offset by hand, then verified
every one lands on the expected code. The outer review's round 2 then caught
that content-matching is not enough for a RANGE END: `fill_widget`'s cited end
landed on the checkbox branch's `raise` instead of the function's last line,
excluding the very text-write path the sentence names -- the same two-`raise`
ambiguity I had hand-resolved for `fit_comb_value` one line above. Corrected
to :218-293 and re-verified with an indentation-based end-finder (all three
def-anchored ranges), not another content match. Section 5 also gained the
denylist bullet it was missing. The general lesson, now twice-demonstrated: recovering
an abandoned branch endangers DOCS in two distinct ways -- a stale prose edit
reverts what landed meanwhile, and new code silently invalidates line anchors
elsewhere. Neither shows up as a merge conflict.

Two follow-up beads were re-measured against the shipped cut and corrected
rather than inherited: bd dhds (unpinned unlock guard) is ALREADY RESOLVED
here -- the test now records the route's real calls, and the mutation proves
it; bd 6u6h is PARTIALLY STALE -- its `firm_name_line1` gap is real, but its
ptin examples now refuse and its `g28` leading- claim does not match the
shipped pattern. Both beads carry the measured correction.

## Lessons

- **A convention cannot carry a legal invariant.** `_ignored_fields` looked like
  protection and was authoring ergonomics. The test is always "what happens when
  the client does not cooperate?" -- and here the answer was "we write the
  field," because the backend never consults its own schema.
- **Redundant guards need per-layer tests.** Two guards are correct for a
  high-stakes invariant, but with both live, neither is pinned: disabling either
  leaves the suite green. Test each layer alone, or the redundancy silently
  becomes a single point of failure the day one is refactored.
- **A rule keyed on POSITION is a fact about one artifact, not a rule.** "Part 6
  is the interpreter's certification" is true of the I-90 and false of the
  N-400. Any pattern encoding a position (a part number, a page, an index) is
  scoped to the thing it describes, or it will misfire in both directions on the
  next thing. The tell: a pattern whose comment has to name a specific form to
  justify itself.
- **Every pattern in a list needs its own pinning test.** Nine of sixteen here
  could be deleted with the suite green, and one of those was already DEAD --
  matching nothing, while its comment claimed it was the critical one. Redundant
  coverage hides both dead rules and removals. Give each entry an input only it
  satisfies.
- **Enumerate reality, do not list it.** Every one of the three bugs above came
  from a hand-written list; every one was caught by a test that read the shipped
  schema instead. Where a rule must cover a whole block, derive the block.
