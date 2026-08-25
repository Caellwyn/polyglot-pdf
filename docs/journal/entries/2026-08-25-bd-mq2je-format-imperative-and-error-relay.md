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

### The bucket was widened, then reverted

Round 2 of review argued `format` was too narrow: it is emitted only by
`_validate_date`, while `pattern` carries the message literally "Invalid format"
and fires on 24 shipped i-90 fields where only the punctuation is wrong. That
argument is half right, which made it convincing.

Round 3 found the other half. `pattern` cannot distinguish a SHAPE failure from
a CONTENT one -- all of these emit exactly `constraint="pattern"`,
`message="Invalid format"`:

| value | field | what is actually wrong |
|---|---|---|
| `"K1A 0B1"` | postal code | punctuation -- reshapeable |
| `"12345"` | 7-9 digit A-Number | too few digits -- NOT reshapeable |
| `"A"`, `"A---"` | A-Number | normalizes to empty -- no answer at all |
| `"notanemail"` | email | not an address -- NOT reshapeable |

Telling the model "do NOT ask the user" on the bottom three orders it to retry
a value it cannot fix. Worse, the validation-error path deliberately RESETS the
unknown-rejection loop breaker, on the reasoning that a validation error is "a
working path the model should keep retrying" -- which held only while the
recovery said "ask the user again". **The re-ask WAS the bound.** Removing it
for `pattern` re-opens the runaway bd `polyglot-pdf-b1gj` was filed for, which
was observed live at 338 retries to idle timeout.

So `pattern` is back in the re-ask bucket, with the reasoning recorded beside
the set so the same convincing half-argument does not win next time. `format` is
safe precisely because it comes from one place: a date that parsed as a real
date in the wrong LAYOUT, where a correct value provably exists.

## Scar tissue: a "derived from source" test that derived nothing

The partition test was supposed to extract the constraint list from
`field_validator.py` rather than trust a hand-written copy. It searched for
`constraint="..."` -- but `constraint` is the FOURTH POSITIONAL argument to
`ValidationError`, never a keyword. The regex matched zero occurrences, the
resulting empty set was trivially a subset of anything, and the test passed
while checking NOTHING.

It looked like the strongest test in the file. It was the weakest.

Caught by mutating the validator to emit a new constraint and watching the test
stay green. Now anchored on the real call shape, plus an explicit
`assert emitted` so an extraction that finds nothing fails loudly instead of
passing vacuously -- the same fail-loud polarity the earlier reviewer checked
for on the plain-meaning example checker.

The same test then failed a SECOND way. Fixed to anchor on the real call shape,
it matched 16 of 17 emission sites -- skipping exactly one, the
normalize-to-empty guard, because that site spells its first arguments
`field.get("id", "")` instead of `field_id`. A guard claiming to enumerate a
complete set while missing a member is the CLAUDE.md scar-#7 failure it existed
to prevent.

Now it walks the AST for every `ValidationError` call and reads the 4th
positional argument, which is immune to how the earlier arguments are written.
Verified by planting a novel constraint at the previously-missed site: the regex
version stayed green, the AST version reddens.

Two mutation attempts in this bead ALSO silently failed to apply (a `ValueError`
and an `AssertionError` inside the mutation script), each leaving a green suite
that looked like "the mutation survived". Both were caught by `grep -c` on the
mutated file afterward. **Confirm a mutation LANDED before reading its result** --
a no-op mutation and a surviving mutation are indistinguishable from the test
output alone.

### And `format` alone was wrong too

Round 4 found the reverted position was *also* unsound. The code (and my own
comment) claimed `format` was safe because "a rejection means the date PARSED as
a real date in the wrong LAYOUT, so a correct value provably exists". The first
clause is true; the second is false. `_validate_date` is a bare `strptime` in a
`try`, so every one of these emits `constraint="format"` identically:

| value | reshapeable? |
|---|---|
| `1980-10-26`, `26/10/1980` | YES -- a real date, wrong order |
| `banana`, `I do not remember`, `never` | NO -- not a date at all |
| `13/45/2020` | NO -- impossible date |
| `10/26` | NO -- the year is genuinely missing |

A user answering "I don't remember" on a date of birth would get a model ordered
never to ask them again, with no retry bound.

The real lesson across three rounds: **the constraint NAME cannot establish
reshapeability, for any constraint.** So the check now re-derives it from the
VALUE -- `_is_reshapeable_date` tries the other known layouts, and only a value
some layout accepts is treated as the right answer in the wrong shape. It reuses
`field_validator`'s own `_DATE_LAYOUTS`, so a layout added there is understood
here automatically rather than drifting.

That is the third framing of this fix, and the first that is actually true. Each
round I reasoned from the motivating example -- a real date in ISO order -- and
each round the population contained cases the example did not represent.

## Scar tissue: a guard that was complete but not fail-loud

Round 3 fixed the derived constraint-set guard from "matches nothing" to
"matches 16 of 17 sites". Round 4 found the remaining hole was not coverage but
POLARITY: a new `ValidationError` written with `constraint="x"` as a KEYWORD, or
via `**kwargs`, is still counted as a call site but yields no constraint -- so
the extracted set stays correct-looking, `missing` is empty, and the guard passes
green while the new constraint ships unclassified.

The `assert emitted` added in round 3 only fires when extraction finds NOTHING.
Now the guard asserts PER SITE: every `ValidationError` call must expose its
constraint as a literal, and one that does not fails by line number with an
explanation. Three rounds to get one checker honest.

### Round 5: the value check could order the model to INVENT a date

The value-derived check was right in principle and wrong in its trial set. It
tried EVERY layout in `_DATE_LAYOUTS` -- which is a RESOLUTION table (which
layout a field declares), not a completeness one, and also holds `%Y` and
`%m/%Y`. So on a MM/DD/YYYY field:

- `"1980"` parses as `%Y` -> judged reshapeable
- `"1/2020"` parses as `%m/%Y` -> judged reshapeable

There is no month or day to reorder. The model, told "do NOT ask the user",
has fabrication as its only compliant move -- a wrong date of birth on a legal
form, and a direct violation of the SI's own NEVER INVENT A VALUE rule. That is
worse than the pedantic re-ask this branch was written to remove, and worse than
the behavior on `dev`.

Fixed by trialling only layouts with the SAME COMPONENTS as the field declares,
compared on directive LETTERS (`{m, d, Y}`) so separators and order -- the very
things being reshaped -- do not count as differences. A same-components layout
added to `_DATE_LAYOUTS` is still picked up automatically; a fewer-components
one can never produce a false positive.

**Five rounds, four blocking defects, all in one small branch.** The pattern is
consistent: each fix was reasoned from the motivating example (a real date in
ISO order) and each round the population held a case the example did not
represent -- prose hints, content-deficient values, unparseable answers, partial
dates. The reviewer found every one by enumerating the real data. The lesson is
not "review more" but **enumerate the input population before writing the
predicate, not after**.

## Verification

- Full backend suite: 2615 passed, 2 skipped.
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
