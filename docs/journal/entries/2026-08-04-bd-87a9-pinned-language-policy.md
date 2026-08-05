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

**Both reviewers caught the same thing: my sweep was incomplete.** I fixed the
comments I had touched and stopped. Independently, both Opus passes found the same
residue -- a body comment in the test file still naming the deleted
`changeSpokenLanguage`, two tier-2 docs (`ws-protocol.md`, `websocket-routing.md`)
still defining the message as a language *change*, two comments a call frame deeper
in `form_filling_service.py` asserting the retired flow, a "below" that should read
"above" in both overlay notes, and a dangling "the language handler" cross-reference
pointing at the function I removed. In a PR whose entire product is comment truth,
that is the defect itself, one layer out.

`websocket-routing.md` is the one that stings: my own journal claimed the stale
tier-2 docs "track files this branch did not touch", and that doc tracks
`websocket_routes.py`, which this branch does touch. I asserted a sweep I had not
run.

**The sweep took THREE passes, and that is the lesson.** Round 1 I fixed the
comments I had touched. Round 2 both reviewers found residue I had missed. Round 3
both reviewers found MORE -- including a twin of an already-corrected sentence 32
lines below it, in the same function I had just edited, and a tier-2 standard
(`si-reduction.md`) whose `Tracks:` globs miss this branch, so the freshness
checker reported it OK while it contradicted the new SPEC outright.

Each round I fixed the instances I was shown instead of re-running the search.
The fix that finally worked was mechanical: one repo-wide grep for every phrasing
of the retired claim, across code, tests, and docs, filtered against the phrasings
that state the policy correctly -- then fix everything it returns and re-run it
until it comes back clean. That is what "sweep" should have meant from the first
round; spot-fixing what a reviewer points at is not a sweep, it is a queue.

Ironically `form_filling_service.py:593` already said "SESSION-START ONLY --
mid-session language changes are not a supported flow". The codebase contradicted
itself before this PR; I had simply never looked at all of it at once.

**Round 4: the README was telling readers to try the unsupported thing.** My
"repo-wide grep" still missed three survivors, because I searched for the
phrasings *I* had used. The README says "changing languages mid-session" and
"real-time switching" -- neither matches "mid-session language change". Reviewer A
found them by thinking about how the claim could be worded rather than how I had
worded it. One was the repo's front-door quick-test steps, instructing a reader to
do the exact thing the PR declares unsupported; another was a Working Features
bullet claiming the capability outright.

So the round-3 lesson was right in method and wrong in execution: a grep is only
as complete as its list of phrasings. The durable version is to search for the
CONCEPT from several angles (the message name, the feature name, the user action,
the noun and the verb forms) and to have someone else generate phrasings too.

**The enforcement test now guards the invariant, not two names.** Both reviewers
showed the source scan could be evaded by RENAMING the switcher. The scan now
checks every `change_spoken_language` send site and requires its `spoken_language`
to come from `state.selectedLanguage` -- a renamed switcher fails, because what is
banned is a caller-supplied language, not a spelling. The name-based check is kept
as a second, narrower test so a verbatim restore is caught at declaration. All
three cases are mutation-verified, including the rename evasion.

**Round 5 found the one that actually mattered: the SYSTEM INSTRUCTION.** Five
rounds of sweeping comments and docs, and the shipped SI still told the model
*"only the user's explicit request to switch changes the session language."* That
is not prose a human reads -- it is instruction the model acts on. If a user asked
to switch, the model would comply while the ASR bias, the option-label overrides
and both initiating templates all stayed pinned to the original language, until
the next reconnect snapped it back.

It survived every previous sweep *because* it is not a comment. I had been
grepping for stale documentation, and this is code. The SI now says the language
is fixed for the whole form and tells the model that a user who asks would need
to start over -- a useful answer rather than an impossible one. It describes the
clear-form control by what it DOES and never names it, because the on-screen
label is translated (see the round-6 section below; the first version of this
clause quoted the English label and had to be fixed). Pinned by a test asserting
the superseded sentence is GONE, not merely that the new one is present.

Final SI cost, measured at HEAD rather than mid-round: 17,178 -> 17,555 chars
(+377, +2.2%), matching si-reduction.md. An earlier draft of this paragraph said
"+136 (0.8%)" -- the round-5 figure, taken before round 6 rewrote the clause.

Both reviewers filed it independently in the same round (bd o1k9 / nl6v, both now
closed), which is the argument for the two-independent-passes gate: they had
converged on comment residue for three rounds, and the one with runtime effect
still needed two sets of eyes to surface.

**The enforcement test needed a third guard.** A reviewer showed the send-site
scan could be evaded by a switcher that PERSISTS the caller's language first and
then sends `state.selectedLanguage` -- which is exactly the deleted function's own
shape, so my journal's claim that "a renamed switcher fails" was false for the one
shape that matters. The fix moves upstream: only the entry flow may WRITE the
pinned language (`setSelectedLanguage` has exactly one production caller). A
second writer is a switcher by definition, whatever it is named. Mutation-verified
against that exact evasion.

**Two process scars from this round, both mine.**

First: I used `git checkout origin/dev -- .` inside the worktree to test whether a
suite flake predated the branch. That pulled ~20 unrelated files from dev into the
tree on top of a stash pop, producing merge conflicts and a mess that looked, for
a moment, like lost work. Nothing was lost -- every real change was either
committed or in the stash -- but the recovery cost several careful steps, and the
`git reset --hard` reflex I reached for was (correctly) blocked as destructive.
The right way to answer "does this flake predate my branch?" is to stash, test,
and pop -- never to pull another ref's files into a dirty tree. Recovery was
`git checkout HEAD -- .`, unstage-and-delete the strays, then pop.

Second: I mangled the same test file three times by writing TypeScript through a
Python heredoc, where backslash escapes (newline, word-boundary, whitespace) are
interpreted before they ever reach the file. Once it silently produced a file with
a literal newline inside a regex and the suite reported "0 tests" rather than an
error -- a broken file that looks like a clean run. Writing *this very paragraph*
through a heredoc mangled it a fourth time, which is a fair measure of how durable
the habit is. Write/Edit exist for this; a heredoc is only safe for text with no
backslashes.

**Round 6: my own fixes had bugs, and the guard watched the wrong thing.** The
round that was meant to be the last found two real defects in the round-5 work:

- The SI clause I wrote to fix the policy quoted the English label `'clear form'`
  -- but that button is translated per session language (a Spanish user sees
  "Borrar formulario"). That is precisely the defect bd polyglot-pdf-s863 already
  fixed for the disclaimer's Agree button, and my new test *pinned the English
  literal*. There is no `{...}` placeholder on this path (static SI, not a
  per-turn template), so the clause now describes the control by what it DOES and
  explicitly forbids inventing or anglicizing a label.
- The enforcement guard watched the two state-manager MUTATORS, but the pinned
  value can be written by plain assignment -- and the disclaimer-accept path in
  both overlays already does exactly that. A switcher written that way touched
  neither mutator and passed every case. The guard now watches the FIELD in any
  write form and asserts the COMPLETE list of eight legitimate write sites, so a
  new writer anywhere fails and names itself. An earlier version had also
  allowlisted all of `connection.ts` -- the one file most likely to regrow the
  switcher.

Three attempts to write this guard, three evasions found by reviewers: a rename,
a whole-file allowlist, and a direct assignment. Each time I had guarded the shape
of the code I deleted rather than the property I wanted. The property is "the pin
is written only before the form starts"; everything else was a proxy for it, and
every proxy had a hole. Worth remembering when the next invariant needs a test:
name the property first, then find the narrowest thing that is true if and only if
the property holds.

 Both reviewers noted that a
re-added switcher would break no test -- documentation alone had already failed
once here, so `pinned-language-policy.test.ts` pins two things: the surviving
`change_spoken_language` sender carries a language byte-identical to the persisted
one (a re-assertion, not a switch), and no production source declares or calls
`changeSpokenLanguage` / `handleLanguageChange` at all. The second is a source
scan rather than a behavior test on purpose: the removed code was dead for months
and passed every behavior test that existed. Both are mutation-verified.


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

**Round 7, and the guard finally holds.** Reviewers found a FIFTH evasion shape (a
bracket-key write, `st["selectedLanguage"] = x`) plus two more of my own errors:
the SI size figure I recorded was stale by 241 chars, because I rewrote the clause
in round 6 and reused the round-5 number -- in the very doc whose job is tracking
SI size against the per-turn cost invariant. And the tier-2 SPEC still described
the SI as "pointing them at the clear form button", omitting the
describe-don't-name rule that makes the fix correct, so anyone re-implementing
from the spec would have reintroduced the s863 defect.

The guard now matches the FIELD with any right-hand side -- assignment,
bracket-key, object-literal, and mutator forms -- and asserts the eight legitimate
write sites WITH LINE NUMBERS, because two of them are textually identical and a
site could otherwise move between them undetected. Five evasion shapes tested,
five caught: rename, spread, `Object.assign`, aliased manager, bracket key.

The English-label test went from a blacklist to allowlist-first, per this repo's
own scar tissue ("banning a word is one synonym from defeat"). It pins the RULE
-- describe it by what it does, never invent a label, the on-screen label is
translated -- which holds whatever label someone adds, plus a no-residue check on
the original literal. Verified: swapping in "'Reset Form' button" now fails.

## Doc freshness

- **Bumped `docs/standards/voice-and-vad.md`** -- the standard whose `Tracks:`
  globs cover every file this change touches (both overlays, `connection.ts`,
  `webFormConnection.ts`, `websocket_routes.py`). New SPEC section + stamp; the
  checker reports OK.
- **Amended `docs/journal/entries/2026-08-04-bd-575i-...md`** with a correction
  block rather than a rewrite.
- **Bumped `docs/standards/ws-protocol.md` and `docs/components/websocket-routing.md`**
  -- both still defined `change_spoken_language` as a language *change*, directly
  contradicting the new SPEC section, and `websocket-routing.md` tracks
  `websocket_routes.py`, which this branch DOES touch. An earlier draft of this
  entry claimed the remaining stale docs "track files this branch did not touch";
  that was wrong, and both reviewers caught it.
- Reviewed and left: the tier-2 docs the checker still flags STALE genuinely track
  files this branch does not touch (re-checked, not assumed, this time).
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
- `docs/standards/ws-protocol.md`, `docs/components/websocket-routing.md` -- the `change_spoken_language` rows + the initiating-message prose corrected; stamped.
- `backend/services/form_filling_service.py` -- two comments that asserted the retired flow (comment-only; behavior unchanged).
- `frontend/src/__tests__/pinned-language-policy.test.ts` -- new; pins the re-assertion invariant and bans a re-added switcher at source level.
