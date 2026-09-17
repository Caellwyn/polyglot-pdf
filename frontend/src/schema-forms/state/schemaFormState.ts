/**
 * SchemaFormState - State manager for schema-driven form filling
 *
 * Manages form state in sessionStorage for PDF schema-based forms.
 * Enhanced with WebSocket compatibility for voice AI integration.
 *
 * Features:
 * - Persistent state across page reloads (sessionStorage)
 * - Part/section-based navigation
 * - Validation state tracking
 * - Field value management with AI confirmation tracking
 * - WebSocket handshake generation
 */

import type { FormSchema, FormSection, FormField, FormPart, FieldValue, ValidatorFinding } from "../types/schema";
import { buildHandshakeManifest, buildContinuousManifest, getFieldSchema } from "../utils/manifestUtils";
import { normalizeFieldValue, isFieldRequired, shouldShowField } from "../utils/validation";
import { isBlankFieldValue, isConfirmedButBlank } from "../utils/fieldValue";
import { readFieldEntryWithAlias, findFieldWithAlias } from "../utils/fieldValue";
import { loadOnboardingState, clearOnboardingState } from "../onboardingStorage";
import { clearClientLinkToken } from "../../shared/sessionCredential";
// Value imports for the JIT handshake's first-unfilled-field selection + hint.
// navigation.ts back-references SchemaFormState as a TYPE-only import, so this
// does not create a runtime import cycle (bd polyglot-pdf-jnjj.9).
import { computeNextField, formatNextFieldHint, getFieldOrder } from "../../navigation";

export interface SchemaFormState {
  schema: FormSchema;
  fieldValues: Record<string, FieldValue>; // field_id -> FieldValue (with confirmed flag)
  currentSectionId: string; // Section ID (e.g., "part_1_2_addresses")
  completedSections: Set<string>; // Track completed sections
  validationErrors: Record<string, string>; // field_id -> error message
  lastUpdated: number;
  sessionId?: string; // Set by backend during handshake (Gemini session ID)
  formSessionId: string; // Persistent ID for this form filling session (survives reconnects)

  // Phase 3: JIT (Just-In-Time) Schema Loading - Token Reduction
  loadedFieldIds: Set<string>; // Field IDs where Gemini has received full schema
  jitModeEnabled: boolean; // Whether JIT mode is active (from backend feature flag)

  // W2 (bd polyglot-pdf-kxkw): the async-validator STRIDE window builder. As
  // fields are confirmed, the client sends overlapping windows (size ~20, stride
  // ~10 over schema field order) of confirmed values to the backend validator via
  // the `validate_windows` message. This Set tracks which window INDICES have
  // already been sent so a window is never re-validated (the persisted
  // validated-window high-water mark; page-agnostic -- no pdf_position dependency,
  // report-cadence revision 2026-07-13). Serialized to an array like the other
  // Sets; defaults to empty for old sessions (no migration key needed -- brand new).
  validatedWindowIndices: Set<number>;

  // W3 (bd polyglot-pdf-pr3i): the finding-driven validator queue. A `validation_result`
  // (report-only since W3) carries surviving contradictions as CANDIDATES; the client
  // ENQUEUES them here and drains IMMEDIATELY via a `drain_findings` round-trip (the
  // backend composes + injects one steer). A plain array (order-preserving, small);
  // serialized as-is (no Set conversion); defaults to [] for old sessions. CLIENT-OWNED:
  // survives a reconnect + batches concurrent findings into one steer (NOT a boundary
  // buffer). A drained + delivered finding is consumed (removed) on the drain result.
  validatorFindingsQueue: ValidatorFinding[];
  // Continuous-session mode (bd polyglot-pdf-x8rt): the whole form runs as ONE
  // session (no section resets). When on, the handshake spans every field as a
  // single synthetic section and section advancement is suppressed. From the
  // backend CONTINUOUS_SESSION flag via session_ready.
  continuousSessionEnabled: boolean;

  // Disclaimer acceptance tracking
  disclaimerAccepted: boolean; // Whether user has accepted disclaimer
  disclaimerAcceptedAt?: number; // Timestamp of disclaimer acceptance
  selectedLanguage?: string; // User's selected spoken language

  // Field-level navigation pin (bd polyglot-pdf-jnjj.36): set by the AI's
  // switch_to_field tool. While set (and the field is visible + unconfirmed),
  // computeNextField returns THIS field first, so every "what's next" consumer
  // -- the next-field hint, the DTI schema drip, UI focus via onNextField --
  // follows the jump with no extra plumbing. Cleared when the pinned field is
  // confirmed or skipped (the form then resumes its normal fill order).
  pinnedFieldId?: string | null;

  // Where the next-field search RESUMES from (bd polyglot-pdf-a08po). Set to
  // the field the user most recently acted on -- a manual edit, or a click/
  // focus while no audio is playing. computeNextField starts its scan at this
  // field's position and WRAPS to the top, instead of always restarting at
  // index 0.
  //
  // Why: without it, every manual edit re-targeted the model at the FIRST
  // unconfirmed field while the user was working far below it, so a
  // mostly-manual user had the model's focus yanked back to the top of the
  // form after each entry. Wrapping also means fields the user skipped past
  // are swept up on the way around -- there is no separate end-of-form
  // "redirect to missed fields" phase, and completion is unchanged (the
  // search coming up empty is still exactly isFormComplete's condition).
  //
  // This is a SEARCH ORIGIN, not a pin: it never forces a field to be next
  // (an unconfirmed field AT the origin is returned by the normal priority
  // rules, not by virtue of being the origin), and a stale value is harmless
  // -- an id that no longer resolves just falls back to index 0.
  searchOriginFieldId?: string | null;

  // Whether the origin field is itself the FIRST candidate in the rotation
  // (bd polyglot-pdf-a08po). The two gestures that set an origin mean opposite
  // things about the field they name:
  //   true  -- a CLICK/focus: the user is POINTING at it, so it must be offered
  //            next, or the model asks about a neighbour while their cursor
  //            sits here.
  //   false -- a manual EDIT: the user just ANSWERED it, so the scan resumes
  //            AFTER it (the rotation still returns to it last if it is
  //            somehow still unconfirmed).
  searchOriginIncludesSelf?: boolean;
}

export class SchemaFormStateManager {
  private static readonly STORAGE_KEY = "schema_form_state";

  /**
   * Generate a unique form session ID
   * Format: fss_<timestamp>_<random>
   */
  private static generateFormSessionId(): string {
    const timestamp = Date.now().toString(36); // Base36 encoded timestamp
    const random = Math.random().toString(36).substring(2, 10); // 8 random chars
    return `fss_${timestamp}_${random}`;
  }

  /**
   * Reconcile a STORED session against a FRESH schema (bd polyglot-pdf-g2fpr,
   * PR 3c -- the stale-session guard).
   *
   * A session persisted under one shape of the kit can be resumed under
   * another: the select migration turns option values from export codes
   * ('AL') into slugs ('alabama') while a browser still holds 'AL' in
   * sessionStorage. Left alone, that value matches no option: the <select>
   * renders EMPTY, the field stays confirmed so it is never re-asked, and the
   * filler writes 'AL' verbatim -- right only because the old value happens
   * to equal the new pdf_on_value. So, for every select whose stored value is
   * not one of the fresh schema's option values:
   *   - if it equals some option's pdf_on_value, map it to that option's
   *     value (the migration case, lossless, confirmation kept);
   *   - otherwise clear the field and drop its confirmation, so it is asked
   *     again rather than silently kept.
   * Non-select fields and values that already match are untouched. Pure:
   * returns a new state; the caller saves.
   *
   * Also ADOPTS the fresh schema. init() reused the stored schema wholesale
   * for an hour after any kit edit, so a migrated kit's new options never met
   * the stored values until fill time.
   */
  static reconcileSelectValues(state: SchemaFormState, freshSchema: FormSchema): SchemaFormState {
    const fields = freshSchema.fields || [];
    const next: Record<string, FieldValue> = { ...state.fieldValues };
    let changed = false;
    for (const field of fields) {
      if (field.type !== 'select' || !Array.isArray(field.options)) continue;
      const entry = next[field.id];
      if (!entry || typeof entry.value !== 'string' || entry.value === '') continue;
      const opts = field.options.filter((o): o is any => !!o && typeof o === 'object');
      if (opts.some((o) => o.value === entry.value)) continue;       // already current
      // A CLAIMANT is an option carrying this code in pdf_on_value AND a real
      // (non-empty string) value -- the same filter /resume-form applies
      // (pdf_fill_routes.resolve_select_resume_value). Fresh-eyes found the
      // first cut accepting an empty-valued option and mapping the field to
      // '' while keeping it confirmed.
      const byCode = opts.filter(
        (o) => (o as any).pdf_on_value === entry.value
          && typeof o.value === 'string' && o.value !== '',
      );
      if (byCode.length === 1) {
        next[field.id] = { ...entry, value: byCode[0].value };      // lossless map
      } else {
        // Unmappable (or ambiguous -- never guess between two claimants):
        // clear it and let the session ask again.
        delete next[field.id];
      }
      changed = true;
    }
    const schemaChanged = state.schema !== freshSchema;
    if (!changed && !schemaChanged) return state;
    // Adopting a fresh schema can strand ids the stored session computed
    // against the old one. Reset the three that name a single field/section
    // and would otherwise dangle; the id Sets (loadedFieldIds,
    // validatedWindowIndices) tolerate extras and are left alone.
    const fieldIds = new Set(fields.map((f) => f.id));
    const sectionIds = new Set((freshSchema.sections || []).map((s) => s.id));
    // Leave an id UNTOUCHED unless it dangles, so a caller comparing before
    // and after sees a change only when one really happened. (load() already
    // normalizes a missing id to null, so this is the cleaner contract rather
    // than something the persist gate depends on -- a mutant that rewrote
    // undefined to null reddened nothing.)
    const pinned = state.pinnedFieldId && !fieldIds.has(state.pinnedFieldId)
      ? null : state.pinnedFieldId;
    const origin = state.searchOriginFieldId && !fieldIds.has(state.searchOriginFieldId)
      ? null : state.searchOriginFieldId;
    const section = sectionIds.has(state.currentSectionId)
      ? state.currentSectionId
      : (this.getFirstSection(freshSchema)?.id ?? state.currentSectionId);
    return {
      ...state,
      schema: freshSchema,
      // Identity is the contract: a caller persists only when VALUES changed,
      // never for a bare schema swap (the vanilla path's load migrations are
      // lazy by contract; a value change is a real migration worth persisting).
      fieldValues: changed ? next : state.fieldValues,
      pinnedFieldId: pinned,
      searchOriginFieldId: origin,
      currentSectionId: section,
    };
  }

  /**
   * Initialize or load existing form state
   */
  static init(schema: FormSchema): SchemaFormState {
    const existing = this.load();

    // Clean up duplicate sections (e.g., Part 7 appears twice with different capitalization)
    const cleanedSchema = this.deduplicateSections(schema);

    // If schema matches and it's recent (< 1 hour), reuse state
    if (
      existing &&
      existing.schema.form_metadata.form_number === cleanedSchema.form_metadata.form_number &&
      existing.schema.form_metadata.version === cleanedSchema.form_metadata.version &&
      Date.now() - existing.lastUpdated < 60 * 60 * 1000
    ) {
      // Ensure formSessionId exists (migration for existing sessions)
      if (!existing.formSessionId) {
        existing.formSessionId = this.generateFormSessionId();
        this.save(existing);
      }
      // Backfill for states created before bd p8sq: an in-flight session may
      // carry no selectedLanguage even though onboarding recorded one -- seed
      // it so the next (re)connect handshake carries the language.
      if (!existing.selectedLanguage) {
        const onboardingLanguage = loadOnboardingState().language;
        if (onboardingLanguage) {
          existing.selectedLanguage = onboardingLanguage;
          this.save(existing);
        }
      }
      // The stored session meets the FRESH schema here and nowhere else
      // (bd polyglot-pdf-g2fpr, PR 3c): adopt it and map every select value
      // through it, so a session saved under the pre-migration shape does
      // not resume with values no option carries.
      const reconciled = this.reconcileSelectValues(existing, cleanedSchema);
      if (reconciled !== existing) {
        this.save(reconciled);
        return reconciled;
      }
      return existing;
    }

    // New session - initialize with first section
    const firstSection = this.getFirstSection(cleanedSchema);

    const newState: SchemaFormState = {
      schema: cleanedSchema,
      fieldValues: {},
      currentSectionId: firstSection?.id || "",
      completedSections: new Set(),
      validationErrors: {},
      lastUpdated: Date.now(),
      formSessionId: this.generateFormSessionId(), // Persistent ID for this form session
      // JIT schema loading (Phase 3: Token Reduction)
      loadedFieldIds: new Set(),
      jitModeEnabled: false, // Will be set during handshake based on backend flag
      // W2 (bd polyglot-pdf-kxkw): validated-window high-water mark (empty at start).
      validatedWindowIndices: new Set(),
      // W3 (bd polyglot-pdf-pr3i): finding-driven validator queue (empty at start).
      validatorFindingsQueue: [],
      continuousSessionEnabled: false, // Set during handshake from the backend CONTINUOUS_SESSION flag
      // Disclaimer acceptance
      disclaimerAccepted: false,
      disclaimerAcceptedAt: undefined,
      // Seed the spoken language from the app-start onboarding choice (bd
      // polyglot-pdf-p8sq): the FIRST connect's handshake reads
      // state.selectedLanguage, and before this seed it was only written at
      // disclaimer-AGREE -- so the disclaimer-phase connection got an en-US
      // ASR bias and skipped the option-translation warm-up (bd y25o / ow1e
      // intent defeated for the first connect).
      selectedLanguage: loadOnboardingState().language ?? undefined,
      pinnedFieldId: null, // Field-level navigation pin (bd jnjj.36)
      searchOriginFieldId: null, // Next-field search origin (bd a08po)
      searchOriginIncludesSelf: false,
    };

    this.save(newState);
    return newState;
  }

  /**
   * Load state from sessionStorage
   */
  static load(): SchemaFormState | null {
    try {
      const stored = sessionStorage.getItem(this.STORAGE_KEY);
      if (!stored) {
        // Silently return null if no stored state
        return null;
      }

      // Silently load - only log on init, not on every load
      const parsed = JSON.parse(stored);

      // Restore Set from array
      if (parsed.completedSections) {
        parsed.completedSections = new Set(parsed.completedSections);
      } else if (parsed.completedParts) {
        // Backwards compatibility: migrate completedParts -> completedSections
        parsed.completedSections = new Set(parsed.completedParts);
        delete parsed.completedParts;
      }

      // Backwards compatibility: migrate currentPartId -> currentSectionId
      if (parsed.currentPartId && !parsed.currentSectionId) {
        parsed.currentSectionId = parsed.currentPartId;
        delete parsed.currentPartId;
      }

      // Phase 3: JIT schema loading - Restore loadedFieldIds Set
      if (parsed.loadedFieldIds) {
        parsed.loadedFieldIds = new Set(parsed.loadedFieldIds);
      } else {
        // Initialize if missing (old state)
        parsed.loadedFieldIds = new Set();
      }

      // W2 (bd polyglot-pdf-kxkw): restore the validated-window index Set. No
      // legacy-key migration -- the key is brand new, so an old session simply
      // starts with an empty set (every window re-eligible, which is correct: a
      // pre-W2 session never sent any windows).
      if (parsed.validatedWindowIndices) {
        parsed.validatedWindowIndices = new Set(parsed.validatedWindowIndices);
      } else {
        parsed.validatedWindowIndices = new Set();
      }

      // W3 (bd polyglot-pdf-pr3i): restore the finding queue (a plain array -- no Set
      // conversion). Default [] for a pre-W3 session (no key stored). Guard the type
      // so a corrupted non-array blob cannot crash the enqueue/drain ops downstream.
      parsed.validatorFindingsQueue = Array.isArray(parsed.validatorFindingsQueue)
        ? parsed.validatorFindingsQueue
        : [];

      // Initialize jitModeEnabled if missing (old state)
      if (parsed.jitModeEnabled === undefined) {
        parsed.jitModeEnabled = false;
      }

      // Initialize continuousSessionEnabled if missing (old state)
      if (parsed.continuousSessionEnabled === undefined) {
        parsed.continuousSessionEnabled = false;
      }

      // Initialize the navigation pin if missing (old state, bd jnjj.36)
      if (parsed.pinnedFieldId === undefined) {
        parsed.pinnedFieldId = null;
      }

      // Initialize the search origin if missing (old state, bd a08po). A
      // persisted session from before this field existed resumes from the top,
      // which is exactly the previous behavior.
      if (parsed.searchOriginFieldId === undefined) {
        parsed.searchOriginFieldId = null;
      }
      if (parsed.searchOriginIncludesSelf === undefined) {
        parsed.searchOriginIncludesSelf = false;
      }

      // Initialize disclaimer fields if missing (migration for existing sessions)
      if (parsed.disclaimerAccepted === undefined) {
        parsed.disclaimerAccepted = false;
      }
      if (parsed.disclaimerAcceptedAt === undefined) {
        parsed.disclaimerAcceptedAt = undefined;
      }
      if (parsed.selectedLanguage === undefined) {
        parsed.selectedLanguage = undefined;
      }

      return parsed as SchemaFormState;
    } catch (error) {
      console.error("[SchemaFormState] Failed to load state:", error);
      return null;
    }
  }

  /**
   * Save state to sessionStorage
   */
  static save(state: SchemaFormState): void {
    try {
      // Convert Sets to arrays for JSON serialization
      const toStore = {
        ...state,
        completedSections: Array.from(state.completedSections),
        loadedFieldIds: Array.from(state.loadedFieldIds), // Phase 3: JIT schema loading
        validatedWindowIndices: Array.from(state.validatedWindowIndices), // W2 (bd kxkw)
        lastUpdated: Date.now(),
      };

      // Silently save - no need for console spam
      const jsonString = JSON.stringify(toStore);
      sessionStorage.setItem(this.STORAGE_KEY, jsonString);

      // Fire custom event so SchemaForm knows to reload
      window.dispatchEvent(new CustomEvent('schemaFormStateChange', { detail: state }));
    } catch (error) {
      console.error("[SchemaFormState] Failed to save state:", error);
    }
  }

  /**
   * Update a field value (WebSocket-compatible)
   *
   * @param state Current state
   * @param fieldId Field ID to update
   * @param value Raw value OR FieldValue object
   * @param options Additional options (confirmed, etc.)
   */
  /**
   * W4 (bd polyglot-pdf-ny4s): value-equality for the re-arm decision. A field's
   * value is a string / boolean / null (single fields) or an array of strings
   * (checkbox groups). Compare by NORMALIZED content:
   *   - empty-ish values (undefined / null / '' / all-blank []) all count as "no
   *     value", so a fill that clears a previously-filled field is a change but a
   *     blank->blank write is not;
   *   - a checkbox group is a SET, so arrays compare ORDER-INSENSITIVELY after
   *     dropping blank placeholders. (The real CheckboxField.handleToggle APPENDS a
   *     re-checked value, so unchecking then re-checking a box yields the same set
   *     in a different order -- an order-sensitive compare would wrongly re-arm the
   *     marker, nagging the user for a no-op toggle: fresh-eyes finding.)
   *   - primitives compare by ===.
   */
  private static _sameFieldValue(a: any, b: any): boolean {
    const isEmpty = (v: any): boolean =>
      v === undefined || v === null || v === '' ||
      (Array.isArray(v) && v.every((x) => x === undefined || x === null || x === ''));
    if (isEmpty(a) && isEmpty(b)) return true;
    if (isEmpty(a) !== isEmpty(b)) return false;
    if (Array.isArray(a) || Array.isArray(b)) {
      // Set-equality on the non-blank members (a checkbox group is an unordered set).
      const clean = (v: any): string[] =>
        (Array.isArray(v) ? v : [v])
          .filter((x) => x !== undefined && x !== null && x !== '')
          .map((x) => String(x))
          .sort();
      const aa = clean(a);
      const bb = clean(b);
      if (aa.length !== bb.length) return false;
      return aa.every((x, i) => x === bb[i]);
    }
    return a === b;
  }

  static updateField(
    state: SchemaFormState,
    fieldId: string,
    value: any | FieldValue,
    options?: {
      confirmed?: boolean;
      confirmationMethod?: 'ai_voice' | 'manual_edit';
      // Internal: set on the recursive writes this method makes to a field's
      // copy_to targets, so a target carrying its own copy_to does not chain.
      // Callers should not pass it (bd polyglot-pdf-gpaed).
      //
      // NOTE for a future caller: the fan-out passes `value` through unchanged,
      // so if you ever call updateField with a FieldValue OBJECT rather than a
      // raw value, the branch below copies that object's OWN confirmed/method
      // and the fan-out's `confirmed: true` is silently ignored -- re-opening
      // the navigation trap. All 8 call sites pass raw values today; the
      // signature (`value: any | FieldValue`) is what invites otherwise.
      skipCopyTo?: boolean;
    }
  ): SchemaFormState {
    // Normalize the raw value to its canonical stored form (e.g. strip an
    // A-Number's "A" prefix/separators) so manual edits store the same canonical
    // value the backend stores for AI fills (bd polyglot-pdf-0zr). Idempotent for
    // already-canonical values (e.g. AI fills, which the backend pre-normalizes).
    // Resolve the schema field via the same `[]`-alias fallback used for the prior
    // entry below: a value written under the bracketed variant (fieldId[]) must
    // still find its schema field so it is NORMALIZED consistently -- otherwise a
    // bracket-variant write of a format_preset field (a_number etc.) stores the raw
    // value, and a later same-answer canonical write normalizes and compares
    // unequal, spuriously re-arming the marker (W4 fresh-eyes finding).
    const field = findFieldWithAlias(state.schema.fields, fieldId);

    // The B5 `steered` marker (bd polyglot-pdf-jnjj.17, Codex PR #275) rides the
    // FieldValue. The normal edit/fill path REPLACES the FieldValue object, which
    // would silently drop it. Read the prior entry via the same `[]`-alias fallback
    // as markFieldsSteered: the marker may sit under the bracketed/unbracketed
    // variant of this id (Gemini drops/adds the bracket), and an exact-key read
    // would drop it when the value migrates between variants (bd polyglot-pdf-5k52).
    const aliasId = fieldId.endsWith('[]') ? fieldId.slice(0, -2) : fieldId + '[]';
    // Track WHICH key the prior entry lived under so a cross-variant migration can
    // remove the stale one (bd polyglot-pdf-got6). Exact key wins; else the []-alias.
    const priorKey =
      state.fieldValues[fieldId] !== undefined
        ? fieldId
        : state.fieldValues[aliasId] !== undefined
          ? aliasId
          : undefined;
    const priorEntry = priorKey ? state.fieldValues[priorKey] : undefined;
    const priorSteered = priorEntry?.steered;

    // W4 (bd polyglot-pdf-ny4s): RE-ARM the marker on a VALUE change. The prior
    // rule carried `steered` forward unconditionally, so a CORRECTION to an
    // already-adjudicated field was never re-validated (a correction that introduces
    // a fresh contradiction slipped the net) and a genuinely new conflict on a
    // steered field was suppressed forever. New rule: carry `steered` forward ONLY
    // when the field's normalized VALUE did not change; a value change CLEARS it, so
    // the corrected field re-enters the validator net. The no-nagging guarantee
    // (jnjj.17 criterion 3) is preserved where it matters: a user who confirms "both
    // are intentional" changes NO value, so the marker stays and they are never
    // re-asked -- only a field whose value actually moved re-arms.
    const incomingRawValue =
      value && typeof value === 'object' && 'value' in value
        ? (value as FieldValue).value
        : value;
    const normalizedNewValue = field
      ? normalizeFieldValue(field, incomingRawValue)
      : incomingRawValue;
    // Normalize the PRIOR value too before comparing -- a value written under the
    // bracket-variant before this alias-aware lookup landed may be stored raw, so
    // compare both sides in canonical form (normalizeFieldValue is idempotent on an
    // already-canonical value) to avoid a spurious re-arm on a genuinely-same answer.
    const normalizedPriorValue = field
      ? normalizeFieldValue(field, priorEntry?.value)
      : priorEntry?.value;
    const valueChanged = !this._sameFieldValue(normalizedPriorValue, normalizedNewValue);
    // Carry the marker forward only if it was set AND the value is unchanged.
    const carrySteered = priorSteered !== undefined && !valueChanged;

    // If value is already a FieldValue, use it directly (normalize its .value)
    // Otherwise, wrap it
    let fieldValue: FieldValue;
    if (value && typeof value === 'object' && 'value' in value) {
      // Already a FieldValue object
      const fv = value as FieldValue;
      const merged = field ? { ...fv, value: normalizeFieldValue(field, fv.value) } : { ...fv };
      // An explicit `steered` on the incoming FieldValue wins; otherwise re-arm rule.
      if (merged.steered === undefined) {
        if (carrySteered) merged.steered = priorSteered;
        else delete merged.steered;
      }
      fieldValue = merged;
    } else {
      // Wrap raw value in FieldValue
      fieldValue = {
        value: normalizedNewValue,
        confirmed: options?.confirmed,
        confirmedAt: options?.confirmed ? new Date().toISOString() : undefined,
        confirmationMethod: options?.confirmationMethod,
        lastModified: Date.now(),
        ...(carrySteered ? { steered: priorSteered } : {}),
      };
    }

    const nextFieldValues = {
      ...state.fieldValues,
      [fieldId]: fieldValue,
    };
    // W6-adjacent hygiene (bd polyglot-pdf-got6): a value that MIGRATES between the
    // []-alias variants (prior entry under `field-1`, new write under `field-1[]` or
    // vice-versa) must not leave the STALE entry (old value + old steered marker)
    // under the other key. Both coexisting would let a downstream reader that prefers
    // the exact schema-id key (buildValidatorFields' valueFor) pick up the stale
    // value/steered and defeat W4's re-arm. Drop the stale variant so exactly ONE
    // entry represents the field.
    if (priorKey && priorKey !== fieldId) {
      delete nextFieldValues[priorKey];
    }

    const newState = {
      ...state,
      fieldValues: nextFieldValues,
      lastUpdated: Date.now(),
    };

    // Clear validation error for this field
    if (newState.validationErrors[fieldId]) {
      const { [fieldId]: removed, ...rest } = newState.validationErrors;
      newState.validationErrors = rest;
    }

    // AUTO-POPULATE (copy_to) fans out HERE, at the single write chokepoint, so
    // EVERY path gets it (bd polyglot-pdf-gpaed). It used to live in exactly one
    // caller -- SchemaForm's React manual-edit handler -- so the VOICE path
    // never fanned out at all: a value Gemini filled left its copy targets
    // blank. Combined with the read-only coupling the editor now applies to a
    // copy target (bd polyglot-pdf-g33y2), a REQUIRED target was unreachable --
    // the AI cannot write a read_only field and isSectionValid does not excuse
    // it, so the section gate could never be satisfied.
    //
    // Placed before save() so the targets persist in the same write. Each hop
    // RE-ENTERS this method, so a target is normalized against ITS OWN schema
    // field -- source and target need not share a format_preset for the target
    // to store a canonical value.
    //
    // ONE HOP, not transitive: a target's own copy_to is not followed. That
    // matches what the single-caller version did, so this changes WHICH paths
    // fan out, not how far. `skipCopyTo` makes the recursion explicit rather
    // than relying on that -- a chained link would otherwise re-enter here per
    // target and each re-entry would save() again.
    if (!options?.skipCopyTo) {
      const targets = Array.isArray(field?.copy_to) ? field.copy_to : [];
      let fanned = newState;
      for (const targetId of targets) {
        if (typeof targetId !== 'string' || !targetId) continue;
        if (targetId === fieldId) continue;          // self-link: hand-edited junk
        // A fanned target is CONFIRMED, always -- even when the source write
        // was not. A copy target is not a question anyone can answer: the AI
        // is refused (it is read_only), and skip_field is refused too once it
        // holds a value. So an unconfirmed target is a TRAP -- computeNextField
        // navigates to the first filled-but-unconfirmed field, and on the
        // shipped i-90 kits that is p8_a_number et al, which the model can
        // neither fill nor skip. isFormComplete and computeReadyWindows also
        // key on confirmed, so the form could never read complete.
        //
        // Inheriting confirmation is honest: the human DID answer this value,
        // on the source. The method records HOW -- carrying the source's own
        // confirmationMethod, or 'manual_edit' when the source write carried
        // none (the AI-fill case), since a fan-out is a derived write rather
        // than something the model said (fresh-eyes + cross-surface, round 2).
        fanned = SchemaFormStateManager.updateField(fanned, targetId, value, {
          ...options,
          confirmed: true,
          confirmationMethod: options?.confirmationMethod ?? 'manual_edit',
          skipCopyTo: true,
        });
      }
      if (fanned !== newState) {
        this.save(fanned);
        return fanned;
      }
    }

    this.save(newState);
    return newState;
  }

  /**
   * Set validation error for a field
   */
  static setValidationError(
    state: SchemaFormState,
    fieldId: string,
    error: string | null
  ): SchemaFormState {
    const newState = { ...state };

    if (error) {
      newState.validationErrors = {
        ...state.validationErrors,
        [fieldId]: error,
      };
    } else {
      const { [fieldId]: removed, ...rest } = state.validationErrors;
      newState.validationErrors = rest;
    }

    this.save(newState);
    return newState;
  }

  /**
   * Navigate to a different section
   */
  static navigateToSection(state: SchemaFormState, sectionId: string): SchemaFormState {
    const newState = {
      ...state,
      currentSectionId: sectionId,
      // A section change abandons any field-level navigation pin, same as
      // switchToSection -- a stale voice-set pin must not hijack next-field
      // computation after a MANUAL section jump (bd polyglot-pdf-jnjj.36,
      // outer review).
      pinnedFieldId: null,
      lastUpdated: Date.now(),
    };

    this.save(newState);
    return newState;
  }

  /**
   * Page the VISIBLE section to follow the voice model in continuous mode
   * (bd polyglot-pdf-gz20; continuous-mode design is bd polyglot-pdf-55jg). Sets
   * ONLY currentSectionId -- unlike navigateToSection
   * it PRESERVES pinnedFieldId, because this is not a manual jump that should
   * abandon a voice-set pin: it follows the model's own focus, and a switch_to_field
   * to an out-of-section target sets the pin THEN drives this via onNextField -- so
   * clearing the pin here would wipe the pin that same tool just set (both the
   * connection's state and this one persist through the shared sessionStorage key, so
   * a pin-clearing save would clobber it). No completed-section side effects either;
   * continuous mode never grows completedSections. Idempotent when already on the
   * target section.
   */
  static setVisibleSection(state: SchemaFormState, sectionId: string): SchemaFormState {
    if (state.currentSectionId === sectionId) return state;
    const newState = {
      ...state,
      currentSectionId: sectionId,
      lastUpdated: Date.now(),
    };
    this.save(newState);
    return newState;
  }

  /**
   * Mark section as completed
   *
   * DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
   * continuous-DTI is the live flow. Kept as a fallback, not deleted.
   * Do not extend.
   */
  static markSectionComplete(state: SchemaFormState, sectionId: string): SchemaFormState {
    const newState = {
      ...state,
      completedSections: new Set([...state.completedSections, sectionId]),
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  /**
   * Get current section from schema
   */
  static getCurrentSection(state: SchemaFormState): FormSection | null {
    return state.schema.sections.find((s) => s.id === state.currentSectionId) || null;
  }

  /**
   * Get fields for current section
   */
  static getCurrentSectionFields(state: SchemaFormState): FormField[] {
    const section = this.getCurrentSection(state);
    if (!section) return [];

    // []-alias-aware lookup (bd polyglot-pdf-rctj), matching
    // findSectionIdForField below: a section.fields entry and the matching
    // field.id can carry DIFFERENT bracket forms of the same field (Gemini
    // drops/adds the trailing [] inconsistently), so an exact-only match can
    // silently drop a field that IS in this section from the rendered list
    // -- the field would appear missing even though onNextField correctly
    // paged the UI to this section for it.
    return section.fields
      .map((fieldId) => {
        return findFieldWithAlias(state.schema.fields, fieldId);
      })
      .filter((f): f is FormField => f !== undefined);
  }

  /**
   * Get next section (for navigation)
   */
  static getNextSection(state: SchemaFormState): FormSection | null {
    const currentSection = this.getCurrentSection(state);
    if (!currentSection) {
      return null;
    }

    const sortedSections = [...state.schema.sections].sort((a, b) => a.order - b.order);
    const currentIndex = sortedSections.findIndex((s) => s.id === currentSection.id);

    if (currentIndex === -1) {
      console.error('[getNextSection] Current section ID not found in sorted sections!');
      return null;
    }

    if (currentIndex === sortedSections.length - 1) {
      return null; // No next section
    }

    return sortedSections[currentIndex + 1];
  }

  /**
   * Get previous section (for navigation)
   */
  static getPreviousSection(state: SchemaFormState): FormSection | null {
    const currentSection = this.getCurrentSection(state);
    if (!currentSection) return null;

    const sortedSections = [...state.schema.sections].sort((a, b) => a.order - b.order);
    const currentIndex = sortedSections.findIndex((s) => s.id === currentSection.id);

    if (currentIndex <= 0) {
      return null; // No previous section
    }

    return sortedSections[currentIndex - 1];
  }


  /**
   * Find the ID of the section that contains a given field, or null if the
   * field is in no section. Used to advance the paged UI to follow the voice
   * model in continuous mode (bd polyglot-pdf-gz20): the model fills fields
   * across the whole form in one session, but the simplified view still renders
   * one section at a time -- so when the model's focus (onNextField) lands on a
   * field outside the currently-shown section, the UI must page to that field's
   * section. Mirrors getCurrentSectionFields' `section.fields` (array of field
   * ids) lookup. Matches across the []-alias variants because the incoming id
   * and the section's `fields` entry can carry DIFFERENT bracket forms of the
   * same field (Gemini drops/adds the bracket, so a generated schema may list
   * `race[]` in section.fields while a caller passes the base `race`, or vice
   * versa). Today's callers pass a base schema id (computeNextField /
   * resolveFieldForNavigation both return `field.id`), so the fallback bites
   * only on the section-side bracket variant -- matching both directions keeps
   * it robust to either side carrying the bracket.
   */
  static findSectionIdForField(state: SchemaFormState, fieldId: string): string | null {
    if (!fieldId) return null;
    const baseId = fieldId.endsWith('[]') ? fieldId.slice(0, -2) : fieldId;
    const aliasId = baseId + '[]';
    for (const section of state.schema.sections) {
      if (
        section.fields.includes(fieldId) ||
        section.fields.includes(baseId) ||
        section.fields.includes(aliasId)
      ) {
        return section.id;
      }
    }
    return null;
  }

  /**
   * Get first section from schema
   */
  private static getFirstSection(schema: FormSchema): FormSection | null {
    const sortedSections = [...schema.sections].sort((a, b) => a.order - b.order);
    return sortedSections[0] || null;
  }

  /**
   * Deduplicate sections with EXACT duplicate IDs only
   * (Disabled the aggressive "Part N" merging for section-based navigation)
   */
  private static deduplicateSections(schema: FormSchema): FormSchema {
    // Only deduplicate if there are actual duplicate IDs (exact matches)
    const seenIds = new Set<string>();
    const deduplicatedSections: FormSection[] = [];

    for (const section of schema.sections) {
      if (!seenIds.has(section.id)) {
        seenIds.add(section.id);
        deduplicatedSections.push(section);
      } else {
        // True duplicate found - merge fields
        console.warn(`[SchemaFormState] Duplicate section ID found: ${section.id}`);
        const existing = deduplicatedSections.find(s => s.id === section.id);
        if (existing) {
          existing.fields = [...existing.fields, ...section.fields];
        }
      }
    }

    // Sort by original order field
    deduplicatedSections.sort((a, b) => a.order - b.order);

    if (schema.sections.length !== deduplicatedSections.length) {
      console.log(`[SchemaFormState] Removed ${schema.sections.length - deduplicatedSections.length} duplicate sections`);
    }

    return {
      ...schema,
      sections: deduplicatedSections,
    };
  }

  /**
   * Clear all state (for testing/logout)
   */
  static clear(): void {
    sessionStorage.removeItem(this.STORAGE_KEY);
  }

  /**
   * The single Clear-form path (bd polyglot-pdf-8v8i7): wipes the form state,
   * the onboarding form/language selection, and a redeemed client-link token
   * in one call, so every browser-PII clearing trigger (form complete, idle
   * timeout, logout) leaves no client answer or credential behind on a
   * shared device. `clear()` above is a silent `sessionStorage.removeItem` --
   * it does not dispatch `schemaFormStateChange` -- so a caller that needs the
   * UI to react to the wipe must refresh it itself.
   */
  static clearAllClientState(): void {
    this.clear();
    clearOnboardingState();
    clearClientLinkToken();
  }

  /**
   * Get form completion progress (percentage). Delegates to getProgressCounts
   * (below) for the actual {filled, total} -- see that method's doc for the
   * full visible-field-filtering rationale (bd polyglot-pdf-52qm.7 /
   * polyglot-pdf-kbkd); this wrapper only turns the ratio into a percentage.
   */
  static getProgress(state: SchemaFormState): number {
    const { filled, total } = this.getProgressCounts(state);
    if (total === 0) return 0;
    return (filled / total) * 100;
  }

  /**
   * Get the raw {filled, total} counts behind getProgress -- for a caller
   * that wants to display "N of M fields" rather than a percentage (bd
   * polyglot-pdf-kbkd). Same visible-field filter, same SKIPPED-counts-as-done
   * rule, factored out so a UI counter cannot drift from what the progress
   * bar itself counts -- the exact drift VoiceOverlay/VoiceOverlayMobile had
   * with their own inline `schema.fields.length` + raw fieldValues scans.
   *
   * Counts ONLY the fields the user can actually act on right now (bd
   * polyglot-pdf-52qm.7). Visibility is `shouldShowField` ALONE -- deliberately
   * NOT `!f.hidden && shouldShowField(...)`. shouldShowField already returns
   * `!field.hidden` for the no-show_if case, so ANDing an extra `!f.hidden`
   * diverges from what actually renders: a field with `hidden: true` AND a
   * SATISFIED `show_if` is rendered by FieldRenderer and is required by
   * isSectionValid, so excluding it here would drop an answerable field from
   * BOTH halves of the ratio -- the very "bar never reads complete" bug this
   * function was fixed for. isSectionValid documents the same trap (a prior
   * fresh-eyes finding); this now matches it.
   *
   * `ignored` fields need no filter -- ignoring quarantines the field out of
   * `schema.fields` entirely (schema-editor/src/utils/ignoreField.ts), so they
   * are already absent here.
   *
   * Both halves matter. `total` used to be `schema.fields.length`, so the 7
   * statically hidden fields on the shipped W-7 could never be filled and
   * progress capped around 87% -- the form never read complete. `filled` was
   * independently wrong: it counted keys of `fieldValues`, so a stale value
   * for a field that has since been hidden (or whose show_if flipped off) kept
   * counting, and could even push progress past 100%. Both now walk the SAME
   * visible-field list, which is what makes the ratio meaningful.
   *
   * `total` is intentionally DYNAMIC: revealing a conditional field grows it,
   * so progress can move backwards when the user's answer opens a new branch.
   * That is honest -- there really is more work to do.
   */
  static getProgressCounts(state: SchemaFormState): { filled: number; total: number } {
    const visibleFields = state.schema.fields.filter((f) =>
      shouldShowField(f, state.fieldValues, state.schema.fields)
    );
    if (visibleFields.length === 0) return { filled: 0, total: 0 };

    // A SKIPPED field counts as done, matching isSectionValid (which accepts a
    // skipped required field) and computeReadyWindows' SETTLED definition
    // (confirmed / skipped / not shown). Without this, a user who legitimately
    // skips a field -- deferring to a translator, or genuinely having no answer
    // -- completes the section while the bar sticks below 100%, which is the
    // same "never reads complete" complaint the hidden-field filter fixed.
    const doneFields = visibleFields.filter((f) => {
      const fieldValue = state.fieldValues[f.id];
      if (fieldValue?.skipped) return true;
      // Shares the blankness definition with isSectionValid, isFormComplete and
      // computeNextField (bd polyglot-pdf-5ovod). It used to hand-write the same
      // check untrimmed, so a whitespace field counted as DONE: the progress bar
      // and the overlay's field counter read 100% while the completion gate --
      // correctly -- said the form was not finished. A progress bar that
      // disagrees with the gate it is reporting on is worse than no bar.
      return !isBlankFieldValue(fieldValue?.value);
    }).length;

    return { filled: doneFields, total: visibleFields.length };
  }

  /**
   * Check if current section is valid (all required fields filled).
   *
   * "Required" is evaluated DYNAMICALLY via isFieldRequired (bd c7st): a field is
   * required if it is statically required OR a satisfied require_if condition makes
   * it required right now. The prior gate read only the static field.validation?.
   * required, so every conditionally-required field (e.g. f1040 designee
   * name/phone/pin when "allow" is yes) was never actually insisted on.
   *
   * A required field is SATISFIED when it has a non-empty value OR the user
   * force-skipped it (FieldValue.skipped, bd 4dxt) -- a required field must stay
   * skippable (defer to a translator, or genuinely no answer) or the user is
   * trapped. A field that is not currently SHOWN (its show_if is unmet) is never
   * required here: it cannot be filled, so require_if on a hidden field must not
   * block the section.
   */
  static isSectionValid(state: SchemaFormState, sectionId: string): boolean {
    const section = state.schema.sections.find((s) => s.id === sectionId);
    if (!section) return false;

    // []-alias-aware, matching getFieldsForSection / findSectionIdForField (bd
    // polyglot-pdf-una9): a section.fields entry and the matching field.id can
    // carry DIFFERENT bracket forms of the same field, so an exact-only match
    // silently DROPS a field from the validity check -- a required, unfilled
    // checkbox group would vanish from sectionFields and the section would
    // report VALID with that answer missing.
    const sectionFields = section.fields
      .map((fieldId) => findFieldWithAlias(state.schema.fields, fieldId))
      .filter((f): f is FormField => f !== undefined);

    for (const field of sectionFields) {
      // A shown, currently-required field must be filled OR force-skipped.
      // "Shown" MUST match FieldRenderer's own visibility test (shouldShowField
      // alone, which already folds in field.hidden for the no-show_if case) --
      // gating on an extra !field.hidden here would diverge from what actually
      // renders: a field with hidden:true AND a satisfied show_if renders and is
      // answerable, so it must still be required (fresh-eyes review).
      const shown = shouldShowField(field, state.fieldValues, state.schema.fields);
      if (shown && isFieldRequired(field, state.fieldValues, state.schema.fields)) {
        const fieldValue = state.fieldValues[field.id];
        if (!fieldValue?.skipped) {
          const actualValue = fieldValue?.value;
          // Whitespace-only is BLANK (bd polyglot-pdf-5ovod): typing spaces into
          // a required field used to satisfy this gate while printing blank on
          // the PDF -- and the backend never even heard about it, since the
          // notify path trims.
          if (isBlankFieldValue(actualValue)) {
            return false;
          }
        }
      }

      // Check if field has validation errors
      if (state.validationErrors[field.id]) {
        return false;
      }
    }

    return true;
  }

  // ============================================================================
  // WebSocket Integration Methods
  // ============================================================================

  /**
   * Get current section number (for WebSocket section_number field)
   * Maps sections[].order to section_number
   */
  static getCurrentSectionNumber(state: SchemaFormState): number {
    const section = state.schema.sections.find(s => s.id === state.currentSectionId);
    return section?.order ?? 1;
  }

  /**
   * Switch to a different section by ID
   * Used for section switching via WebSocket
   *
   * JIT Mode: Clears loadedFieldIds because Gemini context resets on section switch
   *
   * DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
   * continuous-DTI is the live flow. Kept as a fallback, not deleted.
   * Do not extend.
   */
  static switchToSection(state: SchemaFormState, sectionId: string): SchemaFormState {
    // Only mark current section as completed if switching to a different section
    const completedSections = sectionId !== state.currentSectionId
      ? new Set([...state.completedSections, state.currentSectionId])
      : state.completedSections;

    // JIT mode: Clear loaded field IDs when switching sections
    // (Gemini context resets, so we need to send manifests again)
    const loadedFieldIds = state.jitModeEnabled ? new Set<string>() : state.loadedFieldIds;

    const newState = {
      ...state,
      currentSectionId: sectionId,
      completedSections,
      loadedFieldIds,
      // A section switch abandons any field-level navigation pin -- a stale
      // pin from another section must not hijack the new section's next-field
      // order (bd polyglot-pdf-jnjj.36).
      pinnedFieldId: null,
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  /**
   * Complete current section and add to completed set
   */
  static completeSection(state: SchemaFormState, sectionId: string): SchemaFormState {
    const newState = {
      ...state,
      completedSections: new Set([...state.completedSections, sectionId]),
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  /**
   * Extract fields for a specific section (for WebSocket handshake)
   * Returns schema with only fields from the specified section
   */
  /**
   * Extract fields for a specific section (for WebSocket handshake)
   *
   * Returns schema with ALL fields from the section, including locked/hidden fields.
   * Gemini receives the full manifest - dependency logic is handled by:
   * - computeNextField() filters on shouldShowField ALONE (bd polyglot-pdf-ubam);
   *   it does NOT skip read_only/locked fields, so a locked field can still be
   *   offered as next_field_hint
   * - The locked-field refusal is a CLIENT-side gate: webFormConnection's
   *   handleFieldUpdate checks isFieldReadOnly before accepting a write
   *
   * @param schema - Full form schema
   * @param sectionId - Section ID to extract
   * @returns Schema containing all fields for the section
   */
  static extractSectionFields(
    schema: FormSchema,
    sectionId: string
  ): FormSchema {
    const section = schema.sections.find(s => s.id === sectionId);
    if (!section) {
      console.warn(`[SchemaFormStateManager] Section ${sectionId} not found in schema`);
      return {
        ...schema,
        fields: [],
        sections: []
      };
    }

    // Extract ALL fields for this section (no filtering)
    // Dependency checking is handled by computeNextField() and backend validation
    const sectionFields = schema.fields.filter(f => section.fields.includes(f.id));

    return {
      ...schema,
      fields: sectionFields,
      sections: [section]
    };
  }

  /**
   * Get spoken names from completed sections (for WebSocket previous_spoken_names)
   * Returns array of spoken names from all completed sections
   */
  static getPreviousSpokenNames(state: SchemaFormState): string[] {
    const spokenNames: string[] = [];

    for (const sectionId of state.completedSections) {
      const section = state.schema.sections.find(s => s.id === sectionId);
      if (!section) continue;

      // Collect spoken names from all fields in this section
      // []-alias-aware for the same reason as isSectionValid above (bd
      // polyglot-pdf-una9): an exact-only miss drops a field's spoken name (and
      // its aliases) from the already-answered list handed to the model.
      section.fields.forEach(fieldId => {
        const field = findFieldWithAlias(state.schema.fields, fieldId);
        if (field?.spoken_name) {
          spokenNames.push(field.spoken_name);
          // Also include spoken aliases
          if (field.spoken_aliases) {
            spokenNames.push(...field.spoken_aliases);
          }
        }
      });
    }

    return spokenNames;
  }

  /**
   * Generate WebSocket handshake payload
   * Used when connecting to backend or switching sections
   * Automatically uses JIT mode if enabled in state
   */
  static getHandshakePayload(state: SchemaFormState, fillLanguage: string = 'English', resume: boolean = false) {
    // Check if JIT mode is enabled
    if (state.jitModeEnabled) {
      return this.getJITHandshakePayload(state, fillLanguage, resume);
    }

    // Legacy mode: send full schema for current section
    const currentSection = state.schema.sections.find(s => s.id === state.currentSectionId);

    // Extract schema for current section only
    const sectionSchema = this.extractSectionFields(state.schema, state.currentSectionId);

    // Get previous spoken names from completed sections
    const previousSpokenNames = this.getPreviousSpokenNames(state);

    return {
      type: 'handshake',
      form_session_id: state.formSessionId, // Persistent ID for logging/metrics
      schema: sectionSchema,
      // FULL form schema (all parts/sections/fields) for the secretary catalog
      // (bd polyglot-pdf-p68s / jnjj.45d). The per-section `schema` above drives
      // the live-model SI; the secretary needs the whole form. Schema only, no
      // PII -- the backend caches it in-session and rebuilds it from this on every
      // (re)connect, so the stateless invariant holds.
      full_schema: state.schema,
      current_values: state.fieldValues, // Already in FieldValue format
      section_number: currentSection?.order ?? 1, // Use order as section_number
      section_label: currentSection?.label ?? '',
      total_sections: state.schema.sections.length,
      previous_spoken_names: previousSpokenNames,
      fill_language: fillLanguage,
      // The user's app-start language choice (bd polyglot-pdf-y25o): the Live
      // session's transcription language bias is per-connect config, so the
      // backend needs the language BEFORE Gemini connects -- the later
      // change_spoken_language message arrives too late for that.
      spoken_language: state.selectedLanguage ?? null,
      // kit_id rides the LEGACY payload too (bd polyglot-pdf-s1iex.6). It is the
      // UNIQUE kit key -- two kits can share a form_number, and only kit_id
      // tells them apart in the confirmation audit trail -- and it is
      // deliberately NOT a form_metadata key, so the backend has no fallback:
      // whatever the handshake omits is simply absent from every record.
      //
      // This branch runs whenever jitModeEnabled is still false -- which is the
      // case for a FRESH tab's first handshake, since the flag is only set from
      // the backend's session_ready. (A soft reload within the state's 1h reuse
      // window restores a persisted jitModeEnabled=true and takes the JIT
      // branch instead; setting kit_id at the SOURCE covers both, which is why
      // the fix lives here rather than on the intro path.) The omission used to
      // be harmless because a second, JIT handshake always followed; with the
      // intro path's single connect it is the only one, so it silently dropped
      // kit_id from the audit trail (Opus cross-surface review).
      kit_id: loadOnboardingState().formId ?? null,
      resume,
    };
  }

  /**
   * Generate JIT mode handshake payload with manifest
   * Only sends field_id|spoken_name pairs, not full schemas
   */
  static getJITHandshakePayload(state: SchemaFormState, fillLanguage: string = 'English', resume: boolean = false) {
    const currentSection = state.schema.sections?.find(s => s.id === state.currentSectionId);

    // Continuous-session mode (bd polyglot-pdf-x8rt): one synthetic whole-form
    // section carrying every field, so the backend runs ONE compression-bounded
    // session instead of chopping by section. computeNextField (below) also spans
    // the whole form in this mode, so first_field_schema/next-hint stay correct.
    const continuous = state.continuousSessionEnabled;

    // Build manifest: whole-form (continuous) or current + previous sections.
    const manifest = continuous
      ? buildContinuousManifest(state.schema)
      : buildHandshakeManifest(state.currentSectionId, state.schema, state);

    // Send the FIRST UNFILLED field's schema, not the section's positional first
    // field -- on a reconnect/revisit, fields[0] may already be confirmed, and the
    // backend renders whatever single schema we send as {next_field_schema}
    // (bd polyglot-pdf-jnjj.9, gap D). computeNextField(skipConfirmed) is the same
    // selection the runtime next-field hint uses, so schema and hint agree.
    const nextField = computeNextField(state, { skipConfirmed: true });
    let firstFieldSchema = null;
    if (nextField) {
      firstFieldSchema = getFieldSchema(nextField.id, state.schema);
    } else if (continuous) {
      // Whole form already complete / reconnect at the very end: fall back to the
      // form's first field so the SI still has a schema (mirrors the section case).
      if (state.schema.fields.length > 0) {
        firstFieldSchema = getFieldSchema(state.schema.fields[0].id, state.schema);
      }
    } else {
      // No unfilled field (section already complete / reconnect at the boundary):
      // fall back to the section's first field so the SI still has a schema.
      const sectionSchema = this.extractSectionFields(state.schema, state.currentSectionId);
      if (sectionSchema.fields.length > 0) {
        firstFieldSchema = getFieldSchema(sectionSchema.fields[0].id, state.schema);
      }
    }

    // Compute the next-field hint string the same way the runtime path does, so
    // {next_field_hint} is the real next field on first connect, not the generic
    // "the first unfilled field" fallback (gap D, hint half).
    const initialFieldHint = nextField
      ? formatNextFieldHint(nextField, getFieldOrder(state, nextField.id) || undefined,
          state.selectedLanguage)
      : null;

    return {
      type: 'handshake_jit',
      form_session_id: state.formSessionId, // Persistent ID for logging/metrics
      manifest: manifest,
      first_field_schema: firstFieldSchema,
      // FULL form schema for the secretary catalog (bd polyglot-pdf-p68s /
      // jnjj.45d). JIT/DTI sends only the manifest + first field's schema for the
      // live model; the secretary needs the whole form. Schema only, no PII; cached
      // in-session and rebuilt from this on every (re)connect (stateless invariant).
      full_schema: state.schema,
      loaded_field_ids: Array.from(state.loadedFieldIds),
      current_values: state.fieldValues,
      resume,
      // Continuous mode presents as ONE section spanning the whole form.
      section_number: continuous ? 1 : (currentSection?.order ?? 1),
      section_label: continuous
        ? (state.schema.form_metadata?.title || 'Full Form')
        : (currentSection?.label ?? ''),
      total_sections: continuous ? 1 : (state.schema.sections?.length ?? 1),
      fill_language: fillLanguage,
      // The JIT handshake previously UNDER-SENT these three, leaving the JIT SI's
      // {form_title}, {previous_spoken_names}, and {next_field_hint} wrong
      // (bd polyglot-pdf-jnjj.9, gaps O / M / D-hint):
      form_title: state.schema.form_metadata?.title ?? 'Form',
      // The form NUMBER (e.g. "W-7") rides the manifest-first handshake too
      // (bd polyglot-pdf-n0em): the backend's confirmation audit trail derives
      // form_id from schema.form_metadata.form_number, which the JIT transport
      // does not carry -- so every confirmation event logged form_id="unknown"
      // and the liability record could not name the form. Distinct from
      // form_title (a human label); this is the identifier the audit uses.
      form_number: state.schema.form_metadata?.form_number ?? null,
      // Kit identity + government EDITION for the audit trail (bd
      // polyglot-pdf-47r3). form_number alone identifies neither:
      //  - kit_id is the UNIQUE kit key -- two kits can share a form_number
      //    (a standard W-7 and a firm-specific variant, which the firm-tier
      //    epic anticipates), and only kit_id tells them apart;
      //  - edition_date is the government's own edition marker (USCIS/IRS
      //    revise forms and enforce edition dates), so a disputed filing can
      //    answer "which edition did the client confirm against?".
      // NOT form_metadata.version: that is a schema-AUTHORING field whose
      // values are inconsistent across kits ("v9_conformant", "draft"), so it
      // would put a version-shaped field with per-kit meaning into a legal
      // record.
      kit_id: loadOnboardingState().formId ?? null,
      edition_date: state.schema.form_metadata?.edition_date ?? null,
      previous_spoken_names: this.getPreviousSpokenNames(state),
      initial_field_hint: initialFieldHint,
      // The user's app-start language choice (bd polyglot-pdf-y25o): needed
      // BEFORE the Gemini connect for the per-connect transcription language
      // bias (change_spoken_language arrives after session_ready -- too late).
      spoken_language: state.selectedLanguage ?? null,
    };
  }

  /**
   * Set session ID from backend
   */
  static setSessionId(state: SchemaFormState, sessionId: string): SchemaFormState {
    const newState = {
      ...state,
      sessionId,
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  /**
   * Whether the persisted state represents an already-in-progress form session
   * -- the user has accepted the disclaimer and filled at least one field.
   *
   * Used to decide resume:true on the FIRST handshake after a soft page refresh
   * (bd polyglot-pdf-hc4b). The instance-scoped hasConnectedOnce flag is false on
   * a brand-new post-reload WebFormConnection, so without this a genuine
   * mid-form refresh would send resume:false and the backend would re-greet /
   * re-introduce the section. Derived purely from persisted state, so it
   * survives the reload that resets hasConnectedOnce.
   */
  static hasInProgressSession(state: SchemaFormState): boolean {
    return state.disclaimerAccepted && Object.keys(state.fieldValues).length > 0;
  }

  /**
   * Get section label by order number
   */
  static getSectionLabel(state: SchemaFormState, orderNumber: number): string {
    const section = state.schema.sections.find(s => s.order === orderNumber);
    return section?.label || '';
  }

  /**
   * Find section ID by label (case-insensitive)
   */
  static findSectionByLabel(state: SchemaFormState, label: string): string | null {
    const lowerLabel = label.toLowerCase();
    const section = state.schema.sections.find(s =>
      s.label.toLowerCase() === lowerLabel
    );
    return section?.id || null;
  }

  /**
   * Phase 3: JIT Schema Loading - Mark field schema as loaded
   *
   * Called when Gemini receives a field's complete schema:
   * - Initial handshake (first field)
   * - After update_form_fields (next field schema)
   * - From switch_to_field (if schema not already sent)
   */
  static markFieldSchemaLoaded(state: SchemaFormState, fieldId: string): SchemaFormState {
    if (state.loadedFieldIds.has(fieldId)) {
      // Already loaded, no state change needed
      return state;
    }

    const newState = {
      ...state,
      loadedFieldIds: new Set([...state.loadedFieldIds, fieldId]),
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  /**
   * Phase 3: JIT Schema Loading - Check if field schema has been sent to Gemini
   */
  static isFieldSchemaLoaded(state: SchemaFormState, fieldId: string): boolean {
    return state.loadedFieldIds.has(fieldId);
  }

  /**
   * Enable/disable the manifest-first handshake TRANSPORT (the `jitMode` name is
   * historical -- it is the carrier DTI rides on, not the removed JIT SI mode; bd
   * polyglot-pdf-en2j). Set during handshake from the backend's
   * session_ready.jit_mode_enabled signal, which is now `= settings.USE_DTI`.
   */
  static setJitMode(state: SchemaFormState, enabled: boolean): SchemaFormState {
    if (state.jitModeEnabled === enabled) {
      return state;
    }

    const newState = {
      ...state,
      jitModeEnabled: enabled,
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  /**
   * Continuous-session mode (bd polyglot-pdf-x8rt) - enable/disable.
   * Called during handshake from the backend CONTINUOUS_SESSION flag. When on,
   * the handshake spans the whole form as one synthetic section and section
   * advancement is suppressed.
   */
  static setContinuousSession(state: SchemaFormState, enabled: boolean): SchemaFormState {
    if (state.continuousSessionEnabled === enabled) {
      return state;
    }

    const newState = {
      ...state,
      continuousSessionEnabled: enabled,
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  /**
   * Phase 3: JIT Schema Loading - Clear loaded field IDs
   *
   * Called when switching parts/sections to reset tracking
   */
  static clearLoadedFieldIds(state: SchemaFormState): SchemaFormState {
    const newState: SchemaFormState = {
      ...state,
      loadedFieldIds: new Set<string>(),
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  // ============================================================================
  // Confirmation Status Management
  // ============================================================================

  /**
   * Confirm a field with timestamp and method
   */
  static confirmField(
    state: SchemaFormState,
    fieldId: string,
    method: 'ai_voice' | 'manual_edit'
  ): SchemaFormState {
    // Resolve the `[]`-alias like updateField and markFieldSkipped do. Without
    // it a confirm for `race` no-ops when the value lives under `race[]` -- and
    // reconcileFieldValues now actively consolidates a pair onto the schema's
    // variant, so the model dropping the bracket (bd polyglot-pdf-5k52) reaches
    // exactly that state. The gate in handleConfirmFieldRequest reads through the
    // alias too, so without this the gate would pass and the write silently do
    // nothing -- confirming neither variant.
    const aliasKey = fieldId.endsWith('[]') ? fieldId.slice(0, -2) : fieldId + '[]';
    const targetKey = state.fieldValues[fieldId] !== undefined ? fieldId
      : (state.fieldValues[aliasKey] !== undefined ? aliasKey : fieldId);
    const fieldValue = state.fieldValues[targetKey];
    if (!fieldValue) {
      // bd polyglot-pdf-0y7: a confirm for a field with no entry in fieldValues is
      // a no-op (nothing to confirm until a value lands). This was previously
      // SILENT, which made the confirm/next-field spin invisible -- log it so the
      // failure is diagnosable. NOTE this guard only catches a MISSING entry (it does
      // NOT catch an entry that exists with value null/empty -- such an object is
      // truthy and would be confirmed here). The real no-value protection lives in
      // handleConfirmFieldRequest, whose loop-breaker gates on the field VALUE before
      // calling confirmField at all; this branch only backstops the missing-entry case
      // for that path (a direct caller passing a null/empty-valued entry would bypass
      // both this guard and the upstream gate).
      console.warn(`[SchemaFormState] confirmField('${fieldId}') no-op: field has no entry to confirm`);
      return state; // Field doesn't exist / has no value
    }

    const newState = {
      ...state,
      fieldValues: {
        ...state.fieldValues,
        // Write back to the RESOLVED key, not the requested one -- writing to
        // `fieldId` when the entry was found under the alias would create a
        // SECOND entry and break the got6 one-entry invariant.
        [targetKey]: {
          ...fieldValue,
          confirmed: true,
          confirmedAt: new Date().toISOString(),
          confirmationMethod: method
        }
      },
      // A confirmed pinned field releases the pin -- the form resumes its
      // normal fill order (bd polyglot-pdf-jnjj.36).
      pinnedFieldId: state.pinnedFieldId === fieldId ? null : state.pinnedFieldId,
      // ...and the search resumes from the field just answered, not from
      // wherever the origin last pointed (bd polyglot-pdf-a08po, fresh-eyes).
      // Without this, a voice jump-and-answer released the pin back onto a
      // STALE origin -- the same "focus snaps backward" failure this bead
      // exists to fix, arriving via the verbal path instead of the manual one.
      // includesSelf=false: this field was just answered, so resume AFTER it.
      searchOriginFieldId: fieldId,
      searchOriginIncludesSelf: false,
      lastUpdated: Date.now()
    };

    this.save(newState);
    return newState;
  }

  /**
   * 4dxt: force-skip a required-but-unanswered field. The user was asked a
   * required field but has no answer right now (defer to a translator, or it
   * genuinely does not apply). Sets FieldValue.skipped=true and clears the value
   * to empty so the field:
   *   - SATISFIES the section-validity gate (isSectionValid honors `skipped`),
   *   - renders visibly distinct as "skipped -- needs follow-up" (the `skipped`
   *     flag with an empty value, NOT a silent blank),
   *   - fills BLANK on the PDF (unwrapFieldValue returns the empty value).
   * It counts as confirmed via the given method so it does not re-prompt. Setting
   * a real value later (updateField) drops `skipped` (a fresh FieldValue), which
   * is the intended "answered after all" transition. A field with no prior entry
   * gets a fresh skipped entry (skipping an untouched required field is valid).
   */
  static markFieldSkipped(
    state: SchemaFormState,
    fieldId: string,
    method: 'ai_voice' | 'manual_edit' = 'manual_edit'
  ): SchemaFormState {
    // Resolve the `[]`-alias like updateField does, and drop the stale variant.
    // Without this, a skip whose id drops (or adds) the bracket writes a SECOND
    // key beside the existing one -- breaking the got6 one-entry invariant and
    // making this the only remaining producer of the both-variants state that
    // reconcileFieldValues then has to arbitrate (bd polyglot-pdf-8c97).
    const aliasKey = fieldId.endsWith('[]') ? fieldId.slice(0, -2) : fieldId + '[]';
    const priorKey = state.fieldValues[fieldId] !== undefined
      ? fieldId
      : (state.fieldValues[aliasKey] !== undefined ? aliasKey : fieldId);
    const prior = state.fieldValues[priorKey];

    // NOTE the asymmetry with confirmField, which writes to the RESOLVED key:
    // this writes to the REQUESTED one. Safe because both callers only ever pass
    // a SCHEMA id -- handleSkipFieldRequest rejects anything else as
    // `unknown_field` (exact `f.id === field_id`), and the UI passes `field.id`
    // -- so the requested key IS the schema key. If a caller is ever added that
    // can pass a non-schema variant, write to priorKey instead.
    const nextFieldValues = {
      ...state.fieldValues,
      [fieldId]: {
        ...prior,
        value: null,
        skipped: true,
        confirmed: true,
        confirmedAt: new Date().toISOString(),
        confirmationMethod: method,
        lastModified: Date.now(),
      },
    };
    if (priorKey !== fieldId) {
      delete nextFieldValues[priorKey];
    }

    const newState = {
      ...state,
      fieldValues: nextFieldValues,
      lastUpdated: Date.now(),
    };

    // A skipped field is intentionally empty -- clear any stale validation error.
    // Clear it under the PRIOR key too: now that the alias is resolved above, an
    // error recorded against the variant we just deleted would otherwise outlive
    // the entry it describes.
    if (newState.validationErrors[fieldId] || newState.validationErrors[priorKey]) {
      const rest = { ...newState.validationErrors };
      delete rest[fieldId];
      delete rest[priorKey];
      newState.validationErrors = rest;
    }

    // A skipped pinned field releases the pin, same as a confirm
    // (bd polyglot-pdf-jnjj.36).
    if (newState.pinnedFieldId === fieldId) {
      newState.pinnedFieldId = null;
    }
    // A skip is "done with this field" just as a confirm is, so it advances the
    // search origin the same way (bd polyglot-pdf-a08po). Keeping these two in
    // step matters: they are the pair that releases a pin, and an origin left
    // stale by only ONE of them would strand the scan exactly where the other
    // path fixed it.
    newState.searchOriginFieldId = fieldId;
    newState.searchOriginIncludesSelf = false;

    this.save(newState);
    return newState;
  }

  // ============================================================================
  // Field-level navigation (bd polyglot-pdf-jnjj.36)
  // ============================================================================

  /**
   * Resolve a field identifier the AI passed to switch_to_field: an exact
   * field_id first (verbatim from guidance -- the preferred form), then a
   * case-insensitive match on spoken_name, display name, or spoken_aliases.
   *
   * Searches the WHOLE schema deliberately -- a section-scoped search would go
   * blind past section 1 in continuous mode (bd polyglot-pdf-lt9z). A navigation
   * target may live anywhere in the form; the caller decides whether an
   * out-of-section target is reachable in the current mode.
   */
  static resolveFieldForNavigation(
    state: SchemaFormState,
    identifier: string
  ): string | null {
    if (!identifier) return null;
    const exact = state.schema.fields.find(f => f.id === identifier);
    if (exact) return exact.id;
    const needle = identifier.trim().toLowerCase();
    if (!needle) return null;
    for (const field of state.schema.fields) {
      if (field.spoken_name?.toLowerCase() === needle) return field.id;
      if (field.name?.toLowerCase() === needle) return field.id;
      if (field.spoken_aliases?.some(a => a.toLowerCase() === needle)) {
        return field.id;
      }
    }
    return null;
  }

  /**
   * Nearest navigable-field candidates for an identifier that did NOT resolve
   * exactly (bd polyglot-pdf-3vby). Returns up to `limit` currently-visible
   * fields, ranked by whole-WORD overlap between the identifier and each field's
   * spoken name/aliases, then document order. This is a SUGGESTION aid only --
   * the model picks one and switch_to_field re-resolves it EXACTLY, so no fuzzy
   * match ever auto-fills a field (the lt9z mis-fill trap is avoided). Hidden and
   * conditionally-inactive fields are excluded because they are not navigable.
   */
  static suggestNavigationCandidates(
    state: SchemaFormState,
    identifier: string,
    limit = 6
  ): Array<{ field_id: string; spoken_name: string }> {
    const words = (identifier || "")
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter(w => w.length > 2);
    // shouldShowField ALONE (bd polyglot-pdf-ubam): an extra `!f.hidden &&`
    // dropped a `hidden: true` field whose show_if is SATISFIED out of the
    // navigable set, so a field the form actually shows could not even be
    // SUGGESTED as a navigation target.
    const navigable = state.schema.fields.filter(f =>
      shouldShowField(f, state.fieldValues, state.schema.fields)
    );
    const scored = navigable.map((f, idx) => {
      const hay = [f.spoken_name, f.name, ...(f.spoken_aliases || [])]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      const hayWords = new Set(hay.split(/[^a-z0-9]+/).filter(Boolean));
      const overlap = words.reduce((n, w) => n + (hayWords.has(w) ? 1 : 0), 0);
      return { f, idx, overlap };
    });
    scored.sort((a, b) => b.overlap - a.overlap || a.idx - b.idx);
    // When nothing overlaps at all, fall back to the first navigable fields in
    // document order so the model still gets a concrete pick-list to choose from.
    return scored
      .slice(0, limit)
      .map(s => ({
        field_id: s.f.id,
        spoken_name: s.f.spoken_name || s.f.name || s.f.id,
      }));
  }

  /**
   * Pin a field as the navigation target (see pinnedFieldId on the state
   * interface). computeNextField returns the pinned field first while it is
   * visible + unconfirmed; confirm/skip release the pin.
   */
  static pinField(state: SchemaFormState, fieldId: string): SchemaFormState {
    const newState = { ...state, pinnedFieldId: fieldId, lastUpdated: Date.now() };
    this.save(newState);
    return newState;
  }

  /**
   * Move the next-field search origin to `fieldId` (see searchOriginFieldId on
   * the state interface, bd polyglot-pdf-a08po). Called when the user acts on a
   * field directly -- a manual edit, or a click/focus while no audio is playing
   * -- so the search resumes from where they ARE instead of the top of the form.
   *
   * Deliberately NOT a pin: this only moves where the scan starts. The field
   * itself is returned only if the normal priority rules pick it.
   */
  static setSearchOrigin(
    state: SchemaFormState,
    fieldId: string,
    // Does the search START at this field, or just after it? A CLICK points at
    // the field (true); a manual EDIT answers it and moves on (false). See
    // searchOriginIncludesSelf on the state interface.
    options?: { includesSelf?: boolean },
  ): SchemaFormState {
    const includesSelf = options?.includesSelf === true;
    // Compare BOTH halves: the same field can be re-set with the other
    // intent (click a field, then type in it), and that must still persist.
    if (
      state.searchOriginFieldId === fieldId &&
      state.searchOriginIncludesSelf === includesSelf
    ) {
      return state;
    }
    const newState = {
      ...state,
      searchOriginFieldId: fieldId,
      searchOriginIncludesSelf: includesSelf,
      lastUpdated: Date.now(),
    };
    this.save(newState);
    return newState;
  }

  /**
   * Clear the navigation pin without confirming/skipping the field.
   */
  static clearPinnedField(state: SchemaFormState): SchemaFormState {
    if (!state.pinnedFieldId) return state;
    const newState = { ...state, pinnedFieldId: null, lastUpdated: Date.now() };
    this.save(newState);
    return newState;
  }

  /**
   * B5 (bd polyglot-pdf-jnjj.17): mark fields as already-steered by the cheap-model
   * validator. Sets `steered: true` on each field's FieldValue and persists to
   * sessionStorage so the marker survives the section switch / reconnect and rides
   * the NEXT contract-2 payload -- the client-owned half of the max-resteer bound
   * (the stateless backend cannot remember it; validation-delegation.md contracts
   * 2 + 3). A field with no FieldValue entry is skipped (nothing to mark).
   */
  static markFieldsSteered(
    state: SchemaFormState,
    fieldIds: string[]
  ): SchemaFormState {
    if (!fieldIds || fieldIds.length === 0) return state;
    const fieldValues = { ...state.fieldValues };
    let changed = false;
    for (const fieldId of fieldIds) {
      // The verdict echoes the schema field.id, but the value may be stored under the
      // `[]` alias (Gemini drops/adds the bracket) -- mirror the same fallback
      // buildValidatorFields uses for reads, or the marker lands on a non-existent
      // key and the next payload still sends steered:false -> infinite re-steer
      // (Codex PR #275).
      let key = fieldId;
      if (!fieldValues[key] && !key.endsWith('[]') && fieldValues[key + '[]']) key = key + '[]';
      if (!fieldValues[key] && key.endsWith('[]') && fieldValues[key.slice(0, -2)]) key = key.slice(0, -2);
      const fv = fieldValues[key];
      if (!fv) continue; // no entry to mark under either variant
      if (fv.steered === true) continue; // already marked
      // Stamp lastModified like every other fieldValues writer. This is a real
      // write to the entry, and reconcileFieldValues resolves the two-writer
      // divergence on that stamp -- an unstamped write loses to any stamped one
      // ("dated beats undated"), which would silently discard the steer marker
      // and defeat W4's re-arm bound.
      fieldValues[key] = { ...fv, steered: true, lastModified: Date.now() };
      changed = true;
    }
    if (!changed) return state;
    const newState = { ...state, fieldValues, lastUpdated: Date.now() };
    this.save(newState);
    return newState;
  }

  /**
   * W3 (bd polyglot-pdf-pr3i): a stable key for a finding = its SET of field_ids
   * (order-insensitive), mirroring the backend's frozenset dedupe. Two findings that
   * name the same fields are "the same conflict" for queue-dedup + consume-match.
   */
  private static findingKey(finding: { field_ids?: string[] }): string {
    const ids = Array.isArray(finding.field_ids) ? finding.field_ids : [];
    return JSON.stringify([...ids].map(String).sort());
  }

  /**
   * W3 (bd polyglot-pdf-pr3i): ENQUEUE validator findings from a report-only
   * `validation_result`. Appends only findings whose field-id SET is not already in
   * the queue (dedupe -- overlapping windows + repeated results can re-report the
   * same conflict). Malformed findings (no field_ids) are dropped. Returns the state
   * unchanged (same reference) when nothing new is added, so the caller can skip the
   * drain. Persisted (survives reconnect).
   */
  static enqueueValidatorFindings(
    state: SchemaFormState,
    findings: ValidatorFinding[]
  ): SchemaFormState {
    if (!Array.isArray(findings) || findings.length === 0) return state;
    const existing = new Set(state.validatorFindingsQueue.map(f => this.findingKey(f)));
    const toAdd: ValidatorFinding[] = [];
    for (const f of findings) {
      const ids = Array.isArray(f?.field_ids) ? f.field_ids.filter(i => typeof i === 'string') : [];
      if (ids.length === 0) continue; // malformed -> drop (cannot steer/consume it)
      const key = this.findingKey({ field_ids: ids });
      if (existing.has(key)) continue; // already queued
      existing.add(key);
      toAdd.push({
        field_ids: ids,
        reason: typeof f.reason === 'string' ? f.reason : '',
        field_names: (f.field_names && typeof f.field_names === 'object') ? f.field_names : {},
      });
    }
    if (toAdd.length === 0) return state;
    const newState = {
      ...state,
      validatorFindingsQueue: [...state.validatorFindingsQueue, ...toAdd],
      lastUpdated: Date.now(),
    };
    this.save(newState);
    return newState;
  }

  /**
   * W3 (bd polyglot-pdf-pr3i): CONSUME (remove) the findings whose field-id sets
   * match the DELIVERED conflicts from a `drain_findings_result`. An un-delivered
   * finding (dead session -> not in `delivered`) STAYS queued to retry on the next
   * drain. Returns the state unchanged when nothing matched. Persisted.
   */
  static consumeValidatorFindings(
    state: SchemaFormState,
    delivered: Array<{ field_ids?: string[] }>
  ): SchemaFormState {
    if (!Array.isArray(delivered) || delivered.length === 0) return state;
    const drainedKeys = new Set(delivered.map(d => this.findingKey(d)));
    const remaining = state.validatorFindingsQueue.filter(
      f => !drainedKeys.has(this.findingKey(f))
    );
    if (remaining.length === state.validatorFindingsQueue.length) return state; // nothing matched
    const newState = { ...state, validatorFindingsQueue: remaining, lastUpdated: Date.now() };
    this.save(newState);
    return newState;
  }

  /**
   * Get list of field IDs that are filled but not confirmed
   * These are the priority for next field hint
   */
  static getUnconfirmedFields(state: SchemaFormState): string[] {
    const unconfirmed: string[] = [];

    for (const [fieldId, fieldValue] of Object.entries(state.fieldValues)) {
      if (fieldValue.value != null && fieldValue.value !== '' && !fieldValue.confirmed) {
        unconfirmed.push(fieldId);
      }
    }

    return unconfirmed;
  }

  /**
   * Get count of confirmed fields (for progress tracking)
   */
  static getConfirmedFieldCount(state: SchemaFormState): number {
    return Object.values(state.fieldValues).filter(fv => fv.confirmed === true).length;
  }

  /**
   * W2 (bd polyglot-pdf-kxkw): compute the async-validator STRIDE windows that are
   * ELIGIBLE to send and NOT already sent. PURE (no side effects) so it is unit-
   * testable in isolation. Page-agnostic -- keys ONLY on schema field ORDER and the
   * per-field SETTLED state (confirmed / skipped / not-applicable), never
   * pdf_position.page, so a source:"web" / pageless schema behaves identically to a
   * paginated one (report-cadence revision 2026-07-13).
   *
   * Windows tile the schema field array: window k covers indices
   * [k*stride, k*stride + size). A window is ELIGIBLE once EVERY field it covers is
   * SETTLED -- confirmed, skipped, or hidden by conditional logic (shouldShowField
   * false = not part of the active form). This is stricter than a high-water "fill
   * has passed this window" mark: an out-of-order voice fill or a trailing OPTIONAL
   * field left unanswered inside a window's range keeps that window PENDING, so a
   * field is never permanently starved of validation (a fresh-eyes finding on the
   * earlier high-water design -- confirming f0..f19 while f5 is still open would
   * otherwise fire + retire window 0 and never re-check f5). The window fires the
   * moment its region is genuinely done, which for the tail window is naturally at
   * form end -- no separate isFormComplete release is needed.
   *
   * Already-sent windows (state.validatedWindowIndices) are excluded, so each fires
   * exactly once across reloads. A field's later value EDIT does not re-open a sent
   * window here (re-validation on edit is W4's re-arm concern, not W2's).
   *
   * Returns the eligible-and-unsent windows as {index, start, end} (end exclusive,
   * clamped to the field count), ascending by index. Empty when nothing new is
   * ready. The caller renders each range through buildValidatorFields and persists
   * the sent indices.
   */
  static computeReadyWindows(
    state: SchemaFormState,
    size: number,
    stride: number
  ): Array<{ index: number; start: number; end: number }> {
    const fields = state.schema?.fields ?? [];
    const total = fields.length;
    if (total === 0 || size <= 0 || stride <= 0) return [];

    // A field is SETTLED (no longer awaiting an answer) when it is confirmed,
    // explicitly skipped, or not shown by conditional logic (not part of the active
    // form). An unsettled field inside a window holds that window pending.
    const isSettled = (index: number): boolean => {
      const field = fields[index];
      if (!shouldShowField(field, state.fieldValues, fields)) return true; // N/A
      const fv = readFieldEntryWithAlias(state.fieldValues, field.id);
      if (fv?.skipped === true) return true;
      // A confirmation of BLANKNESS does not settle a field (bd
      // polyglot-pdf-5ovod), and the cost here is higher than at the other
      // gates: a window marked ready is added to validatedWindowIndices, which
      // PERSISTS to sessionStorage -- so retiring it on a whitespace field means
      // that field is never validated again, even after a real answer arrives.
      // That is a silent, permanent loss rather than a cosmetic disagreement,
      // and it defeats this function's own "no field is ever permanently
      // starved of validation" promise.
      //
      // A skipped field (handled above, value:null) and an optional field's
      // confirmed '' (the deliberate "does not apply" answer, bd
      // polyglot-pdf-6oe6) both remain settled.
      return fv?.confirmed === true && !isConfirmedButBlank(fv?.value);
    };

    const sent = state.validatedWindowIndices;
    const ready: Array<{ index: number; start: number; end: number }> = [];

    // Enumerate window start positions across the field array. Guard: stride > size
    // would leave gaps (fields no window covers); clamp the enumeration stride to
    // `size` so coverage is always contiguous regardless of the configured stride
    // (production is 10/20, stride < size, so this is a latent-config backstop).
    const step = Math.min(stride, size);
    for (let index = 0, start = 0; start < total; index++, start = index * step) {
      if (sent.has(index)) continue;
      const end = Math.min(start + size, total);
      // Eligible only when EVERY field in [start, end) is settled.
      let allSettled = true;
      for (let i = start; i < end; i++) {
        if (!isSettled(i)) { allSettled = false; break; }
      }
      if (allSettled) ready.push({ index, start, end });
    }
    return ready;
  }

  /**
   * Get count of filled but unconfirmed fields (needs attention)
   */
  static getUnconfirmedFieldCount(state: SchemaFormState): number {
    return Object.values(state.fieldValues).filter(
      fv => fv.value != null && fv.value !== '' && !fv.confirmed
    ).length;
  }

  /**
   * Accept disclaimer and set selected language
   */
  static acceptDisclaimer(
    state: SchemaFormState,
    language: string
  ): SchemaFormState {
    const newState = {
      ...state,
      disclaimerAccepted: true,
      disclaimerAcceptedAt: Date.now(),
      selectedLanguage: language,
      lastUpdated: Date.now()
    };

    this.save(newState);
    return newState;
  }

  /**
   * Pin the session's selected language.
   *
   * NOT a mid-session switch: the spoken language is pinned for the whole form
   * (bd polyglot-pdf-87a9, docs/standards/voice-and-vad.md). This mutator's one
   * production caller is `readDisclaimer` in shared/connection.ts; the overlays'
   * disclaimer-accept path writes `state.selectedLanguage` DIRECTLY instead, so
   * the pin has several entry-flow writers, not one. All of them run before the
   * form starts -- none is reachable mid-form, which is what makes the language
   * pinned. `pinned-language-policy.test.ts` asserts the complete list, so a new
   * writer anywhere fails a test.
   */
  static setSelectedLanguage(
    state: SchemaFormState,
    language: string
  ): SchemaFormState {
    const newState = {
      ...state,
      selectedLanguage: language,
      lastUpdated: Date.now()
    };

    this.save(newState);
    return newState;
  }
}
