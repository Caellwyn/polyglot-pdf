---
date: 2026-08-13
bead: polyglot-pdf-hqztg
title: "The author approval round -- and what ten review rounds on one status cost"
sprint: 19
tags: [testing, conventions, review, permissions]
---

## Trigger

Sprint 19 (docs/sprint_19_firm-tier-kit-lifecycle_plan.md). Filed during bd
polyglot-pdf-xzw5 when the maintainer asked for a step between an editor
finishing a form and it going live: "editors are likely to be subcontractors. I
want a confirmation level above them."

The shape came from two maintainer decisions. Editors submit; authors publish.
And editors never take destructive actions -- "their work should always be
recoverable. So, no deletions."

## What shipped

A fourth kit status, `submitted`, sitting between `draft` and `complete`. It is
write-locked, so the version an author reviews is the version they publish. The
permission split is per TRANSITION inside one `/status` handler rather than per
route: an editor may submit and may reopen their own submission; publishing, and
reaching back into a live kit, are author-only. Rejection clears the author
version, since a kit that was never live has no confirmation record naming it.

Over that sits a role-scoped editing lock (`POST`/`DELETE
/api/editor/kits/{id}/lock`). An author can always take a kit back from an
editor, never the reverse. It is role-scoped rather than per-user because the
editor API has only two shared tokens -- two editors sharing one still collide
(bd polyglot-pdf-ijntk).

## The cost, stated plainly

Ten inner rounds, 25 findings, then the outer cross-surface review. That is the
most expensive bead of this epic by a wide margin, and the findings were
overwhelmingly REAL BEHAVIOUR rather than weak tests:

- an editor could UNPUBLISH a live form, and then could not restore it
- submitting ran ZERO validation, so an editor could freeze a kit around a
  garbage schema and fill an author's review queue with unpublishable work
- taking a lock on a kit with unparseable metadata REPLACED the file, dropping
  `status` -- which silently removes a live form from the deploy manifest
- a successful submit told the editor "reverted to draft"
- a Cmd+S rewrote a submitted kit's metadata under the reviewing author
- sending a kit back BRICKED the editor out of their own draft

## The pattern underneath, which is the durable lesson

Nearly every finding was one mistake wearing different clothes: **I added a
fourth value to a set, and something that enumerated the other three silently
changed meaning or fell through.**

It happened in `_WRITE_LOCKED_STATUSES` (which a publishedness check was
borrowing), the structural-gate conditional, the hosted notice chain, the local
card branch, the `setKitStatus` guard, the App save-stamp guard, and a
catalogue predicate. Seven sites, each found by a separate review round, because
each round SAMPLED. Round 7 stopped sampling and enumerated every
status-switching site in both languages; that round and the exhaustive
96-cell lock table in round 10 are what actually converged this.

Two structural fixes came out of it:

1. **When one constant answers two questions, split it before adding a value.**
   `_WRITE_LOCKED_STATUSES` answers "may its bytes change?"; `_PUBLISHED_STATUSES`
   answers "do confirmation records name it?". They overlap, which is why
   sharing one tuple looked fine -- and adding `submitted` silently answered the
   second question wrong, reintroducing a bug bd polyglot-pdf-xzw5 had just
   fixed one status over.

2. **A hand-typed list cannot notice the set grew.** `App.local-stamp.test.tsx`
   read `it.each(['complete','unpublished'])` under a comment saying "The FULL
   write-locked set, not a sample". Adding a status made that comment false and
   the test stayed green. There was no shared write-locked set in TypeScript at
   all -- three sites retyped it. There is one now, and the test enumerates the
   CONSTANT.

## The lock was wrong three times, in three different ways

Worth recording because the sequence is instructive:

- **Round 8:** the lock was never released, so an author sending a kit back left
  the editor 409'd on every action with no control to self-rescue.
- **Round 9:** my fix released on EVERY transition -- which dropped the author's
  own lock when they reopened a live kit specifically in order to edit it. I had
  traded a liveness bug for a safety one, which is exactly what I had asked that
  round to check.
- **My first correction** keyed on the target status, and instantly recreated
  round 8's lockout, because the send-back is also a `-> draft`. **Round 8's own
  test caught it within a minute.**

That last point is the argument for revising a test that encodes a rule you
later revise, rather than deleting it: the superseded test was the only thing
standing between me and re-shipping the bug it was written for. The rule is now
keyed on the SOURCE -- reopening a live kit begins an editing turn; every other
transition ends one.

## What the reviews caught that I would have shipped

Two things deserve naming because both were confidently wrong in MY OWN work:

- A UI comment asserting "an editor's SUBMIT runs the same readiness/lint gate"
  when it ran none, defended by a test that passed only because the API was
  MOCKED to reject. A false comment and a test passing for an unrelated reason,
  guarding the same non-existent behaviour.
- A commit message claiming both status writes shared one lock helper "so they
  cannot drift apart again". They did not -- the supersede path hardcoded its
  own copy and the helper had one call site. Inert, but the guarantee I asserted
  did not exist.

Both are the same failure this session hit repeatedly: **a doc or comment
claiming behaviour the code does not have.** It is also why the lock UI was
wired in this bead rather than deferred -- shipping it unreachable would have
made the docs I had already written false.

## Cross-surface result

The outer review traced every changed contract into untouched consumers and
found no behavioural defect. The one I most expected to break -- the new
`editing_lock` key riding into a `metadata.json` that ships to GCS and gets
grepped by the deploy script -- is genuinely inert: both stores write metadata
verbatim, both deploy scripts read only `status`, the manifest generator reads
four named keys, and nothing in the repo validates a key set.

It did find that the contractor onboarding overlay still instructed a new
subcontractor to click a button this diff deleted, and that EDITOR_GUIDE.md
promised "Revert to draft -- always available" for a tier that can no longer do
it. Fixed here rather than deferred: that is the onboarding path for the exact
people this bead is built for.

## Follow-ups

- bd polyglot-pdf-ijntk (P1) -- per-user identity. Several deliberate
  compromises here collapse once locks can name a person rather than a role.
- bd polyglot-pdf-4ehxf -- the lock controls render only in the expanded card
  grid, not the compact strip.
- bd polyglot-pdf-iwy01 -- pre-existing: `POST /label` has the same
  read-merge-write metadata clobber the lock routes were fixed for.
