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

**Cross-surface (Opus) fresh-eyes review, round 1: 1 blocker, fixed.** Both
rubric items (the socket-precedence test intent, the malformed-mint/read-time
exact-set tripwire) scored PASS, independently mutation-verified by the
reviewer against a scratch copy of the passthrough bug. One blocker: the
"Two kits declare a per-form ceiling today... their links are now bounded at
$3" comment added at `websocket_routes.py:1449-1451` stated present-tense
production behavior that this diff does not deliver -- `link_routes.py`
(untouched by this PR) still calls `mint_link_token` with no `cap_usd=`
argument, so w7/i-90 links remain on the $10 global until A3 lands, exactly
as this same entry's "Deferred, on purpose" paragraph and `link_budget.py`'s
own docstring both already said. Fixed by rewriting the comment to match:
it now says the two kits declare a ceiling but A3 (still open, blocked by
this bead) is what would actually put `cap_usd` on their tokens, and until
then they fall through to the global like any uncapped token. No other
findings; no beads filed (the one finding was this diff's own added text,
fixed inline rather than deferred). Full backend suite (3331 passed, 72
skipped) and root suite (1397 passed, 46 skipped) re-run clean after the
fix; comment-only change, no test/mutation-verify needed.

**Cross-surface (Opus) outer review, round 2: 1 blocker + 2 nits, blocker
fixed, both nits ADOPTED as filed beads (no code change here).**

- **ADOPT (fixed): `websocket_routes.py:1462` resolved the ceiling directly
  on the event-loop thread.** `cost_ceiling_usd_for claims(claims)` was a
  bare synchronous call sitting outside the `asyncio.to_thread(check_budget,
  ...)` call immediately below it -- for an uncapped token (every token
  until A3 lands) it falls through to `default_cost_ceiling_usd()` ->
  `runtime_config.link_cost_ceiling_usd()`, which on a cold 45s-TTL cache is
  a blocking sync Admin-SDK Firestore read. This is the exact hazard
  `link_routes.py:141-147` and `auth.py:293-296` already document for the
  same `runtime_config` call, and pre-this-bead the same resolution happened
  *inside* `check_budget`'s own `to_thread` call -- so the diff had hoisted
  a previously-threaded blocking read onto the shared Cloud Run loop,
  stalling every other concurrent request (in-flight audio included) on a
  cold-cache connect. Fixed by folding both calls into ONE local closure,
  `_resolve_ceiling_and_check_budget`, passed as the single callable to
  `asyncio.to_thread` -- the ceiling resolution and the budget check now run
  together, off the loop, exactly as they did before this bead touched the
  call site. New test
  `test_ceiling_resolution_runs_OFF_the_event_loop_thread` in
  `test_websocket_link_budget.py` captures the thread id
  `cost_ceiling_usd_for_claims` actually runs on and asserts it differs from
  the test coroutine's own thread; mutation-verified by reverting to the
  bare pre-fix call (ceiling resolved outside the thread) and confirming the
  new test reddens (`AssertionError: ... assert 38652 != 38652`), then
  restoring.
- **DEFER (filed, not fixed here): the global ceiling is resolved twice per
  client connect.** `cost_ceiling_usd_for_claims` calls
  `default_cost_ceiling_usd()`, then `check_budget` -> `_ceiling_for` ->
  `cost_ceiling_usd_for_kit` calls it again unconditionally before even
  looking at the key -- correctness is unaffected (idempotent parse of an
  already-good number) but it doubles cold-cache Firestore reads on the paid
  gate. Filed as `polyglot-pdf-ysg9e`; the cheapest fix (an
  already-resolved `ceiling_usd:` parameter on `check_budget` that
  short-circuits `_ceiling_for`) also cleans up the `{KIT_COST_CEILING_KEY:
  ...}` shape the reviewer separately called cosmetic-but-misleading, folded
  into that bead's exit criteria rather than raised twice.
- **DEFER (filed, not fixed here): three untouched tier-2 doc passages
  restated the pre-A4 contract and were now wrong about the code.**
  `docs/technical_guide.md:776-783` and `:845-848`, plus
  `docs/components/config-deployment.md:192-196`, all asserted the socket
  "passes no kit metadata" / per-form caps are "declared-but-inert" /
  the mechanism is "the handshake" -- all three were true before this bead
  and false after it (bead `polyglot-pdf-4tjt7`, which those passages named
  as still-open, is closed by this one). `docs/components/auth.md` was
  updated thoroughly by the original diff; these two files restating the
  same contract were missed (CLAUDE.md scar #8 -- the set, not the
  instance). Reported as a GAP (a tier-1/2 doc making a wrong current-state
  claim), not merely filed: fixed directly in this round rather than only
  filing `polyglot-pdf-ebm6a` -- both passages in `technical_guide.md` and
  the one in `config-deployment.md` now describe the token-`cap_usd`-over-
  global precedence and name bead `ah5d3`/`4tjt7` correctly; both files'
  `Last updated:` parentheticals gained an `ah5d3` entry.
  `check_doc_freshness.py` confirms both files `OK` and the wrong-claim
  strings (`grep -rn "passes no kit metadata\|declared-but-inert\|not yet
  threaded through the handshake" docs/`) no longer appear anywhere in
  `docs/`.

Full backend suite re-run clean after the round-2 fixes: 3332 passed, 72
skipped, 3 deselected (was 3331/72 before this round's one added test).
Root suite: 1397 passed, 46 skipped, unchanged.

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
  socket ceiling resolution wired into `check_budget`; round-2 fix folds
  the ceiling resolution and `check_budget` into one `to_thread`-run
  closure so neither runs on the event loop.
- `backend/tests/unit/test_websocket_link_budget.py` (new) -- end-to-end
  precedence tests through the real socket handshake path; round-2 adds a
  thread-identity test pinning the off-loop-thread property.
- `docs/components/auth.md` -- `cap_usd` claim + socket precedence
  documented; Tracks line + Last-updated bumped.
- `docs/technical_guide.md` -- round-2: two passages (`:776-783`,
  `:845-848`) rewritten from the stale pre-A4 "socket passes no kit
  metadata" / "not yet threaded through the handshake" claims to the actual
  token-`cap_usd`-over-global precedence; `Last updated:` gained an `ah5d3`
  entry.
- `docs/components/config-deployment.md` -- round-2: the "declared-but-
  inert" passage (`:192-196`) rewritten the same way; `Last updated:`
  gained an `ah5d3` entry.
