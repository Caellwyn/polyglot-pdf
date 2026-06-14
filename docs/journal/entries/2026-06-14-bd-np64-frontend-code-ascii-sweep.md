---
date: 2026-06-14
beads: [polyglot-pdf-np64]
pr: TBD
tags: [conventions]
---

# np64: strip non-ASCII from frontend code comments + console/log strings

## Trigger

Follow-on from `uj57` (which cleaned `webFormConnection.ts` alone); fresh-eyes had
noted ~27 other `frontend/src` files still carried non-ASCII. The maintainer
clarified the real concern at the start of this work: **latent encoding errors** --
stray non-ASCII in machine-read code positions (comments, `console.*`/log strings)
that crashed on cp1252/Linux in past incidents -- NOT a directive to strip emoji
from the user-visible frontend.

## What shipped

Swept **188 non-ASCII occurrences across 15 files**, replacing them in code
comments and `console.*`/log string literals only:

- emoji -> ASCII tags (`[OK]`, `[mic]`, `[send]`, `[warn]`, `[chart]`,
  `[reconnect]`, `[timer]`, ...)
- operators/punctuation -> ASCII (`->` for arrows, `>=`/`<=`/`~=` for math,
  `-` for bullets, `x` for the multiplication sign)
- zero-width joiners / variation selectors dropped

**Deliberately left untouched** (intentional UTF-8 content the browser reads as
UTF-8 -- not a cp1252 crash risk, and stripping it would change behavior/UX):

- **~70 JSX-rendered UI emoji**: button labels (mic / pause / print / reconnect),
  status glyphs (`{isRecording ? red : white}`), dropdown arrows, modal icons,
  section-complete checkmarks -- across VoiceOverlay/VoiceOverlayMobile/SchemaForm/
  LanguageSelectionModal/VADTuningDashboard/VADControlPanel/field components.
  Replacing these would be a visible demo-UX change, out of scope.
- **~98 translation/content lines**: the 18-language disclaimer in
  `DisclaimerModal.tsx` (including required **U+200C ZERO WIDTH NON-JOINER** for
  correct Farsi/Arabic rendering -- removing it would break those scripts),
  `greetingPrompts.ts` multilingual greetings, `languages.ts` native-script names.

### How the scope was enforced

A line was treated as in-scope only if its stripped form starts with `//`, `*`, or
`/*` (a comment), OR it contains `console.`. Everything else carrying non-ASCII
(JSX text, computed display strings, translation data) was left. The classifier was
verified against the known JSX UI lines (e.g. `VoiceOverlay.tsx` button rows,
`VADTuningDashboard.tsx` `<h1>` + status indicators) BEFORE applying -- all
confirmed `in_scope=False`. Post-sweep verification: 0 remaining in-scope non-ASCII;
70 UI-render lines + 98 content lines preserved exactly.

The replacement used a codepoint-keyed map (no literal emoji in the helper source,
to avoid a shell/encoding round-trip mangling the keys -- the first dry-run attempt
hit exactly that and produced `?` sentinels). A `--dry-run`/`--apply` one-shot
helper drove it and was deleted after applying.

### Pre-PR assess (fresh-eyes)

Rubric (revised criterion): PASS. Fresh-eyes ran 2 rounds:

- Round 1: `GAPS-FOUND (1)` -- the classifier's `in_scope()` only matched lines
  that START with `//` (full-line comments) plus `console.` lines, so a
  `code; // comment with ->` TRAILING inline comment slipped through. Fresh-eyes
  found 2 (`schemaFormState.ts:21,24`); re-scanning for the same blind spot
  surfaced 2 more (`metrics.ts:21,22`). All 4 were `U+2192 ->` arrows; fixed.
  Re-verified zero non-ASCII in any comment (full OR trailing) or console string.
- Round 2: `NO-GAPS`.

Lesson reinforced: a positional classifier ("line starts with //") misses trailing
inline comments -- match the comment SUBSTRING, not the line prefix.

## Lessons

"Remove all non-ASCII" is the wrong frame for a frontend: a multilingual app
legitimately contains large amounts of intentional Unicode (translations, native
scripts, required joiners) and deliberate UI glyphs. The actual goal -- preventing
cp1252/Linux parse/print crashes -- is specifically about non-ASCII in **machine-read
code positions** (comments, log strings), so the fix must classify by position, not
blanket-strip. A blanket sweep here would have corrupted 18 languages and changed
the demo UI. (Scar #6 itself says markdown/content is exempt and the TS rule is a
*consistency* rule for source -- the spirit is code, not content.)

## Doc freshness

Bumped 5 docs that track files this branch touched -- `config-deployment.md`
(config.ts), `pdf-filling.md` (pdfFiller.ts), `schema-forms.md` (schemaFormState/
SchemaForm/FieldRenderer), `voice-ai.md` (connection.ts/audioManager.ts),
`terminology.md` (schemaFormState.ts) -- each with a note that this was a cosmetic
comment/console-string change, no behavior impact.

Left two flagged docs UNCHANGED because they track files this branch did NOT touch
(they were stale before this branch, from other merged backend work on dev):
`context-compression.md` (tracks `form_filling_service.py`, last touched by other
work) and `tool-call-flow.md` (tracks `request_coordinator.py`). Per the
doc-freshness rule, a doc stale on a file this branch didn't change is not this
PR's to bump.

## Files touched

15 files under `frontend/src` (VoiceOverlay.tsx, VoiceOverlayMobile.tsx,
fieldManager.ts, metrics.ts, connection.ts, audioManager.ts, navigation.ts,
VADTuningDashboard.tsx, security.ts, schemaFormState.ts, pdfFiller.ts, config.ts,
FieldRenderer.tsx, SchemaForm.tsx, useVADConfig.ts) -- comments + console/log
strings only.
