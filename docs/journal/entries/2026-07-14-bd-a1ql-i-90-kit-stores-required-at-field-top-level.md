---
date: 2026-07-14
bead: polyglot-pdf-a1ql
title: "I-90 kit stores 'required' at field top level; production reads validation.required (gate never enforced)"
tags: [hotfix, extractor, testing]
---

## Trigger

Three i-90 kit / g1b data-hygiene bugs surfaced by the full-form stress-test epic
(polyglot-pdf-00pt / n86b) and its fresh-eyes assess, bundled into one PR because
each is individually too small for its own review cycle:

- **a1ql** (P2): the i-90 kit stored `required` at each field's TOP level, but
  every consumer -- the frontend `isFieldRequired` / confirm gate, the Pydantic
  `ValidationRules`, and the other three shipped kits (f1040, w7, w7-2) -- reads
  `validation.required`. Net effect: every I-90 field was silently treated as NOT
  required, so an empty confirm on a genuinely required field passed the gate.
- **o0ow** (P3): the interpreter signature field `p6_line6a_signature` carried a
  phone validation (`{pattern ^\d{10}$, format_preset phone}` + a "10 digits"
  format_hint), copied from the adjacent interpreter phone fields during
  extraction. Harmless to the voice loop (signatures bypass voice fill) but any
  future validation of signature values would reject every real signature.
- **kpa1** (P2): the g1b answer key was stale against the current kit --
  `p1_line2_acctidentifier` was 13 digits under a `^[0-9]{12}$` kit, and
  `p2_checkbox2[5]` was marked NA citing a commuter-only `show_if` the kit no
  longer has.

## What shipped

**a1ql -- required-shape migration.** Migrated `form-kits/i-90/schema.json` from
the dead top-level `required` to the canonical `validation.required` (dropped 124
inert `required: false` keys). Marked the A-Number (`p1_line1_aliennumber`)
required -- the bead's named exemplar -- so the gate is actually enforced; a
required A-Number now rejects an empty confirm in production semantics
(`FormSchema.validate_field_value` returns `(False, "... is required")`, pinned by
a test that loads the real kit). Fixed the two backend raw-dict readers that read
the dead top-level key (`ai_context.py`, `manifest_service.py`) to read
`validation.required`. Added a `schema_lint` rule `required-top-level` (ERROR,
v2-gated, flags only a TRUTHY top-level `required`) so a new kit from the old
extractor path cannot drift back; the rule is wired into the editor's
Mark-complete publish gate. Only the A-Number was marked required deliberately:
deciding the full set of legally-mandatory I-90 fields is a product/legal call, so
it was **deferred to fast-follow bead polyglot-pdf-tg0s** rather than guessed.

**o0ow.** Removed the phone `validation` (-> `null`) and the phone `format_hint`
from `p6_line6a_signature`, matching the clean applicant signature field. The live
extractor (`scripts/authoring/extract_form.py`, via the Pydantic model) does not
reproduce the top-level-required or phone-on-signature shapes; the
`scripts/bakeoff/prior_extractor/` copy that did is a frozen bakeoff artifact read
by no runtime path, so no extractor change was needed -- the lint rule is the
guardrail.

**kpa1.** Fixed `p1_line2_acctidentifier` 13 -> 12 digits; set `p2_checkbox2[5]`
to the persona's documented lost-card reason
(`my_previous_card_has_been_lost_stolen_or_destroyed`, VISIBLE for a plain LPR
under the current `in [lawful_permanent_resident,
permanent_resident_in_commuter_status]` gate) and removed its stale NA_REASON.
Extended `validate_answer_key()` with a digit-preset pattern/length check that
calls the SAME production `normalize_value` the live update path uses (so it
cannot pass a value production would reject), scoped to the `a_number` /
`uscis_account` presets. A new test pins that a 13-digit `uscis_account` drift is
caught.

Deferred / filed this sprint: **tg0s** (mark the genuinely-mandatory I-90 fields
required), **8n2s** (the schema-editor's "Required" checkbox still writes the dead
top-level shape the new lint rule now rejects -- filed by the fresh-eyes review).

## Lessons

- **A kit field's `required` has one canonical home: `validation.required`.**
  Every runtime consumer reads it there; a top-level `required` is invisible to
  all of them. The i-90 kit was the lone holdout (from the old `prior_extractor`),
  which is exactly why its required-gate silently never fired. The new
  `required-top-level` lint ERROR makes this mechanically enforced.
- **A data-hygiene self-check that claims to "mirror production" must call the
  production code, not re-implement its normalization.** The first draft of the
  digit-preset check hand-rolled a wider punctuation strip than production's
  `_DIGIT_PUNCT_RE`, so it could have passed an odd value production would reject;
  the Opus outer review caught the overstated comment. Reusing `normalize_value`
  directly makes the mirror exact.

## Doc freshness

The doc-freshness checker flagged ~25 docs STALE, but all were already stale from
prior-session commits (dates 2026-07-12/13) to files this branch did not touch, or
this branch's touches (`ai_context.py`, `manifest_service.py`) do not change the
CURRENT-STATE prose in `si-reduction.md` / `terminology.md` / `jit-schema.md`
(none document the required-shape canon; only journal entries mention it). No
current-state doc needed a content update for this change; left as-is per the
doc-maintenance rule for docs tracking untouched files.

## Files touched

- `form-kits/i-90/schema.json` -- migrated required to validation.required (A-Number required); removed phone validation from p6_line6a_signature.
- `backend/services/ai_context.py` -- read validation.required, not top-level.
- `backend/services/manifest_service.py` -- read validation.required, not top-level.
- `backend/services/schema_lint.py` -- new required-top-level ERROR rule (v2, truthy-only).
- `backend/scripts/g1b_answer_key.py` -- 12-digit acct id; p2_checkbox2[5] lost-card reason; digit-preset pattern/length check via production normalize_value.
- `backend/tests/unit/test_ai_context.py` -- real-i90 required-field rejects-empty test.
- `backend/tests/unit/test_manifest_service.py` -- required read from validation, not top-level.
- `backend/tests/unit/test_dti.py` -- NESTED_FIELD fixture moved required into validation.
- `backend/tests/test_schema_lint.py` -- required-top-level rule tests (v1/v2/truthy/clean).
- `backend/tests/unit/test_g1b_answer_key_coherence.py` -- digit-preset drift test; inverted p2_checkbox2[5] reason test.
