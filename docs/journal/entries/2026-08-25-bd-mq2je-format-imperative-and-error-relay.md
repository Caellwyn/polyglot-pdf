---
date: 2026-08-25
bead: polyglot-pdf-mq2je
title: "fix(voice-dates): a bare 'Format:' label lost to 'Type: date', and the rejection reason never reached the user"
tags: [voice-ai, system-instruction, dates, validation]
---

## Trigger

Live-testing the date fixes (bd `polyglot-pdf-mpfmr` + `polyglot-pdf-md20o`) on
the W-7, the maintainer said "October 26th, 1980" and got two distinct failures
in one turn:

1. The model called `update_form_fields` with `1980-10-26` -- ISO -- on a field
   declaring `MM/DD/YYYY`. Correctly rejected (`error_count: 1`).
2. The app told them "I'm sorry, there was an error." Their note: "(not
   helpful)".

## Gap 1: ignored on a COLD first attempt

The interesting part is what this is NOT. Two explanations were checked and
ruled out:

- **Not reading a coerced value back from the DOM** -- the field was empty.
- **Not adapting to a validation error** -- no error had occurred yet. That IS
  the mechanism behind bd `polyglot-pdf-3t3l`, but it cannot apply to a first
  attempt.

The guidance block was verified by rendering it directly. It carried the format
**three times**:

```
ID: date_of_birth | Spoken: date of birth | Type: date | Required: true |
Instructions: Give your date of birth as month, day, and year... |
Format: MM/DD/YYYY | Official reference text: Line 4. Enter your date of birth
in the month/day/year (MM/DD/YYYY) format...
```

Plus the DTI SI's DATES block separately says to convert the date itself. The
model ignored all of it.

**The hypothesis, and it is a hypothesis:** `Type: date` pulls toward ISO-8601 --
the convention models associate with a date type -- while `Format: MM/DD/YYYY`
is a bare LABEL stating a fact that nobody is told to act on. A fact next to a
strong convention loses.

`Type:` cannot simply be dropped: it is load-bearing for radio/select option
presentation (`test_dti_si_voice_rules` pins `Type: radio` / `Type: select`). So
the fix raises the format instead of lowering the type: `Store the value EXACTLY
in this format: MM/DD/YYYY`. An imperative competes on the same footing as a
convention; a label does not.

This is the same COMPETING-SIGNAL shape as the other two open voice beads
(`polyglot-pdf-apkdl` spellback, `polyglot-pdf-kt7c6` digits-vs-words). Three
instances in one session is a pattern worth naming.

## Gap 2: the reason was on the wire and got swallowed

The backend DID send a well-formed reason -- confirmed by reproducing the
payload:

```
4 Date of birth (month / day / year): '1980-10-26' | format=MM/DD/YYYY
DISCARD the rejected value(s) above -- ...
```

604 chars on the wire, naming the field, the rejected value, and the required
format. The model turned that into a generic apology.

**And the SI arguably told it to.** Two rules combined badly:

- TOOL PROTOCOL: "on a validation error, retry with a corrected value or ask the
  user to clarify" -- a bare apology satisfies this.
- LANGUAGE: "Never echo, quote or answer system text in English" -- and a
  validation error IS system text.

So suppressing the reason was defensible under the instructions as written.
That is why this needed more than adding "tell the user what went wrong": the
new rule has to resolve the contradiction explicitly, and it does -- put the
reason in the model's OWN words in the session language, never quoting the
English. A test pins that coexistence specifically, so a future edit cannot
resolve it in the wrong direction.

The rule also closes the loop the maintainer actually cares about: on a FORMAT
error, fix it yourself and retry rather than asking the user to re-say the same
answer differently. They already gave the answer; the shape is ours. Re-asking
is reserved for when a genuinely different ANSWER is needed.

## Scar tissue: the imperative was applied too widely

Fresh-eyes review caught the first cut applying the imperative to EVERY
format_hint. Most shipped hints are not shapes -- they are descriptions or
examples. Enumerated from the kits:

| hint | kind |
|---|---|
| `MM/DD/YYYY` | layout literal |
| `5 digits`, `Alphanumeric postal code` | prose description |
| `Phone Number`, `*@*.*` | prose / pattern gloss |
| `e.g. parent, child, grandchild` | EXAMPLE LIST |
| `MM/DD/YYYY or "Never Entered US"` | two alternatives, not one shape |

"Store the value EXACTLY in this format: e.g. parent, child, grandchild" is
incoherent, and worse than incoherent -- it invites the model to treat an
example list as a literal template. Of 20 distinct shipped hints, exactly ONE
is a layout literal.

Now scoped with the same layout-literal test the frontend's maxLength guard
uses (bd `polyglot-pdf-md20o`): a hint made only of placeholder characters and
separators gets the imperative; everything else keeps the descriptive `Format:`
label, which is the right register for a description.

**This is the third time in one day that a fix was written to the shape of ONE
case and then fired on the whole population.** The maxLength guard fired on 26
fields to fix 2; the plain-meaning carve-out picked colliding examples twice.
The common cause each time: reasoning from the motivating example instead of
enumerating the real data first. The enumeration takes about a minute --
`format_hint` values across three kits is one script -- and would have caught
all three before review did.

## Gap 3: the tool response was fighting the SI, in the same turn

The cross-surface review found the real reason gap 1's SI rule might not have
taken. The `update_form_fields` error response ends with:

> DISCARD the rejected value(s) above ... **Ask the user again for the current
> field and fill exactly what THEY say.**

Unconditional, on every rejection including a pure FORMAT failure. That is the
pedantic re-ask the DATES block already forbids -- and it is read in the SAME
TURN as the error, while the SI rule sits thousands of characters upstream.
Recency favours the wrong behavior. Adding an SI sentence while leaving this in
place would have been the fourth round of prompt-strengthening against a signal
the prompt was never beating.

The recovery instruction now branches on constraint type: a format-only
rejection says "re-send the SAME answer corrected to the required format -- do
NOT ask the user to say it again in a different format"; anything else keeps the
re-ask, because an out-of-options value genuinely needs a DIFFERENT answer, not
a reshaped one. Mixed errors fall back to the re-ask, since reshaping cannot fix
an invalid option.

**The anti-leak half is untouched and still unconditional.** That is bd
`polyglot-pdf-djnk`'s guarantee -- a rejected value silently became the fill for
the NEXT field -- and a test now asserts it holds across every branch, so
narrowing the recovery cannot erode it.

This is the pattern the whole session keeps hitting: the SI is rarely the thing
being disobeyed. Look for the competing signal in the runtime path first (repo
memory `error-messages-are-training-signal`).

## Verification

- Full backend suite: 2590 passed, 2 skipped.
- Mutation-verified: reverting the imperative reddens 1 test; removing the
  relay rule reddens 3; removing the prose/literal scoping reddens 7; disabling the format
  carve-out in the tool response reddens 1.
- **A mutation that silently no-op'd nearly passed as evidence.** The first
  attempt at the relay-rule mutation used string slicing that raised
  `ValueError: substring not found`, the edit never applied, and the suite came
  back green -- which looks identical to "the mutation survived". Caught by
  `grep -c` returning 0 afterward. Confirm a mutation LANDED before reading its
  result (repo memory `new-tests-must-be-mutation-verified`).

## What this does NOT establish

It changes what the model is TOLD, not what it does. The bead's exit criteria
demand a measured first-attempt compliance rate (n>=20 per arm, scored on the
STORED VALUE) and one live turn confirming the relay. **Neither was run** -- this
landed on demo eve, and the measurement needs the voice harness plus ~40 live
turns.

Split into `polyglot-pdf-ebkl4` rather than closed on the wording alone. The
prior for "we reworded the SI, therefore behavior changed" is bad here: two
earlier rounds of prompt-strengthening on this exact date format failed, because
the prompt was never what was being obeyed.

Note for whoever measures: score the STORED VALUE, not tool success. The
maintainer's session had a SUCCESSFUL second write that stored the WRONG format,
so a naive success metric scores that turn as a pass.
