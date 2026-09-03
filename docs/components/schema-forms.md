# Schema forms & client state

**Tracks:** frontend/src/schema-forms/state/schemaFormState.ts frontend/src/schema-forms/types/schema.ts frontend/src/schema-forms/components/SchemaForm.tsx frontend/src/schema-forms/components/FieldRenderer.tsx frontend/src/schema-forms/utils/fieldValue.ts frontend/src/schema-forms/utils/validation.ts frontend/src/schema-forms/utils/normalizeToComposite.ts frontend/src/schema-forms/utils/conditionalFieldCheck.ts

*Last updated: 2026-09-03 (bd polyglot-pdf-5ovod: blankness has ONE definition, `isBlankFieldValue` -- whitespace-only is not an answer at any of the six predicates that decide whether a field is filled).*

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
- `searchOriginFieldId` — where `computeNextField`'s scan RESUMES from, set to
  the field the user most recently acted on: a manual edit, or a click/focus
  **while no audio is playing** (bd polyglot-pdf-a08po). The scan starts just
  after it and WRAPS to the top, instead of always restarting at index 0 — so a
  user filling out of order is not dragged back to the first unconfirmed field
  after every entry, while fields they skipped past are still swept up on the way
  around. It is an ORIGIN, not a pin: it never forces a field to be next (a live
  `pinnedFieldId` still outranks it), and a stale id degrades to the old
  top-of-form scan. The companion `searchOriginIncludesSelf` says WHERE the
  origin sits in the rotation, because the two gestures mean opposite things
  about the field they name: a CLICK points AT it (`true` -- it is offered next,
  or the model would ask about a neighbour while the cursor sits here), while a
  manual EDIT answers it (`false` -- resume AFTER it; the rotation still returns
  to it last if it is somehow still unconfirmed). Confirming or skipping a field
  advances the origin to it too, so a verbal jump-and-answer resumes from the
  field just handled instead of falling back to a stale origin. The click
  suppression gates on `isAnyAudioPlaying()` -- the clip-INCLUSIVE union, not
  `isModelSpeaking()`: the deterministic spell-back clip plays only after the
  model's own PCM has drained, so a model-PCM-only gate leaves that whole window
  open, and `name_spellback` carries no field_id (it resolves the field through
  this same search), so a click there would spell a different field's value back.
  The reason a click waits at all: under DTI the model holds one field's schema
  and the backend coercion pointer is singular, so retargeting mid-question would
  mis-fill the spoken answer. Typing is unambiguous intent and moves the origin
  either way. Completion is unchanged: an empty search still means every shown
  field is confirmed.
- **Blankness has one definition where it GATES: `isBlankFieldValue`**
  (`utils/fieldValue.ts`, bd polyglot-pdf-5ovod). The predicates that decide
  whether a field is answered -- and so whether the form can complete, whether
  the model may confirm, and what it asks next -- all route through it:
  `isSectionValid` (the completion gate), `validateField`'s required check,
  `SectionRenderer`'s skip affordance, `hasUsableValue` (the confirm gate), and
  BOTH `hasValue` predicates in `computeNextField`.

  **This is NOT yet every value-presence check in the frontend.** Several
  lower-stakes ones still test `=== ''` untrimmed -- the progress counters, the
  `skip_field`/`switch_field` acks, the resume-section scan, and the preview
  painter -- so they can still read whitespace as present. None of them gates
  completion or confirmation, which is why they were out of this bead's scope;
  they are tracked as bd polyglot-pdf-qpz11. Do not read the list above as the
  complete set of emptiness checks.
  Whitespace-only counts as BLANK: typing spaces is not a decision, and leaving a
  field blank on a legal intake draft has to be explicit -- said aloud, or via the
  skip control.

  Those six sites each hand-wrote the check and every copy tested `=== ''`
  without trimming, so a space-filled field satisfied the completion gate, passed
  the required check, hid its own skip button, and was confirmable -- while
  printing blank on the PDF and never reaching the backend (whose predicates all
  `.strip()`, so the two sides disagreed about whether the field existed). The
  sharpest case was `computeNextField`, where BOTH priorities rejected it and the
  field became invisible to navigation entirely.

  Distinct from a genuine `''`: on an OPTIONAL field a confirmed empty string
  means "the user said this does not apply" (bd polyglot-pdf-6oe6 / w3ic), which
  is a real verbal answer and still confirms. Whitespace is NOT normalised to
  `''` -- doing so would make that path reachable by typing spaces.
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

`fieldValues` has **two independent writers**, and `validationErrors` is a third
map the UI owns alone (`SchemaForm.tsx`'s blur handler persists it without
touching `this.state`), so the reconciling handlers adopt the persisted
`validationErrors` wholesale — a fieldValues-only merge reverted a blur error
raised during the window, which stopped `isSectionValid` blocking on a genuinely
invalid field. The connection does not *add* entries to that map, but it does
**clear** them (`updateField` and `markFieldSkipped` delete the entry for the
field they write), which is why each adopt must stay *before* its mutator. The React UI (`SchemaForm.tsx`
`handleFieldChange` / `handleFieldSkip`) persists through `SchemaFormStateManager`
and never touches `WebFormConnection`'s in-memory `this.state`; the voice layer
holds `this.state` across turns. Any connection handler ending in
`SchemaFormStateManager.save(this.state)` can therefore persist a stale in-memory
copy over an on-screen edit.

**Every `SchemaFormStateManager` mutator spread-replaces the whole state and calls
`save()` internally**, so *any* of them invoked on a stale `this.state` persists
that stale copy. `reconcileFieldValues` (`utils/fieldValue.ts`) is the single
arbiter. The most important call site is **`WebFormConnection.updateField` — the
chokepoint every AI fill and manual edit funnels through**; its persisting call
sits two frames below the message handler, which is why six rounds of
handler-level auditing missed it. The others are `handleSessionReady`,
`handleConfirmFieldRequest`, `handleSkipFieldRequest`, `handleSectionSwitched`,
`handleDrainFindingsResult`, `handleValidationResult`, and `handleFormUpdated`
(bd `polyglot-pdf-qim7` / `uw3w` / `3irc` / `tare` / `6iwn`).

`confirmField` and `markFieldSkipped` both resolve the `[]`-alias and write back to
the RESOLVED key, exactly as `updateField` does — and `handleConfirmFieldRequest`'s
usable-value gate reads through the alias too. That matters *because* the reconcile
consolidates a pair onto one variant: the model routinely drops the bracket
(bd `polyglot-pdf-5k52`), so an exact-key read would miss the answer, refuse the
confirm as `no_value`, and the loop-breaker would tell Gemini to stop trying —
stranding a field that holds the user's answer. `markFieldSkipped` additionally
deletes the stale variant — it was the last remaining producer of the both-variants
state the reconcile then had to arbitrate (bd `polyglot-pdf-8c97`).

`handleSwitchFieldRequest` needs no reconcile: it adopts the persisted snapshot
wholesale at entry (bd `polyglot-pdf-ezg2`), so its write cannot be stale.

**A stale READ is as damaging as a stale write.** `handleFieldUpdate` and
`handleFormUpdated` reconcile at HANDLER ENTRY, not merely before their writes,
because their availability gate calls `shouldShowField` against
`this.state.fieldValues`. On a stale copy, a field whose `show_if` is satisfied by
a trigger the user answered *on screen* reads as unavailable, so the AI fill is
REFUSED outright — the value is never stored and the model is told "do not retry
until then", making the field unfillable for the turn. The `updateField`
chokepoint's own reconcile sits two frames below that gate, which is too late.

There is a **second staleness shape** that reconciling `this.state` does not
cover: `const s = load()` … `await` … `mutator(s)`. Here the local snapshot goes
stale across the await and the mutator persists it. `switchToSection` had exactly
this — its `waitForBufferDrain` polls for up to a full second — and the fix there
is to re-read *after* the await, not to reconcile two diverged copies.

`webFormConnection.persistsites.test.ts` pins both shapes: the persist-site list
as an **allowlist** (a newly-added site fails by default) and a check that no
persisting mutator reads a snapshot captured before an `await`. Six successive
review rounds each found one more instance, which is why the enumeration is
enforced in a test rather than trusted to a convention.

> **Why not just reconcile inside `save()`?** Because `confirmField` deliberately
> does not bump `lastModified` — it changes only confirmation metadata — so a
> reconcile there would see a tie, prefer the persisted entry, and silently drop
> `confirmed: true` on every confirmation. Verified by probe. Hence per-call-site
> reconciles.

It resolves
**per logical field**, not per raw key:

- The newer `lastModified` wins; a stamped entry beats an unstamped one; an equal
  stamp goes to the more authoritative side. The ordering rule and the marker
  carry each live in exactly ONE helper (`firstWins`, `mergeEntries`), used by
  both the cross-side comparison and the intra-side collapse — but the
  **no-ordering-information** case is an explicit argument, because the two
  callers genuinely differ. Across sides the two maps are two copies of one
  field's *history*, so a stamped blanking is a real later decision and the
  in-memory side is the conservative default (bd `pjws`). Within one side the two
  variants are not a history — they are one answer plus a stray key — so the
  entry that actually holds an answer must survive; importing the cross-side
  default there let a dated hollow entry destroy a real confirmed answer. That is deliberate:
  three review rounds found the intra-side path drifting from the cross-side one
  a cell at a time — first stamps, then dated-vs-undated, then equal stamps and
  the marker carry — each time letting a fresher hollow write (a skip, or the
  user clearing a field) lose to a staler answer on one side while winning across
  sides. Sharing the helpers makes that divergence structurally impossible rather
  than something to remember.
- `[]`-alias variants (`p1_grp` / `p1_grp[]`) collapse into ONE decision, so a
  merge can never resurrect a key `updateField` deleted on migration — that
  resurrection is what broke the one-entry invariant (bd `polyglot-pdf-got6`).
  **The surviving key is the one the SCHEMA declares**, which is why callers pass
  the schema's field ids; with no schema to consult it is the key of the *winning
  entry*, derived from the winner rather than computed separately (computing it
  separately let a bracketed winner land under the bare key). `SchemaForm`, `getProgress` and `isSectionValid` all
  index `fieldValues[field.id]` exactly, and a shipped kit really does use
  bracketed ids (`adult_intake_demo_schema.json`: `race[]`, `reason[]`,
  `risk_concerns[]` and three more) — so re-keying `race[]` → `race` would leave
  the answer live but invisible: blank on screen, progress down, required section
  no longer validating.
- A same-millisecond tie goes to the **persisted** side. `Date.now()` is coarser
  than the AI-write → on-screen-edit gap, so ties are a real case, and *both*
  directions are unsafe if the stale in-memory copy wins: a typed answer gets
  blanked by a skip, **and** a value the user cleared gets revived (and marked
  confirmed) by a confirm. A "meaningful entry wins" tie-break only covers the
  first — the cleared-value direction has the stale side holding the meaningful
  entry — so the durable side wins outright instead. A tie between two *different*
  meaningful values therefore resolves arbitrarily; that is safe only because it
  is unreachable, since every connection write stamps `lastModified` **and** saves
  in one step (so an equal stamp means both sides hold the same write).
  `markFieldsSteered` stamps for exactly this reason — an unstamped write would
  lose to any stamped one and the steer marker would be silently discarded.
  **Adding a path that mutates `this.state.fieldValues` without stamping and
  persisting would break that assumption.**
- An entry present on only one side is kept, so an in-memory-only value stays
  visible to the confirm handler's usable-value gate and the skip handler's
  already-filled guard (bd `polyglot-pdf-pjws`).
- The winner decides the VALUE, but sticky markers (`confirmed`, `confirmedAt`,
  `confirmationMethod`, `steered`, `skipped`) carry across from the losing side
  **when both sides agree on the value**. `confirmField` sets `confirmed` without
  bumping `lastModified`, so the loser can be the only side holding it, and
  dropping it would cause a spurious re-ask; `skipped` is load-bearing the same
  way, since `isSectionValid` and `getProgress` both honour it. The gate is value
  agreement, not a stamp tie: a marker describes the answer it was attached to, so
  it may follow that answer but must never follow a *different* one.

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
(desktop `VoiceOverlay` / mobile `VoiceOverlayMobile`, classified via a debounced
dead-zone hysteresis -- a flat 768px threshold at initial mount only, then a
700px/820px dead-zone band on later resizes so a width oscillating between them
keeps whatever mode is already active, bd polyglot-pdf-6vo -- which exists to stop
a resize-driven Gemini-session-restart loop)
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
(`handleFieldChange`). `field.copy_to` auto-copies the value to listed target
fields at the **write chokepoint** -- `SchemaFormStateManager.updateField` --
so EVERY path fans out, the voice path included (bd polyglot-pdf-gpaed). A
fanned target is always stamped confirmed, even when the source write was not:
a copy target is read_only, so the AI can neither fill nor skip it, and leaving
it unconfirmed would strand `computeNextField` on it. Validation runs on blur (`validateField`).
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

**`hidden: true` and `show_if` may not BOTH be set** (bd
`polyglot-pdf-pfx1`, maintainer decision 2026-08-04). When they are, this
function resolves the contradiction toward the CONDITION -- the third branch
returns `evaluateConditionGroup(...)` without consulting `hidden` -- so a
field marked never-show is DISPLAYED once its condition matches. That reading
is pinned (`utils/hiddenShowIfPrecedence.test.ts`, all four combinations) but
is NOT relied on: the state is made unauthorable upstream instead, by the
schema editor's mutual gate and schema-lint's `hidden-with-show-if` ERROR.

**But do NOT "simplify" the runtime toward that rule.** A kit is malformed at
the AUTHORING gate; at RUNTIME the seven `ubam` call sites must keep treating a
satisfied-condition field as fully live -- it renders, it is required, and it
must stay voice-reachable. Re-adding a `field.hidden ||` short-circuit anywhere
(navigation, the completion check, the voice field list) would skip such a
field and reintroduce exactly the false-completion + voice-unreachability bug
bd `polyglot-pdf-ubam` closed across seven sites. The gate stops the state being
CREATED; it does not license the runtime to start ignoring it.
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
- **`signature`/`address_group`/`table` are stubs** — don't assume all 13
  `FieldType`s render.
