---
date: 2026-08-03
beads: [polyglot-pdf-3t3l, polyglot-pdf-9kj4, polyglot-pdf-egy2]
tags: [voice, validator, dates, speech-config, cost, system-instruction]
surfaces: [backend/utils/field_validator.py, backend/services/validation_handler.py, backend/adapters/live_ai_gemini.py, backend/config.py]
---

# The error message was training the model: date layout, voice, and the pro validator

Three fixes from one tester session. The first two share a shape worth naming:
**a prompt symptom with a non-prompt cause.** In both cases the system
instruction already said exactly the right thing, had said it for weeks, and was
verified present in the deployed SI -- and the behaviour was still wrong.

## 1. The date layout (bd polyglot-pdf-3t3l)

**Symptom.** On a form whose printed label and schema hint both say `mm/dd/yyyy`,
the voice model kept asking users for `yyyy/mm/dd`.

**What was NOT wrong.** The obvious suspects were all innocent, and checking them
first was what made the real cause findable:

- The DTI system instruction already carried a `DATES:` block instructing the
  model to accept a naturally-spoken date and convert it ITSELF, including the
  line *"NEVER ask the user to restate a date in a format like 'year, month,
  day'; the format requirement is for YOU, not for them."*
- The per-field guidance already rendered `Format: MM/DD/YYYY`, sourced from
  `help.format_hint` via `manifest_service.build_guidance` -> `ai_context`.
- Both were verified present in the live SI at runtime (`USE_DTI=True`, 16,513
  chars), and the branch matched `origin/dev`, so both were deployed.
- A hardcoded `yyyy-MM-dd` at `config.py:784` looked like the smoking gun but
  sits in the LEGACY `SYSTEM_INSTRUCTION`, which production does not use.

**The actual cause -- two faults compounding.**

1. `field_validator._validate_date` resolved the expected layout ONLY from a flat
   `format` key, with a hardcoded `"YYYY-MM-DD"` fallback. No shipped kit sets
   flat `format` on a date field: i-90 and w7 both carry the layout in
   `help.format_hint` (the schema editor's "Format Hint" box), and i-90 also in
   `validation.hint`.
2. `validation_handler._convert_fields_to_dicts` did not forward `format`,
   `help`, or `validation.hint` into the validator dict at all -- so even a kit
   that DID set `format` could not have reached the validator.

**The feedback loop, which is the interesting part.** The model is *told*
`MM/DD/YYYY` by the guidance. It complies and writes `10/25/1984`. The validator
rejects it with *"Invalid format (expected YYYY-MM-DD)"*. The SI instructs the
model to retry on a validation error. So the model adapts to what the error text
demands and starts asking users for year-first dates. **The error message was
the training signal, and it outranked the instruction.** That is why two rounds
of prompt strengthening never held: the prompt was never the thing being obeyed.

Worth savouring: the W-7 field's own name is `"4 Date of birth (month / day /
year)"`. The form said month-first, the hint said month-first, the model said
month-first -- and the validator overruled all three.

**Knock-on defect, found in passing.** Every constraint check
(`date_constraint`, `min`, `max`) was nested inside
`if format_pattern == "YYYY-MM-DD"`. Since real kit fields never matched that
branch, those checks were unreachable in production -- **no date-sanity rule
could ever fire**, including `past_only` on a future date. That is a second,
independent reason the maintainer's future-date test produced no complaint.
Constraints now sit outside any format branch.

**Self-review catch.** The first cut of the prose-hint matcher iterated the
layout table longest-first, so among equal-length tokens the dict's own order
decided the winner rather than position in the sentence. A hint naming two
layouts (`"Use DD/MM/YYYY not MM/DD/YYYY"`) resolved to the one the author had
explicitly ruled OUT. No shipped kit has that shape -- all three real hint
strings across i-90/w7/f1040 name exactly one layout -- so it was latent, not
live. Now scored on `(earliest index, then longest token)`: position dominates,
length breaks ties so a bare `yyyy` cannot shadow `yyyy-mm-dd`.

## 2. The voice (bd polyglot-pdf-9kj4)

**Symptom.** Still rushing and slurring after TWO rounds of SI work -- bd
polyglot-pdf-rvac (PR #453) added PACE and character-by-character rules; PR #513
added ARTICULATION.

**Cause.** The adapter set `speech_config.language_code` and nothing else. No
`voice_config` had ever been set, so every session ran Google's documented
default voice, **Puck ("Upbeat")** -- the wrong register for a stressful legal
intake. (The maintainer had guessed Zephyr from the sound; nothing in the code
ever selected any voice.)

**Why prose could not win.** Google's Live API documentation describes no pace,
prosody, or style parameter for native audio, and offers no prompt-steering
guidance for delivery. Voice selection is the only documented lever. Two failed
prompt rewrites are consistent with that.

Set `LIVE_VOICE_NAME`, default `Iapetus` ("Clear"). Native-audio Live models
accept any of the 30 TTS prebuilt voices.

**Trap handled.** The `language_code` block *assigns* `config['speech_config']`.
A bare assignment in the voice block would silently drop the language code (or
vice versa, depending on order). The voice block MERGES, and tests pin both
orderings plus the empty-name fallback. Also note the SDK types `voice_name` as a
bare `Optional[str]` with no enum -- a typo is caught only at the endpoint (1007
at connect), never locally.

**Unverified by ear.** Whether Iapetus actually fixes the delivery needs a demo
deploy and a listen. If it still rushes, the next step is a voice A/B on the
deployed service, NOT more SI prose.

## 3. The pro validator, on by default (bd polyglot-pdf-egy2)

Maintainer cost decision, taken knowingly: the end-of-form whole-form
`gemini-2.5-pro` contradiction pass now defaults ON. Rationale in their words --
the per-form cost is a number they *want* in the accounting rather than an
unmeasured absence, and *"one or two cents on the i-90 is worth the 2nd
validation."*

Measured cost (W5, bd polyglot-pdf-g0w1, 42-call sweep on a 132-field i-90):
**~$0.0093/call**. Thinking is ~46% of per-call cost (427 tok median), BOUNDED to
512 -- the bound is load-bearing, since a prior incident showed a dynamic budget
running 10-50x the answer tokens.

**Accepted known limitation:** W5 measured whole-form precision **0.750**,
over-flagging the Part 5/6 preparer-interpreter certification block. W6 shipped
an anti-over-flag block in `WHOLE_FORM_PRO_SI` but **precision was never
re-measured** -- the original GO was explicitly conditional on that re-measure.
Tracked as bd polyglot-pdf-n0qk. Findings are report-only and the pass is
fail-open at every layer, so an over-flag surfaces a spurious question, never a
block.

**Stale-claim sweep, and why it mattered here.** The cost harness
(`measure_form_session_costs.py`) gated `--pro-pass` behind the rationale
"FORM_COMPLETE_PRO_VALIDATOR defaults OFF in production." That claim is now
false, and it bites precisely the goal the flag was flipped for: a default
harness run would have UNDERSTATED real per-form cost while being trusted as the
accounting number. Help text, comment, and
`docs/standards/validation-delegation.md` all corrected.

## Lessons

1. **When a model ignores a verified instruction, look for a competing signal in
   the runtime path.** Tool responses, validation errors, and retry directives
   are training signal too, and a concrete error message beats an abstract rule.
   Before rewriting a prompt a third time, check what the code is *telling* the
   model.
2. **Verify the instruction is actually reaching the model before rewriting it.**
   Two rounds of prompt work here were spent on text that was already correct and
   already deployed. One runtime assertion of SI content would have redirected
   the effort.
3. **A whitelist that copies "the constraints" will silently drop the one nobody
   thought of.** `_convert_fields_to_dicts` had a hand-maintained key list; the
   date layout was simply never added. `_resolve_constraint`'s own docstring
   already documents this exact class of bug from bd polyglot-pdf-0mv2 -- it
   recurred anyway, one field over.
4. **A default that no data satisfies is a trap, not a fallback.** Defaulting to
   ISO looked safe and made every real field take the wrong branch -- silently
   disabling three other checks along the way.
