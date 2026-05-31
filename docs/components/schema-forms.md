# Schema forms & client state

**Tracks:** frontend/src/schema-forms/state/schemaFormState.ts frontend/src/schema-forms/types/schema.ts frontend/src/schema-forms/components/SchemaForm.tsx frontend/src/schema-forms/components/FieldRenderer.tsx frontend/src/schema-forms/utils/fieldValue.ts frontend/src/schema-forms/utils/validation.ts

*Last updated: 2026-05-31*

The schema-driven form surface: a `FormSchema` (JSON) drives a React form whose
state lives entirely in the browser. This is the client half of the
[client-owns-state invariant](../standards/stateless-architecture.md); the voice
layer that fills it is in [voice-ai.md](voice-ai.md) and
[websocket-routing.md](websocket-routing.md); PDF export is in
[pdf-filling.md](pdf-filling.md). Terminology (sections vs parts, field-ids) is in
[../standards/terminology.md](../standards/terminology.md).

## State: `SchemaFormStateManager` + sessionStorage

`frontend/src/schema-forms/state/schemaFormState.ts` owns all form state under the
single sessionStorage key **`schema_form_state`**. It's a static class (no
instances) operating on a `SchemaFormState` value:

- `fieldValues: Record<string, FieldValue>` — the answers (see FieldValue below).
- `currentSectionId` + `completedSections: Set<string>` — **section**-based
  navigation (not parts; see terminology).
- `formSessionId` — persistent `fss_<base36-ts>_<random>`, survives reconnects
  (the durability boundary; see stateless-architecture).
- `validationErrors`, `loadedFieldIds`/`jitModeEnabled` (JIT token-reduction),
  `disclaimerAccepted`/`selectedLanguage`.

Lifecycle: `init(schema)` reuses existing state if the same form (number+version)
was touched <1h ago, else seeds a new session at the first section. `save()`
serializes the `Set`s to arrays **and dispatches a `CustomEvent('schemaFormStateChange')`**
so `SchemaForm` re-renders on same-window updates (cross-window uses the native
`storage` event). `clear()` is `sessionStorage.removeItem(...)` — a **silent** wipe
that does *not* fire the change event (a clear-on-logout feature must refresh the UI
itself; same caveat noted in stateless-architecture).

Back-compat migrations on `load()`: `completedParts → completedSections`,
`currentPartId → currentSectionId` — residue of the parts→sections rename.

## `FieldValue` wrapper

Each answer is wrapped, not bare (`types/schema.ts`):

```ts
interface FieldValue {
  value: string | boolean | null;
  confirmed?: boolean;
  confirmedAt?: string;             // ISO
  confirmationMethod?: 'ai_voice' | 'manual_edit';
  lastModified?: number;
  availability?: 'available' | 'locked' | 'hidden';
  lockedReason?: string;
}
```

> **Terminology gotcha:** the frontend's `confirmationMethod` enum is
> `ai_voice` / `manual_edit`, but the **backend** `confirm_field` tool +
> `confirmation_logger` use `verbal` / `manual` (see
> [../standards/confirmation-and-audit.md](../standards/confirmation-and-audit.md)).
> Two vocabularies for the same concept on the two sides of the wire.

`utils/fieldValue.ts` unwraps: `unwrapFieldValue` / `unwrapToString` /
`unwrapToBoolean` (with an `isFieldValue` type guard). **Always unwrap before
sending values to the PDF filler** — `SchemaForm.handleDownloadPDF` maps every
`fieldValues` entry through `unwrapFieldValue` first, because a raw wrapper renders
as `[object Object]` / breaks fill (the bug `fieldValue.ts` was created to fix).

## Rendering

`SchemaForm.tsx` renders one section at a time (`getCurrentSectionFields`), with a
progress bar (`getProgress`), prev/next nav (`getNextSection`/`getPreviousSection`,
gated by `isSectionValid`), and a final Submit. It also mounts the voice overlay
(desktop `VoiceOverlay` / mobile `VoiceOverlayMobile`, `window.innerWidth <= 768`)
and the PDF print/download buttons, and creates the shared mic `MediaStream` +
`ConnectionManager` once the stream is ready.

`FieldRenderer.tsx` routes by `field.type` to a component. **Implemented:** `text`,
`email`, `tel`, `textarea`, `radio`, `checkbox`, `date`, `select` (and `number`,
which reuses `TextField`). **Not yet implemented** (render a placeholder):
`signature`, `address_group`, `table`. Unknown types render an error block.

Manual edits from the React UI are **auto-confirmed** as `manual_edit`
(`handleFieldChange`), and `field.copy_to` auto-copies the value to listed target
fields (also auto-confirmed). Validation runs on blur (`validateField`).

## Conditional fields

`utils/validation.ts#shouldShowField` evaluates `field.show_if` (a
`{field, operator, value}` `ConditionalDisplay`); a hidden field renders `null`.
A field with `conditional_behavior.unlock_method === "flip_readonly_bit"` becomes
**editable when its `show_if` condition is met** even if `read_only` — the same
flag the PDF filler honors to unlock locked widgets (see
[pdf-filling.md](pdf-filling.md)). The richer `controls_fields` /
`ConditionalControl` (shows/hides/locks/unlocks/makes_required) supersedes the
deprecated `conditional_fields`.

## Backend half

The backend never stores `fieldValues` — it holds only the schema in-memory for
Gemini's prompt context (`backend/services/form_filling_service.py#update_schema`),
per stateless-architecture. The form-session/section metadata the client computes
here (`getHandshakePayload` / `getJITHandshakePayload`) is what the WS handshake
carries (see [websocket-routing.md](websocket-routing.md)).

## Scar tissue

- **Unwrap before PDF / display** — a bare `FieldValue` renders `[object Object]`.
- **`clear()` is silent** — no `schemaFormStateChange`; refresh the UI yourself.
- **sections, not parts** — `parts?` is optional/legacy on the schema; navigation
  is section-based, with load-time migration of the old `*Part*` keys.
- **`signature`/`address_group`/`table` are stubs** — don't assume all 12
  `FieldType`s render.

*Last updated: 2026-05-31*
