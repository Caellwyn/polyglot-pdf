---
date: 2026-08-28
bead: polyglot-pdf-rhc2v
title: "chore(auth): delete the two shared editor tokens -- epic ijntk closes"
tags: [auth, schema-editor, cleanup]
---

## Trigger

The last child of epic `polyglot-pdf-ijntk`. Its own description set the gate:
*"Runs LAST, once the replacement is proven working end to end. Removing the
fallback before that would lock everyone out."*

That precondition is now met, and not by inference: the maintainer signed into
the deployed editor with Google, the catalogue loaded six kit schemas (all 200s,
authenticated by their own ID token), and a save landed as
`PUT /kits/form/schema -> 200`. The replacement is proven on the live surface,
so the fallback can go.

## What was actually left

Less than the bead assumed, and the enumeration is why. A grep across every
non-journal file found 26 files mentioning the tokens -- 167 hits in one test
file alone -- which looks like a large removal. It is not:

- **The settings were already dead.** `SCHEMA_EDITOR_TOKEN` /
  `SCHEMA_AUTHOR_TOKEN` were declared in `backend/config.py` and read by
  NOTHING (verified: zero non-test readers). `hn0jq` stopped consulting them
  without deleting them.
- **The 161 test hits are a fixture convention -- but one that RODE the
  production parameter, which I got wrong first time.** `conftest` maps the
  suite's `X-Editor-Token` values to two distinct people, a shim `hn0jq` added
  so 28 test files would not need rewriting. I read that as "the tests do not
  depend on the production header" and said so. Half right: the shim patched
  `verify_editor_token`, but the thing that CALLED it was the very parameter I
  was deleting. Removing it silently disconnected the shim and **225 tests
  401'd**.
- **The `link_tokens` / `link_routes` mentions are a different feature.** Both
  are prose about a *superseded* per-firm API key design that was once described
  as "X-Editor-Token-style". Out of scope, and deleting them would have been the
  wrong kind of thorough.

So the real change is four files: the two dead settings, the header fallback in
`editor_auth.py`, and a launcher that minted a token nothing reads.

## What shipped

`require_editor_actor` now takes `Authorization: Bearer` and nothing else. The
`X-Editor-Token` parameter is gone from its signature, which is what actually
closes the door: FastAPI binds header params by name, so a header no parameter
declares is a header the app cannot read.

`scripts/run-schema-editor.sh` stops minting a per-run token and stops passing
it to uvicorn. Local dev authenticates through `VFF_DISABLE_AUTH`, as it already
did; the token was cargo.

## The 225-test failure, and what it cost to be sure

The fix is a translation at the test boundary, not a revived path: the shim
now also rewrites the suite's header into the `Authorization: Bearer` a real
client sends. It lives in `conftest`, never in `backend/`, and the test that
asserts the parameter is gone runs under `real_editor_auth` so the shim cannot
answer for it.

**I then overstated what that proves, and review caught it.** I wrote that
disabling Bearer parsing fails tests, "which argues the shim does not mask the
production path" -- true of the files I ran, and not true generally. Measured
after the reviewer pushed back: `test_editor_kit_routes.py` (177 tests) passes
with production Bearer parsing entirely disabled, because it installs
`app.dependency_overrides` and never calls the real `require_editor_actor` at
all. `test_kit_revision_archive.py` and `test_editor_identity.py` DO catch it.

So the accurate claim is narrower: the shim is genuinely exercised by the tests
that reach the real dependency, and those catch a broken Bearer path. A large
block of editor tests is structurally blind to production auth -- pre-existing
from `hn0jq`, not introduced here, and filed as `polyglot-pdf-q1gtz` rather than
widened into this bead. The lesson is about the EVIDENCE, not the code: a
mutation that reddens the file you happened to run tells you about that file.

The process lesson is sharper than the technical one. I ran the targeted
tests, saw them pass, and reported the change verified -- while the full
suite was still running and about to fail 225 tests. The targeted run was
chosen to cover what I had changed, which is exactly the blind spot: it
cannot show what my change broke somewhere I was not thinking about. A
narrow green is not evidence, and saying "verified so far" does not make it
one.

## Scar tissue

**A retired path left accepted is a path that comes back silently.** The header
was kept deliberately in `hn0jq` so the frontend could cut over in its own bead
without landing in the same commit as the server -- a good call. But once that
cutover shipped, leaving the second door open meant a client regressing to the
old header would have kept working. Nothing would have failed, so nothing would
have been noticed. The test that pins this asks the DEPENDENCY's signature, not
a route's behaviour, because "the app no longer reads this header" is a fact
about what the function declares.

**Dead config teaches.** Two settings that nothing read still told the next
author "this is how auth works here". That is the same class as the stale docs
the cross-surface reviewer caught twice in this epic: the cost of leaving a
retired mechanism described as current is that someone restores it believing
they are fixing something.

## Epic ijntk, closed

Four children, in the order they had to happen:

1. `hn0jq` -- the server learns who you are (per-user Firebase identity, its own
   role claim, its own allowlist).
2. `5tuas` -- the kit lock re-scoped from a role to a person.
3. `yswp3` -- the browser learns to sign you in.
4. `rhc2v` -- the shared secrets deleted.

Worth recording about the sequence: server-first was correct, but it opened a
window on a LIVE surface where the editor was unopenable -- the front door asked
for a key the lock had been re-keyed against -- and nothing in the plan flagged
that the window had opened. The maintainer found it by trying to use the editor.
A plan that changes auth in two commits should say which one makes the product
temporarily unusable.
