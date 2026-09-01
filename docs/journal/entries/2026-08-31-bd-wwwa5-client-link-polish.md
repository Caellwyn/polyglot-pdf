---
date: 2026-08-31
bead: polyglot-pdf-wwwa5, polyglot-pdf-leakz, polyglot-pdf-lvhqa, polyglot-pdf-m80z1, polyglot-pdf-k6dpa, polyglot-pdf-ua5gi, polyglot-pdf-b395j, polyglot-pdf-iyh69, polyglot-pdf-ryz2r, polyglot-pdf-mxuzl
title: "client links: the panel stopped contradicting the modal -- and four guards that each pinned a spelling instead of a structure"
tags: [client-links, voice-ux, frontend, testing, review-rounds, ast]
---

## Trigger

Follow-ons from bd `cke6v` (PR #707). A spent link now shows a translated
"voice has finished" modal -- but three things behind it said otherwise.

## What shipped

- **The connect poll stops waiting.** The backend ACCEPTS the socket before
  closing it 1013/budget_exhausted, so `connect()` resolves and the loop burned
  its full 5s against a decided outcome, then set an untranslated English
  "Connection timed out - please try again".
- **Four more sites said "please click Reconnect"** -- naming a button bd cke6v
  removed -- on the disclaimer-agree path, which is the DEFAULT (the intro clip
  is off by default). Then eight MORE in catch blocks.
- **A status write erased the terminal state.** Suppressing the error TEXT while
  leaving `setStatus('error')` beside it meant a watchdog could restore the dead
  button 15s later and vanish the level-triggered save nudge.

All 14 sites now route through one `setConnectionError` helper per overlay. A
connection error added later inherits the suppression instead of becoming the
next contradiction.

Also: `onCancel` is now type-required for the spend-ceiling variant (forgetting
it traps the client behind a full-viewport overlay), and websocket-routing.md
documents the second terminal status.

## The real story: four guards, each pinning a spelling

The shipped code was correct from round 2. Rounds 3-6 fixed the GUARD, and a
reviewer defeated every version by running a mutation rather than reading the
pattern:

| Version | Defeated by |
|---|---|
| `setError('Connection...')` | the ternary house style -- 7 of 9 real call sites |
| `[^;]*?` + `\)\s*$` | a semicolon; a trailing comment |
| `[\s\S]*?` | a nested call: `setError(x.trim() + ' - Connection lost')` |
| hand-counted parens/braces | a `)` inside a string; a `{` inside a COMMENT |

Each round I patched the specific hole and shipped something defeatable in a way
I had not thought of yet. **Being on version 3 of a regex was the signal**, and I
read it four rounds late.

The fix is not a better pattern. These are `.tsx` files where braces in comments
and parens in prose strings are ORDINARY, so no character scan can separate code
from text -- that is a formal limit, not a tuning problem. `typescript` is
already a devDependency, and `ts.createSourceFile` + `forEachChild` answer "is
this a call to setError" and "is this node inside that if's THEN branch" by
construction, in about the same line count.

**Then re-run every PREVIOUS defeat, not just the newest.** All five redden
against the AST version. That check is what distinguishes closing the holes from
trading one for another -- and I only did it on the last round.

Recorded as `bd remember` key `structural-claims-need-a-parser-not-a-regex`: if
the assertion contains "inside", "balanced", "every call to", or "not in a
comment", reach for the AST immediately.

## Two other things worth carrying

**A vacuous parametrization.** The status guard ran over both overlays, but
mobile has ZERO `setStatus('error')` writes -- so its arm looped over an empty
list and asserted nothing, reading as two-file coverage while being one-file
coverage. Scar #8's shape, hidden inside a `describe.each`.

**I asserted a CI fact without checking it.** I wrote "npm run typecheck is a
required CI job" in two source comments; `ci.yml` says NON-BLOCKING BY DESIGN in
capitals and the live rulesets carry no required checks. That was load-bearing,
not cosmetic: I used it to demote a runtime guard to "unreachable, costs
nothing", inviting a future reader to delete a real backstop. Recorded as
`ci-is-non-blocking-never-cite-it-as-a-gate`.

## Deliberately not done

- **bd `c5olf`** (raw snake_case status tokens shown to clients) -- released
  back to open with a scoping note. It needs ~9 labels x 19 languages with NO
  existing translated source to lift from, so authoring them means
  machine-translating an immigration-intake surface. Proposed a smaller first
  slice: render NOTHING rather than a raw token -- no translations, one line.
- **bd `afqbq`** -- `webFormConnection.handleError` can still overwrite the
  terminal status. Pre-existing, in an untouched file, and it makes this
  branch's "FOUR surfaces" enumeration one short. Filed.
- The mobile save-nudge gap, bd `7cy2f`, bd `b1h4z`, bd `r982r`, bd `wd6bb`.
