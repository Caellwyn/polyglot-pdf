# Validation delegation (cheap-model validator) -- frozen contract

**Tracks:** backend/adapters/live_ai_gemini.py backend/adapters/text_ai_gemini.py backend/ports/live_ai_port.py backend/ports/text_ai_port.py backend/dependencies.py backend/utils/field_validator.py backend/services/validator_service.py backend/config.py

*Last updated: 2026-07-13 (bd polyglot-pdf-ny4s (W4, async validator): the `steered` marker is NOT session-permanent -- the client RE-ARMS it (clears it) when a field's value changes in the updateField write path, so a correction re-enters the validator net; an unchanged edit keeps it (no-nagging). See the `steered` contract-2 note.). Prior: 2026-07-05 (bd polyglot-pdf-mpoe staleness sweep: contract 5 now shows `ITextAI.ask()` alongside `validate()` -- the port grew a second method for the A-pillar secretary and the doc's "single method is enough" line was stale; also refreshed stale line-number pointers into `webFormConnection.ts` / `form_filling_service.py` / `config.py` that had drifted from later commits; added `backend/ports/text_ai_port.py` to Tracks). See [../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md](../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md).*


This is the FROZEN interface for pillar B of the SI-reduction epic: a separate,
cheap `gemini-2.5-flash-lite` TEXT model (the "validator") that, at section and
form boundaries, reads the client's current form state and catches cross-field
contradictions (zip-vs-state, contradictory addresses, future-dated births) that
field-level validation cannot see. It exists so the LIVE voice model no longer
has to carry the in-system-instruction ADDRESS-CONSISTENCY check itself -- that
prose is what pillar B replaces.

Multiple agents build B's beads (B2-B5) against the shapes frozen here, so they
can work in parallel without colliding on the verdict / payload / steering
contracts. This doc owns: the verdict shape, the minimal client-state payload, the
steering-message shape, the proactive section/form-complete events' PAYLOAD
shapes, the `ITextAI` port boundary, the `MODEL_LABELING` reuse-vs-rename call,
and the PII/PHI data-flow sign-off.

Sibling contracts:
- The SI-shape contract and the ADDRESS-CONSISTENCY removal ownership live in
  [si-reduction.md](si-reduction.md) (F1) -- this doc does NOT duplicate that
  handoff; it owns the validator's wire shapes.
- The WebSocket message-TYPE registry (the reserved type names for the
  section-complete / form-complete events) lives in
  [ws-protocol.md](ws-protocol.md) (F2). **F2 owns the
  type names; F3 (this doc) owns the PAYLOAD shapes those messages carry.**
- The model-selection rule (which model, why flash-lite) lives in
  [ai-models.md](ai-models.md).
- The logging discipline this doc signs off against lives in
  [hipaa-pii-policy.md](hipaa-pii-policy.md).

---

## Current state: text-model path wired (jnjj.14)

The Live API path (audio + tool-calling) is unchanged:

- Port: `backend/ports/live_ai_port.py::ILiveAI` (with the `LiveAISession` Protocol).
- Adapter: `backend/adapters/live_ai_gemini.py::LiveAIGemini`.
- Wiring: `backend/dependencies.py::get_live_ai()` constructs a fresh `LiveAIGemini`
  per WebSocket connection.

The **text-generation path** was added in bd polyglot-pdf-jnjj.14:

- Port: `backend/ports/text_ai_port.py::ITextAI` -- two methods:
  `validate(payload) -> verdict` (B-pillar validator) and `ask(query, context) -> str`
  (A-pillar secretary, implemented in jnjj.45: maps a prose form query to a prose
  answer over the whole-form catalog + current values; fail-open `""` on error so
  the principal asks the user directly).
- Adapter: `backend/adapters/text_ai_gemini.py::TextAIGemini` -- mirrors
  `LiveAIGemini`'s three-way client construction (Vertex/AI-Studio/bare). Calls
  `client.aio.models.generate_content`, NOT the Live bidi path. Accepts
  `stable_prefix` + `fresh_tail` separately so the leading token sequence is stable
  for implicit caching; logs `cached_content_token_count` on every call (`cache_hit`
  bool) for observability. **Model-fallback (jnjj.42, hardened jnjj.45/j268):**
  `_generate()` walks an ordered LITE-tier Gemini chain (configured model ->
  `DEFAULT_FALLBACK_MODELS`: just `gemini-3.1-flash-lite`) on a transient
  availability error (5xx, or 404/429). The chain stays lite-tier ON PURPOSE
  (cost) -- the full `gemini-flash-latest` is NOT a fallback, and the invalid
  `gemini-flash-lite-latest` string was removed (j268). Auth/config 4xx
  (400/401/403) AND lite-chain exhaustion are LOGGED at ERROR (PII-free: type +
  status code + model) then re-raised for the caller's fail-open -- never masked,
  never escalated to a pricier model. Logs the serving model + `is_fallback`.
  `validate()`/`ask()` fail-open is preserved (fallback just fires it less).
  Chain is all-Gemini (BAA-safe). **Secretary `ask()` (jnjj.45):** builds the
  request as a BYTE-STABLE `[SECRETARY_SI + render_static_catalog(schema)]` prefix
  (the implicit-cache target, never mutated within a session) + an APPEND-ONLY
  `[render_values_tail(...) + the prose query]` tail, calls `_generate`, and
  returns the model's `answer` prose. PII-safe logging (ids/counts/lengths only,
  never the query / values / answer). The renderers live in
  `backend/services/secretary_context.py` (jnjj.45a). The blocking call is
  timeout-guarded by `FormFillingService.handle_ask_secretary` (jnjj.45c).
- Wiring: `backend/dependencies.py::get_text_ai()` constructs a fresh `TextAIGemini`
  reading `settings.MODEL_LABELING` (default `gemini-2.5-flash`; set
  `MODEL_LABELING=gemini-2.5-flash-lite` in deploy env for the lite validator tier).

`MODEL_LABELING` is no longer orphaned -- `get_text_ai()` is its live consumer. The
original field-labeling normalizer it was named for is still deprecated (`config.py`,
the `MODEL_LABELING` field comment).

Field-level validation is **per-value only**: `backend/utils/field_validator.py`
checks one value against its own schema constraints; the frontend mirror is
`frontend/src/schema-forms/utils/validation.ts`. **Neither does cross-field
contradiction detection** -- that gap is filled by the B-pillar validator service,
`backend/services/validator_service.py::ValidatorService` (jnjj.15, "B3"). It
renders the contract-2 client-state payload (`render_validator_payload`) into the
flash-lite request, calls `ITextAI.validate()`, and returns the contract-1 verdict;
fail-OPEN on any timeout/error/bad-shape (contract 6). The contradiction prompt
(`CONTRADICTION_SI`) reproduces the FLASH_LITE_PROMPT the G1 keystone probe
(jnjj.5) scored GO. The service is standalone -- wiring it to the boundary events
(contract 4) is B4 (jnjj.16) + B5 (jnjj.17).

---

## Frozen contract 1 -- Verdict shape

The validator's text output, parsed into:

```json
{
  "conflicts": [
    {
      "field_ids": ["addr_state", "addr_zip"],
      "reason": "State is West Virginia but ZIP 50301 is in Iowa."
    }
  ]
}
```

- `conflicts`: a list, **empty `[]` when no contradiction is found** (the
  no-conflict verdict). An empty list is the explicit "all clear" signal, not a
  missing key.
- Each conflict carries:
  - `field_ids`: the field IDs the conflict implicates -- **1 or more** (always
    field IDs, never field values -- IDs are the safe-to-log handle per the PII
    policy). Cross-field contradictions (zip-vs-state) carry 2+; a SINGLE-field
    semantic error (e.g. a future-dated birthday) carries exactly 1. Requiring 2+
    would make the single-field checks this validator advertises unrepresentable,
    so one ID is valid.
  - `reason`: a short, human-readable explanation, in a form the live model can
    relay to the user. It MAY quote the conflicting values (it is an in-band
    instruction to the model, not a log line -- see the PII sign-off below for
    why that is acceptable and where it must NOT be logged).

This is the raw verdict the flash-lite model emits; a parse failure is treated as
fail-OPEN (see PII sign-off below).

**Two distinct shapes -- do not conflate them.** The raw verdict above is what the
model returns to the backend. When the backend pushes the verdict to the client
(the `validation_result` WS type F2 reserves -- e.g. for a UI badge), it wraps the
verdict in a typed envelope so sender and receiver agree:

```json
{ "type": "validation_result", "conflicts": [ { "field_ids": [...], "reason": "..." } ] }
```

i.e. the envelope is the raw verdict with a top-level `"type": "validation_result"`
added (the `conflicts` list is spread at top level, NOT nested under a `verdict`
key). The STEERING directive (contract 3) is a SEPARATE thing -- it goes to the
Live model, not over this wire message.

**`validation_result` is sent for EVERY validated boundary, including a clean
verdict.** A clean verdict is `{"type": "validation_result", "conflicts": []}`.
This is REQUIRED, not optional: the ordering rule (contract 4) pauses the section
auto-advance until the validator answers, so the client needs a deterministic
"clean -> resume" signal. Without a mandatory clean response the no-conflict path
would stall until the fail-OPEN timeout (or hang, depending on B4). So: clean
verdict -> `validation_result` with empty `conflicts` (the client resumes the
switch); conflicts -> `validation_result` with the conflicts (the client stays
in-section until resolved); validator outage -> fail-OPEN (the client resumes
after the timeout). Every boundary gets exactly one of these three terminal
signals.

**W3 (bd polyglot-pdf-pr3i, report-cadence revision) -- the async-validator path
(W1-W3) supersedes the inline steer.** For the async `validate_windows` trigger
(and the async `section_complete`/`form_complete` arms since W1), the
`validation_result` is now **REPORT-ONLY**: it carries the surviving conflicts but
the backend does NOT inject a steer on it. The client OWNS the finding queue
(stateless-backend invariant + it owns the `steered`-marker + W4 re-arm lifecycle):
it ENQUEUES a conflict into `validatorFindingsQueue` (persisted; each conflict
carries a `field_names` id->name rider) and drains it FINDING-DRIVEN via a
`drain_findings` round-trip, which composes+injects the steer (contract 3) and
replies `drain_findings_result` with the delivered conflicts -- only THEN does the
client mark the fields `steered` + consume them. A CLEAN result drains nothing (no
voice turn on an all-clear). The "conflicts -> validation_result with a steer" line
above describes the original synchronous `handle_validation_boundary` shape, which
is no longer on any live wire path (W1 rerouted section_complete/form_complete
through the async report-only `handle_validation_windows`; `handle_validation_boundary`
survives only as a test-covered single-window helper). The live async path routes
the steer through the drain instead.

---

## Frozen contract 2 -- Minimal client-state payload

What the validator READS. Rich enough to spot the named contradiction classes,
but with NO schema/structural overhead -- it is the FILLED values plus just enough
field identity to name a conflict. It is NOT the full schema, NOT the manifest,
NOT confirmation/section bookkeeping.

```json
{
  "fields": [
    { "field_id": "addr_state", "name": "State", "value": "West Virginia", "steered": false },
    { "field_id": "addr_zip",   "name": "ZIP code", "value": "50301", "steered": false },
    { "field_id": "dob",        "name": "Date of birth", "value": "2031-04-02", "steered": false }
  ]
}
```

- Only fields with a non-empty value are included (empty/unfilled fields give the
  validator nothing to check and only cost tokens).
- `field_id`: stable handle, echoed back in the verdict's `field_ids`.
- `name`: the human spoken/label name, so the model's `reason` and any steering
  message can name the field naturally (and so the validator has the semantic
  context -- "ZIP code" vs "State" -- to apply world knowledge).
- `value`: the current filled value (the canonical stored form).
- `steered`: the per-field "already steered back about this field once" marker
  (default `false`). **This is how the max-resteer bound survives the stateless
  backend** (contract 3, invariant 2): the backend MUST NOT remember which fields
  it has steered on, so the CLIENT owns that marker in `sessionStorage` alongside
  the field state and sends it in every payload. B5 suppresses any conflict that
  references an already-`steered: true` field (per-field, not "all field_ids
  steered" -- see contract 3 invariant 2 for why), and sets `steered: true` on the
  fields of each conflict it steers. Without this client-sent flag the
  loop-prevention rule could not be honored without violating the stateless
  invariant.

  **RE-ARM on value change (W4, bd polyglot-pdf-ny4s).** The marker is NOT
  session-permanent: the client CLEARS a field's `steered` flag when that field's
  normalized VALUE changes (in the `updateField` write path). So a CORRECTION to an
  adjudicated field re-enters the validator net (a correction that introduces a
  fresh contradiction is caught; a genuinely new conflict on the field is no longer
  suppressed forever). The no-nagging guarantee still holds where it matters: a user
  who confirms "both are intentional" changes NO value, so the marker stays and they
  are never re-asked -- only a field whose value actually moved re-arms. An edit that
  does not change the value (a re-confirm / no-op write) keeps the marker.

The client already holds all of this in `sessionStorage`; the backend rebuilds
nothing server-side (stateless invariant). The payload is assembled from the same
client state that drives navigation -- it is a projection of `fieldValues` plus the
per-field `steered` marker, not a new store.

---

## Frozen contract 3 -- Steering directive (injected into the Live session)

How a non-empty verdict becomes an in-band instruction that sends the LIVE voice
model back to the problem field. The validator does not talk to the user; it
hands the live model a correction directive, which the live model voices.

**Routing (critical -- this is NOT a frontend WS message).** The directive goes
**backend -> Gemini Live session**, injected as a text turn via the adapter's
existing path (`LiveAIGemini.send_text_message` ->
`send_client_content` / `send_realtime_input`, the same mechanism the initiating
message uses). It is NOT sent to the browser: the frontend has no role in voicing
a steer, and an unknown message type falls through the frontend dispatcher's
default-ignore path (`webFormConnection.ts`, the message-handler `switch`'s
`default` case), so a steer routed to the client would simply be dropped and the
conflict never voiced. Accordingly there is
**no `validator_steer` WS message type** -- F2's message-type registry does not list
one (an earlier draft wrongly reserved it as backend->frontend; removed). The
shape below is the internal directive the backend builds and injects, not a wire
envelope:

```text
field_ids:  ["addr_state", "addr_zip"]
reason:     "State is West Virginia but ZIP 50301 is in Iowa."
instruction (the text injected into the Live session):
  "Name both fields and ask the user to verify which is correct. Accept the
   user's answer if they confirm both are intentional."
```

The backend composes `instruction` from `reason` + the two invariants below and
injects it as a Live text turn; `field_ids` / `reason` are the inputs it builds
from, not separate wire fields.

Two invariants this shape MUST preserve:

1. **User-override escape hatch.** The directive MUST carry the legacy semantics
   from the SI prose it replaces: "Accept the user's answer if they confirm." A
   user who says "yes, both are correct" overrides the validator -- the validator
   flags a possible conflict, it does NOT block. (This is the same escape hatch
   the in-SI ADDRESS-CONSISTENCY block had at `config.py:354` / `:418`.)
2. **Max-resteer bound: a given field is re-flagged at most ONCE.** After the
   live model has steered the user back to a field once and the user resolved or
   overrode it, that field is NOT re-flagged on a later validator pass -- no
   infinite zip-vs-state loop. The marker is the `steered` flag on each field in
   the contract-2 payload -- **client-owned** (the stateless backend cannot
   remember it). **Suppression is PER-FIELD, not per-conflict:** B5 drops any
   conflict that REFERENCES AN ALREADY-`steered: true` FIELD (if any of its
   `field_ids` is already steered, the whole conflict is suppressed), then sets
   `steered: true` on every field of each conflict it does steer. The naive "all
   field_ids steered" rule has a hole -- after `addr_state`+`addr_zip` are steered,
   a later `addr_state`+`country` conflict has one un-steered field and would
   re-steer `addr_state`; the per-field rule suppresses it because `addr_state` is
   already steered. (Cost: a genuinely new conflict on `addr_state`+`country` is
   also suppressed -- accepted, since the user already reviewed `addr_state` once
   and the override semantics stand; never re-pester about a field the user
   already adjudicated.) See contract 2 for the flag's home.

The steering mechanism is **IMPLEMENTED** in bead B5 (polyglot-pdf-jnjj.17):
`FormFillingService._compose_validator_steer` builds the directive (names the
fields + the override escape hatch) and `_inject_validator_steer` sends it via
`LiveAIGemini.send_client_content` into a live session;
`_suppress_already_steered` enforces the per-field max-resteer bound on the
incoming payload's `steered` flags. This doc freezes its payload + the two
invariants it honors.

---

## Frozen contract 4 -- Section-complete / form-complete events

Today completion is **reactive-only**: the backend pulls a hint via a
`get_next_field_hint` request and the frontend answers it
(`frontend/src/webFormConnection.ts::handleGetNextFieldHintRequest` ->
`computeNextFieldHintString`), computing
`isFormComplete` / `computeNextField` from `frontend/src/navigation.ts` only when
asked. Nothing is emitted proactively.

Bead **B4 (polyglot-pdf-jnjj.16)** makes the client PROACTIVELY emit two events at
the boundaries where the validator should run. The wire TYPE names are reserved in
[ws-protocol.md](ws-protocol.md) (F2); the PAYLOADS each carries are frozen here:

Both events **carry their own `fields` payload** -- the backend is stateless and
keeps NO server-side form values (`FormFillingService.start_session` treats
`current_values` as client-owned and does not persist them --
`backend/services/form_filling_service.py`, the `current_values` param docstring
and the "client is source of truth" comment in its body), so the validator's
input MUST ride on the event itself; there is nothing server-side to project from
after the message arrives.

**Section-complete** -- emitted when the last field in the current section is
confirmed:

```json
{
  "type": "section_complete",
  "section_id": "addr_section",
  "fields": [
    { "field_id": "addr_state", "name": "State", "value": "West Virginia", "steered": false },
    { "field_id": "addr_zip",   "name": "ZIP code", "value": "50301", "steered": false }
  ]
}
```

- `section_id`: the just-completed section.
- `fields`: the minimal client-state payload (contract 2) scoped to that section
  -- the validator's input for this boundary (including the `steered` markers).

**Form-complete** -- emitted ONCE when the whole form is confirmed
(`isFormComplete` true):

```json
{
  "type": "form_complete",
  "fields": [
    { "field_id": "addr_state", "name": "State", "value": "West Virginia", "steered": false }
    /* ... the contract-2 projection of the WHOLE form ... */
  ]
}
```

- `form_complete` is **once-only per completion**: the client guards it so it does
  not re-fire on every state change while the form sits complete.
- `fields`: the contract-2 payload for the WHOLE form (the full-form validator
  pass's input). It is NOT a bare event -- a bare `{type: "form_complete"}` would
  give the stateless backend no values to validate.
- **Re-validation after post-completion edits (the once-only hole):** the UI allows
  `manual_field_update` edits to an already-completed form. A strictly once-only
  guard would let a user change a value after the full-form pass and submit it
  unchecked -- bypassing the validator entirely. So the guard is on the COMPLETED
  STATE, not a fire-once latch: when the form re-reaches the complete state AND any
  field value has changed since the last `form_complete`, the client re-emits
  `form_complete` (with the updated `fields`) so the full-form pass runs again
  before submit. (Track a "validated snapshot" client-side -- a dirty-since-last-
  validation flag -- and re-emit on the complete->edit->complete cycle; do NOT
  re-emit when nothing changed.) This keeps the no-pester property (no re-emit on a
  static complete form) while closing the edit-after-complete bypass.

### Ordering: the validator must run BEFORE the section auto-switch

Today, when the last field of a section is confirmed, the client auto-advances to
the next section IN THE SAME confirm handler
(`frontend/src/webFormConnection.ts`, the confirm-field handler around line 1583
-> `computeNextField` -> `switchToSection`, which restarts the Live session into
the next section). If
`section_complete` simply fires alongside that, **the validator's verdict arrives
after Gemini has already been restarted into the next section**, and the
steer-back-to-the-problem-field flow cannot work (the live model is no longer in
the section that owns the conflicting fields).

So the contract REQUIRES: **B4 gates the auto-switch on the validator round-trip.**
On section-complete the client emits the event and PAUSES the auto-advance until
either (a) a clean verdict / `validation_result` returns, or (b) the validator
fails-OPEN (timeout/error -- contract: advance unchecked, never block). If the
verdict has conflicts, the steer (contract 3) runs while still in the current
section, and the switch happens only after the user resolves/overrides. The
fail-OPEN bound keeps a validator outage from stranding the user mid-form. This
ordering is owned by B4 (jnjj.16) + B5 (jnjj.17); implementers MUST NOT let the
existing fire-and-forget auto-switch race the validator.

---

## Frozen contract 5 -- `ITextAI` port boundary

The net-new port, mirroring `ILiveAI`:

```python
# backend/ports/text_ai_port.py
class ITextAI(ABC):
    @abstractmethod
    async def validate(self, payload: dict) -> dict:
        """Run a contradiction check over the minimal client-state payload
        (contract 2) and return the verdict (contract 1). Fail-open: on
        timeout/error the caller advances unchecked (see PII sign-off)."""
        ...

    async def ask(self, query: str, context: dict) -> str:
        """Send a prose query + current-values context to the secretary agent
        and return its prose answer. Fail-open: on error returns "" so the Live
        model can ask the user directly. Non-abstract with a NotImplementedError
        default (the A-pillar secretary, jnjj.45)."""
        ...
```

- Method: `async validate(payload) -> verdict` -- payload is contract 2, verdict
  is contract 1 (B pillar). `async ask(query, context) -> str` is the A-pillar
  secretary method (jnjj.45): a plain prose query in, a prose answer out,
  fail-open to `""`. `ask()` is declared non-abstract (default raises
  `NotImplementedError`) so an adapter that predates the secretary bead fails
  loudly rather than silently; `TextAIGemini` implements both.
- Adapter: `backend/adapters/text_ai_gemini.py::TextAIGemini`, mirroring
  `LiveAIGemini`'s constructor convention --
  `TextAIGemini(api_key=..., model=..., vertexai=...)`, constructing a
  `genai.Client(...)` the same way the Live adapter does, but calling the
  text-generation API (not `connect()`/Live).
- Wiring: `get_text_ai(settings) -> ITextAI` goes in
  `backend/dependencies.py`, next to `get_live_ai()`, returning a fresh
  `TextAIGemini(...)` (the per-connection freshness rationale that applies to
  `get_live_ai` -- avoiding cross-connection callback bleed -- does not bind a
  stateless `validate()`, but keep the same provider shape for consistency).

### DECISION: reuse `MODEL_LABELING`, do not rename

The validator's model id reuses the existing **`MODEL_LABELING`** env knob.
`get_text_ai()` reads `settings.MODEL_LABELING` for the validator model.

Rationale (this is a decide-by-default call -- naming, no external contract):
- `MODEL_LABELING` is already the project's "the cheap, non-Live text model"
  knob. It is currently orphaned (only `/health` reads it), defaults to a cheap
  flash-tier id, and was always intended as "a separate env-swappable knob for a
  cheap auxiliary model." The validator is precisely that role -- reusing it gives
  the validator an env-swappable model id with zero new config surface.
- A rename to `MODEL_VALIDATOR` would mean: a new `Settings` field, a `/health`
  edit, deploy-env plumbing, and a doc churn -- for no behavioral gain, since the
  knob has no other live consumer to disambiguate from.
- The only cost of reuse is the stale NAME ("labeling" vs "validating"). That is
  cosmetic and reversible: if a real labeling model ever returns, split the knobs
  then. Reversible default, taken now; note left here for the maintainer to
  overturn if they prefer the clearer name up front.

Set the validator id to `gemini-2.5-flash-lite` via this knob (its default stays
`gemini-2.5-flash`; the env pins the lite tier where the validator runs).

---

## Frozen contract 6 -- PII / PHI data-flow sign-off

The validator payload (contract 2) IS full form PII/PHI -- names, addresses,
dates of birth -- sent to a SECOND Gemini endpoint. This is signed off as
acceptable under [hipaa-pii-policy.md](hipaa-pii-policy.md), with two hard
conditions:

1. **Inside the existing Gemini trust boundary -> the data FLOW is acceptable.**
   The Live model already receives this exact data on every turn (it fills the
   form from it). The validator is a second call to the same vendor (Gemini),
   under the same project/auth (`VERTEXAI` path or the same `GEMINI_API_KEY`),
   within the trust boundary the project has already accepted for the Live model.
   It introduces NO new third party, datastore, or egress -- it is the same data
   to the same vendor, so it is not a new data-flow decision requiring
   escalation. (If it ever pointed at a different vendor or a new persistence
   sink, that WOULD be a step-2 escalation; it does not.)

2. **NO PHI logged at the new call site.** The validator adapter and its caller
   MUST mirror the `callback_handler` PII-safe discipline
   ([hipaa-pii-policy.md](hipaa-pii-policy.md), "Tool-call console" row): log
   field IDs, counts, lengths, latency, model name, token/cost -- **never** the
   payload, the field values, or the `reason`/verdict text. Keep all new logging
   on `_log.*` with redacted (`*_length` / `*_count`) kwargs; the
   `test_no_pii_logging_anywhere_in_backend` sweep covers the new module by
   default the moment it lands (no `GUARDED_FILES` edit needed), so a value-bearing
   log kwarg fails the build. The verdict `reason` is allowed to ride the in-band
   steering message TO the model (that is not a log sink); it must never reach a
   `_log` / `print` / stdout sink.

### Fail-OPEN policy (B3)

On validator **timeout, error, or unparseable output, the user advances
UNCHECKED** -- the validator never blocks form progress. A voice UX must not stall
on an auxiliary text-model outage: a missed contradiction is a soft degradation
(the field-level validation and the user's own confirmation still stand), whereas
a blocked advance is a hard UX failure. `validate()` callers treat any non-verdict
outcome as an empty-`conflicts` (all-clear) result and proceed. This fail-open
behavior is owned by **bead B3**.

---

## What changes this contract

Any edit that alters the verdict shape, the minimal payload shape, the steering
payload or its two invariants, the section/form-complete payloads, the `ITextAI`
method signature, the `MODEL_LABELING` reuse decision, or the PII sign-off updates
THIS doc first (current-state only -- the journal holds the history), then the
code. The reserved wire TYPE names live in [ws-protocol.md](ws-protocol.md) (F2);
coordinate any type-name change there.
