---
date: 2026-08-27
bead: polyglot-pdf-kvrfq
title: "fix(voice): stale-arrival guards for spell-back -- PTT level check, post-interrupt cooldown, delivered dedup"
tags: [postmortem, testing, hotfix]
---

## Trigger

The maintainer's live demo session just after midnight on 2026-08-26:
interrupting a spell-back clip with PTT talked over them instead of yielding,
the clip restarted after each interrupt attempt, then replayed once per
attempt after they gave up, and finally the model introduced the next field
over and over until a pause/unpause. Their hypothesis -- queueing/wiring, not
model guidance -- turned out to be exactly right, and the first (code-only)
diagnosis wrong in an instructive way.

## What shipped

**The wire-verified mechanism** (demo Cloud Run logs, project
polyglot-demo-aa709, window 2026-08-26 07:31:30Z-07:35:30Z): holding the
`name_spellback` tool response open does NOT park the model. Under user
barge-in pressure it kept emitting fresh calls while earlier ones were
unanswered; because the tool callback runs inline on the adapter receive
loop, TEN calls queued on one field and dispatched back-to-back -- each
`timing_tool_call_received` landed **3-9ms** after the previous response's
`tool_response_sent`, which no model generation latency can produce, so the
calls were sitting in the SDK receive buffer. Each unguarded arrival ran a
full fetch+play round-trip (the replays), re-engaged the spell-back mic hold
OVER the user's active PTT press (the worklet gate
`(pttModeEnabled && inputMuted) || spellbackHold` silences even an unmuted
mic, so the model never heard the "yes"), and -- once the field confirmed and
the client's pointer advanced -- five more queued calls resolved `no_value`
in 500ms, each response prompting another next-field intro. Two hypotheses
from the first diagnosis were DISCONFIRMED by the same window: zero
`GEMINI_INTERRUPTED` events (no barge-in cancellation of pending calls) and
zero `duplicate_tool_response_dropped` (no same-call-id duplication).

**The fix is client wiring only** -- three guards at the top of
`spellbackPlayer.play()`, running before any mic hold or fetch, plus a
pinned invariant:

1. a request arriving while PTT is held (new `isPttHeld` dep from the
   connection manager) is acked `interrupted` instantly; the refusal arms
   the cooldown so the guard covers the release tail of a long hold;
2. a request within `PTT_INTERRUPT_COOLDOWN_MS` (5s) of a real PTT
   interrupt (mid-clip or pre-playback) is acked `interrupted` instantly;
   cooldown refusals do not refresh the window, so a drain always
   converges;
3. a value+language delivered within `DELIVERED_DEDUP_WINDOW_MS` (3s) is
   acked `delivered` instantly (open-mic native mode has no held signal;
   this is its guard). `cancel()` (teardown) arms nothing.

No prompt/guidance changes and no receive-loop redesign: with the queue
neutralized the retry-inviting response texts have nothing to feed. Running
the spellback callback off the receive loop (so cancellations are observed
live) is noted on the bead as an explicitly deferred design option.

Nine new tests pin every guard, arming site, the non-refresh property, the
language-sensitivity of dedup, and the never-hold-while-held invariant.
Each was mutation-verified individually (guard disabled / arming dropped /
refresh added / recording dropped / language check dropped / cancel armed);
every mutation reddened exactly its own tests.

Full-suite note: the frontend full suite showed 1-2 rotating failures under
load; a clean `dev` baseline on the same machine failed SIX rotating overlay
files, and every flagged file passes in isolation -- pre-existing fork-load
flakiness, not this diff (filed as bd `polyglot-pdf-qta6l`).

Fresh-eyes triage breakdown: (folded in after the Step 5.5 loop.)

## Lessons

- **A held-open tool response is not a parked model.** The design assumed
  the model waits on the pending `FunctionResponse`; under live user audio
  it does not -- it keeps generating, including new tool calls, and a
  blocking round-trip turns those into a stale queue. Any future
  long-blocking tool design needs level-triggered arrival guards on the
  client, not just an edge-triggered interrupt. (Durable home:
  `docs/components/voice-ai.md`, the `name_spellback` bullet.)
- **The discriminating observation came from wire timing, not code
  reading.** The code-only diagnosis produced a plausible-but-wrong
  mechanism (barge-in cancellation); the 3-9ms response-to-next-call gaps in
  the production logs settled it in one query. When a duplication/ordering
  bug has both model-behavior and wiring explanations, get the wire timeline
  before theorizing -- `timing_coordinator_roundtrip` +
  `timing_tool_call_received` were enough to reconstruct the whole incident.
- **The local dev I/O log is polluted by test runs.** The backend suite
  writes into the same `backend/logs/gemini_<date>.jsonl` as real local
  sessions (sentinel values, `fss_reconnect_test` sessions, 16 suite runs
  interleaved that night), which made forensics slower and initially looked
  like the incident had been captured locally when it had not. Filed as bd
  `polyglot-pdf-m1yps`.

## Doc freshness

- `docs/components/voice-ai.md`: bumped to 2026-08-27 -- the "model stays
  parked" claim corrected to the verified behavior, the stale-arrival guards
  documented in the `name_spellback` bullet, and
  `frontend/src/shared/spellbackPlayer.ts` added to its **Tracks:** line.
- Other docs flagged STALE by the checker track files this branch did not
  touch; left as-is (pre-existing).

## Files touched

- `frontend/src/shared/spellbackPlayer.ts` -- the three stale-arrival guards,
  cooldown arming in both interrupt branches, delivered recording, new
  exported window constants, header rationale.
- `frontend/src/shared/connection.ts` -- wires `isPttHeld` (the connection
  manager's `pushToTalkHeld`) into the player deps.
- `frontend/src/shared/spellbackPlayer.test.ts` -- nine guard tests + harness
  extensions (`isPttHeld` override, clock `advance`).
- `docs/components/voice-ai.md` -- see Doc freshness.
- `docs/journal/entries/2026-08-27-bd-kvrfq-spellback-stale-arrival-guards.md`
  -- this entry.
