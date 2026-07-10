# JIT schema loading -- REMOVED (tombstone)

**Tracks:** backend/services/ai_context.py backend/config.py

*Last updated: 2026-07-09 (bd polyglot-pdf-en2j -- JIT SI mode purged). Removal record: [../journal/entries/2026-07-09-bd-en2j-purge-jit-si-mode.md](../journal/entries/2026-07-09-bd-en2j-purge-jit-si-mode.md).*

The **JIT (Just-In-Time manifest) SI mode was removed in bd polyglot-pdf-en2j.** The
`USE_JIT_SCHEMA` flag, the `JIT_SYSTEM_INSTRUCTION` template, and the manifest-text SI
helpers (`generate_part_manifest`, `get_next_field_schema`,
`format_manifest_for_context`, `should_include_schema_in_response`,
`estimate_manifest_tokens`, plus the runtime next-field drip) are all gone.

**The shipped reduced-SI mode is DTI** (Dynamic Turn Injection, `USE_DTI=true`): a thin
static SI plus per-field guidance injected via the initiating message and the
`confirm_field` tool response. See
[../standards/si-reduction.md](../standards/si-reduction.md) for the SI-shape contract
and DTI's guidance-injection path.

**The manifest-first handshake TRANSPORT survives** as DTI's carrier -- it was NOT
removed:

- the `handshake_jit` WS message type,
- the `schema["jit_mode"]` key,
- the `jit_mode_enabled` session-ready signal (`= settings.USE_DTI`),
- the frontend's `jitModeEnabled` state + `handshake_jit` builder.

These are documented in
[../components/websocket-routing.md](../components/websocket-routing.md) (the WS
handshake / routing) and
[../components/schema-forms.md](../components/schema-forms.md) (the frontend manifest
builder + client state).
