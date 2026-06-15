# Validation delegation (cheap-model validator) -- frozen contract

**Tracks:** backend/adapters/live_ai_gemini.py backend/ports/live_ai_port.py backend/dependencies.py backend/utils/field_validator.py backend/config.py

*Last updated: 2026-06-14. Created as the F3 foundation contract for the SI-reduction epic (bd polyglot-pdf-jnjj.4). See [../journal/entries/2026-06-14-bd-jnjj.4-validation-delegation-standard.md](../journal/entries/2026-06-14-bd-jnjj.4-validation-delegation-standard.md) for closeout details.*

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
  [ws-protocol.md](ws-protocol.md) (F2, being written in parallel). **F2 owns the
  type names; F3 (this doc) owns the PAYLOAD shapes those messages carry.**
- The model-selection rule (which model, why flash-lite) lives in
  [ai-models.md](ai-models.md).
- The logging discipline this doc signs off against lives in
  [hipaa-pii-policy.md](hipaa-pii-policy.md).

---

## Current state: no text-model path exists

Every Gemini call today is the **Live API** (audio + tool-calling), routed
through one port and one adapter:

- Port: `backend/ports/live_ai_port.py::ILiveAI` (with the `LiveAISession`
  Protocol).
- Adapter: `backend/adapters/live_ai_gemini.py::LiveAIGemini` (the only adapter
  in `backend/adapters/`).
- Wiring: `backend/dependencies.py::get_live_ai()` constructs a fresh
  `LiveAIGemini(api_key=settings.GEMINI_API_KEY, model=settings.MODEL_NATIVE,
  vertexai=settings.VERTEXAI)` per WebSocket connection.

There is **no request/response text-generation path** anywhere -- nothing calls
`generate_content` / a non-Live model. `MODEL_LABELING` (`backend/config.py:70`,
default `gemini-2.5-flash`) is an **orphaned env knob**: its ONLY reader is
`backend/main.py:62`, which surfaces it on the `/health` response for display; no
handler, service, or adapter consumes it (the field-labeling normalizer it was
named for is deprecated -- see the `config.py:55` comment). The
`dependencies.py:21` comment's reference to a "LabelingAIGemini" constructor
convention is stale prose; no such adapter exists in the tree.

Existing validation is **field-level only**: `backend/utils/field_validator.py`
(`validate_updates` -> `validate_field_value`) checks one value against its own
schema constraints (min/max, pattern, date_constraint, options); the frontend
mirror is `frontend/src/schema-forms/utils/validation.ts`. **Neither does any
cross-field or contradiction detection** -- a zip that disagrees with a state
passes both, because each field is valid in isolation. That gap is exactly what
the validator fills.

The validator (`ITextAI` / `TextAIGemini`) is **net-new** and MIRRORS the
`ILiveAI` / `LiveAIGemini` structure: a port in `backend/ports/`, an adapter in
`backend/adapters/`, and a `get_text_ai()` provider slotted into
`backend/dependencies.py` alongside `get_live_ai()`.

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
  - `field_ids`: the 2+ field IDs that disagree (always field IDs, never field
    values -- IDs are the safe-to-log handle per the PII policy).
  - `reason`: a short, human-readable explanation, in a form the live model can
    relay to the user. It MAY quote the conflicting values (it is an in-band
    instruction to the model, not a log line -- see the PII sign-off below for
    why that is acceptable and where it must NOT be logged).

This is the only shape B parsers consume. The flash-lite model is prompted to
emit exactly this JSON; a parse failure is treated as fail-OPEN (see PII sign-off
below).

---

## Frozen contract 2 -- Minimal client-state payload

What the validator READS. Rich enough to spot the named contradiction classes,
but with NO schema/structural overhead -- it is the FILLED values plus just enough
field identity to name a conflict. It is NOT the full schema, NOT the manifest,
NOT confirmation/section bookkeeping.

```json
{
  "fields": [
    { "field_id": "addr_state", "name": "State", "value": "West Virginia" },
    { "field_id": "addr_zip",   "name": "ZIP code", "value": "50301" },
    { "field_id": "dob",        "name": "Date of birth", "value": "2031-04-02" }
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

The client already holds all of this in `sessionStorage`; the backend rebuilds
nothing server-side (stateless invariant). The payload is assembled from the same
client state that drives navigation -- it is a projection of `fieldValues`, not a
new store.

---

## Frozen contract 3 -- Steering-message shape

How a non-empty verdict becomes an in-band instruction that sends the LIVE voice
model back to the problem field. The validator does not talk to the user; it
hands the live model a correction directive, which the live model voices.

```json
{
  "type": "validator_steer",
  "field_ids": ["addr_state", "addr_zip"],
  "reason": "State is West Virginia but ZIP 50301 is in Iowa.",
  "instruction": "Name both fields and ask the user to verify which is correct. Accept the user's answer if they confirm both are intentional."
}
```

(The wire `type` name is reserved/owned by [ws-protocol.md](ws-protocol.md) (F2);
the fields above are the F3-owned payload.)

Two invariants this shape MUST preserve:

1. **User-override escape hatch.** The directive MUST carry the legacy semantics
   from the SI prose it replaces: "Accept the user's answer if they confirm." A
   user who says "yes, both are correct" overrides the validator -- the validator
   flags a possible conflict, it does NOT block. (This is the same escape hatch
   the in-SI ADDRESS-CONSISTENCY block had at `config.py:354` / `:418`.)
2. **Max-resteer bound: a given field is re-flagged at most ONCE.** After the
   live model has steered the user back to a field once and the user resolved or
   overrode it, that field is NOT re-flagged on a later validator pass -- no
   infinite zip-vs-state loop. Track a per-field "already steered" marker
   (client-side, alongside the field state) and suppress repeat conflicts that
   reference an already-steered field.

The steering mechanism is owned by **bead B5 (polyglot-pdf-jnjj.17)**; this doc
freezes its payload + the two invariants it must honor.

---

## Frozen contract 4 -- Section-complete / form-complete events

Today completion is **reactive-only**: the backend pulls a hint via a
`get_next_field_hint` request and the frontend answers it
(`frontend/src/webFormConnection.ts::handleGetNextFieldHintRequest` ->
`computeNextFieldHintString`, ~lines 822-876), computing
`isFormComplete` / `computeNextField` from `frontend/src/navigation.ts` only when
asked. Nothing is emitted proactively.

Bead **B4 (polyglot-pdf-jnjj.16)** makes the client PROACTIVELY emit two events at
the boundaries where the validator should run. The wire TYPE names are reserved in
[ws-protocol.md](ws-protocol.md) (F2); the PAYLOADS each carries are frozen here:

**Section-complete** -- emitted when the last field in the current section is
confirmed:

```json
{
  "type": "section_complete",
  "section_id": "addr_section",
  "fields": [
    { "field_id": "addr_state", "name": "State", "value": "West Virginia" },
    { "field_id": "addr_zip",   "name": "ZIP code", "value": "50301" }
  ]
}
```

- `section_id`: the just-completed section.
- `fields`: the minimal client-state payload (contract 2) scoped to that section
  -- the validator's input for this boundary.

**Form-complete** -- emitted ONCE when the whole form is confirmed
(`isFormComplete` true):

```json
{ "type": "form_complete" }
```

- `form_complete` is **once-only**: the client guards it so it fires a single
  time per form session, never re-emitted on subsequent state changes. (A
  full-form validator pass, if run at this boundary, uses the contract-2 payload
  for the whole form; the event itself carries no field payload.)

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
```

- Method: `async validate(payload) -> verdict` -- payload is contract 2, verdict
  is contract 1. A single method is enough for B; resist widening the port until a
  second text-model use exists.
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
