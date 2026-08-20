---
date: 2026-08-20
bead: polyglot-pdf-nsb4y
title: "legal(disclaimer): ONE SOURCE -- the written and spoken disclaimers are the same text"
sprint: 20
tags: [conventions, testing, doctrine]
---

## Trigger

Filed during sprint 20 as a P1 bug: `intro_script.json` and `intro_tts.py`
both assert a HARD INVARIANT ("the modal renders exactly these paragraphs --
one source, no separate fullText") that the shipped frontend did not hold.

## The actual defect

Two legal REGISTERS behind ONE Agree button:

- **Written** (`DisclaimerModal`'s own `p2`): "We **strongly advise** you to
  have a qualified professional check your final form." -- ADVICE.
- **Spoken** (`intro_script.json` para 7): "you **agree to review** the
  completed document yourself and with a certified professional before
  filing." -- an UNDERTAKING.

Which posture the applicant accepted depended on whether they listened or
read. And `script_version` (bd `s1iex.7`) hashes the SPOKEN script, so the
audit record I had just shipped named text a modal reader never saw -- a flaw
in the evidence chain, not merely a copy inconsistency.

**Maintainer decision 2026-08-19: ONE SOURCE.** The modal shows the spoken
script. This strengthens the obligation on the applicant in 18 languages, so
it was a product-owner call, not an implementation detail -- escalated with
the three options and their tradeoffs rather than decided.

## What shipped

- **The fix is one condition.** The one-source path already existed (bd
  `s1iex.5`): the modal accepts `introParagraphs` and renders them. Both
  overlays just gated it on `introEnabled` -- tying the WRITTEN legal text to
  whether AUDIO plays. Removing that gate is the core change.
- **The spoken LEGACY path needed it too.** All four `readDisclaimer` sites
  passed `DISCLAIMER_TRANSLATIONS.fullText`, which carries the advisory
  wording. Fixing only the modal would have kept two registers and merely
  relocated them (reader now strong, listener still weak).
- `DISCLAIMER_TRANSLATIONS` survives only as the modal TITLE source and an
  unused fallback; a SET test pins that no app code consumes its body.
- Docs corrected: the register table (Advised -> RETIRED, Undertaken -> LIVE),
  the "what ships today" paragraph, the SI policy comment in `config.py`, and
  `config-deployment.md`'s flag description.

## Lessons

- **A guard test told me to stop, and it was right.** An existing test
  asserted the disclaimer must NOT say "agree to review", naming THIS bead as
  what had to be settled first and pointing at the standards doc. That is
  exactly what a guard on user-facing legal copy should do: refuse to let an
  agent change legal posture on its own judgment. I escalated instead of
  editing it, and INVERTED it once the maintainer decided -- deleting it would
  have thrown away the protection for the next change.
- **My first replacement tests were VACUOUS, and I proved it rather than
  assuming.** They rendered `DisclaimerModal` with `introParagraphs` passed
  explicitly -- which bypasses the overlay gate that WAS the bug. Restoring
  the bug left 112 tests green. Rewritten at the OVERLAY level, driving the
  real component with no prop; both mutations then failed, on desktop AND
  mobile. The tell: a test that constructs the exact input whose ABSENCE is
  the defect can never observe the defect.
- **A string-scan pin is not a behavioral pin -- fresh-eyes DEFEATED mine.**
  I guarded the retirement by scanning overlay source for `.fullText`. The
  reviewer reintroduced the bug on the SPOKEN half with
  `const { fullText } = DISCLAIMER_TRANSLATIONS[...]` -- no `.fullText`
  substring anywhere in the code -- and the entire suite stayed green. That is
  this repo's "guard the PROPERTY, not the code shape" scar, and I walked
  straight into it: I pinned a spelling, and a synonym defeated it. The fix
  asserts the VALUE handed to `readDisclaimer` (it contains the undertaking,
  it does not contain the advisory copy, and no placeholder or `undefined`
  leaked), on both overlays. Re-running the reviewer's exact evasion now fails
  that test. The source scan stays as a cheap second layer, explicitly labelled
  as not being the guarantee.
- **I pinned ONE of two call sites and believed I had pinned the other.** My
  spoken-side test clicked Agree and asserted the last `readDisclaimer` call.
  Round 2 showed the click was a NO-OP for that assertion: the call had
  already fired at mount, from the `pendingDisclaimerRead` effect. So the test
  passed for a reason I had not understood, and the "Listen Again" handler --
  a real button, an independently editable second call site -- was pinned by
  nothing. Reverting only that site left all 116 tests green. Both sites are
  now driven explicitly, and the Listen Again test asserts the call count
  INCREASED before reading the last call, or it would just be asserting site 1
  twice. Each of the four sites (2 per overlay) is individually
  mutation-verified.
  The general shape: when a test asserts "the last call to X", know WHICH call
  that is. A passing test whose trigger you have misidentified is not
  evidence.
- **A mutation that does not COMPILE proves nothing.** My first attempt at
  reproducing the evasion left unbalanced parens; vitest reported exit 1 and a
  passing test count, which reads like a catch. It was a transform error -- the
  test never ran. Re-done syntactically valid before trusting the red.
- **Do not duplicate a pin that already exists, badly.** My first per-language
  test asserted the ENGLISH phrase "agree to review" against translated text
  and failed in 17 of 18 languages. The backend suite already pins this well
  (English verbatim + calibrated per-language length floors,
  `test_intro_script.py`). The frontend's job is the WIRING -- that what
  renders IS the shared script; the content pin stays where it works.
- **A flag may gate the CLIP; it must never gate the TERMS.** That separation
  is now stated in both `config-deployment.md` and the overlay comments,
  because the bug was precisely one flag doing both jobs.

## Doc freshness

- `docs/standards/confirmation-and-audit.md`: **UPDATED** -- the register
  table and both surrounding paragraphs described the pre-fix reality.
- `docs/components/config-deployment.md`: **UPDATED** -- said flag-OFF meant
  "the legacy `p1/p2/p3` text", which is no longer true. Stamp bumped.
- `backend/config.py`: the SI register comment said the disclaimer "only
  ADVISES"; corrected, with the guardrail it was protecting (do not promise a
  review WILL happen) preserved and sharpened.
- Freshness-flagged but reviewed and LEFT: `context-compression.md`,
  `jit-schema.md`, `pdf-filling.md`, `auth.md` -- flagged on files this branch
  does not change; their staleness predates it.

## Files touched

- `frontend/src/demo/VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`
- `frontend/src/demo/VoiceOverlay.disclaimer.test.tsx` (overlay-level pins)
- `frontend/src/schema-forms/components/DisclaimerModal.test.tsx`
- `backend/config.py` (SI register comment)
- `docs/standards/confirmation-and-audit.md`, `docs/components/config-deployment.md`
- `docs/journal/entries/2026-08-20-bd-nsb4y-disclaimer-one-source.md` (this entry)
