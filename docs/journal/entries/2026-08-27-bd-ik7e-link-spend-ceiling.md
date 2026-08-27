---
date: 2026-08-27
bead: polyglot-pdf-ik7e
tags: [client-links, cost, billing, firestore, testing]
---

# The client-link spend ceiling, and why the per-firm half is not a gate

bd `polyglot-pdf-ik7e`, the last pilot blocker before the client tier could be
switched on. It is what flips `LINK_MINTING_ENABLED`: a live link is an
unauthenticated entry point to a paid Gemini session, and shipping one without
a spend bound was the thing ugm6 deliberately deferred.

## The bead named the wrong key, and it mattered

The design notes said `form_session_id` "survives reconnects and is the correct
key". It does survive reconnects -- but it is generated IN THE BROWSER
(`fss_<timestamp>_<random>`, `schemaFormState.ts`) and lives in
`sessionStorage`. A client who wants more free AI time clears storage and gets
a fresh budget. **A ceiling defeated by a page refresh is not a ceiling.**

The `jti` comes from the token we signed and cannot be forged or reset by its
holder, so that is the key. This is the same rule already load-bearing across
the client-link work: trust what we signed, never what the caller hands us.
`form_session_id` stays as the DIAGNOSTIC grouping, which is what it is
actually good for.

Two of the bead's other assumptions were already satisfied and worth recording
so nobody rebuilds them: live per-turn cost in USD already accrues
(`live_ai_gemini.py`, `_session_total_cost`), and it resets per CONNECTION --
which is exactly the reconnect hole the bead warned about, confirmed in code
rather than assumed.

## The maintainer's answer inverted the per-firm half

I had built the per-firm cap as an abuse limit and was about to enforce it.
The maintainer: *"it's going to fit into an example possible tiered
subscription model, $500/mo for 30 links. Then $15 per link after. That's why
the $10 cap ... We might offer other tiers, or pay as you go, too."*

That is a BILLING allowance, not an abuse cap, and the correct behavior
inverts: **a firm minting link 31 has paid for link 31.** Refusing it would
break a paying customer to enforce a number the maintainer explicitly called
provisional. So the per-firm side counts, flags `over_allowance` as the
billable-overage signal, and never gates. Margin is protected by the per-LINK
ceiling, which is what bounds a $15 link to $10 of AI.

The counting had to move too: the redemption record is only created when a
client OPENS a link, so counting documents would miss every minted-but-unopened
link -- exactly the set a firm was billed for. It counts at MINT.

## Four socket tests went red, and they were right

My gate refused whenever the redemption store was disabled. But
`enforce_link_redemption` already fails closed on exactly that condition and
runs FIRST on every paid door -- so it was a second refusal for one condition,
and it broke local dev and any test that stubs the redemption path. The spend
read now returns 0.0 there and defers.

The test that pinned the old behavior was rewritten to pin the real invariant:
**the ADMITTING door is the one that fails closed.**

## Testing the banking honestly cost three attempts

The gate is useless unless spend is actually RECORDED, and nothing covered
that path. The first test I wrote **mocked out the very function containing the
code under test** and passed vacuously. The rewrite that drove the real handler
**wedged in its receive loop** and had to be killed -- the honest signal that I
was building an elaborate harness to reach one small piece of logic.

So the banking was EXTRACTED into `_bank_link_spend` and tested directly, with
a SEPARATE guard, derived from the shipped route source, that the teardown
actually calls it. A perfectly tested helper nobody calls banks nothing.
Mutation-verified both ways: deleting the call reddens the wiring guard while
every helper test stays green; deleting the gate reddens the refusal test.

**The generalisable bit:** when a test needs a large harness to reach a small
decision, that is evidence the decision wants extracting -- and then the WIRING
needs its own guard, or you have moved the untested gap rather than closed it.

## A mutation that was a genuine no-op

Deleting a bool carve-out in `link_budget` reddened nothing. It turned out to
be truly redundant -- the `str()` round-trip below it already rejects `"True"`.
Removing BOTH (the realistic "why are we stringifying a number?" cleanup) makes
a `true` in metadata.json resolve to a **$1.00 ceiling**, and reddens two tests.
The redundancy is deliberate and now says so in the code, rather than carrying
a comment claiming a guard is critical when it is not.

## What is NOT done, each deliberately

- **Per-FORM ceilings** resolve and are tested in `link_budget`, but the socket
  passes the GLOBAL ceiling: threading one through costs a metadata load on
  every client connect for a feature no kit uses yet.
- **Turns-per-question as a reported diagnostic.** There is NO turn counter on
  the Live adapter -- I wrote an accessor against one, discovered it did not
  exist, and removed it rather than fake it. Cost is what enforces; the
  diagnostic needs a counter built first.
- **Mid-session termination.** The check is at CONNECT, so a single session that
  blows the ceiling mid-call runs to its end and is caught on the next connect.
  Overrun is bounded by one session, and documented at the call site.

## The bigger thing this surfaced

Asked whether a firm could refresh a client's cap, the answer was no -- and
chasing it found something worse that has nothing to do with spend:
`schemaFormState.ts` discards form state after **60 minutes** and re-initialises
with `fieldValues: {}`. A client who steps away for lunch loses their answers
today, cap or no cap. That is bd `polyglot-pdf-dft1`, which now carries the
maintainer's design: the client's own saved PDF becomes the save file (verified:
both custom metadata AND field values round-trip through PyMuPDF), with
`polyglot-pdf-1uyof` carrying `form_session_id` across a replacement link so one
client's form stays one record.
