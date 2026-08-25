---
date: 2026-08-25
bead: polyglot-pdf-gs5f0
title: "fix(voice-si): the model hedged on 'what does ITIN stand for' because nothing said definitional questions are different"
tags: [voice-ai, system-instruction, confirmation-and-audit]
---

## Trigger

Testing the live app, the maintainer asked what "ITIN" stands for while on the
W-7. The model refused and read from the form's "What is an ITIN" instructions
section instead of just expanding the acronym -- an expansion that is printed in
the form's own title.

Their read, which was right: "I'm not sure if this is a case of clinging too
lightly to 'only what's on the instructions' or if this is appropriate. But,
I'm sure the model does know what it means."

## Root cause

The DTI SI's `ANSWERING QUESTIONS` block had **no carve-out for definitional
questions**. It says to ground answers in the current field's Official reference
text, never invent legal or document requirements, route to `ask_secretary` when
the text does not clearly answer, and then:

> ALWAYS HEDGE AND DEFER on anything touching eligibility, requirements,
> documents, or what a rule means for THIS user

Expanding an acronym is none of those things. But nothing in the block said so,
so "what does ITIN stand for" had nowhere to land except the hedge path. The
model was following its instructions correctly; the instructions collapsed two
different question types into one.

## The distinction now encoded

- **Definitional / orientational** -- "what does ITIN stand for", "what is a
  surname", "what does exemption mean". One correct answer, no dependence on the
  user's situation, no legal consequence. **Answer plainly.**
- **Applicative** -- "am I eligible for an ITIN", "do I need one", "should I
  check box a". Depends on the user's facts, carries legal consequence.
  **Hedge and defer, unchanged.**

## Why the scoping is the load-bearing part

The hedge policy is not stylistic. It rests on a deployment invariant -- the app
produces a DRAFT, is never used for self-filing, and a qualified human reviews
the form before filing (`docs/standards/confirmation-and-audit.md`). "Confirm
with the firm or professional reviewing your form" points at a real person only
because of that. A carve-out written loosely -- "you may explain things" -- would
leak straight into the applicative side and defeat the policy.

So the carve-out carries its own boundary rather than relying on the reader to
infer one. It names the line (what the word MEANS vs what APPLIES to them),
names eligibility questions as still hedged even when the answer feels obvious,
and breaks ties toward hedging. It is placed **before** the hedge rule so the
hedge reads as the default and this as the narrow exception -- not as a later
override of it. (Ordering carries real weight in this SI: the spellback addendum
is load-bearing partly *because* it is last, per bd `polyglot-pdf-ku69b`.)

## Testing both halves, not just the new one

Three tests, and deliberately not one: the permission, the boundary, and their
coexistence. Pinning only the permission would let the boundary rot silently
under a future SI diet -- the redundant-guard trap (repo memory
`redundant-guards-need-per-layer-tests`).

Mutation-verified twice, and the second mutation is the one that matters:

1. Remove the carve-out entirely -> 3 tests red.
2. **Keep the permission, strip the boundary** (replace the scoping sentence
   with "Answer these helpfully.") -> the boundary test goes red specifically.

Mutation 2 is the realistic failure mode. A future editor trimming the SI for
tokens would plausibly keep the useful-sounding permission and drop the
qualifying sentence as verbose -- which is exactly the edit that would turn this
into a licence to interpret rules for applicants.

## An existing test caught a collision

The first draft used "what does alien registration number mean" as an example.
That reddened `test_jit_mode_schema_routes_to_dti_si_when_dti_off`, which
asserts a specific field's `spoken_name` is ABSENT from the DTI SI and uses that
absence to discriminate the DTI branch from the legacy one. My example phrase
contained that spoken name verbatim and destroyed the discriminator.

The test was right and the example was wrong, so the example moved to "what does
exemption mean". Worth recording as the general shape: **an SI example phrase is
not free text -- it shares a namespace with every string other tests assert the
SI does or does not contain.**

## Scar tissue: the example set pointed at the leak

The fresh-eyes review caught the carve-out listing "what does exemption mean" as
a SANCTIONED plain-meaning example. On the W-7, "exemption" and "exception 3"
are not ordinary words -- they are rule labels whose meaning IS the eligibility
condition. So the example held up rule-interpretation as the model of a safe
definitional question, aimed squarely at the leak the boundary exists to close.

The original boundary line ("what the word MEANS vs what APPLIES to them") did
not resolve it either, because the "word" in question is the name of a legal
condition. "What does exception 3 mean" is syntactically identical to "what does
ITIN stand for" while requiring a completely different answer.

Redrawn as ORDINARY WORD vs NAMED RULE, with a flat statement that a named rule
is never plain meaning however the question is phrased, and the hard cases named
explicitly. Ties break to "rule question".

The general shape, and the third time a variant of it appeared today: **an
example is not decoration -- it teaches the boundary more concretely than the
rule does.** A wrong example silently widens the rule it illustrates, and it
does so in the direction the reader is most likely to follow.

The review also found a surviving mutation: the boundary tests asserted only
that each clause was PRESENT in the SI, so relocating the tie-break to a
different paragraph passed. A tie-break floating elsewhere no longer says which
class of question it disambiguates. The tests now assert structural containment
INSIDE the carve-out sentence.

## Verification

- Full backend suite: 2551 passed, 2 skipped.
- FOUR mutations confirmed red, then restored: carve-out removed; boundary
  stripped while the permission survives; tie-break relocated out of the
  carve-out; named-rule guard dropped on its own.
- SI size impact is one sentence, which matters under the SI-reduction epic
  (`polyglot-pdf-jnjj`): a short added clause rather than a new block.

## Not addressed here

Whether the model actually COMPLIES with the new carve-out is unmeasured. This
bead changes what it is told, not what it does -- and this session has now seen
two separate cases (`polyglot-pdf-apkdl` spellback, `polyglot-pdf-mq2je` date
format) where clear SI text was ignored in favor of a competing signal. If the
ITIN question still hedges after this, the next step is measurement, not more
prompt strengthening.
