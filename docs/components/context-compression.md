# Context-window compression (Gemini Live)

**Tracks:** backend/adapters/live_ai_gemini.py backend/config.py backend/services/form_filling_service.py

*Last updated: 2026-06-12 (session resumption evaluated -> not adopted, GoAway done; bd polyglot-pdf-wnt/c5t). See [../journal/entries/2026-06-12-bd-wnt-session-resumption-eval.md](../journal/entries/2026-06-12-bd-wnt-session-resumption-eval.md) for the resumption no-go evaluation and [../journal/entries/2026-06-12-bd-c5t-goaway-handling.md](../journal/entries/2026-06-12-bd-c5t-goaway-handling.md) for the GoAway path. Earlier: l3a.1 root cause (compression is a no-op on native-audio).*
*Design doc for epic `polyglot-pdf-l3a` (phase 2, bead `polyglot-pdf-nv0`).*
*Implemented by `polyglot-pdf-45o`; workaround sideline owned by `polyglot-pdf-7kp`.*

> **STATUS (2026-06-04): DEAD END -- compression does NOT work on our models.**
> `ContextWindowCompressionConfig` is an unreleased/unsupported stub on the
> native-audio Live models we use: the server accepts the config but never evicts
> (bd `polyglot-pdf-l3a.1`, closed; see [Validation status](#validation-status----dead-end-compression-is-a-no-op-on-native-audio) below). The
> cost-win design that follows is the ORIGINAL premise and **did not hold** -- it is
> kept for context and in case Google later ships native-audio support. The feature
> stays `CONTEXT_COMPRESSION_ENABLED=False`. Do not re-pursue without re-verifying
> against the live endpoint first.

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

**The headline: against the status quo (unbounded), compression is a large cost
win -- it turns a quadratic cost curve linear.** Today the in-session context is
**not bounded at all**; it grows unbounded within a connection (exactly why the
`tak` spike measured 6.6x growth). Because every turn re-bills the whole context and
the context grows ~linearly with turns, **cumulative cost grows roughly
quadratically (~n^2) in session length.** A sliding window caps the per-turn context,
so once it saturates the per-turn cost is ~constant and **cumulative cost grows
linearly (~n).** Quadratic -> linear is the whole game at scale.

The compression win, then, is all three of:

1. **Cost** -- linear instead of quadratic. The gap widens without bound as sessions
   lengthen (table below): at 120 long-intake turns it's **$6.79 unbounded vs. ~$0.94
   bounded (~7x)**; at 240 turns **$26.86 vs. $1.91 (~14x)**. At deployment scale
   that is the difference between viable and runaway per-form economics.
2. **Duration** -- it lifts the 15-min audio cap; sessions can run unbounded.
3. **Simplicity / robustness** -- a single built-in server-side bound replaces any
   hand-rolled reset/restart machinery: much simpler to implement, debug, and
   reason about, and far less fragile than restart-timing logic.

The one honest caveat: a window is *not* the theoretical cost minimum. A full
context *reset* (drop to the ~271-token base) would be marginally cheaper still,
because a window retains `target_tokens` of history while a reset keeps none -- see
the reset baseline in the table. But we don't have (or want) a cost-driven reset
mechanism, and the residual gap is small next to the quadratic->linear win. **This is
a cost reduction -- a big one vs. how the system bills today.** (Directional model;
`45o` confirms with a real run.)

### Cost model: unbounded (status quo) vs. sliding window

Modeled with code from the `tak` curve (per-turn context increment, audio fraction
0.69, 3.1 pricing from `backend/config.py`). Cost is dominated by re-billed
**audio_input** (6x the text rate). The **"unbounded" row is the current system**;
the windows are the proposal. The "full reset" row is an **illustrative-only**
theoretical floor (NOT an existing code path -- the backend has no cost-driven
restart; 8 = the `tak` spike's measurement window), shown so the residual
window-vs-reset gap is visible.

**40 turns, short answers (~tak rate, +218 tok/turn):**

| Scenario | cum $ | vs unbounded |
|---|--:|--:|
| **Unbounded (current system)** | **0.462** | **100%** |
| Sliding window 2k tok | 0.212 | 46% |
| Sliding window 3k tok | 0.279 | 60% |
| Sliding window 4k tok | 0.336 | 73% |
| Sliding window 6k tok | 0.418 | 91% |
| _Full reset (illustrative floor only)_ | _0.141_ | _30%_ |

**120 turns, long intake (longer answers, +400 tok/turn) -- the case scale cares
about most:**

| Scenario | cum $ | vs unbounded |
|---|--:|--:|
| **Unbounded (current system)** | **6.793** | **100%** |
| Sliding window 2k tok | 0.678 | 10% |
| Sliding window 3k tok | 0.941 | 14% |
| Sliding window 4k tok | 1.198 | 18% |
| _Full reset (illustrative floor only)_ | _0.598_ | _9%_ |

Reading the table:

- **vs. the current system (unbounded), a sliding window saves ~3x-10x** and the
  saving grows with session length -- because it converts quadratic cumulative cost
  into linear. That is the cost case for this feature.
- A full reset would be marginally cheaper than a window (it keeps no history vs. the
  window's `target_tokens`), but that gap is small and we have no reset mechanism --
  the quadratic->linear win against the status quo is what matters.
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

Rationale: a ~3-4k window keeps enough recent history for coherent dialog while
holding per-turn cost low (the table's cost saving vs. unbounded is already large at
this size; shrinking further buys little). Our sessions peak near ~9k tokens, so the
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

## Session resumption + GoAway

`LiveConnectConfig` also exposes `session_resumption` (a `SessionResumptionConfig`
with a `handle` valid 2h) and the API sends `GoAway` before terminating a
connection. Both were deferred out of `45o` and resolved separately:

- **GoAway handling -- DONE** (`c5t`). The adapter reads `event.go_away` in the
  receive loop and the backend forwards `{"type":"go_away","time_left": ...}` to the
  client so it can reconnect ahead of the close. See
  [websocket-routing.md](websocket-routing.md) ("GoAway"). The reconnect POLICY
  (acting on the signal) is a follow-up (`l3a.2`).
- **Session resumption -- evaluated, NOT adopted** (`wnt`; conditional). The
  re-greeting that made reconnect jarring is handled at the prompt layer by the
  `is_reconnect` RESUME override (`vmxx`); and because this is a form-filler, the
  durable state is the FORM (field values + confirmations), which the
  client-owns-state design already makes lossless across reconnect. A vmxx
  reconnect loses only CONVERSATIONAL context (the last few spoken turns), which is
  low value for a field-at-a-time flow. So native resumption's win does not move the
  needle here, while it adds a 2h handle lifecycle + a stale-handle failure mode.
  (Note: the old "adds server-correlated state" objection is weaker than first
  thought -- the handle can live CLIENT-side in `sessionStorage` and pass back
  through the stateless backend, so the stateless invariant would hold.) **Re-open
  if** live verification of `vmxx` shows suppress-greeting is insufficient (e.g.
  Gemini repeats an answered question or mis-tracks the field on reconnect).

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

## Validation status -- DEAD END: compression is a no-op on native-audio (`l3a.1`, 2026-06-04)

**The cost model above is MODELED, and live validation came back NEGATIVE: compression
is a silent no-op on the native-audio Live models.** A window-size sweep
(`scripts/spikes/sweep_compression_window.py`,
`scripts/spikes/sweep_compression_window_findings.md`) found `prompt_token_count` kept
compounding (10x-14x) with compression on, even past `trigger_tokens`. The `l3a.1`
root-cause diagnostics (`scripts/spikes/l3a1_compression_rootcause_findings.md`) then
RULED OUT every config-side cause: the config serializes correctly, the server **accepts**
it (no rejection across triggers 200-4096), and behavior is **identical under `v1alpha`
and `v1beta`** (so the preview-API-version theory is wrong) and **identical on
`gemini-2.5-flash-native-audio` and `gemini-3.1-flash-live`** (so it isn't 3.1-specific).
**Conclusion: `contextWindowCompression` is accepted but never honored -- no eviction --
on any native-audio Live model reachable on this key.** Most likely it is simply not
implemented for native-audio Live models (the genai docs' compression example uses a
*cascade* model, which this key cannot reach to compare). **Keep
`CONTEXT_COMPRESSION_ENABLED=False`.** The config is plumbed and reversible: if Google
ships eviction for native-audio later, the existing flag turns it on with no code change.
The one untested branch (does it evict on a cascade model?) needs a key with cascade
Live access; until then `l3a.1` stays open as a watch item, not an active bug.

The one clean positive: **response latency was low and stable** across all window sizes
(median ~0.8-1.1s, p90 ~1.2-1.8s) -- no latency cost from enabling compression.

The original success criteria (kept as the bar `l3a.1` must clear):

1. **Prompt tokens plateau at the window size** instead of compounding. *(NOT met --
   the headline finding above.)*
2. **A session survives past the 15-min audio cap** -- the primary, non-cost win.
   *(Not yet exercised; the sweep ran short 12-turn sessions.)*
3. The measured curve matches the modeled table. *(NOT met; the model's plateau did not
   reproduce.)*

Harness reuse: the sweep captures cost from the session-end summary in `finalize()`
([logging-and-cost.md](../standards/logging-and-cost.md)) and latency from the
`on_audio` callback. The older single-config probe
(`scripts/spikes/measure_live_token_curve.py`) measured the unbounded baseline.
