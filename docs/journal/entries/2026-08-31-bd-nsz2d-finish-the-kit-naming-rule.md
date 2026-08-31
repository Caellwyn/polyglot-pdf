---
date: 2026-08-31
bead: polyglot-pdf-nsz2d
title: "fix(schema-editor): finish the kit-naming rule -- success strings named a kit by label alone"
tags: [schema-editor, ux, error-messages]
---

## Trigger

Bd `polyglot-pdf-kztlr` established a rule -- a kit must be named the way the
catalogue names it -- and applied it to every REFUSAL. Its own code comment
says why a label alone is not enough:

> nothing makes labels unique, so two kits can share one and a label-only
> refusal is ambiguous in exactly the way an id-only one was.

That reasoning was left unapplied to the SUCCESS and STATUS messages, which the
cross-surface reviewer filed as this bead. So the same PR that argued
label-only is ambiguous shipped ~15 label-only messages, in the same
components.

The sharpest instance is delete, where a refusal and its own success notice
disagreed:

| | |
|---|---|
| refusal (fixed by kztlr) | `"W-7" (form-7) has been published, ...` |
| success (label-only) | `"W-7" was deleted permanently.` |

With two kits labelled "W-7", the success banner cannot say which one was
permanently destroyed -- on the one irreversible action, and the one whose own
code comment already calls out that "did that just delete something?" must
never be ambiguous.

**Nothing enforces label uniqueness.** `set_editor_kit_label` validates
characters and length via `_safe_label`; there is no collision check, and
`RetireCandidate`'s docstring says two same-numbered kits legitimately coexist.
This is a real state, not a hypothetical one.

## What changed

18 sites now route through `kitName()`: 9 in RemoteCatalogue (delete success,
three lock notices, four status transitions, rename), 7 in FormCatalogue
(unpublished refusal, translate/complete notices, the deploy `confirm()`,
rename), and 2 in App.tsx.

The App.tsx pair are worth naming: they are `throw new Error(...)`, not
`setError(...)`, so the sink-based scan that found the rest missed them. They
are the frontend counterpart of the backend "Kit {name} has no schema yet" that
kztlr had already fixed -- the same sentence, on the same surface, reached a
different way.

Rename gets the id for a reason beyond uniqueness: afterwards the OLD label
appears nowhere on screen, so the id is the only handle back to the card.

## What deliberately stayed label-only

**The delete dialog heading.** It reads `Delete W-7 permanently?` twelve lines
above an input that makes the human TYPE the id to confirm. Both identities are
already in one small dialog; repeating the id in the heading would say the same
thing twice. The reasoning is now a comment there, so the next reader does not
"fix" it.

**The card hover tooltips.** `title={...}` on the card whose subtitle renders
the id three lines below. Same argument -- the identities are already adjacent.

Note `kitTitle()`, which the bead expected to use for the heading case, no
longer exists: it shipped unused in kztlr and was deleted during that review, so
the bead's third exit criterion was already met on arrival.

## The guard, and the exemption that defeated itself

Criterion 1 asked for the coverage scan to flag bare `${x.label}` too. Writing
it immediately found four sites the sink-based enumeration had missed -- the
card tooltips -- which is the guard doing its job on its author.

Those needed an exemption, and **the first exemption was defeatable in exactly
the way kztlr's deleted `text-gray-500` carve-out had been.** Keyed to the LINE
containing `title={`, it waved through any offender that merely shared a line
with a tooltip. I did not reason that out -- I wrote the version, then wrote the
evasion:

```
setNotice(`"${kit.label}" gone`); const t = <b title={`x`} />;
```

and watched it pass. The exemption now covers the OFFSET of the matched
expression inside a brace-tracked `title={...}` region, so an offender
elsewhere on the line is still flagged. Verified by re-running that same
evasion against the fixed guard.

The lesson generalizes past this file: **an exemption keyed on something
ADJACENT to what it means to excuse will eventually excuse something else.**
First it was a CSS class, now a line number; both times the fix was to key it to
the thing itself.

## Tests

- `RemoteCatalogue.test.tsx` gains the case criterion 2 asks for: two kits both
  labelled "W-7", delete one, assert the notice carries the deleted kit's id and
  NOT the survivor's. Reverting the banner reddens exactly that test.
- One existing lock-notice assertion was updated rather than deleted -- same
  behaviour, newer wording.
- The coverage guard's label half is mutation-verified in both directions:
  reverting a converted site flags it, and the tooltip exemption stays narrow
  under the evasion above.

## Review: the exemption was defeated a THIRD time, so the mechanism changed

I wrote above that keying the exemption to the LINE was the mistake and keying
it to the OFFSET was the fix. Review defeated the offset version too, with the
mirror of my own evasion -- an offender **after** the tooltip closes on the same
line:

```
const t = <b title={`x`} />; setNotice(`"${kit.label}" gone`);
```

The cause was structural, not a missed case. Walking one line at a time meant
re-deriving "am I inside a region?" at every line boundary, and my `regionEnd`
never stopped extending once a region opened. Each fix repaired one boundary and
opened the next.

So the mechanism changed rather than the patch. Tooltip spans are now computed
ONCE over the whole file: a span opens at `title={` and closes when its braces
balance, wherever that lands. There is no per-line state left to get wrong, and
membership is a plain interval test.

This is the shape CLAUDE.md scar #8 describes, met for the second time in two
beads: **when the same defect class survives your fix twice, the fix is wrong,
not incomplete.** Both earlier evasions are now kept as an explicit battery in
the test file, so a future simplification cannot quietly reopen one.

The remaining hole is stated rather than hidden: this is not a JSX parser, so a
`title={` inside a comment or string literal would open a phantom span. Narrower
than what it replaces, and the battery pins the shapes that matter.

Two smaller corrections from the same round: the guard's docstring claimed
components receiving a `kitLabel` prop "have no id to pair with it", which is
false for `DeleteKitDialog` (it receives both and stays label-only for its own
stated reason); and `RetireCandidatesDialog` renders label-and-id as separate
JSX elements -- kitName's rule spelled out in markup -- which now says so, since
otherwise it reads as an omission.

One genuine pre-existing gap was filed rather than folded in
(`polyglot-pdf-5ivqx`): the catalogue dropdown renders `{k.label}` as a JSX TEXT
node, a shape this guard's regex cannot see, so two same-labelled kits are
indistinguishable there. Unchanged on dev, and outside this bead.

## Round 2: I fixed the helper and left the caller broken

Two findings, and the first is the one worth remembering.

**The defect moved up one layer instead of dying.** `tooltipSpans` was now
correct, and the code calling it still used `line.search(...)` -- which returns
only the FIRST match on a line. So a line whose first label sat inside an
exempted tooltip was skipped entirely, and a second, genuinely bare label later
on that same line was never checked. That is the identical shape the whole-file
rewrite was meant to eliminate: an offender coexisting with a tooltip on one
line. I had repaired the helper and left its consumer single-match.

**And my battery could not see it.** This is the sharper half. The battery
tested `tooltipSpans` directly on synthetic strings, so reverting the caller
from `matchAll` back to `.search()` left every case GREEN -- the helper was
still right, and only the code around it had regressed. I ran that mutation
expecting red and got a pass.

So the guard's scan is now extracted as `scanForBareLabels(text)` and the
battery drives THAT. Re-running the same mutation reddens it. **A battery aimed
one layer below the bug proves nothing about the bug** -- and "the helper is
well tested" is exactly the sentence that hides it.

Second finding: an unbalanced `title={` -- a phantom from a comment or string
literal -- ran its span to EOF, silently exempting every offender downstream.
Maximum blast radius, zero signal. An unbalanced span is now DISCARDED, and the
docstring says so rather than describing the hole as narrow.

Both are pinned in the battery, which now holds every historical evasion: after
a tooltip closes, before one opens, two labels on one line, an unbalanced
phantom, and a legitimate multi-line tooltip that must stay exempt.

## What three rounds across two beads actually taught

Every round in both beads found a defect in a CHECK, never in the shipped
messages. The messages have been correct since each bead's first pass.

The recurring error has a single shape: **I keep verifying the piece I just
wrote instead of the behaviour I care about.** The guard tested variable names
instead of the naming rule; the exemption tested a line instead of a position;
the battery tested a helper instead of the scan. Each was locally reasonable
and each left the real question unasked -- and in every case a green run was
what made it feel finished.
