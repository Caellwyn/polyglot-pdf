---
date: 2026-08-04
bead: polyglot-pdf-87a9
title: "fix(voice): codify the pinned-language policy -- remove dead mid-session language-change code + correct the docs"
tags: [conventions, doctrine]
---

## Trigger

Reviewing the PR #541 merge report, the maintainer read this line about bd pjws:

> "After a mid-session language switch, the app kept sending labels in the old
> language and the next confirmation wrote the old language back over the new
> one, so the switch survived about one turn."

and replied: *we don't support mid-conversation language switches. The language
code should be pinned in the config and SI, and the model should be expected to
stick to it for the entire form. It should only be changed by creating an
entirely new session with the 'clear form' button and selecting a new language
from the modal. Is that clearly codified in documentation and code?*

The answer was no -- and worse, several comments said the opposite.

## What shipped

**The product already behaved correctly; nothing said so.** Verified before
changing anything:

- `LanguageSelectionModal` is bound only to `handleInitialLanguageSelect` in both
  overlays and is gated behind `showLanguageModal` -- a one-time entry gate.
- `handleLanguageChange` was **dead code in both overlays**: defined, never bound
  to any `onChange`, no `<select>` rendering it. Its own comment read "from
  dropdown - for changing language later" -- documenting the unsupported flow as
  if it were supported.
- `connectionManager.changeSpokenLanguage` had **zero production callers** once
  those two were accounted for; only test mocks referenced it.
- The one LIVE sender of the `change_spoken_language` WS message is
  `webFormConnection.ts`'s reconnect opener, which **re-asserts the SAME pinned
  language** after a socket teardown (section switch / reconnect drops the Gemini
  session). It is a re-assertion, not a switch -- the message name is a misnomer
  for what it now does.

**Removed** (maintainer-approved scope: delete the dead code, document the
policy, leave the backend handler's behavior alone since the reconnect path
depends on it): `handleLanguageChange` from `VoiceOverlay.tsx` and
`VoiceOverlayMobile.tsx`, `changeSpokenLanguage` from the connection-manager
interface and implementation, the now-unused `computeNextField` /
`formatNextFieldHint` imports from both overlays, and the stale `vi.fn()` mocks
from seven test files. Each removal site carries a note explaining the policy and
why the code is gone, so the next reader does not re-add it.

**Documented.** `docs/standards/voice-and-vad.md` gains a SPEC section under
"fill-language vs spoken-language" stating the pin-for-the-whole-form rule, the
only supported change path, and that `change_spoken_language`'s live use is
reconnect re-assertion. The backend handler in `websocket_routes.py` carries the
same, marked MISNOMER at the point a maintainer would read it. The two axes are
now explicitly asymmetric: fill-language is data and changes freely;
spoken-language is session config and does not.

**Corrected the record from PR #541.** The pjws code comments in
`webFormConnection.ts` (four of them) and the `hint-language-freshness` test file
described mid-session switching as a supported flow being fixed. They now state
the policy and explain that the fix stands on different grounds. The 2026-08-04
journal entry gains a correction block at the top of "What shipped" rather than a
rewrite -- the journal is the chronological record, so the wrong framing stays
visible with the correction attached.

**Re-scoped the two beads that inherited the bad premise.** `mpqs` (backend
translation overrides not following a mid-session change) is **closed as an
invalid premise** -- under a pinned language, building the overrides once at
`connect()` is correct, not a gap. `qim7` (handleSessionReady clobbering state)
is **kept and re-scoped**: I re-read the code, and its stale-write is real --
`setSessionId` / `setJitMode` / `setContinuousSession` all `save()` an unrefreshed
`this.state`, so they persist over anything written outside the object. Only the
"clobbers a language change" framing was wrong; the likely victim is a field
value the user typed on screen.

## Lessons

**Verify the PREMISE of a bead, not just its claims.** bd pjws described a
mid-session language switch, and I checked that the code did what the bead said
-- the state really did go stale, the confirm really did write it back. Every
factual claim held. I never asked whether the *scenario* was one the product
supports. It was not, and the whole write-up inherited that. A bead's description
of a user flow is an assertion about the product, and it deserves the same
scepticism as an assertion about the code: cheap to check (who calls this? is the
UI reachable?), and it invalidates everything downstream when wrong.

The tell was there and I walked past it. `handleLanguageChange` had **no caller**
-- I even grepped `changeSpokenLanguage` during the pjws work and saw the two
overlay hits. I read "there is a UI path" and moved on, instead of asking whether
that path was wired to anything. Dead code reads exactly like live code when you
are looking for confirmation rather than for the truth.

**Dead code is a documentation defect, not just clutter.** These two functions
cost nothing at runtime and misled a whole PR: they made an unsupported flow look
supported, to me and to four Opus reviewers, none of whom flagged the premise
either -- because the code plainly showed a language-change path. Removing them
was worth more than the diff suggests. Where a reader might expect the capability,
the comment now says why it is absent.

**A correction belongs where the wrong claim is read, not only where it is
fixed.** The wrong framing lived in code comments, a test file's header, a
journal entry, and two bead descriptions. Fixing only the code would leave four
places asserting the opposite. The journal keeps its original text plus a
correction block (it is a historical record); the code comments were rewritten
outright (they are current-state).

## Doc freshness

- **Bumped `docs/standards/voice-and-vad.md`** -- the standard whose `Tracks:`
  globs cover every file this change touches (both overlays, `connection.ts`,
  `webFormConnection.ts`, `websocket_routes.py`). New SPEC section + stamp; the
  checker reports OK.
- **Amended `docs/journal/entries/2026-08-04-bd-575i-...md`** with a correction
  block rather than a rewrite.
- Reviewed and left: the other tier-2 docs the checker flags STALE track files
  this branch did not touch.
- No CLAUDE.md changes.

## Files touched

- `frontend/src/demo/VoiceOverlay.tsx` -- removed `handleLanguageChange` + the now-unused navigation import; policy note in its place.
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- same.
- `frontend/src/shared/connection.ts` -- removed `changeSpokenLanguage` from the interface and the implementation; policy note in its place.
- `frontend/src/webFormConnection.ts` -- corrected the four pjws comments that framed the fix as a mid-session-switch fix.
- `frontend/src/__tests__/hint-language-freshness.test.ts` -- header rewritten to state the policy and label `selectedLanguage` as a test fixture for the stale-state class; test names de-languaged.
- Seven `frontend/src/demo/*.test.tsx` files -- dropped the stale `changeSpokenLanguage` mocks.
- `backend/routes/websocket_routes.py` -- MISNOMER note on the `change_spoken_language` handler (behavior unchanged; the reconnect path depends on it).
- `docs/standards/voice-and-vad.md` -- the SPEC section + stamp.
- `docs/journal/entries/2026-08-04-bd-575i-...md` -- correction block.
