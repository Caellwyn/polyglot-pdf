---
date: 2026-08-31
bead: polyglot-pdf-gpaed
title: "fix(voice): fan copy_to out at the write chokepoint -- and the fix that would have trapped the session worse than the bug"
tags: [voice, schema-forms, testing, review]
---

## Trigger

Found by the cross-surface review of bd polyglot-pdf-g33y2, which had just made
auto-populate links easy to author in the schema editor. The links did nothing
on the product's primary path: the `copy_to` fan-out lived in exactly ONE caller
-- SchemaForm's React manual-edit handler -- so a value Gemini filled left its
copy targets blank. Zero `copy_to` references anywhere in `webFormConnection.ts`.

The compound risk was the reason it was P1. The editor now sets `read_only` on
every copy target, `read_only` makes a field permanently AI-unwritable, and
`isSectionValid` does not excuse read_only fields -- so a REQUIRED copy target
would dead-end a voice session. The four gold i-90 targets are non-required,
which is why it had never bitten; making links easy to author is what changes
that.

## What shipped

The fan-out moved INTO `SchemaFormStateManager.updateField` -- the single write
chokepoint, 8 call sites across SchemaForm, `shared/connection.ts` (x3) and
`webFormConnection.ts`. Voice, manual, preview and resume all get it, and a
one-path special case is deleted rather than duplicated.

A fanned target is stamped **confirmed unconditionally**, and that is the part
that took three review rounds to get right.

## Lessons

**The obvious fix location was blocked, and the blocker pointed at a better
design.** Claiming the bead collided with an in-progress P1 (`a08po`) on BOTH
files the direct fix would touch. Rather than wait, I looked for another way in
and found `updateField` -- unclaimed, already resolving the schema field for its
own normalization, and the single point every write passes through. The
collision produced a better change than the uncontested path would have.

**MY FIX WOULD HAVE TRAPPED THE SESSION WORSE THAN THE BUG.** The Opus
cross-surface review traced it against the real i-90 kits. The AI ingress passes
`confirmed: undefined`, so `finalConfirmed` lands FALSE; my fan-out inherited
that, leaving each target FILLED BUT UNCONFIRMED. `computeNextField`'s priority-1
pass returns the first such field in whole-form order -- on both i-90 kits that
is `p8_a_number` et al, `read_only`, at index 70-73 of 94. So the session would
jump to Part 8 right after the first confirm.

And it could not get out. `update_form_fields` is refused (read_only);
`skip_field` is refused too, because the fan-out had just given the field a value
-- **before the fix the target was empty and skip WAS available**. Only
`confirm_field` still worked, on a field the model was never able to ask about.
`isFormComplete` and `computeReadyWindows` also key on `confirmed`, so the form
could never read complete.

The fix is to confirm a fanned target unconditionally, which is honest rather
than a workaround: a copy target is not a question anyone can answer, and the
human DID answer the value -- on the source. The method records HOW (the
source's own, or `manual_edit` for a derived write).

**My tests could not see the voice path breaking, because they never used it.**
Every chokepoint test passed `confirmed: true` -- a state the voice path cannot
produce -- and my ingress tests asserted only `.value` and `isSectionValid`,
never `.confirmed` or navigation. That is why the trap survived two fresh-eyes
rounds AND my own mutation testing: **a test that constructs its own input can
pin a state the real caller never reaches.** I probed the actual path to confirm
the reviewer's claim before changing anything, rather than reasoning about it.

**Fresh-eyes caught both exit criteria unmet, and the second was the sharper
miss.** I had proven the value propagates; the criterion asked whether the
section GATE clears, which is what "dead-ends a voice session" actually means. I
tested the mechanism I built instead of the outcome the bead promised. Both now
have non-vacuity floors asserting the section is INVALID first.

**A CRLF anchor no-opped a mutation and printed a meaningless pass.** The
harness warns about this and it still got me: my first attempt to revert the
`confirmed` fix silently matched nothing, and both suites went green. Now I
`diff` the file to prove the mutation applied before reading any result.

**The doc-freshness checker found one drifted citation; checking its neighbours
found three.** My +21 lines pushed `schemaFormState.ts:1084` onto a blank line.
The other two citations in the same sentence had ALSO drifted (984 -> 1040,
1106 -> 1162) -- silently wrong rather than detectably wrong, since the checker
only fires on blank/EOF. Re-anchored all three to symbol names.

## Deliberately left

The now-redundant fan-out in `SchemaForm.tsx` stays: its file belongs to `a08po`,
in flight. It rewrites the same targets with the same values, pinned by an
idempotency test. The measured cost is a third `save()`/dispatch per manual edit
plus timestamp drift -- filed as `polyglot-pdf-fdfot`.

## Follow-ups filed

- `polyglot-pdf-fdfot` -- the redundant SchemaForm fan-out (once `a08po` clears).
- `polyglot-pdf-mzo7y` -- `skip_field` on a copy SOURCE leaves the target holding
  a stale value that reaches the printed PDF.
- `polyglot-pdf-eqoyw` -- `extractSectionFields` docstring claims
  `computeNextField` skips locked fields; `navigation.ts` has no read_only
  handling. Pre-existing.
- `polyglot-pdf-73o17` -- `previewEdit` test flakes under full-suite load. Proven
  pre-existing by reproducing it on a pristine `origin/dev` worktree. Its NAME
  mentions copy_to, so it reads like a regression in this very work.

## Files touched

- `frontend/src/schema-forms/state/schemaFormState.ts` -- the fan-out
- two test files: the chokepoint, and the AI ingress + navigation
- `docs/components/schema-forms.md`, `docs/components/pdf-view.md` -- both had
  located the fan-out in the old place; pdf-view called it "the single place"
- `docs/standards/ws-protocol.md` -- three re-anchored citations
