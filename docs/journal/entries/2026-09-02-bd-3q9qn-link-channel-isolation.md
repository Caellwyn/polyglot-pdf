---
date: 2026-09-02
bead: polyglot-pdf-3q9qn
title: "links: isolate staging from demo -- and four rounds of verifying a proxy instead of the property"
tags: [links, staging, security, testing, review-rounds, verification]
---

## Trigger

Maintainer, 2026-09-01, deciding the question left open by bd `hvui4`:

> Staging should only mint mock-links, tied to a dev account. Never pulling from
> firm assigned accounts. That said, staging will need a mock firm to test
> related features. So, staging links only work for staging firms on the staging
> site, and same with demo.

That is broader than the bead as filed (which framed it as a shared signing key)
and reframed the work: the goal is CHANNEL ISOLATION, and staging needs a firm
identity of its own.

## What was wrong

A client link is a signed token. Before this, the payload carried no marker for
which channel minted it, so any validly-signed token opened on either backend.
Three shared surfaces:

- **Signing** -- one `LINK_TOKEN_SECRET`, no `aud` claim: a staging link
  verified on the demo.
- **Redemption** -- `link_redemptions` keyed by `jti` alone: a staging
  test-drive burned a real client's single-use link.
- **Billing** -- `record_mint` incremented `firms/{id}/link_usage/{YYYY-MM}`,
  the counter the per-link pricing bills against.

Cost today: nothing (no pilot firms). Cost the day a firm is live: a test
consumes a client's link, and the client sees a dead link with no explanation.

## What shipped

**A channel claim, not a per-channel secret.** A different key per channel also
blocks cross-channel verification -- but it fails as `bad signature`, the same
error a forged token gives, so an operator debugging a link that *should* work
is pointed at a security incident rather than a config difference. The claim
refuses with a reason. The reason goes to the LOG; the route returns the same
generic 404 for every failure, deliberately, so responses cannot be used to
probe which links exist.

**A per-channel redemption collection.** The demo keeps the bare
`link_redemptions` name so nothing already recorded is orphaned. Separate from
the claim: `aud` stops a staging link OPENING on the demo, this stops the two
channels writing over each other's ledger. `link_spend.py` imports the same
private accessor rather than re-deriving the name, so spend followed the rename
for free -- the reviewer flagged that as the one place a rename could have
silently split a link's spend from its redemption record.

**Billing needed no code.** The path is already firm-scoped, so a staging
channel minting only for its own mock firm writes elsewhere by construction.
Documented in `link_metering.py` precisely BECAUSE the isolation then rests on
provisioning rather than code -- a staging account stamped with a real
`firm_id` would still bill that firm.

**The mock firm needs no code either.** `scripts/bootstrap_firm.py` already
creates the firm document and stamps `firm_id` onto an account.

`LINK_CHANNEL` defaults to `demo` -- the safe side, so an unconfigured deploy
behaves exactly as before. Both scripts set it explicitly anyway.

## Four rounds of verifying a proxy

The feature was right early. Five review rounds went almost entirely to my
verification being wrong in the same way four times:

| # | What I verified | What I claimed | Why the proxy could not fail |
|---|---|---|---|
| 1 | the pure function `_collection_name()` | the ledger is per-channel | nothing proved the production path CALLS it -- every test swaps the accessor wholesale, so reverting the call site left 4390 tests green |
| 2 | a COUNT of stale docs (dev 25, branch 24) | I introduced no staleness | the doc I broke was ALREADY stale, so the omission could not move the count |
| 3 | `check_doc_freshness.py`'s EXIT CODE | docs clean | it prints warnings and exits 0; it had been flagging the file all along |
| 4 | that a `report_*()` call exists in `main()` | my new check works | the docstring-count test passes on existence alone -- the body could be `return` |

Each proxy was genuinely correlated with the property, which is why it felt like
verification. None could move in the failure case I cared about.

**The discriminating question, now in `bd remember` as
`verify-the-property-not-a-proxy`:** *in the exact failure I am guarding
against, would this observation CHANGE?* A count that stays 24, an exit code
that stays 0, a substring that survives inside a comment, a test that passes
when the body is deleted -- all no.

**Instance 4 is the one worth keeping**, because it is self-referential: I wrote
a check to catch the omission instance 2 had missed, and then verified that
check with a count. The reviewer found it had no tests at all, plus two real
defects (it would have fired on 54 of 93 docs that carry no stamp by
convention, and it decided "was the stamp bumped?" by substring rather than by
date, so a RENAMED doc reported clean). I reverted it. The gap is real and
stays filed as `8gixw` with the whole design; shipping a warn-only check that
cries wolf is worse than shipping none, because it teaches the reader to skip
the section.

**And then instance 5, one message after writing all that down:** my revert
read the file as text and wrote it back mis-encoded, mangling 21 em-dashes. I
had printed a check for exactly this -- and misread it. The output said
`1 file changed, 21 insertions(+), 21 deletions(-)` directly above my own label
reading `(empty = identical)`. I saw the label I had written, not the line above
it. The suite passed, because the damage was confined to comments. Fixed with
`git checkout` -- a byte copy, no decoder round-trip.

## Other things worth remembering

**A comment that was true when written and false one line later.** The staging
script said `LINK_BASE_URL` is "the ONE link value that must NOT match the
demo." My own change added a second one directly beneath it. An operator
following that comment would copy the channel name across and silently undo the
entire isolation. Twice this bead I wrote or left a comment that its own
neighbouring line contradicted.

**My session context had the wrong date.** It said 2026-09-01; git said 09-02. I
stamped three docs with yesterday's date, which is exactly why one read as stale
against code committed that morning.

**The full suite caught what targeted runs did not.** A test asserts the doc
checker's docstring lists as many checks as `main()` runs. The doc-freshness
tests and the checker itself both passed; only the full suite failed. A guard
protecting a file does not necessarily live in that file's obvious test module.

## Left open

- `8gixw` (+ dependents `pxwth`, `9ttdc`) -- the unbumped-stamp check, done
  properly.
- The billing surface is isolated by PROVISIONING, not code. Before staging is
  used in anger: create the mock firm and stamp the dev account with it.
