# Context-window compression (Gemini Live)

**Tracks:** backend/adapters/live_ai_gemini.py backend/config.py backend/services/form_filling_service.py

*Last updated: 2026-08-08 (the derived compression figures are RE-EXECUTED against the v4 SI (bd polyglot-pdf-6a79): floor 4289 -> window 4888 -> trigger 6388, still above the 5000 API bound so the clamp does not fire. Earlier: 2026-08-06 (docs audit bd polyglot-pdf-2zk3: corrected the TRIGGER_MARGIN_TOKENS default to 1500 and re-executed the per-form derivation against the shipped config -- on today's SI the derived trigger clears the API minimum on its own, so the clamp/retune path does NOT fire; documented the two easily-missed derivation inputs (the session's filtered tool list, and `injection_budget_tokens`); shrank the session-resumption design to record its wont-do rejection (bd polyglot-pdf-l3a.3). Continuous-DTI remains the production law of the land: `CONTEXT_COMPRESSION_ENABLED` defaults TRUE alongside `CONTINUOUS_SESSION` + `USE_DTI`, bd polyglot-pdf-7872; the sliding window is the SHIPPED default, validated by the jnjj.25 cost gate + the G3 correctness gate; the Live API hard-bounds trigger_tokens to [5000, 128000] at connect (Vertex 1007, wire-verified).
See [../journal/entries/2026-07-06-bd-x8rt-continuous-session-mode.md](../journal/entries/2026-07-06-bd-x8rt-continuous-session-mode.md).*

> **STATUS: SHIPPED as the production default (bd polyglot-pdf-7872).**
> `CONTEXT_COMPRESSION_ENABLED` defaults TRUE; the continuous whole-form session
> is bounded by the sliding window on every production connect. Sliding-window
> eviction is real and reliable on both tiers -- `gemini-3.1-flash-live-preview`
> (3/3 twenty-turn runs, 3-4 evictions each, 54-74% below the unbounded baseline
> at turn 20 -- `scripts/spikes/eycd_compression_eviction_findings.md`) and
> `gemini-2.5-flash-native-audio-preview-12-2025` (2-3 evictions each; ON
> oscillating ~2,100-3,400 vs OFF compounding to ~6,500; the `h04c` matrix). This
> overturned the 2026-06-04 dead-end verdict (bd `l3a.1`, SDK 1.38.0; the journal
> keeps that story). **Probe trap** (still relevant when re-measuring): 2.5 dies
> with `1011` after turn 1 on any probe that passes `tool_declarations=None` --
> identically with compression off, so it was never compression-related; pass the
> production tool declarations (`--tools real`) and 2.5 is stable (bd memory
> `gemini-2p5-1011-needs-tool-declarations`). Re-measure with
> `backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_matrix_sdk28.py --tools real`
> (`--tools real` is LOAD-BEARING; 20 turns is the minimum for eviction detection).

The Gemini Live API can bound its own context window server-side via
`ContextWindowCompressionConfig` (a compression *trigger* + a *sliding window*).
Related: the adapter ([voice-ai.md](voice-ai.md)), the stateless contract
([../standards/stateless-architecture.md](../standards/stateless-architecture.md)),
the PII layering ([../standards/hipaa-pii-policy.md](../standards/hipaa-pii-policy.md)),
the authoritative SDK reference ([../genai_docs/README.md](../genai_docs/README.md)),
the original exploration plan
([../archive/sprint_4_sliding-window-context_plan.md](../archive/sprint_4_sliding-window-context_plan.md)),
and the go/no-go brief that came out of it
([../archive/sliding-window-go-no-go-brief.md](../archive/sliding-window-go-no-go-brief.md)).

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

The framing that decided this was NOT "compression vs unbounded" -- it was
**compression (the continuous whole-form session) vs the section-reset machinery**.
That comparison is now RESOLVED and shipped; the table records why continuous won.
The "Section resets" column is the DEPRECATED fallback (bd polyglot-pdf-55jg).

| | Section resets (DEPRECATED fallback) | Sliding window (SHIPPED default) |
|---|---|---|
| Cost bound | Per-section: context dies at each boundary; ~3.4-3.6 KB system instruction re-sent per reset | Per-turn: conversation history capped at `target_tokens`. Under DTI the SI floor is ~one field, so the whole-form SI no longer dominates and the window is a real saving (not the ~2% wash the wyhh matrix saw under the full-form SI) |
| Session length | Bounded by the session-duration GoAway within a section (sections finish well inside it) | Context-size cap lifted; the session-duration GoAway STILL arrives (~13-15 min, bd wyhh, WITH compression evicting), handled by the GoAway -> reconnect path, which opens a FRESH session rehydrated from the client handshake (c5t / l3a.2; SDK session resumption was rejected, bd polyglot-pdf-l3a.3 wont-do) |
| Conversational continuity | Lost at every boundary (re-greeting suppressed by `vmxx` resume, but context is gone) | Preserved (subject to eviction of old turns) |
| Moving parts | Reset orchestration: `switch_to_section` finalize/restart, section chopping, carried-over `previous_spoken_names` | One server-side config; eviction timing is the server's |

**Verdict + SHIPPED (bd `polyglot-pdf-ctu8` -> `polyglot-pdf-x8rt` -> `polyglot-pdf-7872`):**
under DTI the SI floor is ~one field, so the "SI dominates -> compression is a
wash" ceiling lifts and the sliding window wins. `ctu8` measured continuous DTI +
a **3500-token window** on the real I-90 at ~$1.15/174q vs ~$2.32 for section
resets, AND more coherent (83% fill vs 47% at a too-tight 3000). `x8rt` shipped
the continuous-session mode; `7872` flipped it to the **production default**
(`CONTINUOUS_SESSION` + `CONTEXT_COMPRESSION_ENABLED` default TRUE): the whole
form runs as ONE session (single whole-form handshake, `switch_section` dropped,
section metadata suppressed) bounded by the window, composing with the GoAway
pre-emptive resume (`l3a.2`) to survive the ~13-15 min duration cap. The
section-reset machinery is now the DEPRECATED fallback (bd polyglot-pdf-55jg; see
[../standards/section-reset-deprecation.md](../standards/section-reset-deprecation.md)),
reachable only by setting the flags false.

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
- Steady state oscillates: grow to ~2,000-2,500, drop to ~770-1,600, repeat. At
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

Env-swappable in `backend/config.py`. Under DTI the window/trigger are **derived
per-form** (below); the static token values are the override:

| Setting | Purpose | Current state |
|---|---|---|
| `CONTEXT_COMPRESSION_ENABLED` | Master flag | `True` (production default, bd polyglot-pdf-7872; set `False` only for the deprecated section-reset fallback) |
| `CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR` | Size the window per-form from the rendered SI+tools floor (bd `jnjj.35`) | `True` -- on under DTI; off elsewhere |
| `CONTEXT_COMPRESSION_WINDOW_HEADROOM_TOKENS` | Tokens added ABOVE the estimated floor for the derived window | `599` (calibrated against the I-90's measured eviction floor -- see below) |
| `CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS` | Tokens added above the window for the derived trigger | `1500` (bd polyglot-pdf-7872; on today's DTI SI this derives ~4888/6388 with the clamp NOT firing -- see below) |
| `CONTEXT_COMPRESSION_TRIGGER_TOKENS` | Static `trigger_tokens` (the OVERRIDE: used when derivation is off, or no DTI SI to measure) | `5000` |
| `CONTEXT_COMPRESSION_WINDOW_TOKENS` | Static `target_tokens` to retain, `< trigger` (the OVERRIDE) | `3000` |

### Per-form window derivation (bd `jnjj.35` / A6)

`jnjj.25` proved DTI + eviction is the cost win (`-21%` on the unhappy path) and
that the calibration is **load-bearing and form-specific**: the sliding window must
sit JUST ABOVE the unevictable SI+tools floor. Too loose -> Gemini barely evicts
(`l3a`) -> no win; `<=` the floor -> compression fires turn 1. A fixed constant is
therefore wrong for any form whose floor differs. So when `USE_DTI` and
`CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR` are both on and a DTI SI is present,
`_build_live_config` derives:

```
floor   = (len(rendered SI) + len(serialized tool declarations)) / 4   # ~ tokens
window  = floor  + CONTEXT_COMPRESSION_WINDOW_HEADROOM_TOKENS + injection_budget_tokens
trigger = window + CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS
trigger = clamp(trigger, 5000, 128000)   # Live API hard bound -- see below
```

Two inputs are easy to miss and both move the result by thousands of tokens:

- **The tool declarations are the SESSION's, not the raw settings list.**
  `_build_tool_declarations` (`backend/services/form_filling_service.py:219-229`)
  drops `switch_section` whenever `CONTINUOUS_SESSION` is on (the production
  default) -- 6 declarations, not 7. Deriving against the unfiltered
  `settings.TOOL_DECLARATIONS` overstates the floor by ~92 tokens.
- **`injection_budget_tokens` is a real third addend**, passed from
  `guidance_contract.inline_injection_budget_tokens(full_schema)`
  (bd polyglot-pdf-wsao.8, consumed at `backend/adapters/live_ai_gemini.py:1787`).
  It reserves
  room for the largest per-field inline guidance injection the form can produce.
  It is `0` for a form with no `help.details`, so it is invisible on some kits and
  decisive on others -- on the W-7 it is **1652 tokens**. Without it, a
  details-bearing initiating message can exceed the assembled window and Vertex
  closes `1007` AT SESSION ASSEMBLE (the wsao.2 measured failure). It is computed
  at `backend/services/guidance_contract.py:246` and passed in from TWO sites in
  `backend/services/form_filling_service.py` -- `:478` (start) and `:1102`
  (restart); the restart site is the one that regressed wsao.2 when it was
  missed.

**The Live API enforces `trigger_tokens` within `[5000, 128000]`** (wire-verified
2026-07-05: Vertex closes the connect with `1007 "Context window trigger tokens
must be within [5000, 128000]"` -- the session never opens). The clamp exists for
forms whose derived trigger falls below that minimum; when it fires it logs
`compression_trigger_clamped_to_api_bounds` and RE-TUNES the window with the
raised trigger (`window = max(derived, trigger - TRIGGER_MARGIN)`, logged as
`compression_window_retuned_with_clamped_trigger`) -- otherwise each eviction
would chop all the way down to just above the SI floor, stripping the
current-field guidance DTI depends on (measured 2026-07-05: the 5000/2200 run
drifted post-eviction; wider windows stayed coherent).

**On the CURRENT default DTI form the clamp does NOT fire.** Even after the v4
SI diet the derivation lands well above the API minimum on its own (trigger 6388
vs the 5000 bound). Executed against the shipped config
(`derive_compression_window`, today's `DTI_SYSTEM_INSTRUCTION`, the SESSION's 6
tool declarations, headroom 599 / margin 1500): **floor 4289 -> window 4888 ->
trigger 6388** with no injection budget (i-90, f1040), and **window 6540 ->
trigger 8040** on the W-7 (injection budget 1652). These dropped ~1,390 tokens
when the v4 SI diet cut the SI 17,555 -> 11,994 chars (bd polyglot-pdf-6a79). Since every one of those
triggers is > 5000, neither the clamp nor the retune runs and neither log line
appears -- don't go looking for them on a normal session. The clamp-and-retune
path is reached only by a form with a much smaller SI floor. These numbers are
derived from the SI TEXT and the kit, so they move whenever either grows: treat
them as a point-in-time reading and RE-EXECUTE the function (with the session's
filtered tool list and the kit's injection budget) rather than trusting any
written-down figure -- including the rounded ones in
`derive_compression_window`'s own docstring. The old 2800/2200
"winning calibration" numbers were measured on AI Studio before the
`[5000, 128000]` bound existed on the connect path and no longer apply.

The floor is the **rendered (filled) SI plus the tool declarations** -- both
unevictable, both re-billed every turn -- NOT the SI template alone.

**The estimator UNDERSHOOTS the billed floor, and the headroom is calibrated to
absorb that.** The estimate is a coarse `chars/4` of the SI+tools TEXT, but
Gemini's tokenizer plus conversation framing bill MORE than `chars/4` of the raw
text. On the measured I-90 DTI run (jnjj.25 `*.meta.json`) the rendered SI is 3786
chars -> ~946 estimated tok, + ~655 tok tools = **~1601 ESTIMATED floor**, while
the live eviction landing zone was **~1978-2034 MEASURED tok** -- a ~377-tok
undershoot. The headroom default (599) is sized to cover that undershoot: on
that measurement it lifted the ~1601 ESTIMATE to a ~2200 window sitting just
above the ~1978 REAL floor. A naive small headroom (e.g. 222) would have derived
a ~1823 window -- BELOW the real floor -> compression fires turn 1 and evicts all
conversation (the Codex P1 on PR #239). The headroom is anchored to the one form
with measured eviction data; the absolute numbers above are from that
measurement's smaller SI, not today's (see the derivation reading above).
Re-measure when a second form's eviction floor is known. (`estimate_si_floor_tokens` /
`derive_compression_window` in
`backend/adapters/live_ai_gemini.py`; `~4 chars/token` is the file's coarse
estimate, and the headroom/margin bands absorb its slop -- the window only has to
land just above the floor.) The static `TRIGGER`/`WINDOW` constants are the
explicit override for the non-DTI path (a non-DTI SI has no calibrated floor, so
deriving would be guesswork). `CONTEXT_COMPRESSION_ENABLED` defaults ON (the
default-flip shipped in bd polyglot-pdf-7872, after the G2 cost + G3 correctness
gates cleared); this derivation makes the window CORRECT for the enabled default.

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
- **Session resumption -- designed, then rejected** (bd polyglot-pdf-l3a.3,
  wont-do, 2026-06-15). A design existed to adopt `session_resumption` for
  unintentional disconnects only (network drop / `GoAway`), resuming the same
  Gemini session via a client-stored handle instead of reconnecting fresh. The
  maintainer reversed course: reconnect already rebuilds full context from the
  client-owned handshake (field values + section state replay via
  `sessionStorage`), so a handle would only add non-deterministic
  conversational/prosodic continuity across an involuntary drop -- a marginal
  UX gain not worth the adapter+frontend+stateless-boundary handle-plumbing.
  `session_resumption` is not implemented anywhere in this codebase; the
  fresh-reconnect path (`vmxx`'s `is_reconnect` RESUME override) is the only
  mechanism, for every reconnect cause.

## What compression replaced -- and what it must not touch

The cost-bounding machinery, and what happened to it now that compression is the
production default (bd polyglot-pdf-7872):

| Mechanism | Location | Role | Outcome now that compression is live |
|---|---|---|---|
| Section-switch session restart | `backend/services/form_filling_service.py` `switch_to_section` | **Cost mitigation first** (kills compounding context at each boundary), context hygiene second (flushes old-section fields) | REPLACED as the production cost bound by the sliding window. `switch_to_section` itself STAYS (it is the shared continuous-reconnect primitive); the section-reset flow that drove it per-boundary is DEPRECATED (bd polyglot-pdf-55jg) |
| Artificial section chopping (sections smaller than the form's real pages) | form schemas (`frontend/public/*.json`) | Pure cost mitigation | No longer a cost mechanism -- continuous mode ignores section boundaries for the session; sections now page the UI only |
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

## Validation status -- eviction CONFIRMED on both models (SDK 2.8.0)

**3.1 (`gemini-3.1-flash-live-preview`):** eviction works. Evidence:
`scripts/spikes/eycd_compression_eviction_findings.md` (3x 20-turn runs, full
per-turn per-modality tables; 54-74% prompt reduction at turn 20) plus the `h04c`
matrix (`scripts/spikes/diag_compression_matrix_sdk28_runs.jsonl`: 3/3 controlled
20-turn on-live runs evicted, 3-4 drops each; 15/15 3.1 sessions stable across
off/on-inert/on-live arms; the matrix's 10-turn on-live runs showed no eviction,
consistent with the async lag -- see "How eviction actually behaves").

**2.5 (`gemini-2.5-flash-native-audio-preview-12-2025`):** eviction works -- on the
production-shaped config. With the real `TOOL_DECLARATIONS` passed, 3/3 twenty-turn
compression-on runs evicted (2-3 drops each, ~610-1,100 tokens plus one ~220
incremental partial, oscillating ~2,100-3,400) while compression-off compounded
to ~6,000-6,500. Note the with-tools
floor: the unevictable base (system instruction + tool declarations, ~1,137 tokens
at turn 1) sits under the retained window, so post-eviction prompts land
~2,100-2,460 against an 800-token target.

**The 2.5 "instability" was a probe artifact, not the model.** 2.5 dies with `1011
Internal error` after turn 1 on any probe passing `tool_declarations=None` --
identically across compression-off/on-inert/on-live (the OFF control), on v1alpha,
and on the `-09-2025` alias (`-latest` is 1008 not-supported). With real tool
declarations it is stable (one `1008` in 6 with-tools runs is the residual watch
item). Production always passes tools, which is why demo traffic ran clean while
every minimal probe crashed. See bd memory `gemini-2p5-1011-needs-tool-declarations`.

**What changed since the l3a.1 dead-end:** the probes are identical; the SDK moved
1.38.0 -> 2.8.0 (PR #156) and the server-side behavior changed -- most likely Google
shipped native-audio eviction between 2026-06-04 and 2026-06-11. The l3a.1
conclusion was also partially a measurement artifact (verdict keyed on
`cached_content_token_count`, which never moves). Both are reasons every
pre-cutover behavioral claim is treated as a stale hypothesis (bd memory
`pre-sdk28-findings-stale-recheck-everything`).

Enablement criteria (ALL met -- shipped as the production default, bd
polyglot-pdf-7872):

1. Production (trigger, window) chosen from measured realistic-workload curves
   (beads `4loz`/`wyhh`/`6x1y`), not probe values -- DONE (the derived
   per-form window; ctu8-validated 3500 on the I-90).
2. Behavioral integrity holds after eviction: tool-call compliance and dialog
   coherence measured before/after eviction (bead `wyhh`) -- DONE, and the G3
   correctness gate (bd polyglot-pdf-jnjj.7) confirmed no fill-accuracy
   regression vs the full-SI baseline.
3. A whole-form FLOW survives past the session-duration limit -- compression
   (context-size cap) PLUS GoAway-triggered reconnect (a FRESH session
   rehydrated from the client handshake; SDK session resumption was designed
   and rejected, bd polyglot-pdf-l3a.3 wont-do)
   (duration limit): a compression-on session is still terminated by the
   duration GoAway at ~13-15 min (bd wyhh), so the continuous flow COMPOSES
   compression with the l3a.2 GoAway pre-emptive resume -- DONE.
4. Maintainer go/no-go on the section-reset machinery -- DECIDED: section-reset
   is deprecated in place as a fallback (bd polyglot-pdf-55jg), not deleted.
