---
date: 2026-08-27
bead: polyglot-pdf-yswp3
title: "feat(schema-editor): per-user sign-in screen, replacing the shared access code"
tags: [auth, schema-editor, testing]
---

## Trigger

The maintainer could not get into the deployed editor. The landing screen was
still the shared access-code box.

That was not a regression -- it was the seam between two children of epic
`polyglot-pdf-ijntk`, showing up in production. Child 1 (`hn0jq`) moved the
SERVER to per-user Firebase identity and stopped honouring the shared code;
this child was supposed to move the BROWSER. Between them the front door asked
for a key the lock had just been re-keyed against, so `AccessCodeGate` sent an
`X-Editor-Token` the server answered 401 to, every time, for everyone.

Worth naming because the sequencing was deliberate and correct (server-side
identity first, testable with no UI change) -- but a server-first cutover on a
LIVE surface leaves a window where the product is unusable, and nothing in the
plan flagged that the window had opened. The bead's own note called this child
"the least essential"; it was in fact the one standing between the maintainer
and the editor.

## What shipped

`SignInGate.tsx` (email+password / Google / reset) over `utils/editorAuth.ts`,
which owns the editor's Firebase app and hands `remoteKitStore` a fresh ID
token per request. `AccessCodeGate.tsx` is deleted, along with the access-code
storage, `VITE_EDITOR_TOKEN`, and the `X-Editor-Token` header on the client --
verified absent from the built bundle, not just from the source.

No backend change was needed: `require_editor_actor` already accepted
`Authorization: Bearer`, written that way in `hn0jq` precisely so the frontend
could move in its own bead.

**The 403 is a first-class screen, not an error banner.** Authentication and
authorization fail differently here and the remedies are opposites: a 401 means
"sign in again" (a retry can work), while a 403 means "you are who you say you
are, but you are not on the editor's list" -- an operator must run
`bootstrap_editor_user.py`, and retyping a password never helps. Collapsing
them into one "sign-in failed" message would loop a voice-app user through a
step that already succeeded. So `ForbiddenError` is a distinct type in the
store, and the gate renders a distinct screen naming the actual remedy.

**No account creation, deliberately** -- unlike the voice app's `Login.tsx`,
whose shape this otherwise mirrors. Editor access is granted, never
self-served, so a self-served account could only ever hit that same 403.

## Scar tissue

**A second auth site that no test would have caught.** `localStamp.ts` builds
its own request rather than going through `editorFetch` -- one of exactly two
direct `fetch` sites in the editor. Rewiring only `editorFetch` would have left
local-mode readiness stamping sending a header the server ignores, failing
quietly in the one path whose whole job is to avoid a silently stale number.
Found by grepping for the removed functions' callers before deleting them,
which is the general move: enumerate the SET, then fix it.

**The mock that outlived its subscriber.** The first version of the test helper
re-mocked `watchEditorUser` on each state change. Three tests failed, all
"still on the sign-in form" -- because a gate mounted EARLIER was still
subscribed to the PREVIOUS stub, so a later sign-in never reached it. The fix
was to model what Firebase actually does: a listener registry that replays the
current user to each new subscriber. A mock that does not match the real
contract's SHAPE produces failures that look like product bugs.

**Five mutations, five reds.** Each new guard was verified by reverting the
behaviour it claims to pin: disabling the 403 branch (3 red), signing out on a
503 (2 red), folding 403 into `AuthError` in the store (1 red), and dropping
the bearer header in each of the two fetch sites (3 and 1 red). The edited
operator-message guard was re-verified too, since editing a test invalidates
its earlier proof.

**The 403 screen was right at the door and wrong everywhere else.** Review
caught that I had built the refused screen for the GATE and then left every
mid-session catch site folding 403 into the generic error banner -- so an
editor whose role was revoked mid-kit would hit an unactionable message on
every save, repair and regenerate, never reaching the screen built for exactly
that case. Reachable for real: revocation is deliberately delayed up to an
hour (editor_auth.py runs without check_revoked), so a stale-but-valid token
403s while the UI still thinks the person is an editor.

The instructive part is the SHAPE of the fix. Six catch sites in App.tsx, nine
more in RemoteCatalogue -- and the first instinct, patching the one the
reviewer named, would have been the repo's single most expensive mistake
(scar tissue #8: fix the SET, not the instance). Instead the predicate was
widened at every site mechanically, and the routing decision was made ONCE
inside handleAuthExpired, which every site already called. Fifteen call sites,
one place that decides.

**And I still missed one -- which is the actual lesson.** Round 2 fixed 15 sites,
called it "fixed as a SET", and left ValidationPanel: a third file, same shape,
whose lintSchema call is the HIGHEST-frequency remote call in the editor, so a
revoked editor would most likely have hit the unactionable banner there first.
Two rounds, each finding one more member of one set -- the exact pattern scar
tissue #8 names as this repo's largest source of review rounds, walked into
while quoting it.

The fix that mattered was therefore not the one-line widen. It was
`utils/authErrorRouting.test.ts`, which asserts the property over the SOURCE:
every catch site accepts ForbiddenError, every forward carries the error, every
onAuthError prop is typed to receive it. It walks the tree rather than listing
files (a hand-listed set is the same bug again) and keeps a one-name allowlist
for SignInGate, which legitimately branches on 403 first. Reverting the
ValidationPanel omission now turns all three guards red.

Worth stating plainly: the second failure mode there is invisible to tsc.
`onAuthError?.()` against a `(err?: unknown) => void` prop typechecks fine --
the signatures are structurally compatible both ways -- so the routing silently
degrades to treating every 403 as a 401. Only a source-level assertion catches
it.

**Round 3: the guard could only see files that already agreed with it.**
The source-scanner above matched lines containing `instanceof AuthError`.
That set is, by construction, the files ALREADY handling auth. Two files
handling it NOWHERE -- `ArchivedVersions` (both archive fetches) and
`FormCatalogue` (mark-complete through the real backend, local mode
included) -- matched nothing and sailed through green, while shipping the
exact bug the guard was written to stop.

So the guard was rewritten to start from the OTHER end: enumerate the
network functions in `remoteKitStore` (read from the store itself, so a new
route is covered the day it lands), find every file that CALLS one, and
require each to handle auth. Reverting FormCatalogue to its round-2 state --
no auth handling at all -- now names the file and the function it calls.

The generalisable lesson, and the reason this is worth the words: **a guard
that greps for the wrong version of a thing can only find code that is
already thinking about that thing.** Scanning for the BUG shape finds
near-misses; scanning for the OBLIGATION -- who calls something that can
fail this way -- finds silence. Silence is what shipped, twice.

Also fixed in round 3: in LOCAL mode a 403 was being shown the 401's remedy
("the access token may be from an earlier run -- reload this page").
Reloading cannot fix a missing role, so the two messages now split by cause.
Local is not a bypass-only mode -- `run-schema-editor.sh` starts the real
backend, and its author-only routes can refuse a real token on role.

**Round 4: the guard passes trivially for a big file.** The last member was
in `App.tsx` itself -- the readiness-stamp catch swallowed a 401/403 into a
`console.warn` while the six catches above it all routed properly. Two
reasons it survived four rounds: `stampKitReadinessRemote` lives in
`localStamp.ts`, not the store, so the guard's function list never named it;
and even after adding that module, `App.tsx` satisfies a per-FILE substring
check many times over from unrelated imports.

Both were fixed, but the second cannot be fixed by a source scan at all: a
per-file check cannot express a per-call-site obligation. Verified rather
than assumed -- re-deleting the routing leaves the guard green, and only the
new behavioural test in `App.local-stamp.test.ts` goes red. The guard's
docstring now says this outright, so the next reader treats it as a floor
and not a ceiling.

**The honest summary of four rounds on one set:** every round found a real
bug, and every round I believed the set was closed. What actually converged
it was not trying harder to enumerate -- it was moving the check to the
OBLIGATION side (who calls something that can fail this way), and accepting
that the residue needs behavioural tests per site. The cost was four review
rounds on a bead whose feature work was done in the first commit.

## Follow-ups

The shared tokens themselves still exist server-side and in the launcher env;
removing them is the last child (`rhc2v`), which is why this bead left them
alone rather than opportunistically widening.

Getting back INTO the deployed editor also needs a role claim on the
maintainer's own account -- code alone is not sufficient, and that grant is an
operator action against live auth state, not something this bead performs.
