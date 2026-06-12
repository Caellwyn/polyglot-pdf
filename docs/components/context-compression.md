# Context-window compression (Gemini Live)

**Tracks:** backend/adapters/live_ai_gemini.py backend/config.py backend/services/form_filling_service.py

*Last updated: 2026-06-12 (status flip: eviction confirmed working on 3.1 under SDK 2.8.0;
cost-motivation of section resets corrected per maintainer; epic `polyglot-pdf-hcsl`,
bead `polyglot-pdf-h04c`). Session-resumption/GoAway decisions: see
[../journal/entries/2026-06-12-bd-wnt-session-resumption-eval.md](../journal/entries/2026-06-12-bd-wnt-session-resumption-eval.md)
and [../journal/entries/2026-06-12-bd-c5t-goaway-handling.md](../journal/entries/2026-06-12-bd-c5t-goaway-handling.md).*

> **STATUS (2026-06-12): WORKING on 3.1 -- eviction confirmed on SDK 2.8.0; 2.5
> blocked by unrelated instability.** Sliding-window eviction is real and reliable on
> `gemini-3.1-flash-live-preview` given enough post-trigger runway (3/3 twenty-turn
> runs, 3-4 evictions each, ON sessions 54-74% below the unbounded baseline at turn
> 20 -- `scripts/spikes/eycd_compression_eviction_findings.md`). This overturns the
> 2026-06-04 dead-end verdict (bd `l3a.1`, SDK 1.38.0; the journal keeps that story).
> On `gemini-2.5-flash-native-audio-preview-12-2025` compression is UNTESTED: probe
> sessions die with `1011 Internal error` after turn 1 in ALL arms of a controlled
> matrix -- compression off included -- so the failure is NOT compression-related
> (classification in progress, bd `h04c`). **`CONTEXT_COMPRESSION_ENABLED` stays
> `False`** until epic `polyglot-pdf-hcsl` picks production parameters and regression-
> tests coherence. Re-run the verdict:
> `backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_matrix_sdk28.py`
> (matrix) or `... scripts/spikes/diag_compression_usage.py --trigger 1500 --window 800
> --turns 20` (single config; 20 turns minimum -- see "How eviction actually behaves").

The Gemini Live API can bound its own context window server-side via
`ContextWindowCompressionConfig` (a compression *trigger* + a *sliding window*).
Related: the adapter ([voice-ai.md](voice-ai.md)), the stateless contract
([../standards/stateless-architecture.md](../standards/stateless-architecture.md)),
the PII layering ([../standards/hipaa-pii-policy.md](../standards/hipaa-pii-policy.md)),
the authoritative SDK reference ([../genai_docs/README.md](../genai_docs/README.md)),
and the active exploration plan
([../sprint_4_sliding-window-context_plan.md](../sprint_4_sliding-window-context_plan.md)).

## Why -- and what compression actually buys us

The Live API **re-bills the entire accumulated context every turn** (the
compounding billing model in
[../genai_docs/live-api-best-practices.md](../genai_docs/live-api-best-practices.md)),
and native audio accrues tokens fast: in the 2026-06-12 twenty-turn probes the
unbounded prompt reached 4,945-5,729 tokens (18-21x the turn-1 baseline) with
**~73% of prompt tokens being audio**. Without compression, audio-only sessions are
also hard-capped at **15 minutes**.

Because every turn re-bills the whole context and the context grows ~linearly with
turns, **cumulative cost grows roughly quadratically (~n^2) in session length** when
nothing bounds it. A sliding window caps the per-turn context, so once it saturates
the per-turn cost is ~constant and **cumulative cost grows linearly (~n)**.

### The current system already pays for this -- with section resets

**Session restarts at section boundaries exist specifically to mitigate compounding
token cost** (maintainer, 2026-06-12). An unmitigated ~150-question I-90 fill would
cost on the order of **$7 in tokens**; to bound that, the form was deliberately
chopped into sections -- including **artificial sections smaller than the form's real
pages** -- so each Gemini session's context stays short and is thrown away at the
boundary. (The alternative seriously considered at the time was a new session after
EACH question.) The same cost pressure drove the JIT-schema design: never feed the
whole form schema, give the model exploration tools instead.

So the honest framing is NOT "compression vs unbounded" -- it is **compression vs
the section-reset machinery we already run**:

| | Section resets (current) | Sliding window (candidate) |
|---|---|---|
| Cost bound | Per-section: context dies at each boundary; ~3.4-3.6 KB system instruction re-sent per reset | Per-turn: context capped at `target_tokens` continuously |
| Session length | Bounded by the 15-min audio cap within a section | Cap lifted -- a whole form can be one session |
| Conversational continuity | Lost at every boundary (re-greeting suppressed by `vmxx` resume, but context is gone) | Preserved (subject to eviction of old turns) |
| Moving parts | Reset orchestration: `switch_to_section` finalize/restart, section chopping, carried-over `previous_spoken_names` | One server-side config; eviction timing is the server's |

Which side wins on real workloads -- and whether artificial section chopping can be
relaxed -- is exactly what epic `polyglot-pdf-hcsl` measures (three-arm comparison:
unbounded / section-reset emulation / sliding window, per-question token CSVs, both
models). Do not assume the answer in either direction; the maintainer's earlier cost
digging also found **text-in tokens dominated total cost** in production traffic
(the system-instruction + tool-context re-sends), so the per-reset text re-send cost
is a first-class term in that comparison, not a footnote.

## How eviction actually behaves (measured, SDK 2.8.0, 3.1)

From `scripts/spikes/eycd_compression_eviction_findings.md` (3x 20-turn runs,
trigger=1500/window=800) and the `h04c` matrix day-1 data
(`scripts/spikes/diag_compression_matrix_sdk28_runs.jsonl`):

- **Compression is an asynchronous server-side process.** Crossing `trigger_tokens`
  schedules it; the visible prompt-token DROP lands **1-3 turns later**, not on the
  next turn. Short probes miss it: 10-turn sessions (trigger crossed ~turn 7-8)
  detected eviction in only 2/3 and 0/5 of runs; 20-turn sessions detected it 3/3
  with 3-4 evictions each. **Any probe or verdict logic must allow >= 3-4 turns of
  post-trigger runway.**
- **The eviction signal is the prompt_token_count drop.** `cached_content_token_count`
  stays `None` on every turn of every run -- never key a verdict on it (the original
  l3a.1 probe did, which contributed to the dead-end misread).
- **Landing zone is above the configured target:** post-eviction prompts land at
  ~1,000-1,600 tokens against an 800-token window. Treat `target_tokens` as
  approximate, not exact.
- **Evictions can be incremental:** in 2/3 runs one compression event was spread
  across two consecutive turns (e.g. -221 then -502). Sum across adjacent drops when
  measuring.
- Steady state oscillates: grow to ~2,000-2,500, drop to ~1,000-1,600, repeat. At
  turn 20 the ON prompt was 1,402-2,254 vs OFF 4,945-5,729.

## The API (verified SDK syntax)

`docs/genai_docs/` names `ContextWindowCompressionConfig` but ships no runnable
example, so this is the canonical syntax. Introspected from the installed
`google-genai` in `backend/.venv` (2.8.0):

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

The adapter builds its config as a **dict** (see `_build_live_config` in
`backend/adapters/live_ai_gemini.py`); the optional top-level key sits alongside
`proactivity` / `realtime_input_config`:

```python
config["context_window_compression"] = {
    "trigger_tokens": <CONTEXT_COMPRESSION_TRIGGER_TOKENS>,
    "sliding_window": {"target_tokens": <CONTEXT_COMPRESSION_WINDOW_TOKENS>},
}
```

(The SDK accepts snake_case keys and aliases them to the camelCase wire form
`triggerTokens` / `slidingWindow` / `targetTokens`.)

## Parameters

All three are env-swappable in `backend/config.py` -- tuning knobs, not load-bearing
constants:

| Setting | Purpose | Current state |
|---|---|---|
| `CONTEXT_COMPRESSION_ENABLED` | Master flag | `False` until epic `hcsl` completes parameter selection + coherence regression tests |
| `CONTEXT_COMPRESSION_TRIGGER_TOKENS` | Tokens that trigger compression | Production value TBD by the epic's elbow analysis (bead `6x1y`); 1500 is the PROBE value, chosen only to make eviction observable in short runs |
| `CONTEXT_COMPRESSION_WINDOW_TOKENS` | `target_tokens` to retain (must be `< trigger`) | Production value TBD by the same analysis; 800 is the probe value |

Two anchors for the eventual choice: the trigger must leave the async eviction
enough runway below any hard limit it is protecting (it fires 1-3 turns late), and
the window must keep enough recent history for coherent dialog + correct tool calls
after eviction (the epic's behavioral-integrity measurements, bead `wyhh`).

## How compression coexists with the stateless backend

Compression operates on the **live in-session context the API holds** -- it does
**not** touch our handshake rehydration:

- On every (re)connect we still rebuild the system instruction from
  client-supplied `current_values` (see
  [../standards/stateless-architecture.md](../standards/stateless-architecture.md)).
  That path is unchanged.
- **No new server-side state.** The sliding window lives inside the Gemini session
  and dies with it. The stateless invariant ("the client is the single source of
  truth for form field values; the backend is stateless with respect to them") is
  preserved.
- PII layering: the client may store field data (it owns it); the Cloud Run backend
  never stores it (unchanged by compression); Gemini holds it ephemerally in its
  context window, and a sliding window changes only how that ephemeral context ages
  out within a connection. **Maintainer decision (2026-06-11): the PII lifetime in
  Gemini's ephemeral context is not a product concern** -- Google retains session
  context server-side for a period regardless of our session boundaries, so
  per-section resets do not meaningfully shorten its life. See
  [../standards/hipaa-pii-policy.md](../standards/hipaa-pii-policy.md) for the layer
  rules that DO bind (the backend never logs/stores field values).

## Session resumption + GoAway

`LiveConnectConfig` also exposes `session_resumption` (a `SessionResumptionConfig`
with a `handle` valid 2h) and the API sends `GoAway` before terminating a
connection. Both were resolved separately from compression:

- **GoAway handling -- DONE** (`c5t`). The adapter reads `event.go_away` in the
  receive loop and the backend forwards `{"type":"go_away","time_left": ...}` to the
  client so it can reconnect ahead of the close. See
  [websocket-routing.md](websocket-routing.md) ("GoAway"). The reconnect POLICY
  (acting on the signal) is a follow-up (`l3a.2`).
- **Session resumption -- adopt for UNINTENTIONAL disconnects only** (`wnt`). The
  decision turns on the CAUSE of the reconnect:
  - **Unintentional** (network drop / `GoAway`) -- the WebSocket genuinely closed and
    the client AUTO-reconnects. Here we WANT the context kept, so resume the same
    Gemini session. First connect opts in by setting
    `LiveConnectConfig.session_resumption = SessionResumptionConfig()` (handle=None);
    the server then emits `LiveServerSessionResumptionUpdate` messages -- capture
    `new_handle`, store it CLIENT-side (`sessionStorage`), and pass it back via
    `SessionResumptionConfig(handle=...)` on the auto-reconnect handshake. The
    reconnect is then truly invisible (same context), not merely de-greeted.
  - **Intentional reset** -- a fresh session is the POINT (clear context AND bound
    cost -- see above). Covers two shapes: (a) a SERVER-side restart that keeps the
    WebSocket open (section switch `finalize`->`start_session`; the Level-3
    idle-FAREWELL `restart_gemini_session`), and (b) a CLIENT-side WS close+reopen
    that is still intentional -- the section advance via
    `webFormConnection.startSection`/`switchToSection`. Never pass a handle on any
    of these.

  **The correct hook (verified):** the handle must ride ONLY `handleOpen`'s
  auto-reconnect handshake -- the same `resume:true` path gated on `hasConnectedOnce`
  (`webFormConnection.ts`). `startSection`/`switchToSection` deliberately BYPASS
  `handleOpen` (it early-returns while `isSectionSwitching`) and send their own
  handshake, so they get a fresh session for free as long as the handle is attached
  to the `handleOpen` path and nowhere else. (Do NOT key it on "client- vs
  server-initiated" -- `startSection` is a client-initiated reconnect that must NOT
  carry a handle.)

  Stateless invariant holds (handle lives client-side; backend stores nothing).
  `vmxx`'s `is_reconnect` RESUME override stays as the FALLBACK when no valid handle
  exists (expired >2h, or first connect). Open implementation edges (for the impl
  bead): (1) an unintentional reconnect carries both a handle AND the client's
  current form-state handshake; if the handle is stale relative to form state, prefer
  the fresh handshake as source of truth (the handle restores conversational
  continuity, not form state); (2) the idle-TIMEOUT watchdog (distinct from the
  farewell) closes the WS and requires a MANUAL user reconnect -- treat that like a
  fresh start (no handle / vmxx fallback), since the user re-initiated and the handle
  is likely expired. Decided here; implementation is a separate bead (`l3a.3`).

## What compression could replace -- and what it must not touch

The cost-bounding machinery that exists today, and its fate if the epic's go/no-go
lands on "go":

| Mechanism | Location | Role | If compression goes live |
|---|---|---|---|
| Section-switch session restart | `backend/services/form_filling_service.py` `switch_to_section` | **Cost mitigation first** (kills compounding context at each boundary), context hygiene second (flushes old-section fields) | Candidate for RELAXATION: fewer/larger sections, or no per-section restart at all -- the epic's go/no-go decides; never remove before the three-arm data is in |
| Artificial section chopping (sections smaller than the form's real pages) | form schemas (`frontend/public/*.json`) | Pure cost mitigation | Same -- candidate for consolidation if the window holds costs flat |
| Idle/UX recovery prompts (levels 1-3) + idle-timeout watchdog + farewell finalize | `backend/services/form_filling_service.py`, `backend/routes/websocket_routes.py` | UX / connection-health | **Keep** -- not cost machinery |
| `_intentional_shutdown` retry-guard | `backend/adapters/live_ai_gemini.py` | Lifecycle correctness | **Keep** |
| Carried-over `previous_spoken_names` / section history in the SI | `backend/services/form_filling_service.py`, `backend/config.py` | Client-owned rehydration (stateless contract) | **Keep** |
| Per-turn token tracking + session-end cost summary | `backend/adapters/live_ai_gemini.py` | The measurement surface for all of this | **Keep** |
| Session-readiness queue (`_session_ready` + pending) | `backend/adapters/live_ai_gemini.py` | Connect race fix, orthogonal | **Keep** |

Related design idea on file (maintainer, 2026-06-12): a **2.5 -> 3.1 mid-session
failover** -- default to 2.5 for its much lower turn latency, and on a `1011` from
the 2.5 backend immediately open a 3.1 session rehydrated from client state for a
seamless model switch (bd `polyglot-pdf-3v5m`). The stateless handshake makes this
architecturally cheap; it is a separate bead, not part of the compression epic.

## Validation status -- eviction CONFIRMED on 3.1; 2.5 blocked by unrelated 1011s

**3.1 (`gemini-3.1-flash-live-preview`):** eviction works. Evidence:
`scripts/spikes/eycd_compression_eviction_findings.md` (3x 20-turn runs, full
per-turn per-modality tables; 54-74% prompt reduction at turn 20) plus the day-1
matrix (`scripts/spikes/diag_compression_matrix_sdk28_runs.jsonl`: 15/15 3.1
sessions stable across off/on-inert/on-live arms; its 10-turn on-live runs showed no
eviction, consistent with the async lag -- see "How eviction actually behaves").

**2.5 (`gemini-2.5-flash-native-audio-preview-12-2025`):** compression untestable so
far. In the day-1 matrix, 14/15 2.5 probe sessions died with `1011 Internal error`
after turn 1 **identically across compression-off, on-inert, and on-live arms** --
the OFF control proves the failure is NOT compression-related. Whether it is
transient server-side instability (the bd `daa` class), specific to this probe
configuration (no tools / minimal SI -- the 4sv7 reliability spike WITH the full
tool config got clean 2.5 sessions on 2026-06-11), or routing/alias-sensitive, is
the open classification question of bd `h04c` (day-2 matrix adds alias, api-version,
and with-tools cells).

**What changed since the l3a.1 dead-end:** the probes are identical; the SDK moved
1.38.0 -> 2.8.0 (PR #156) and the server-side behavior changed -- most likely Google
shipped native-audio eviction between 2026-06-04 and 2026-06-11. The l3a.1
conclusion was also partially a measurement artifact (verdict keyed on
`cached_content_token_count`, which never moves). Both are reasons every
pre-cutover behavioral claim is treated as a stale hypothesis (bd memory
`pre-sdk28-findings-stale-recheck-everything`).

Success criteria for ENABLING in production (owned by epic `hcsl`):

1. Production (trigger, window) chosen from measured realistic-workload curves
   (beads `4loz`/`wyhh`/`6x1y`), not probe values.
2. Behavioral integrity holds after eviction: tool-call compliance and dialog
   coherence measured before/after eviction events (bead `wyhh`).
3. A session demonstrably survives past the 15-min audio cap with compression on
   (the headline product win -- whole form in one session).
4. Maintainer go/no-go on relaxing the section-reset machinery, decided on the
   three-arm cost data (bead `6x1y`).
