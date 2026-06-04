# Context-window compression (Gemini Live)

**Tracks:** backend/adapters/live_ai_gemini.py backend/config.py backend/services/form_filling_service.py

*Last updated: 2026-06-03.*
*Design doc for epic `polyglot-pdf-l3a` (phase 2, bead `polyglot-pdf-nv0`).*
*Implemented by `polyglot-pdf-45o`; workaround sideline owned by `polyglot-pdf-7kp`.*

The Gemini Live API can bound its own context window server-side via
`ContextWindowCompressionConfig` (a compression *trigger* + a *sliding window*).
This doc is the design `45o` implements against and the hand-off contract telling
`7kp` which of our manual context-bounding workarounds it may sideline. Related:
the adapter itself ([voice-ai.md](voice-ai.md)), the stateless contract
([../standards/stateless-architecture.md](../standards/stateless-architecture.md)),
the PII layering ([../standards/hipaa-pii-policy.md](../standards/hipaa-pii-policy.md)),
and the authoritative SDK reference ([../genai_docs/README.md](../genai_docs/README.md)).

## Why -- and what compression actually buys us

The Live API **re-bills the entire accumulated context every turn** (the
compounding billing model in
[../genai_docs/live-api-best-practices.md](../genai_docs/live-api-best-practices.md)),
and native audio accrues ~25 tokens/sec. The `tak` spike
(`scripts/spikes/tak_token_curve_findings.md`) measured this on real audio: over 8
short turns, prompt tokens compounded **6.6x (271 -> 1,799)** and per-turn cost rose
~4.8x purely from re-billed history. Without compression, audio-only sessions are
also hard-capped at **15 minutes**.

But the honest framing matters here: **compression is not primarily a cost win for
us.** Today the in-session context is **not bounded at all** -- it grows unbounded
within a connection (which is exactly why the `tak` spike measured 6.6x growth).
The closest thing to a context reset we have is the **section-switch restart**
(`switch_to_section`, which finalizes + restarts Gemini at a section boundary to
flush old-section fields) -- but that is driven by section boundaries, not by turn
count or cost, and it is an *intentional* reset we keep. When you model a
**periodic context reset** as a cost baseline (below), it beats any sliding window,
because a full reset drops context to the ~271-token base while a window only
plateaus at the window ceiling. So compression is chosen for:

1. **Duration** -- it lifts the 15-min audio cap; sessions can run unbounded.
2. **UX** -- no audible mid-call restart + re-greeting (a periodic full reset would
   cause a perceptible gap; compression evicts silently).
3. **Simplicity** -- a built-in bound beats hand-rolled reset/restart timing.

Cost ends up roughly on par with -- slightly worse than -- a periodic full reset.
Do not sell compression as a cost reduction.

### Cost model: window sizes vs. unbounded vs. a periodic reset

Modeled with code from the `tak` curve (per-turn context increment, audio fraction
0.69, 3.1 pricing from `backend/config.py`). Cost is dominated by re-billed
**audio_input** (6x the text rate). The "reset every 8 turns" row is an
**illustrative cost baseline -- NOT an existing code path** (the backend has no
turn-count restart; 8 = the `tak` spike's measurement window). It models what a full
context reset would cost, as the lower bound a sliding window is compared against.
Cumulative $ shown as a fraction of the two baselines:

**40 turns, short answers (~tak rate, +218 tok/turn):**

| Scenario | cum $ | vs unbounded | vs reset-baseline |
|---|--:|--:|--:|
| Unbounded (no compression) | 0.462 | 100% | 329% |
| **Periodic reset every 8 turns (illustrative baseline)** | **0.141** | **30%** | **100%** |
| Sliding window 2k tok | 0.212 | 46% | 151% |
| Sliding window 3k tok | 0.279 | 60% | 199% |
| Sliding window 4k tok | 0.336 | 73% | 239% |
| Sliding window 6k tok | 0.418 | 91% | 298% |

**120 turns, long intake (longer answers, +400 tok/turn) -- the case compression
should favour most:**

| Scenario | cum $ | vs unbounded | vs reset-baseline |
|---|--:|--:|--:|
| Unbounded | 6.793 | 100% | 1136% |
| **Periodic reset every 8 turns (illustrative baseline)** | **0.598** | **9%** | **100%** |
| Sliding window 2k tok | 0.678 | 10% | 113% |
| Sliding window 3k tok | 0.941 | 14% | 157% |
| Sliding window 4k tok | 1.198 | 18% | 200% |

Reading the table:

- **Bounding context at all is the big win** -- both compression and a periodic reset
  beat unbounded by up to ~11x in long sessions.
- **A full reset beats every window size on pure cost**, because it drops to the
  ~271-token base, not the window ceiling. The closest a window gets is 2k @ 113% of
  the reset baseline.
- **The docs' example 25k trigger never fires for us.** In the 40-turn scenario the
  unbounded prompt peaks at only ~9k tokens (271 + 218 x 40), far below the 25k the
  best-practices doc assumes; even the 120-turn scenario peaks ~48k. A 25k/8k config
  is effectively a no-op in short sessions; useful windows are 2k-4k. **In practice
  the 15-min audio cap, not a turn count, is what bounds real session length** -- so
  `45o` must re-measure with compression on rather than assume the 9k figure.

The model is a single-session directional baseline; `45o` validates it with a real
re-run (see Validation).

## The API (verified SDK syntax)

`docs/genai_docs/` names `ContextWindowCompressionConfig` but ships no runnable
example, so this is the canonical syntax for `45o`. Introspected from the installed
`google-genai` in `backend/.venv`:

```python
# google.genai.types
LiveConnectConfig(
    ...,
    context_window_compression=ContextWindowCompressionConfig(
        trigger_tokens=...,                 # int; tokens (before a turn) that trigger compression
        sliding_window=SlidingWindow(
            target_tokens=...,              # int; tokens to KEEP. Must be < trigger_tokens.
        ),                                  # if target_tokens unset, trigger_tokens/2 is assumed
    ),
)
```

The adapter builds its config as a **dict** (see `_run_session_loop` in
`backend/adapters/live_ai_gemini.py`), so the implementer adds one optional
top-level key alongside `proactivity` / `realtime_input_config`:

```python
config["context_window_compression"] = {
    "trigger_tokens": <CONTEXT_COMPRESSION_TRIGGER_TOKENS>,
    "sliding_window": {"target_tokens": <CONTEXT_COMPRESSION_WINDOW_TOKENS>},
}
```

(The SDK accepts snake_case keys and aliases them to the camelCase wire form
`triggerTokens` / `slidingWindow` / `targetTokens`.)

## Chosen parameters

Make all three env-swappable in `backend/config.py` so they are tuning knobs, not
load-bearing constants:

| Setting | Purpose | Recommended start |
|---|---|---|
| `CONTEXT_COMPRESSION_ENABLED` | Master flag; also gates the sideline of the old hack (see below) | `False` until validated |
| `CONTEXT_COMPRESSION_TRIGGER_TOKENS` | Tokens that trigger compression | `~5000` |
| `CONTEXT_COMPRESSION_WINDOW_TOKENS` | `target_tokens` to retain (must be `< trigger`) | `~3000-4000` |

Rationale: the table shows a ~3-4k window is where the duration/UX win lands without
cost ballooning toward unbounded, and our sessions peak near ~9k tokens so the
trigger must be **low** (~5k) to ever fire -- the docs' 25k example would be inert.
`45o` re-runs the `tak` probe and tunes from there.

## How compression coexists with the stateless backend

The load-bearing concern this bead exists to resolve. Compression operates on the
**live in-session context the API holds** -- it does **not** touch our handshake
rehydration:

- On every (re)connect we still rebuild the system instruction from
  client-supplied `current_values` (see
  [../standards/stateless-architecture.md](../standards/stateless-architecture.md)).
  That path is unchanged.
- **No new server-side state.** The sliding window lives inside the Gemini session
  and dies with it. The stateless invariant ("the client is the single source of
  truth for form field values; the backend is stateless with respect to them") is
  preserved.

### PII across the three layers

The "backend never stores PII" rule is specifically about the **Cloud Run** layer.
The three layers differ, and compression changes one of them:

| Layer | PII/PID handling |
|---|---|
| **Client** (browser) | *May* store it (`sessionStorage`), and may print / save / send it -- it owns the data. |
| **Cloud Run backend** | **Never** stores it. In-memory, in-transit only. **Unchanged by compression.** |
| **Gemini** | *May* hold it **ephemerally in its context window**. |

Enabling a sliding window changes *how* PII ages out of **Gemini's** ephemeral
context: it is evicted on the sliding-window schedule rather than only at a
section-switch restart or a session teardown. This is a different (generally
*longer*-lived within a connection) eviction profile, but it is still Gemini-side
and ephemeral -- inherent to using the Live API at all. It is called out here so the
change is a conscious, documented choice, not a silent one. See
[../standards/hipaa-pii-policy.md](../standards/hipaa-pii-policy.md).

## Session resumption + GoAway -- deferred

`LiveConnectConfig` also exposes `session_resumption` (a `SessionResumptionConfig`
with a `handle` valid 2h) and the API sends `GoAway` before terminating a
connection. **Both are deferred out of `45o`**, filed as separate beads:

- **Session resumption** is redundant with -- and in mild tension with -- our
  stateless design: our reconnect is already lossless via client-owned rehydration,
  so a server-side 2h handle reintroduces server-correlated session state we
  deliberately avoid. Not adopted.
- **GoAway handling** (graceful pre-termination UX) is worth a small follow-up but
  is not required for the compression win.

## Workaround sideline map (hand-off to `7kp`)

**Important correction for `7kp`:** an audit of the current backend found that we
**never actually built a cost-motivated context-bounding restart.** The mechanisms
that *look* like candidates are all driven by other concerns:

- The **idle-timeout watchdog** (`WS_IDLE_TIMEOUT_SEC` in `backend/config.py`,
  watchdog in `backend/routes/websocket_routes.py`) sends an `idle_timeout` message
  and **closes the WebSocket** on inactivity. It does **not** call `finalize`, and it
  is a connection-health / UX mechanism, not cost-bounding. **Keep it.**
- The **Level-3 "farewell" finalize** (`finalize_gemini_session`, dispatched at
  `backend/routes/websocket_routes.py` on a frontend `finalize_gemini_session`
  message; timing in `backend/services/callback_handler.py`) is **frontend-initiated
  after the goodbye prompt** -- a UX flow, not a cost timer. **Keep it.**
- The **section-switch restart** (`switch_to_section`) is an intentional context
  reset at a section boundary. **Keep it.**

So there is **no cost-bounding hack for compression to retire** -- today the context
simply grows unbounded (the `tak` curve). That means `7kp`'s scope shrinks to a
verification/cleanup pass rather than a removal: confirm no restart path exists that
was *implicitly* bounding cost, and coordinate with `polyglot-pdf-umv`. The epic
title ("replace manual disconnect/restart hacks") was written before this audit; the
"hacks" turned out to be UX/lifecycle mechanisms that stay. Gate compression itself
behind `CONTEXT_COMPRESSION_ENABLED` so the *new* behaviour (bounded vs. unbounded
context) is one env var from reverting; nothing existing needs sidelining.

**Keep active regardless of the flag:**

| Mechanism | Location | Why it stays |
|---|---|---|
| Section-switch restart (finalize + restart to flush old-section fields) | `backend/services/form_filling_service.py` `switch_to_section` | Intentional context *reset*, not cost-bounding. A window carries stale fields until evicted; we want them gone at the switch. (Coordinate with `polyglot-pdf-umv` -- restart-loses-section-metadata -- which may become moot.) |
| Idle/UX recovery prompts (levels 1-3) + idle-timeout watchdog + farewell finalize | `backend/services/form_filling_service.py`, `backend/routes/websocket_routes.py` | UX / connection-health concerns, not cost-bounding. |
| `_intentional_shutdown` retry-guard | `backend/adapters/live_ai_gemini.py` | Lifecycle correctness, unrelated to context size. |
| Carried-over `previous_spoken_names` / section history in the SI | `backend/services/form_filling_service.py`, `backend/config.py` | This is client-owned rehydration -- the stateless contract, not a hack. |
| Per-turn token tracking + session-end cost summary | `backend/adapters/live_ai_gemini.py` | The measurement surface for the compression win. |
| Session-readiness queue (`_session_ready` + pending) | `backend/adapters/live_ai_gemini.py` | A connect race-condition fix, orthogonal to context size. |

## Validation (for `45o`)

Re-run the `tak` probe with compression on:

```
PYTHONPATH=. backend/.venv/Scripts/python.exe scripts/spikes/measure_live_token_curve.py \
    --turns 8 --runs 1 --csv scripts/spikes/tak_token_curve.csv
```

Success criteria:

1. **Prompt tokens plateau at the window size** instead of climbing 6.6x.
2. **A session survives past the 15-min audio cap** -- the primary, non-cost win.
3. The measured curve roughly matches the modeled table above (confirming the model
   held); tune `trigger`/`window` from there.

Reuse the existing session-end cost summary in `finalize()`
([logging-and-cost.md](../standards/logging-and-cost.md)) as the measurement surface.
