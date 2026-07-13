# Section-reset deprecation (bd polyglot-pdf-55jg)

**Tracks:** backend/config.py backend/services/callback_handler.py backend/services/form_filling_service.py backend/services/request_coordinator.py frontend/src/webFormConnection.ts frontend/src/schema-forms/state/schemaFormState.ts frontend/src/shared/connection.ts frontend/src/demo/VoiceOverlay.tsx

*Last updated: 2026-07-12*

## Status: DEPRECATED but LIVE

**Continuous-DTI is the production law of the land** (`CONTINUOUS_SESSION` +
`USE_DTI`, both default `true` -- see CLAUDE.md and
[`sprint_11_continuous-dti-law_plan.md`](../sprint_11_continuous-dti-law_plan.md)).
Section-reset -- the older flow that chops the form into sections and restarts
the Gemini session at each section boundary -- is **dead in production** but
**kept as a fallback** in case continuous-DTI hits an unsolvable issue. It is
not deleted. Every site below carries a

```
DEPRECATED (bd polyglot-pdf-55jg):
```

comment marker (greppable: `grep -rn "DEPRECATED (bd polyglot-pdf-55jg)" backend/ frontend/src/`)
so a later deletion pass is mechanical. **Do not extend any marked site** --
new work belongs in the continuous-DTI path.

## The marked (DEPRECATED) sites

| File | Symbol |
|------|--------|
| `backend/config.py` | `switch_section` tool declaration in `TOOL_DECLARATIONS` |
| `backend/config.py` | The legacy `SYSTEM_INSTRUCTION` section-navigation text: the `AVAILABLE SECTIONS:\n{section_list}` line and the `- switch_section: Navigate to different section...` TOOLS line |
| `backend/services/callback_handler.py` | The `switch_section` dispatch branch in the tool router |
| `backend/services/callback_handler.py` | `_handle_switch_section_tool` |
| `backend/services/form_filling_service.py` | `handle_switch_section` (the AI-tool handler) |
| `backend/services/form_filling_service.py` | `_complete_section_switch` (AI-initiated switch coordination) |
| `backend/services/request_coordinator.py` | `request_section_info` (sends the `prepare_section_switch` request) |
| `frontend/src/webFormConnection.ts` | `handlePrepareSectionSwitchRequest` |
| `frontend/src/webFormConnection.ts` | `proceedSectionSwitch` |
| `frontend/src/webFormConnection.ts` | `switchToSection` (the connection-level method -- backend-side reconnect pattern) |
| `frontend/src/webFormConnection.ts` | `completeSection` |
| `frontend/src/webFormConnection.ts` | The non-continuous (`else`) branch of the `continuousSessionEnabled` guard inside `startSection` (sends the legacy single-section `handshake` message) |
| `frontend/src/webFormConnection.ts` | `resolvePendingSectionSwitch` / `cancelPendingSectionSwitch` (the `pendingSectionSwitch` park/resume/cancel helpers) |
| `frontend/src/schema-forms/state/schemaFormState.ts` | `markSectionComplete` |
| `frontend/src/schema-forms/state/schemaFormState.ts` | `switchToSection` (the state-manager method) |
| `frontend/src/shared/connection.ts` | `switchToSection` / `completeSection` (the connection-manager wrappers over the marked `webFormConnection` methods; distinct from `switchToFirstSection`, the LIVE session-start trigger, which stays unmarked) |
| `frontend/src/demo/VoiceOverlay.tsx` | The manual section-jump dropdown (already `!continuousSession`-gated -- never renders in production) |

## The KEEP list (NOT deprecated -- shared or harness-consumed)

These names look adjacent to the list above but are **not** section-reset-only.
Do not mark them; a later deletion pass must leave them alone unless their own
consumer is also retired.

| File | Symbol | Why it stays live |
|------|--------|--------------------|
| `backend/services/form_filling_service.py` | `switch_to_section` (note the **TO**) + `_switch_to_section_locked` | The shared session-restart primitive: BOTH the manual WS switch and the AI-initiated switch call it, and it is also the mechanism behind continuous-mode's GoAway/1011 reconnect and the harness's baseline arm. Retiring section-reset does not retire this call path. |
| `backend/services/ai_context.py` | The legacy full-SI renderer branch (`section_list` / the non-DTI format branch) | Consumed by `measure_form_session_costs.py --arm section-reset`, the cost/measurement harness's baseline instrument. Needed to keep measuring the alternative arm. |
| `backend/config.py` | `switch_to_field` tool declaration (~line 495) and its SI text | A distinct, LIVE field-level navigation tool (secretary jumps + corrections), unrelated to section-reset. |
| `backend/services/form_filling_service.py` `_build_tool_declarations` | The continuous-mode gate that drops `switch_section` from the declared tools | This is the CONTINUOUS-mode routing gate itself, not the section-reset body it routes away from. |
| (repo-wide) | Any `if continuousSessionEnabled` / continuous-mode guard | The guards are live routing logic; only the section-reset body they route away from is deprecated. |
| (repo-wide) | The manifest-first "jit" transport (`handshake_jit`, `jit_mode`, `buildContinuousManifest`) | This is continuous-DTI's carrier, not section-reset. |
| `backend/services/ai_context.py` | The `or schema.get("jit_mode")` rollback route | Unrelated rollback path, not section-reset. |
| (repo-wide) | Section-reset **tests** | Left unchanged on purpose -- they now guard the deprecated-but-live fallback, not dead code. |

## How the flags route around it

- `USE_DTI` (default `true`): on, the backend uses the DTI (dynamic tool
  injection) SI instead of the legacy full-SI `SYSTEM_INSTRUCTION` template.
- `CONTINUOUS_SESSION` (default `true`): on, the whole form runs as one Gemini
  session bounded by context-window compression; the backend drops the
  `switch_section` tool from the declared tool set and the frontend's
  `continuousSessionEnabled` guards route every section-mutation entry point
  (`startSection`, `proceedSectionSwitch`, `completeSection`,
  `handlePrepareSectionSwitchRequest`) away from the section-reset body.

Setting either flag to `false` re-enables the section-reset path documented
here -- that is the fallback this deprecation pass preserves.

## To delete later

Once continuous-DTI is proven durable (no fallback flip needed for a
sustained period), remove: every site marked `DEPRECATED (bd polyglot-pdf-55jg)`
above, plus the KEEP-list entries that exist ONLY to serve section-reset (the
`ai_context.py` legacy full-SI branch and its harness `--arm section-reset`
consumer) -- but leave `switch_to_section` / `_switch_to_section_locked` and
`switch_to_field` alone, since those stay live independent of this deprecation.
