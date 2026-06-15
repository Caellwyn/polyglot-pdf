# System-instruction (SI) reduction -- frozen contract

**Tracks:** backend/config.py backend/services/ai_context.py backend/services/manifest_service.py

*Last updated: 2026-06-14. Created as the F1 foundation contract for the SI-reduction epic (bd polyglot-pdf-jnjj.2). See [../journal/entries/2026-06-14-bd-jnjj.2-si-contract-standard.md](../journal/entries/2026-06-14-bd-jnjj.2-si-contract-standard.md) for closeout details.*

This is the FROZEN interface that the SI-reduction pillar (A) and the
cheap-model-validator pillar (B) build against, so multiple agents can work in
parallel without colliding on the system-instruction templates. It pins: the SI
template shapes, the surviving placeholder set after reduction, the reduced-SI
token-floor target + how it is measured, and the ownership of the
ADDRESS-CONSISTENCY removal. The cost rationale (why the SI is the lever) lives in
the epic plan; the model-selection rule lives in
[ai-models.md](ai-models.md); this doc owns the **SI shape** contract.

## Current state: two templates, one builder

`backend/services/ai_context.py::build_form_context()` builds the SI on every
(re)connect (the backend is stateless -- it rebuilds from the WS handshake each
time) and branches on the `USE_JIT_SCHEMA` flag (`backend/config.py`, default
`false`):

| Mode | Template (`config.py`) | The cost driver |
|------|------------------------|-----------------|
| **Legacy** (`USE_JIT_SCHEMA=false`, default today) | `SYSTEM_INSTRUCTION` | `{fields_json}` -- the WHOLE form's fields dumped as text (~8,200-token floor). This is what the epic removes. |
| **JIT** (`USE_JIT_SCHEMA=true`) | `JIT_SYSTEM_INSTRUCTION` | `{manifest_text}` (field_id\|spoken_name pairs) + `{next_field_schema}` (the current field only). ~2k today; the reduction target is lower. |

`build_form_context()` calls `.format(...)` on exactly one template per build with
the placeholder set below. Adding/removing a placeholder is a change to THIS
contract -- coordinate it here before editing either template.

## Placeholder sets (the frozen interface)

**Shared by BOTH templates** (a builder change must keep all of these populated):
`{form_title}`, `{section_number}`, `{total_sections}`, `{section_label}`,
`{section_list}`, `{filled_count}`, `{total_fields}`, `{fill_language}`,
`{previous_spoken_names}`, `{next_field_hint}`, `{confirmation_policy}`.

**Legacy-only:** `{fields_json}` (the full field dump -- the removal target),
`{unfilled_count}`.

**JIT-only:** `{manifest_text}` (from `manifest_service.generate_part_manifest`
-> `format_manifest_for_context`), `{next_field_schema}` (from
`manifest_service.get_next_field_schema`, the FIRST unfilled field rendered as one
line: `ID | Spoken | Name | Type | Required | Options:[...]`).

> **`fields_json` is a legacy placeholder NAME, not JSON.** It carries
> pipe-separated field text (the comment at `config.py` notes this -- kept for
> compatibility). Do not "fix" it to JSON; that is a separate decision outside this
> epic.

## The reduced-SI target (what pillar A converges to)

The JIT path is the foundation, but it was built by weaker models and is examined +
improved under A1/A2 before being trusted. The target SI shape after reduction:

- **`fields=[]` -- no full field dump.** The live model holds only the current
  field (`{next_field_schema}`) + the lightweight manifest (`{manifest_text}`); it
  recalls prior answers via the EXISTING exploration tools (`get_field_value`,
  `get_form_status`) instead of carrying the whole form in context. See
  [ai-models.md](ai-models.md) for the tools.
- **Floor target: ~1,850 rendered tokens** (the "drip-in" floor). This is a
  *rendered-on-the-real-largest-section* number, NOT a modeled estimate -- it is
  measured by the G2 cost gate (bd polyglot-pdf-jnjj.6) using
  `scripts/spikes/measure_form_session_costs.py`, and pillar A's default-flip
  (A5) requires that measurement to clear (G2) AND the fill-correctness gate (G3,
  bd polyglot-pdf-jnjj.7) to confirm the live model still fills correctly once the
  dump is gone.
- The legacy `SYSTEM_INSTRUCTION` template stays selectable behind the flag after
  the flip -- the reduction changes the DEFAULT, it does not delete the legacy path.

## ADDRESS CONSISTENCY prose: deleted, owned by B

Both templates carry an `ADDRESS CONSISTENCY:` block (`config.py:348` in
`SYSTEM_INSTRUCTION`, `config.py:412` in `JIT_SYSTEM_INSTRUCTION`) instructing the
LIVE model to cross-check address fields (zip-vs-state, etc.) itself. This is the
contradiction-checking the epic DELEGATES to the cheap validator.

- **The removal is owned by bead B1 (polyglot-pdf-jnjj.13), NOT by any A bead**,
  and is HARD-GATED on the validator being live: B1 depends on B2-B5 closed + the
  G1 detection gate passing, so the in-SI check is never removed until the
  flash-lite validator replaces it (no window with zero contradiction detection).
- Because B1 and A3 (shrink the JIT template) BOTH edit the `config.py` SI block,
  they are serialized **B1 -> A3** (see the epic plan's conflict cheat-sheet).
- The verdict/payload/steering shapes the validator uses are owned by the
  validation-delegation standard (F3, bd polyglot-pdf-jnjj.4), not here.

## What changes this contract

Any edit that adds/removes a placeholder, changes the manifest or next-field-schema
shape, alters the reduced-SI floor target, or moves the ADDRESS-CONSISTENCY
ownership updates THIS doc first (current-state only -- the journal holds the
history), then the code.
