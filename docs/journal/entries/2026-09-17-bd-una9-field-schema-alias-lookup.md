---
date: 2026-09-17
bead: polyglot-pdf-una9
title: "Bug-hunt bundle: []-alias schema lookup, barge-in playback-end pin, translation-map lockstep"
tags: [refactor, testing, conventions]
---

## Trigger

An open-ended bug-hunt session: pick non-epic beads from the store, prefer
cross-surface ones, fix as many as possible autonomously. Three were fixed and
two more turned out to be already fixed on `dev` and were closed as stale.

The through-line was not planned, but all three fixes landed on the same shape:
**the bead reported ONE instance of a pattern, and the pattern had more
members.** In each case the reported instance was real and the fix was correct --
it just was not the whole set. That is CLAUDE.md scar #8 exactly, and it was the
most valuable part of the session.

## What shipped

**bd `polyglot-pdf-una9` -- the `[]`-alias SCHEMA lookup.** Gemini drops or adds
the trailing `[]` on a checkbox-group id inconsistently (bd `5k52`). The VALUE
side of that was already closed; the SCHEMA side was not. So
`handleConfirmFieldRequest` read the value through the alias and then resolved the
field bare -- finding the answer and losing the field. The consequence was not
cosmetic: `fieldSchema?.validation?.required` read off `undefined`, which
**silently defaults a REQUIRED field to OPTIONAL**, and the `''` carve-out
immediately below then accepts a blank as a usable value. A required checkbox
group could be confirmed empty. The re-prompt path also fell back to the raw
bracketed id, so the model would read "race bracket bracket" aloud.

Rather than patch the reported line, enumerated the set first. The same
three-line fallback had been hand-written **four** times (twice in
`webFormConnection`, twice in `schemaFormState`) and skipped in a fifth place --
which is precisely where the bug landed. Extracted one `findFieldWithAlias`
helper beside `readFieldEntryWithAlias` and routed every site through it.

The scan for the set then surfaced **two members the bead never mentioned**, both
iterating `section.fields` ids -- whose bracket form can differ from the
`field.id` they name, as an existing comment in `getFieldsForSection` already
warned:

- `isSectionValid` dropped a required checkbox group from its check entirely, so
  **a section could report VALID with that answer missing**;
- `getPreviousSpokenNames` dropped a field's spoken name and aliases from the
  already-answered list handed to the model.

Neither was in scope as written; both were the same bug.

**bd `polyglot-pdf-8np5` -- barge-in playback-end suppression.** The substance was
already fixed on `dev`, by the mechanism the bead itself recommended: the drain
swaps a NARROWED `onended` onto each source before `stop()`, because `onended` is
dispatched on a later task and no synchronously-cleared boolean can suppress it.
Two genuine residues remained. An **orphaned comment** still sat where the deleted
`isFlushing` flag used to be declared, describing a variable that no longer
exists -- the "future reader relies on a false claim" setup the bead is about. And
the suppression was pinned only for `resetPlaybackClock`, not for
`flushAudioQueue`, the barge-in path the bead actually names.

Also added the **positive control** both suppression tests were missing. Without
it, `expect(endSpy).not.toHaveBeenCalled()` is satisfied just as well by an
audioManager that never fires the event at all -- so the assertions would have
survived deleting the callback outright. Confirmed by mutation: removing the
callback reddens only the new positive control.

**bd `polyglot-pdf-cnwz` -- translation-map lockstep.** Reported as one
unanchored map (`DISCLAIMER_TRANSLATIONS`). Enumerating found **six** maps, of
which **four** were unanchored: OVERLAY, BUTTON, DISCLAIMER, RESUME. Only
CONNECTION_TIMEOUT and VERIFY_FIELD had a genuine `SPOKEN_LANGUAGES` anchor.

Replaced per-map patching with ONE guard (`shared/translationMapLockstep.test.ts`)
that asserts every map is keyed by exactly `SPOKEN_LANGUAGES`, plus a
no-blank-copy check (key parity alone still passes a present-but-empty entry).
Critically it also **proves its own list is complete** by scanning source for
`export const *_TRANSLATIONS` -- a hand-typed list would have reproduced this bug
at map number seven.

Also removed the trap itself: `DisclaimerModal.test.tsx` bound its map-derived
audit set to a local literally named `SPOKEN_LANGUAGES`, **shadowing the real
export**, so the file read as canonically anchored while being self-referential.
Renamed to `INTRO_SCRIPT_LANGUAGES`, which is what it actually is (it derives from
`introScript.json`, a third source again).

**Closed as already-fixed, no code change:** bd `polyglot-pdf-k8x5` (the
draft-kit publish gate landed via bd `fqexm`/`kkos` with 53 passing tests and a
fail-closed `isPubliclyServable`) and bd `polyglot-pdf-9oae` (the
`widget.text_maxlen = 0` line it describes does not exist anywhere in the
backend).

**Assess (Step 5.5.a) scorecard:** all criteria PASS across the three beads.

**Fresh-eyes + outer review:** recorded in the merge ping and the PR body.

## Lessons

**The enumeration rule paid for itself three times in one session, and the
payoff was NOT the reported bug.** In all three beads the reported instance was
correctly diagnosed; the value came from the mechanical scan finding members
nobody had noticed. `una9`'s two extra sites were a genuine correctness bug (a
section validating with a required answer missing) that no bead described.
`cnwz`'s enumeration found 4x the reported scope. The tell to enumerate is not
"the reviewer found another one" -- by then you have already paid for a round.
It is **"this finding is an instance of a pattern"**, which is knowable at the
moment you read the bead.

**Pin the SET mechanically, not the instance -- and make the pin scan source.**
Both new guards (`fieldAliasLookup.test.ts`, `translationMapLockstep.test.ts`)
read the source tree and assert an explicit allowlist, so the NEXT omission fails
CI instead of a review round. Both also carry a **staleness check** on their own
allowlist, because an allowlist entry that outlives the line it excuses silently
re-opens the hole it was documenting.

**A suppression test needs a positive control, or it is vacuous.** Two
`not.toHaveBeenCalled()` assertions had guarded the playback-end event for
several beads, and both would have passed against an audioManager that never
fired the event at all. The mutation that matters is not always the one that
reverts the fix -- here it was deleting the thing the fix was protecting.

**A shadowed constant is worse than a missing one.** `DisclaimerModal.test.tsx`
did not merely lack an anchor; it had a local named `SPOKEN_LANGUAGES` that made
the file LOOK anchored. Every reader (human or model) would have to open the
import list to notice. Naming a derived set for its SOURCE rather than its role
is the cheap fix.

**Stash-to-prove, then check whether the bead already exists.** A
`SchemaForm.previewEdit` failure looked like a regression from this diff; the
stash-to-prove cycle showed it pre-existing. It then turned out to have **nine
open beads** already filed against it by previous sessions, each of which had
paid the same diagnosis cost. Filed a tenth, then closed it as a duplicate and
consolidated the evidence onto `polyglot-pdf-x95xl`. The measurement worth
keeping: that file takes **16.4s against a 5s per-test timeout even on a fully
green base run**, so it sits permanently at the cliff edge and a green CI run on
it is luck rather than evidence. Adding 23 unrelated tests elsewhere was enough
to tip it. Recorded on `acn4d` too, since the `VoiceOverlay.voicemode` flake in
the same cluster looks like one shared root cause (jsdom overlay mounts under
suite load).

**`bd update --notes` is destructive and warns only AFTER the write.** Overwrote
another session's notes on `acn4d` this way. The prior content was not
recoverable -- the `.beads/issues.jsonl` git mirror lags far behind (it predated
the bead entirely) and Dolt history is not reachable via `bd dolt sql` in
embedded mode. Use `--append-notes` on any bead you did not write. Saved to
`bd remember` under `bd-update-notes-overwrites-use-append-notes`.

## Doc freshness

Doc-freshness flagged 9 docs tracking files this branch touched. Two carried
claims the change makes **incomplete**, and both were updated as current-state
prose:

- **`docs/components/schema-forms.md`** -- its `[]`-alias paragraph documented
  only the VALUE side. Added the SCHEMA side (`findFieldWithAlias`, the one
  legitimate exact-only site, the `section.fields` bracket-drift case) and the
  test that pins the set. Stamp bumped.
- **`docs/standards/voice-and-vad.md`** -- the barge-in section described the
  drain but never stated that a drain does NOT fire `vffOnAudioPlaybackEnd`, nor
  why a synchronous flag cannot deliver that. Added both. Its `*Last updated:*`
  line had also accreted into a **running changelog of three bead summaries**,
  which is the chronological-narrative shape `doc-architecture.md` section 3
  bans; normalized it to the per-file-entry form while editing the file.

The other 7 (`schema-key-visibility`, `section-reset-deprecation`,
`stateless-architecture`, `terminology`, `ws-protocol`, `websocket-routing`,
`technical_guide`) were **reviewed and left as-is**: they were flagged on file
mtime, and this diff changes no contract any of them documents (grepped each for
the affected symbols -- the only hit, `BUTTON_TRANSLATIONS` in `ws-protocol.md`,
describes the wire contract, which is unchanged). No stamp bumped on those, per
the rule that a stamp bump without a real prose review is itself a finding.

No CLAUDE.md changes.

## Files touched

- `frontend/src/schema-forms/utils/fieldValue.ts` -- added `findFieldWithAlias`.
- `frontend/src/webFormConnection.ts` -- 3 model-facing lookups routed through it; 1 hand-rolled copy collapsed.
- `frontend/src/schema-forms/state/schemaFormState.ts` -- 2 hand-rolled copies collapsed; 2 newly-found `section.fields` sites fixed.
- `frontend/src/schema-forms/utils/fieldAliasLookup.test.ts` -- NEW; behavior + the source-scanning set guard.
- `frontend/src/shared/audioManager.ts` -- removed the orphaned `isFlushing` comment.
- `frontend/src/shared/audioManager.interruptedFlush.test.ts` -- added the barge-in suppression test + the positive control.
- `frontend/src/shared/translationMapLockstep.test.ts` -- NEW; lockstep over all 6 maps + the completeness guard.
- `frontend/src/schema-forms/components/DisclaimerModal.test.tsx` -- de-shadowed `SPOKEN_LANGUAGES` -> `INTRO_SCRIPT_LANGUAGES`.
- `frontend/src/schema-forms/components/connectionTimeoutTranslations.test.ts` -- header corrected; the gap it disclaimed is now closed.
- `docs/components/schema-forms.md` -- alias SCHEMA-side prose + stamp.
- `docs/standards/voice-and-vad.md` -- playback-end suppression prose + stamp normalized.
