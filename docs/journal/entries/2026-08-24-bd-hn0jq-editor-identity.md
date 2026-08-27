---
date: 2026-08-24
bead: polyglot-pdf-hn0jq
title: "feat(auth): per-user editor identity, and two separate allowlists"
tags: [auth, review, testing]
---

## Trigger

The editor API authenticated with two shared secrets. Everyone holding the
editor token was ONE principal to the server: no user id, no attribution, no
editor-vs-editor locking, and revoking one subcontractor meant rotating the
token for everyone. Child 1 of epic `polyglot-pdf-ijntk` makes the server able
to tell people apart.

## What shipped

Per-user Firebase identity (`backend/services/editor_auth.py`), a grant/revoke
CLI that IS the allowlist (`scripts/bootstrap_editor_user.py`), and `actor=`
on every editor log line that records a mutation.

Mid-review the maintainer resolved a contradiction the reviewer had escalated
-- criterion 3 wanted BOTH directions tested, while the bead's constraint said
not to touch voice auth. Their answer was stronger than either option offered:

> "voice app accounts should be tied to firms, or a devs. editor accounts are
> separate and only tied to access to the editor and the forms in the GCS
> bucket that are not locked or deployed. Those should be 2 separate auth
> lists."

So the voice side gained its own claim check and its own enrolment tool
(`scripts/bootstrap_voice_dev.py`). The reading that had blocked this was
backwards: requiring each surface to check its OWN claim SEPARATES them
further -- it cuts a thread a future separation epic would have had to cut.

## Scar tissue

**A claimed fix that nothing pins is indistinguishable from no fix.** Seven
times across nine review rounds, a fix called done turned out to be unpinned
-- most sharply the revocation pair, where the CLI killed refresh tokens but
the verifier never passed `check_revoked`, so the tool printed "Revoked" while
the account kept working for an hour. Half a mechanism is no mechanism, and
only one half was tested.

**Verify BOTH directions of a guard, not just that it catches things.** Every
round that only checked recall missed a false positive; checking only that a
guard fires cannot distinguish a good guard from one that flags everything.
The write-classifier flagged 9 helpers when 3 write, and a genuinely read-only
route was reported as unattributed -- the failure that trains the next author
to add a noise log rather than fix anything.

**A mutation only proves something if it is the one that would actually
happen.** Two reproductions built to confirm a fix proved nothing: the helpers
were planted INSIDE the route chunk, where the guard sees the write directly,
so the fixed and broken versions failed identically. The dispositive control
put them where the real code puts them.

**Parse, do not pattern-match -- but the seam is usually the assumption, not
the mechanism.** The attribution guard was wrong four times as a regex (chunk
boundaries, a hand-listed write set, comments, then docstrings and nested
defs). Rewriting it on `ast` removed the string seams and left the real error
intact: it still only looked where I assumed. That cost two more rounds -- the
module boundary, then the directory -- before it followed imports to wherever
they point.

**Run the FULL suite, and quote a number measured on the commit you are
naming.** A signature change broke a test in a file this branch never touched;
every targeted run was green and structurally could not see it. Worse, the
number quoted for several messages predated the commit that broke it, so the
branch was red while being reported green.

**A guard that reads source from disk cannot run concurrently with edits to
that source.** A full-suite failure that would not reproduce turned out to be
probe scripts editing the parsed files mid-run. Reproduced deliberately before
believing it.

## Deliberately deferred

The lock still stores a role string, so two editors still collide -- re-scoping
it to a person is `polyglot-pdf-5tuas`. The hosted editor frontend still sends
a typed access code; the dual-header acceptance is the bridge until
`polyglot-pdf-yswp3`. An unenrolled voice account currently reads as a network
error in the browser (filed): the server names the refusal, but nothing
surfaces it, and the fix needs a product decision about what the user sees.

## Doc review (freshness gate)

`check_doc_freshness.py` reports `docs/technical_guide.md` STALE against
`deploy-demo.sh`. Both changed on 2026-08-24, and the checker compares whole
DATES, so a same-day edit to a tracked file cannot be satisfied by a same-day
stamp -- it is a granularity artifact, not a stale doc.

REVIEWED, and the guide is accurate as shipped: the two claims this diff
falsified are corrected (the deleted 503 branch, and the "only two shared
tokens" rationale for editor-vs-editor collisions), and the guide does not
describe the deploy-time enrolment reminder that triggered the flag. It also
gained an explicit `*Last updated:*` line, which it lacked -- without one the
checker fell back to the doc's commit date, making it perpetually stale
against anything touched later in the same session.

The docs already stale on `origin/dev` are untouched; they are not this PR's
to fix.
