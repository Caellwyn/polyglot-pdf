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
