---
date: 2026-08-22
bead: polyglot-pdf-ugm6
title: "Client magic links: the firm's client finally has a way in"
sprint: 19
tags: [security, architecture, testing]
---

## Trigger

The maintainer asked the deployment question directly: "is it working if I
deployed it now?" The honest answer was no -- not because the software was
broken, but because **there was no way to give a client a form.** The only
sign-in was a full Google/email account, and the one interim workaround (a
staff member handing over a signed-in machine) had been explicitly rejected
on 2026-08-17. The firm tier was complete and unusable.

The maintainer promoted this bead and four others from deferred/P3 to
pilot-blocking: "all of those are important and urgent before we start a
pilot."

## Two decisions that were the maintainer's

The bead's own notes flagged both as build-time escalations, and both were
answered 2026-08-22:

1. **Link delivery = COPY-LINK, no email.** The mint response returns the
   URL; the employee sends it through whatever channel they already use with
   that client. Rejected: wiring a transactional email provider (a provider
   choice, an API key, and SPF/DKIM verification -- and it would put the
   client's EMAIL ADDRESS in our systems, which is a client identifier and
   cuts against the split-key invariant this whole design rests on).
2. **Routing = add react-router properly**, rather than a startup branch on
   the URL fragment. The firm console (bd gob8l) needs real routes anyway, so
   the special case would have been rewritten within one bead.

## A circular dependency that had to be resolved, not obeyed

ugm6 said it was BLOCKED by the rate-limits bead (ik7e); ik7e said do NOT
start before ugm6. Unbuildable as literal ordering.

The real constraint is narrower and is about SHIPPING, not building: **a link
that is LIVE and reachable by a client must never exist without a spend
ceiling.** So ugm6 builds first (it defines the jti/firm_id claims ik7e's
limits key on -- building the limiter first would mean inventing that shape
twice), and ships with minting DISABLED BY DEFAULT behind
`LINK_MINTING_ENABLED`. ik7e is what flips it on. Neither bead reaches a
reachable environment alone.

## The bead's own spec was superseded on one point

It specified a per-firm API key, "X-Editor-Token-style". The maintainer had
just asked that this work respect the neighbouring editor-identity epic
(polyglot-pdf-ijntk) and not create contradictory or redundant systems, and
that audit killed the API key three ways:

1. **Redundant.** Firm staff already authenticate with per-user Firebase ID
   tokens carrying firm_id + firm_role (shipped by lo88, consumed by z6bk9).
   A per-firm key is a weaker second credential for callers who hold a
   stronger one.
2. **Contradictory.** Epic ijntk's child 4 DELETES the shared editor tokens
   and the X-Editor-Token path outright. Building a new shared secret is
   precisely "a new thread a future separation epic would have to cut" --
   the explicit test that epic's plan sets for any design choice.
3. **Self-defeating.** This bead's own telemetry requirement needs the
   ORIGINATING EMPLOYEE on every session. A per-firm shared secret identifies
   an organization, never a person. Only the per-user uid can.

So minting authenticates with the same per-user identity as the rest of the
firm tier, and `employee_id` comes from the verified uid -- never the request
body, which would let a caller forge attribution onto a colleague.

The collision audit also found a defect on MY side: this bead DECLARED
`backend/services/auth.py` as a surface, the file most likely to look like a
collision with an editor-auth epic. I do not modify it (I import `get_db`,
read-only). Corrected, because the collision guard reads that declaration.

## The gap that would have made the whole feature unreachable

Everything above -- token, endpoints, entry gate, routing -- and a client
still could not fill a form, because **`/ws/fill` required a Firebase ID
token**. A client has no account. The voice socket is the product.

Fixed by letting the socket resolve EITHER credential, dispatching on SHAPE:
a link token has one dot, a Firebase JWT has two. Not on a caller-supplied
hint, which would let someone opt into the weaker check. This is also what
completes the telemetry requirement for client sessions -- firm, form, and
originating employee all ride the signed link.

**A LINK NAMES ONE FORM, and the handshake is client-controlled.** A link
holder who edits `kit_id` could otherwise fill a DIFFERENT form of the same
firm -- one they were never sent. The token's kit_id wins, and a mismatch is
REFUSED rather than silently corrected: quietly substituting would produce a
signed confirmation record naming a form the client never saw, which in a
product whose value is a defensible record is worse than an error.

**Mutation found this unpinned.** Disabling the mismatch check left every
other test in the bead green. Two handshake-level tests now cover it, and
both the obvious mutation and the subtler "silently substitute" variant go
red.

## Scars from this bead

**A mutation that passes is not automatically good news.** Two examples here,
with opposite resolutions:

- *Forged attribution via the request body* passed because
  `MintLinkRequest` has no such field -- pydantic drops it. The mutation was
  structurally a NO-OP. The honest fix was to pin the property where it
  actually lives (the model's field SET), not to claim a route-level
  mutation verified it.
- *Fail-open on a network error* passed because a state variable happened to
  stay null. That is ACCIDENTAL protection and disappears on the next
  refactor. The fix was to make it structural -- the render guard now
  requires both a ready phase AND a redeemed link -- and then to verify by
  mutating THE GUARD, which reddens two tests.

The distinction is worth keeping: in the first case the code was genuinely
safe and the test needed relocating; in the second the code was accidentally
safe and needed changing. Telling them apart requires understanding WHY the
mutation survived, not just noting that it did.

**A test fake taught me a real bug.** My redemption fake returned a fixed
epoch `opened_at`, so every open 404'd -- the completion deadline was in
1970. The route had trusted the stored timestamp without validating it, which
means a corrupt or missing stamp would lock out a client who had JUST opened
their link. Now validated with a fallback to now, and pinned across six
implausible shapes.

## What is NOT done

- **Link delivery is copy-link only.** No email; that was the decision, not
  an oversight.
- **No firm-facing UI to mint from.** The button belongs to the firm console
  (bd gob8l). Today minting is an API call.
- **Minting stays OFF until bd ik7e ships the spend ceiling.** That is the
  interlock, and it is the next bead.

## Fresh-eyes r1 found two HIGH findings, and both were real

I reported the client path as complete end-to-end. It was not.

**Finding 1 -- the redeemed token was captured and DISCARDED.**
`ClientLinkEntry` called `/open`, stored the result in component state, and
rendered `SchemaFormDemo` -- which takes no props and derives its token from
`user.getIdToken()`. For a client `user` is null by design, so the WS connect
sent no token at all and `/ws/fill` (where `token` is a REQUIRED query param)
rejected it before the handler ran. A client would see "Opening your form..."
and then silently fail to connect.

The fix exposed the ENUMERATE-THE-SET trap in its textbook form. The reviewer
named SIX inline `user.getIdToken()` sites. Grepping the set found NINE --
including `usePDFDocument` and `FilledPreviewModal`, which a client-link
session needs as much as the socket. **Fixing the six named sites would have
left the client tier working on some surfaces and silently unauthenticated on
others**, which is worse than uniformly broken because it looks like it works.
All nine now route through `shared/sessionCredential.ts`, and a
source-derived test fails CI if a tenth appears.

**Finding 2 -- the socket never redeemed, and nothing ever burned a link.**
`_verify_ws_credential` checked the signature and the open window, but never
called `open_link`; `complete_link` had ZERO production callers. So the
one-time guarantee was enforced only on `/api/links/open` -- a route an
attacker need not call. Anyone holding the raw token could open unlimited
paid Gemini sessions for the full ~48h window by connecting directly. My own
auth.md and Surface contract 9 asserted the opposite.

## The scar: my fix for finding 2 crashed on every completed session

The burn reached for `claims`, which lives in `fill_form_from_schema`, while
the burn itself runs in `_handle_fill_session` -- a DIFFERENT function.
NameError on every completion.

**What let it through is the real lesson.** Grep confirmed ZERO tests
referenced `complete_link` anywhere. I had written a security fix for a
replay hole and pinned the REFUSAL side (already-used, store-unavailable,
completion-window) while leaving the BURN side -- the half that makes the
refusal ever fire -- completely untested. A guard that can never trigger is
not a guard.

Six unrelated tests in `test_proactive_complete_events.py` went red and
pointed at it, which is luck, not coverage: they happened to drive the code
path incidentally. `link_jti` is now an explicit parameter (alongside
`firm_id`, which arrives the same way), and three tests pin the burn --
completed burns, ABANDONED does not, staff never touches the store.
Re-introducing the exact NameError as a mutation now reddens 8 tests.

The abandoned case is a product decision, not a technicality: abandonment is
the COMMON case on a 40-minute immigration form, and burning the link there
would strand a client mid-intake with no recourse but to phone the firm.

## A refactor regression worth remembering

Routing nine call sites through one resolver added an `await` before
`usePDFDocument`'s fetch. That effect races its own cleanup -- an existing
test unmounts while the fetch is pending -- and one extra microtask was
enough for cleanup to win, so the fetch never started. Even
`await <non-promise>` costs a microtask. The resolver's fast path is
synchronous (returning a union type rather than being `async`), and the
racing call site awaits only when a promise is actually returned.

