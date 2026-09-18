---
date: 2026-09-17
bead: polyglot-pdf-mwgim
title: "Closing the []-alias drift set: the two shapes my own guard could not see"
tags: [refactor, testing, review]
---

## Trigger

The three beads my own cross-surface review filed against PR #849 (the previous
bug-hunt bundle): `mwgim`, `db1en`, `l39al`. All three are defects in, or
adjacent to, work that PR shipped -- so this entry is really about why a guard
written specifically to enforce "enumerate the whole set" still left two members
of that set unguarded.

## What shipped

**bd `polyglot-pdf-mwgim` -- `resolveFieldForNavigation` was not alias-aware.**
It resolved a `switch_field` identifier exact-only, then fell through to fuzzy
`spoken_name` / `name` / `spoken_aliases` matching. When the model sends `race`
against a schema declaring `race[]`, that rescues it only if one of those names
happens to equal the raw identifier; when none does, `switch_field` is refused as
`unknown_field` for a field the form is visibly showing.

**bd `polyglot-pdf-db1en` -- `extractSectionFields` used an exact
`section.fields.includes(f.id)`.** A drifted entry dropped the field from the
legacy handshake's section schema, and let `getJITHandshakePayload`'s
no-unfilled-field fallback pick the wrong `sectionSchema.fields[0]`.

**A third site, which neither bead named, on the path that matters most.**
Enumerating the membership shape found `applyResume`'s `firstIncompleteSection`
reading `values[fieldId]` by the bare `section.fields` id. A bracket-drifted
checkbox group therefore read as UNANSWERED, its section counted as incomplete,
and a returning client was sent BACK to a section they had finished -- the
precise "saved at question 60, restarted at question 1" outcome that function's
own comment says it exists to prevent. This is the most user-visible of the
three and was not in anyone's bead.

**bd `polyglot-pdf-l39al` -- a wrong tier-2 doc claim, mine, from PR #849.** I
wrote "A drain -- either path -- does NOT fire `window.vffOnAudioPlaybackEnd`",
generalizing a correctly-scoped code comment ("a drained SOURCE is not a natural
playback end") into a claim about the manager as a whole. A synthesized
spell-back clip is not in the model's queue, so a drain does not stop it; when
its `release()` runs it finds both counts at zero and DOES fire. Scoped the
sentence and added a test asserting both halves, so the distinction is
executable rather than merely asserted.

Extracted `sectionDeclaresField` (collapsing `findSectionIdForField`'s
hand-rolled 3-form copy, the fourth instance) and added a second tree-wide scan
over the membership shape, with the same allowlist-plus-liveness discipline as
the lookup scan.

## Lessons

**A completeness guard is only as complete as the SHAPE it matches, and that
limit is invisible from inside.** PR #849 shipped a scan asserting "every
exact-only schema lookup on a model-supplied id is allowlisted", and it was
honest work -- it had already been widened once, tree-wide, after fresh-eyes
caught it resting on a hand-listed pair of files. It still missed two members of
its own set, for two different reasons:

- `resolveFieldForNavigation` named its argument `identifier`, not
  `field_id`/`fieldId`. A NAME-based pattern misses a rename.
- `extractSectionFields` asks the same question with `.includes(...)` instead of
  `.find(...)`. A SHAPE-based pattern misses a different shape.

The general form: a regex guard enumerates over a *convention* (a name, a call
shape), never over the *hazard* ("code that resolves a field id without handling
the bracket"). That gap is not a bug in the guard -- it is what a regex can
express -- but it means **"the set is complete" is always shorthand for "complete
within the convention I matched"**, and the honest move is to say which. I had
already written that caveat into the translation guard after fresh-eyes pushed
on it; I had not applied the same scepticism to the lookup guard, where it was
equally true. When a guard claims completeness, ask what a member would have to
look like to escape it -- and expect the answer to be "a rename or a different
call shape", because those are the two cheapest ways for code to differ.

**The corollary: the follow-up beads from a review are the highest-yield beads
in the store.** These three were filed by a reviewer that had just spent a full
pass building a model of this exact code. Two of them found defects the original
enumeration provably could not reach, and chasing them turned up a third
(`applyResume`) that no one had filed at all. Picking them up immediately, while
the context is still loaded, is cheaper than letting them age into the backlog
where the next session re-derives the whole picture.

**Doc prose that is accurate when written goes stale the moment the follow-up
lands.** PR #849 correctly documented `mwgim` as an open pre-existing gap. That
sentence became false in this branch, one commit after the fix. Current-state
docs need re-reading whenever the thing they describe as broken gets fixed --
the doc-freshness checker flags mtime drift, not truth drift, so nothing
mechanical catches this.

**A failing assertion sometimes means the TEST is wrong about the API.** My
first clip test asserted `isSpeaking()` was true with a clip audible; it is
deliberately MODEL-only (it subtracts `activeClipCount`), and the union
accessor is `isAnyAudioPlaying()`. Worth resisting the reflex to treat a red
assertion as a discovered bug -- read the accessor's contract first.

## Doc freshness

- **`docs/components/schema-forms.md`** -- two edits. Removed the now-false
  "`resolveFieldForNavigation` is NOT alias-aware" paragraph that PR #849 added
  (true when written, fixed here). Added the `section.fields` MEMBERSHIP rule as
  its own named hazard with `sectionDeclaresField`, listing every consumer that
  degrades silently on a wrong answer, and noting that the lookup scan
  structurally cannot see this shape.
- **`docs/standards/voice-and-vad.md`** -- scoped the drain suppression claim to
  drained SOURCES and stated the clip case explicitly (bd `l39al`).

Six other docs were flagged STALE because they track files this branch
touched (`schemaFormState.ts`, `audioManager.ts`):
`section-reset-deprecation`, `schema-key-visibility`, `stateless-architecture`,
`terminology`, `ws-protocol`, `voice-ai`. All **reviewed and left as-is** --
grepped each for every symbol this diff touches (`extractSectionFields`,
`resolveFieldForNavigation`, `sectionDeclaresField`, `findFieldWithAlias`,
`applyResume`, `firstIncompleteSection`, `vffOnAudioPlaybackEnd`) and none
mentions any of them. The one near-miss is `voice-ai.md:38`, which does
describe an end-of-turn event, but that is the BACKEND adapter's
`on_processing_done` callback, not the client's `vffOnAudioPlaybackEnd` --
different surface, unaffected. No stamp bumped on those six, per the rule that
a stamp bump without a real prose review is itself a finding.

Note the checker flags on file MTIME, not on truth, which is the same reason it
could not have caught the `mwgim` sentence going stale one commit after it was
written (see Lessons).

No CLAUDE.md changes.

## Files touched

- `frontend/src/schema-forms/utils/fieldValue.ts` -- added `sectionDeclaresField`.
- `frontend/src/schema-forms/state/schemaFormState.ts` -- `resolveFieldForNavigation` alias-aware; `extractSectionFields` membership-aware; `findSectionIdForField` collapsed onto the helper.
- `frontend/src/schema-forms/applyResume.ts` -- `firstIncompleteSection` reads through the alias.
- `frontend/src/schema-forms/applyResume.test.ts` -- regression test driving the real W-7 section list with one answer re-keyed to its bracket variant.
- `frontend/src/schema-forms/utils/fieldAliasLookup.test.ts` -- removed the stale `mwgim` KNOWN-GAP allowlist entry; added the membership-shape scan (comment lines skipped) + `sectionDeclaresField` behavior tests.
- `frontend/src/shared/audioManager.interruptedFlush.test.ts` -- clip-across-drain test; fake context grew `createMediaElementSource`.
- `docs/components/schema-forms.md`, `docs/standards/voice-and-vad.md` -- as above.
