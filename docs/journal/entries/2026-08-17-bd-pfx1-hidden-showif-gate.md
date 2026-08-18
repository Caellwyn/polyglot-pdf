---
tags: [schema, lint, editor, legal-posture, gate, enumerate-the-set]
beads: [polyglot-pdf-pfx1]
surfaces: [backend/services, schema-editor, frontend/src/schema-forms, docs]
---

# Making a contradictory state unauthorable instead of policing it

`hidden: true` says never show this field. `show_if` says show it when a
condition matches. A field could carry both, and nothing stopped it.

## The failure direction is the bad one

`shouldShowField` resolves the contradiction like this:

```ts
if (!group) return !field.hidden;                    // no condition -> hidden wins
if (conditionHasUnknownOperator(group)) return !field.hidden;
return evaluateConditionGroup(group, fieldValues, fields);   // condition -> hidden IGNORED
```

The condition wins and `hidden` is silently discarded. Nobody decided that --
it falls out of the branch order. And it resolves toward *showing* a field the
author marked never-show, which on an immigration form can mean an
acceptance-agent-only field displayed to the applicant.

## Why a gate rather than a warning, and why the precedence was left alone

The maintainer considered both and chose the gate. The reasoning holds up: a
warning still lets the state reach a saved kit, and then every consumer has to
interpret it. bd `ubam` had already paid that bill -- seven call sites, each
interpreting the same ambiguity differently.

The tempting adjacent fix is to change the precedence so `hidden` wins. I
deliberately did not. `shouldShowField` is byte-identical to `dev` in this
diff, for two reasons:

1. Re-measuring (rather than trusting the bead's figure) found **0 of 361
   fields** across the three shipped kits set both. There is nothing to fix.
2. With nothing to fix, flipping the precedence is a pure risk: a silent
   behavior swap for any kit that ever *did* rely on the current reading.

So the reading is PINNED as documented contract and the state is made
unauthorable upstream. The precedence test exists to make a future flip a
deliberate, visible decision rather than a drift.

## The parity test caught me, which is the point

Adding the backend rule without a `RULE_LABELS` entry failed
`test_lint_rule_parity` on the first run. That test exists because two
implementations of "lint" once disagreed silently; it's satisfying to be
caught by a guard that a previous round built for exactly this.

Worth noting the shape: the backend owns the rule vocabulary and the editor
owns the human-facing labels, and the test is deliberately a BACKEND test so a
new rule fails where it was added, not later in someone else's suite.

## Testing the false-positive half, not just the detection

A gate that fires on a valid schema trains authors to ignore it -- which is
worse than no gate, because it also devalues every other finding in the panel.
So the lint tests parametrize six *legitimate* shapes and assert silence,
alongside the one that must fire.

Two of those six are the empty-condition cases (`show_if: {}` and
`show_if: null`). They matter beyond tidiness: the editor's gate treats `{}` as
absent, and if lint disagreed, the editor would lock the Hidden checkbox over
a condition lint says does not exist -- with nothing on screen to delete. The
two implementations have to agree on "absent", so both are pinned.

## Three ways I was wrong about my own work

The two review layers found four defects in this diff. None were in the gate;
all four were in what I WROTE ABOUT the gate.

**I "corrected" a right number into a wrong one, twice over.** I wrote that
bd `ubam` fixed SEVEN call sites, noticed its bead body enumerates 1-6,
concluded I had inflated the figure, and swept SIX instances across five files
to say six. The outer review reversed it: the live code carries **seven**
distinct `shouldShowField ALONE` sites, and two of them --
`resolveLivePin` and `suggestNavigationCandidates` -- never appear in the
bead's list at all, while the bead's own item 6 is marked DEAD CODE.

So the original number was right. The bead was the incomplete artifact, and I
laundered its undercount into a tier-2 doc while congratulating myself for
citing the authoritative source.

Three lessons, in increasing order of usefulness:

1. My stated rule ("cite the enumeration, not the story about it") was right
   in FORM and wrong in APPLICATION. The bead body *looked* like the
   enumeration because it was numbered; the journal *looked* like narrative.
   Numbering is not authority.
2. The actual authority was neither. It was the CODE -- seven functions each
   carrying a `bd polyglot-pdf-ubam` attribution comment, greppable in one
   command. I reached for two secondhand accounts and never asked the
   artifact they both describe.
3. Correcting a number is a change like any other and deserves the same
   evidence as a code change. I treated "fix the wrong figure" as janitorial,
   swept six files on the strength of one document, and shipped a regression
   into the doc I had just written to be authoritative.

All six reverted. The count is seven, verified by
`grep -rn "shouldShowField ALONE" frontend/src` (excluding tests) returning
seven distinct functions across three files.

**I attached a wrong reason to a right conclusion.** My comment claimed "every
`show_if` write in fieldGrouping is SECTION-level". Six are field-level; my
grep classified by nearby context and misread `updated.show_if` as a section
write. The conclusion (no bypass) survives, but for a reason I had not
established: five of six are precondition-guarded on the field already having
a condition, and the sixth takes both keys from the same source field.

A wrong reason under a right conclusion is worse than no reason, because the
next reader stops checking. The comment now states the load-bearing reason and
what would break it.

**My doc could have led someone to undo a closed P1.** I wrote that a kit
carrying both should be treated as "malformed rather than as an intentional
instruction to this function". True at the authoring gate. As guidance to the
RUNTIME it points the opposite way from bd `ubam`, which spent a P1
harmonizing six sites onto "a satisfied-condition field renders, is required,
and must stay voice-reachable". Someone tidying toward my sentence would
re-add the `field.hidden ||` short-circuit and reintroduce both bugs `ubam`
closed.

The distinction the doc now draws explicitly: **the gate stops the state being
CREATED; it does not license the runtime to start ignoring it.** Those are
different claims about different lifecycle stages, and collapsing them is the
whole failure mode.

## The precedence call, endorsed

I deliberately left `shouldShowField` byte-identical and asked both reviewers
to argue the other side. The outer review agreed with the call and gave a
stronger reason than mine: flipping to hidden-wins would not merely be a
silent behavior swap, it would directly contradict the six live `ubam` sites
and re-open a closed P1. The right defence-in-depth here was the documentation
fix, not a precedence change.

Worth keeping as a pattern: when a fix and an existing invariant seem to point
opposite ways, the reconciliation usually belongs in prose, not in code.

## Process notes

- Mutation-verified per branch rather than per file: flipping the precedence
  reddens the BOTH test; breaking the unknown-operator fallback reddens that
  test; removing the empty-condition guard reddens exactly the `show_if: {}`
  parametrization. Three independent probes, three distinct failures.
- Documented for two different readers deliberately. `schema_format.md` gets a
  pick-one table for the author writing a schema; `components/schema-forms.md`
  gets the "this reading is pinned but not to be relied on" note for whoever
  next reads `shouldShowField` and wonders why the contradiction resolves that
  way.
- The bead's collision guard earned its keep on the way in: my first pick
  (`y2l0p`, editor draft archive) was refused for a write-surface overlap with
  `bdedm`, which is live in `editor_kit_routes.py`. Picked a different surface
  instead of forcing it.
- Also wired a missing dependency found while scouting: `nvqr` (cap the
  validator at 2 runs) reads as READY but its run-2 gate needs the
  flagged/un-verified field state that `vznc` introduces and that does not
  exist yet. Verified by grep, then `bd dep add nvqr vznc` so the next picker
  is not lured into building against a producer that is not there.
