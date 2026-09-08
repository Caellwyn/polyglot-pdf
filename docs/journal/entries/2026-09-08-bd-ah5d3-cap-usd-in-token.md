---
date: 2026-09-08
bead: polyglot-pdf-ah5d3
title: "feat(links): A4 cap_usd signed into the token; socket precedence token > global (closes 4tjt7)"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 2 Track A bead A4 (sprint 22 admin-console plan, "Per-link cap in the
token" section; plan doc `docs/sprint_22_admin-console_plan.md`), closing bd
`polyglot-pdf-4tjt7`. `link_budget.py` already supported a per-form spend
ceiling (`cost_ceiling_usd_for_kit`, two kits set one at $3), but the only
caller that mattered -- the socket's client-link connect gate -- never passed
kit metadata, so every link was bounded by the $10 global regardless of its
form's own price. Resolving the per-form number at connect time would cost a
Firestore kit load on every client socket connect; this bead instead threads
the ceiling through the TOKEN, resolved once at mint (by the still-pending
bead A3) and read by the socket for free.

## What shipped

- `backend/services/link_tokens.py`: `mint_link_token` gains an optional
  `cap_usd` parameter, signed into the payload only for a real, finite,
  positive number -- a bool, NaN, +/-inf, zero, or negative value is DROPPED
  rather than signed in, because there is no way to fix a bad number baked
  into a signed token short of re-minting it. `new_jti()` splits the jti
  generation out of `mint_link_token` so bead A3's mint route can generate a
  jti, reserve a credit under it (ledger debit + `links/{jti}` record), and
  only then sign a token naming that same jti -- `mint_link_token` now
  accepts `jti=` to use a caller-supplied value instead of generating its
  own. `verify_link_token` treats `cap_usd` as optional (a pre-A4 token, or
  one minted for a kit with no resolvable ceiling, carries none) and
  independently refuses a malformed `cap_usd` it finds in an
  otherwise-validly-signed payload -- belt-and-braces against its own
  mint-time guard having a hole.
- `backend/services/link_budget.py`: new
  `cost_ceiling_usd_for_claims(claims)`, reading a client-link token's
  `cap_usd` claim with the identical defensive parsing
  `cost_ceiling_usd_for_kit` already uses (same `_positive_float` helper,
  same bool carve-out) and falling through to the global default for a
  missing or malformed claim. Precedence is token `cap_usd` > global, and
  NOTHING else -- no per-connect kit read exists anywhere in this path.
- `backend/routes/websocket_routes.py`: `_verify_ws_credential` now carries a
  verified token's `cap_usd` claim through into the claims dict it builds
  for the client-link path. The spend-ceiling gate resolves the ceiling via
  `cost_ceiling_usd_for_claims(claims)` and passes it to `check_budget` as a
  `kit_metadata`-shaped dict under `check_budget`'s own
  `KIT_COST_CEILING_KEY` -- `check_budget`'s signature is unchanged, and its
  internal re-parse of that value is a no-op pass over an already-resolved
  number.

**A real bug caught by the new tests, not just theorized:** the first draft
of `_verify_ws_credential`'s claims dict for the client-link path did not
carry `cap_usd` through from the verified payload at all (the dict was
built fresh, field by field, and `cap_usd` was simply missed). The new
end-to-end socket test (`test_a_token_WITH_cap_usd_overrides_the_global_at_
the_socket`) failed against the real code before the fix -- captured
`kit_metadata` showed the global ceiling reaching `check_budget` even for a
token minted with a $3 cap. This is exactly the kind of gap the "mutation-
verify a new test" rule exists to surface, except here it surfaced on the
FIRST run rather than needing a deliberate mutation.

**Deferred, on purpose, to bead A3:** actually resolving `cap_usd` from a
kit's `burn_cap_usd` at mint time and threading it into `mint_link_token`'s
call in `link_routes.py` is A3's job (reserve-before-sign transaction). This
bead ships the plumbing both ends need; A3 is the one caller that will
supply a real `cap_usd` value. Until A3 lands, every minted token is
uncapped exactly as before this bead, and `cost_ceiling_usd_for_claims`
falls through to the global for all of them -- verified by the "uncapped
token uses the global" test pair.

## Lessons

Nothing new generalizes beyond what CLAUDE.md scar tissue #9 (test the
tests) already covers -- this bead is a clean instance of it working as
intended: the socket-level end-to-end test caught a real wiring gap
(the missing `cap_usd` passthrough) that an isolated unit test of
`cost_ceiling_usd_for_claims` alone could never have caught, because that
function was correct in isolation the whole time. The gap was one layer
removed, in the glue code that builds the claims dict the resolver reads.

## Doc freshness

- `docs/components/auth.md` bumped: documented the token's optional
  `cap_usd` field (added to the tracked field-set list) and the socket's
  precedence rule; `Tracks:` line gains `link_tokens.py` and
  `link_budget.py`, touched substantively by this bead for the first time;
  `Last updated:` entry appended.
- `docs/components/websocket-routing.md` was flagged STALE by
  `check_doc_freshness.py` against `backend/routes/websocket_routes.py`, but
  its staleness PREDATES this branch -- the file was last touched by an
  unrelated commit (`9d1f1a34`, the Quiet/Voice mode toggle) before this
  worktree branched, and that doc's content does not cover `check_budget` or
  the spend-ceiling gate at all. This bead's own edit to
  `websocket_routes.py` (the claims passthrough + ceiling resolution) does
  not make anything in that doc wrong. Left un-bumped; reviewed and noted
  here per the closeout triage rule rather than silently skipped.
- All other stale docs `closeout_prep.py` flagged (context-compression.md,
  jit-schema.md, pdf-filling.md, tool-call-flow.md, voice-ai.md,
  ai-models.md, bead-tiers.md, hipaa-pii-policy.md, logging-and-cost.md,
  risk-rating.md, schema-key-visibility.md, section-reset-deprecation.md,
  si-reduction.md, stateless-architecture.md, terminology.md,
  validation-delegation.md, voice-and-vad.md, ws-protocol.md) track files
  this bead never touched (config.py, live_ai_gemini.py, ai_context.py, and
  others edited by unrelated concurrent work on `dev`) -- left as-is,
  out of scope for this bead.

Review outcomes recorded in the closeout ping.

## Files touched

- `backend/services/link_tokens.py` -- `new_jti()`, `jti=` and `cap_usd=`
  params on `mint_link_token`, optional `cap_usd` verify-time validation.
- `backend/tests/unit/test_link_tokens.py` -- widened exact-set tripwire
  (new capped-shape test) + coverage for `new_jti`, caller-supplied `jti`,
  and `cap_usd` mint/verify edge cases.
- `backend/services/link_budget.py` -- new `cost_ceiling_usd_for_claims`.
- `backend/tests/unit/test_link_budget.py` -- precedence + malformed-value
  coverage for the new resolver.
- `backend/routes/websocket_routes.py` -- `cap_usd` claims passthrough,
  socket ceiling resolution wired into `check_budget`.
- `backend/tests/unit/test_websocket_link_budget.py` (new) -- end-to-end
  precedence tests through the real socket handshake path.
- `docs/components/auth.md` -- `cap_usd` claim + socket precedence
  documented; Tracks line + Last-updated bumped.
