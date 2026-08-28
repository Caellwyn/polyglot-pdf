---
date: 2026-08-28
bead: polyglot-pdf-a5nfk
title: "test(iam-guard): bind the privileged-call guard to a real auth receiver"
tags: [testing, iam-guard, mutation-testing]
---

## Trigger

`backend/tests/unit/test_deployed_iam_envelope.py`'s guard against
privileged Firebase Auth calls matched on the bare method name alone
(`fn.attr`), with no check that the receiver was actually the
`firebase_admin.auth` module. `store.get_user(uid)`, `d.update_user(x)`,
and `self._cache.list_users()` all false-positived. No such call exists in
`backend/` today, so this was a latent precision defect, not a live
failure -- but an over-firing guard trains people to delete it instead of
trusting it, which is the exact failure this file exists to prevent.

## What shipped

Rebound the guard to the call's actual receiver: a new `_call_receiver_name`
resolves a call's receiver to a (possibly dotted) string, `
_firebase_auth_aliases` derives every local name bound to the
`firebase_admin.auth` module across every import shape this repo plausibly
uses, and `_direct_privileged_imports` separately tracks names imported
DIRECTLY from `firebase_admin.auth` (which have no receiver at all). A
shared `_privileged_calls_in_tree` generator is now the single
implementation both the production guard and the precision test's
synthetic-source harness call, so the matching rule cannot drift into two
hand-duplicated copies.

## Lessons

**A receiver-binding fix can silently narrow what the OLD bare-name match
used to catch, and each of four review rounds found one more shape it had
dropped.** The original bare-name matcher had no receiver awareness at all,
so it (accidentally) caught every import shape uniformly. Making the check
receiver-aware means every accepted receiver shape has to be enumerated
explicitly -- and this file's own history is the reason to take that
seriously: it already carries a prior scar for exactly this pattern
(SCOPE derived by exclusion, not by hand-listing, because a hand-listed
inclusion silently drops the next case). Four rounds each found a real,
previously-uncaught shape: aliased `from firebase_admin import auth as X`,
a bare dotted `import firebase_admin.auth`, a direct `from
firebase_admin.auth import get_user`, and finally a name bound to the bare
`firebase_admin` PACKAGE (aliased or not) accessed two levels deep as
`<name>.auth.get_user(...)`. Each was fixed in turn and pinned with its own
mutation-verified test case.

**Two shapes were deliberately left unfixed, and stopping there was the
right call, not more chasing.** A wildcard `from firebase_admin.auth import
*` and assignment re-aliasing (`fb2 = fb` then `fb2.auth.get_user(uid)`)
are both real, in-family gaps -- but closing either soundly needs actual
data-flow / constant-propagation analysis, not one more import statement
shape to enumerate. That is a different KIND of gap than the four that got
fixed, which were all closable with the same single-pass AST walk already
used everywhere else in the file. Both are now named explicitly in
`_firebase_auth_aliases`'s docstring as deliberate exclusions, with the
reasoning for why they're a different class -- not silently dropped, and
not chased into a fifth and sixth round for diminishing, currently-unused
coverage. A fifth review round explicitly asked "is this now complete for
everything static-analysis-resolvable," found none, and returned NO-GAPS.

**A negative-control test can look right and still not prove what it
claims.** The `firebase_admin.initialize_app()` non-flagging assertion
(added to prove registering a package alias didn't over-widen the guard)
turned out unable to catch the over-widening bug it existed to guard
against -- `initialize_app` was never in the privileged set to begin with,
so a broken implementation that wrongly flagged every call through a
package alias (not just `.auth`-suffixed ones) would have passed it too.
Fixed by asserting a PRIVILEGED-named method called directly on the bare
alias (`fb.get_user(uid)`, no `.auth` in the chain) stays unflagged --
verified via mutation that this version actually catches the bug the first
version couldn't.

## Files touched

- `backend/tests/unit/test_deployed_iam_envelope.py` -- receiver-bound
  matching, four new import shapes covered, two named as deliberate
  exclusions, all new assertions mutation-verified.
