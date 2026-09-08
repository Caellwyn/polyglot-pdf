---
date: 2026-09-02
bead: polyglot-pdf-0s2wf
title: "fix(schema-editor): the four follow-ups the hide/filter and kit-naming work left behind"
tags: [testing, schema-editor, doctrine]
---

## Trigger

Four beads filed as follow-ups during bd `polyglot-pdf-n5fwd`/`tx8gi` (hide +
filter, PR #715) and bd `polyglot-pdf-kztlr`/`nsz2d` (kit naming). Each was too
small for its own review cycle; bundled into one PR.

- `0s2wf` -- another author hiding your open form discarded unsaved edits in
  silence.
- `5ivqx` -- the catalogue-switcher `<option>` named a kit by label alone.
- `ytd3m` -- the delete-race 404 named a kit by bare id.
- `th60w` -- the two mirrored name formatters disagreed on what whitespace is.

## What each was, and what it turned out to be

### 0s2wf -- the silence, not the loss

`n5fwd` gated the open kit's OWN hide click behind `confirmDiscardOnHide`. That
guard cannot reach the concurrent case: the unwind fires on the next catalogue
refetch, and by then the kit is already hidden on the server -- the answer to a
`confirm()` could not change anything, because the effect is only reconciling
the UI to a decision someone else already made. The work is already gone.

(An earlier draft of this reasoning said the unwind runs "from a background
refresh, outside any user gesture". The outer reviewer checked: there IS no
background refresh -- the only intervals are elapsed-second tickers, and every
`refresh()` sits in a handler for something this session did. The conclusion
held; the stated mechanism did not. That is the THIRD false-mechanism comment
on this branch, and the pattern is below.)

So the fixable part was never the loss -- it was the silence. `clearOpenKit`
now takes an optional reason; passing none is byte-for-byte the old behaviour,
which keeps every other close (folder change, delete, self-hide) quiet, because
those are all the user's own action and already gated where work is at stake.
Only the two catalogues' unwind effects pass `'hidden-by-other'`, and App
renders a dismissible amber banner beside the existing save-error one.

The message distinguishes "your unsaved changes were lost" from "nothing was
lost". Overclaiming is its own bug: a user told their work is gone will go
looking for it.

### 5ivqx -- and the guard that already named its own blind spot

`nsz2d`'s coverage guard matched `${kit.label}` template interpolation. Its
docstring explicitly listed the shape it could not see -- a bare JSX child
`<option>{k.label}</option>` -- and cited this bead. Closing it meant widening
the pattern to both shapes.

Widening immediately found two REAL hits, one per catalogue twin: the card
title. Those are legitimate (the card's own subtitle renders `{kit.id}` two
lines below), so they carry the marker -- which required teaching the marker a
JSX comment spelling, because in a JSX child position a bare `//` renders as
visible text on the card. Forcing a form that cannot be written there would
push an author toward the one thing the guard cannot see: rewording the message
to dodge the pattern.

### th60w -- the bead undercounted, and the fix is the class not the character

The bead reported ONE divergent character (U+FEFF) and recorded U+0085 as
agreeing. Scanning the entire code space on both runtimes found SIX, in both
directions -- and U+0085 diverges the OTHER way:

```
Python strips, JS does not:  U+001C U+001D U+001E U+001F U+0085
JS strips, Python does not:  U+FEFF
```

Only U+0085 and U+FEFF are reachable (`_safe_label` already rejects `ord < 32`).
Both sides now share one ENUMERATED class -- the union of what either language
would strip -- rather than each calling its own `\s`.

Enumerating fixes the CLASS. Patching the two known characters would have left
every future disagreement, and every runtime's Unicode-version drift, open with
no way to notice from inside either language.

## The lesson worth keeping: diagnose a surviving mutation, don't react to it

Two mutations survived across this branch, and BOTH were category (1) --
structurally impossible, not an unpinned hole. In each case my code comment had
asserted a mechanism that was not real -- as did a THIRD comment nobody could
mutate at all (the "background refresh", corrected above), which is the tell
that the habit is writing the explanation rather than testing it:

1. **`0s2wf`.** Moving the dirtiness capture below `clearSchema()` changed
   nothing, because `hasUnsavedChanges` is the render's closed-over value and
   `clearSchema()` only schedules a state update. My comment said "capture
   BEFORE clearSchema, reading it after would always report false." False.

2. **`5ivqx`.** A `(?<!\$)` lookbehind on the JSX arm was unreachable:
   alternation is first-match-wins, so at a `${k.label}` the template arm
   always claims the position. My comment said the lookbehind was "what keeps
   the two arms from double-matching." Also false.

The first was corrected in place; the second was DELETED, because unreachable
code defended by a false rationale teaches the next reader the wrong rule. In
both cases the negative case now pins the property directly instead of the
implementation detail that happens to deliver it.

This is the same defect the `check-defects-proximity-and-wrong-layer` memory
describes -- writing a claim about a mechanism instead of testing it -- and it
recurred three times in one branch despite being a known trap. The cheap tell: if a
comment explains WHY something is safe and you have not mutated that exact
thing, the explanation is a guess.

## A near-miss worth recording

My first `kitOptionName` returned the ID on a restatement, mirroring `kitName`.
That silently downgraded a kit labelled `I-90` in a folder called `i-90` to the
lowercase folder name -- and my first tests ASSERTED that output, written from
what the code did rather than what the dropdown should say. They would have
pinned the regression as correct.

An EXISTING strip test caught it. The two surfaces genuinely want different
answers: prose quotes an identifier (the id is honest there), a dropdown shows
a name (the human's spelling is the point).

## Verification

Every fix mutation-verified against the defect it claims to prevent, including
reintroducing the shipped bug in each case rather than a convenient synthetic.
Six mutations for `th60w` alone (each flattener reverted to its own `\s`, one
character dropped from one side's class, a literal BOM pasted where an escape
belongs).

Full CI scope: 4383 passed backend (both directories), 2190 schema-editor.

Three schema-editor tests failed on one full run and passed on the next, in
files this diff does not touch; they ran concurrently with the backend suite.
Recorded rather than dismissed -- `polyglot-pdf-mwv5m` already tracks the same
load-dependent shape.
