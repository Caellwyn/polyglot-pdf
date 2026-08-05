# Schema forms & client state

**Tracks:** frontend/src/schema-forms/state/schemaFormState.ts frontend/src/schema-forms/types/schema.ts frontend/src/schema-forms/components/SchemaForm.tsx frontend/src/schema-forms/components/FieldRenderer.tsx frontend/src/schema-forms/utils/fieldValue.ts frontend/src/schema-forms/utils/validation.ts frontend/src/schema-forms/utils/normalizeToComposite.ts frontend/src/schema-forms/utils/conditionalFieldCheck.ts

*Last updated: 2026-08-05 (bd polyglot-pdf-uw3w / 3irc / qim7: `fieldValues` has two independent writers -- the React UI and WebFormConnection -- reconciled per logical field by `reconcileFieldValues`; see "Two writers, one map" below).*

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
  navigation state (not parts; see terminology). In production continuous mode
  `completedSections` never grows and manual prev/next is suppressed, but
  `currentSectionId` FOLLOWS the voice model: when the model's focus lands on a
  field in another section (`onNextField`), `SchemaForm` calls
  `setVisibleSection` to page the simplified view to that field's section
  (bd polyglot-pdf-55jg) — so the shown section tracks fill progress even though
  no section-COMPLETE transitions happen. `setVisibleSection` sets only
  `currentSectionId` and PRESERVES `pinnedFieldId` (unlike `navigateToSection`,
  the manual-jump path, which clears the pin). Because this paged
  `currentSectionId` is UI-only in continuous mode -- the connection's persisted
  state keeps it pinned at the first section -- `SchemaForm`'s `schemaFormStateChange`
  and `vffOnSectionChanged` listeners PRESERVE the current React `currentSectionId`
  in continuous mode rather than adopting the pinned value; otherwise every
  confirmation-time field-value save rubber-banded the view back to section 1
  (bd polyglot-pdf-rvac). The section-COMPLETE machinery
  (`markSectionComplete`/`switchToSection`, manual prev/next) drives real
  navigation only in the DEPRECATED section-reset fallback. Sections page the UI
  in both modes.
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
  steered?: boolean;                // B5: validator already steered this field once
}
```

> **`steered`** (bd polyglot-pdf-jnjj.17, B5) is the client-owned half of the
> cheap-model validator's max-resteer bound: once the validator steers the user back
> about a field, `SchemaFormStateManager.markFieldsSteered` sets this so the marker
> rides the next validator payload and the (stateless) backend suppresses re-steering
> it. See [../standards/validation-delegation.md](../standards/validation-delegation.md)
> (contracts 2/3).

> **`lastModified`** is load-bearing, not decorative: it is the tiebreaker for the
> two-writer problem below. `updateField` and `markFieldSkipped` stamp it;
> `confirmField` deliberately does **not**, because confirming changes only
> confirmation metadata and never the value, so the value's timestamp must stay put.

### Two writers, one map: reconciling `fieldValues`

`fieldValues` has **two independent writers**. The React UI (`SchemaForm.tsx`
`handleFieldChange` / `handleFieldSkip`) persists through `SchemaFormStateManager`
and never touches `WebFormConnection`'s in-memory `this.state`; the voice layer
holds `this.state` across turns. Any connection handler ending in
`SchemaFormStateManager.save(this.state)` can therefore persist a stale in-memory
copy over an on-screen edit.

`reconcileFieldValues` (`utils/fieldValue.ts`) is the single arbiter, called at the
three handlers that save state — `handleSessionReady`, `handleConfirmFieldRequest`,
`handleSkipFieldRequest` (bd `polyglot-pdf-qim7` / `uw3w` / `3irc`). It resolves
**per logical field**, not per raw key:

- The newer `lastModified` wins; a stamped entry beats an unstamped one.
- `[]`-alias variants (`p1_grp` / `p1_grp[]`) collapse into ONE decision, so a
  merge can never resurrect a key `updateField` deleted on migration — that
  resurrection is what broke the one-entry invariant (bd `polyglot-pdf-got6`).
- A same-millisecond tie goes to the **persisted** side. `Date.now()` is coarser
  than the AI-write → on-screen-edit gap, so ties are a real case, and *both*
  directions are unsafe if the stale in-memory copy wins: a typed answer gets
  blanked by a skip, **and** a value the user cleared gets revived (and marked
  confirmed) by a confirm. A "meaningful entry wins" tie-break only covers the
  first — the cleared-value direction has the stale side holding the meaningful
  entry — so the durable side wins outright instead.
- An entry present on only one side is kept, so an in-memory-only value stays
  visible to the confirm handler's usable-value gate and the skip handler's
  already-filled guard (bd `polyglot-pdf-pjws`).

Never merge these maps with a raw key union (`{...persisted, ...inMemory}`) — that
makes the in-memory side win unconditionally and reintroduces all three bugs.

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
Note `unwrapFieldValue` returns `string | boolean | string[] | null` — a non-wrapper
input passes through unchanged, so a bare `string[]` (a checkbox group) comes back
as an array even though `FieldValue.value` itself is only `string | boolean | null`.

## Rendering

`SchemaForm.tsx` renders one section at a time (`getCurrentSectionFields`), with a
progress bar (`getProgress`). The whole navigation block -- manual prev/next
(`getNextSection`/`getPreviousSection`, gated by `isSectionValid`) AND the trailing
"Submit Form" button -- renders ONLY in the deprecated non-continuous section-reset
fallback (bd polyglot-pdf-55jg); production continuous sessions show no nav block at
all. The Submit button is hidden for now because there is no downstream submission
target (bd polyglot-pdf-rvac) -- re-add it in the nav block when a real target
exists. It also mounts the voice overlay
(desktop `VoiceOverlay` / mobile `VoiceOverlayMobile`, `window.innerWidth <= 768`)
and the PDF print/download buttons, and creates the shared mic `MediaStream` +
`ConnectionManager` once the stream is ready. It also renders, with no flag gate
(the preview UI is cut over, bd `polyglot-pdf-v437`) -- the toggle always, the
button whenever `pdfUrl` is present (it sits in the same `pdfUrl`-gated
print/download block): a "Preview Filled PDF" button that lazy-loads
`frontend/src/pdf-view/FilledPreviewModal.tsx` (pdf.js render of the real
`/api/fill-pdf` output), and a Simplified/Preview view-mode toggle
(`frontend/src/pdf-view/viewMode.ts`, sessionStorage-persisted, still landing
on Simplified) that swaps the form for the lazy
`frontend/src/pdf-view/PreviewPane.tsx` PDF surface -- the overlays +
ConnectionManager sit outside the switched container, so toggling never
disturbs the voice session (pinned by `SchemaForm.test.tsx`, an overlay-DOM-
identity-survives-toggle test, bd `polyglot-pdf-fdz8`). A live same-tab resize
into mobile width also drops Preview back to Simplified (`viewModeAfterResize`,
bd `polyglot-pdf-ipin`; details in [pdf-view.md](pdf-view.md)). The pdfjs
chunks stay unfetched until the user actually opens one of those preview
surfaces, so a session that stays in Simplified never loads them.

`FieldRenderer.tsx` routes by `field.type` to a component. **Implemented:** `text`,
`email`, `tel`, `textarea`, `radio`, `checkbox`, `checkbox_group`, `date`, `select`
(and `number`, which reuses `TextField`). `checkbox` and `checkbox_group` both
render through `CheckboxField`, which branches on `options[]` (a bare boolean box
vs. a multi-select group). **Not yet implemented** (render a placeholder):
`signature`, `address_group`, `table`. Unknown types render an error block.

Manual edits from the React UI are **auto-confirmed** as `manual_edit`
(`handleFieldChange`), and `field.copy_to` auto-copies the value to listed target
fields (also auto-confirmed). Validation runs on blur (`validateField`).
**AI-applied values are validated too** (bd polyglot-pdf-wpw.3): the voice layer
runs `validateField` on every value the model fills *before* it lands (see
[tool-call-flow.md](tool-call-flow.md)), so an invalid enum/format/required value
never enters client state -- the client is authoritative over its own field state.
`validateField` enforces option membership (enum) for option-backed fields
(`select`/`radio`/checkbox groups) independently of any `validation` block, since
the option set itself is the constraint.

**`help.instructions`, `help.details` and `FormMetadata.details`/`booklet_text`
are MODEL-FACING ONLY** (bd `polyglot-pdf-wsao.1`): they feed the voice guidance
block and the secretary catalog, and are **never rendered on-screen** and never
spoken in the ask-hint. `frontend/src/schema-forms/components/fields/instructions-not-rendered.test.tsx`
guards the two FIELD-level names (`help.instructions`, `help.details`) across
every field component -- if you add either to a rendered surface, that test
fails on purpose. **`FormMetadata.details` and `booklet_text` have no such
guard**: the invariant is identical, but nothing mechanically enforces it, so
putting either on-screen would ship a model-facing booklet excerpt to the user
with a green suite.

## Conditional fields

`utils/validation.ts#shouldShowField` consumes `field.show_if` through
`utils/normalizeToComposite.ts` (bd h76m.7/h76m.8), so BOTH wire dialects
evaluate on one path: the legacy single `{field, operator, value}`
`ConditionalDisplay`, and the schema-v2 composite `{all_of/any_of/none_of}`
group of such atoms ("(A AND B) AND NOT C" = `all_of:[A,B] + none_of:[C]`).
A hidden field renders `null`. An absent, malformed, or unknown-operator
condition falls back to the field's static `hidden` state (fail-open).
`utils/validation.ts#isFieldRequired` evaluates the same legacy-or-composite
shape on `field.require_if` (statically required OR a satisfied require_if;
fail-open = not required). The editor preview mirrors both in
`schema-editor/src/utils/conditionalVisibility.ts`; the shared vector suite
(`shared/conditional-vectors.json` — v0 legacy, v2 composite/membership,
require, and normalize sections) pins the two evaluators against each other
in CI.
Membership semantics: the v2 operators `includes`/`not_includes` test whether
an option slug is in a checkbox-group trigger's selected set (a `string[]`; the
voice-path comma string is converted to an array at the single ingress boundary,
`applyAiValueWithValidation` in webFormConnection.ts, BEFORE storage, so the
evaluator only ever sees an array or a bare scalar single selection).
`equals`/`not_equals` are PURE scalar comparisons (used on radio/select/text
triggers). The old vq4m equals-means-membership hack, the comma-split tolerance,
and the `group_kind` gate were all DELETED at the P6.2 strictness flip
(bd polyglot-pdf-h76m.16); a checkbox group is now identified by its TYPE (the v2
`checkbox_group`, or a legacy `checkbox` carrying options[]), never `group_kind`.
The voice locked-field path (`utils/conditionalFieldCheck.ts`) explains
composite gates by listing EVERY atom's trigger in `required_fields` (the
locked-reason wording names the first trigger, then counts the rest);
`getDependencyChain` walks all atoms and carries a visited-set cycle guard.
A field with `unlock_method === "flip_readonly_bit"` becomes **editable even when
`read_only`** — the unlock is driven by that flag alone (visibility is a separate
`show_if` decision), the same flag the PDF filler honors to unlock locked widgets
(see [pdf-filling.md](pdf-filling.md)).
`FieldRenderer` reads the unlock flag from **either** `conditional_behavior`
(canonical) **or** `conditional_logic` (a legacy alias of the same
`ConditionalBehavior` type, still emitted by some generated form-kit schemas,
e.g. i-90). The trigger-side `controls_fields` / `ConditionalControl` and the
legacy `conditional_fields` were DELETED at the P6.2 strictness flip
(bd polyglot-pdf-h76m.16): v2 has NO trigger-side conditional logic. Every
dependency is expressed target-side as `show_if` (visibility) or `require_if`
(required-ness) -- the migration mirrored the old `shows`/`makes_required` edges
into those (merging with `any_of` when several triggers gate one target).

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
