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

## Follow-ups

The shared tokens themselves still exist server-side and in the launcher env;
removing them is the last child (`rhc2v`), which is why this bead left them
alone rather than opportunistically widening.

Getting back INTO the deployed editor also needs a role claim on the
maintainer's own account -- code alone is not sufficient, and that grant is an
operator action against live auth state, not something this bead performs.
