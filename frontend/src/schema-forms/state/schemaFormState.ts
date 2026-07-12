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

import type { FormSchema, FormSection, FormField, FormPart, FieldValue } from "../types/schema";
import { buildHandshakeManifest, buildContinuousManifest, getFieldSchema } from "../utils/manifestUtils";
import { normalizeFieldValue, isFieldRequired, shouldShowField } from "../utils/validation";
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
      continuousSessionEnabled: false, // Set during handshake from the backend CONTINUOUS_SESSION flag
      // Disclaimer acceptance
      disclaimerAccepted: false,
      disclaimerAcceptedAt: undefined,
      selectedLanguage: undefined,
      pinnedFieldId: null, // Field-level navigation pin (bd jnjj.36)
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
  static updateField(
    state: SchemaFormState,
    fieldId: string,
    value: any | FieldValue,
    options?: {
      confirmed?: boolean;
      confirmationMethod?: 'ai_voice' | 'manual_edit';
    }
  ): SchemaFormState {
    console.log(`[SchemaFormStateManager] updateField: ${fieldId} = ${JSON.stringify(value)}`);
    console.log(`[SchemaFormStateManager] Current state.fieldValues:`, state.fieldValues);

    // Normalize the raw value to its canonical stored form (e.g. strip an
    // A-Number's "A" prefix/separators) so manual edits store the same canonical
    // value the backend stores for AI fills (bd polyglot-pdf-0zr). Idempotent for
    // already-canonical values (e.g. AI fills, which the backend pre-normalizes).
    const field = state.schema.fields.find((f) => f.id === fieldId);

    // Carry forward the B5 `steered` marker (bd polyglot-pdf-jnjj.17, Codex PR #275):
    // the normal edit/fill path REPLACES the FieldValue object, which would silently
    // drop `steered` -- so a user editing (or the model rewriting) an
    // already-adjudicated field would emit steered:false on the next validator
    // payload and the backend could re-steer it, breaking the max-resteer invariant.
    // Preserve it unless the incoming FieldValue explicitly sets its own.
    // Read via the same `[]`-alias fallback as markFieldsSteered: the marker may
    // sit under the bracketed/unbracketed variant of this id (Gemini drops/adds
    // the bracket), and an exact-key read would drop it when the value migrates
    // between variants (bd polyglot-pdf-5k52).
    const priorSteered = (
      state.fieldValues[fieldId] ??
      state.fieldValues[
        fieldId.endsWith('[]') ? fieldId.slice(0, -2) : fieldId + '[]'
      ]
    )?.steered;

    // If value is already a FieldValue, use it directly (normalize its .value)
    // Otherwise, wrap it
    let fieldValue: FieldValue;
    if (value && typeof value === 'object' && 'value' in value) {
      // Already a FieldValue object
      const fv = value as FieldValue;
      const merged = field ? { ...fv, value: normalizeFieldValue(field, fv.value) } : { ...fv };
      if (merged.steered === undefined && priorSteered !== undefined) merged.steered = priorSteered;
      fieldValue = merged;
    } else {
      // Wrap raw value in FieldValue
      fieldValue = {
        value: field ? normalizeFieldValue(field, value) : value,
        confirmed: options?.confirmed,
        confirmedAt: options?.confirmed ? new Date().toISOString() : undefined,
        confirmationMethod: options?.confirmationMethod,
        lastModified: Date.now(),
        ...(priorSteered !== undefined ? { steered: priorSteered } : {}),
      };
    }

    const newState = {
      ...state,
      fieldValues: {
        ...state.fieldValues,
        [fieldId]: fieldValue,
      },
      lastUpdated: Date.now(),
    };

    console.log(`[SchemaFormStateManager] New state.fieldValues after spread:`, newState.fieldValues);

    // Clear validation error for this field
    if (newState.validationErrors[fieldId]) {
      const { [fieldId]: removed, ...rest } = newState.validationErrors;
      newState.validationErrors = rest;
    }

    this.save(newState);
    console.log(`[SchemaFormStateManager] Returning newState with fieldValues:`, newState.fieldValues);
    console.log(`[SchemaFormStateManager] Are they the same object?`, state.fieldValues === newState.fieldValues);
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
   * Mark section as completed
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

    return section.fields
      .map((fieldId) => state.schema.fields.find((f) => f.id === fieldId))
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
   * Get form completion progress (percentage)
   */
  static getProgress(state: SchemaFormState): number {
    const totalFields = state.schema.fields.length;
    const filledFields = Object.keys(state.fieldValues).filter(
      (fieldId) => {
        const fieldValue = state.fieldValues[fieldId];
        const actualValue = fieldValue?.value;
        return actualValue !== null && actualValue !== undefined && actualValue !== "";
      }
    ).length;

    return totalFields > 0 ? (filledFields / totalFields) * 100 : 0;
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

    const sectionFields = section.fields
      .map((fieldId) => state.schema.fields.find((f) => f.id === fieldId))
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
          const isEmpty =
            actualValue === null ||
            actualValue === undefined ||
            actualValue === "" ||
            (Array.isArray(actualValue) && actualValue.length === 0);
          if (isEmpty) {
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
   * - computeNextField() which skips locked/hidden fields for next_field_hint
   * - Backend validation which rejects updates to locked fields with helpful error
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
      section.fields.forEach(fieldId => {
        const field = state.schema.fields.find(f => f.id === fieldId);
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
      ? formatNextFieldHint(nextField, getFieldOrder(state, nextField.id) || undefined)
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
      previous_spoken_names: this.getPreviousSpokenNames(state),
      initial_field_hint: initialFieldHint,
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
    const fieldValue = state.fieldValues[fieldId];
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
        [fieldId]: {
          ...fieldValue,
          confirmed: true,
          confirmedAt: new Date().toISOString(),
          confirmationMethod: method
        }
      },
      // A confirmed pinned field releases the pin -- the form resumes its
      // normal fill order (bd polyglot-pdf-jnjj.36).
      pinnedFieldId: state.pinnedFieldId === fieldId ? null : state.pinnedFieldId,
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
    const prior = state.fieldValues[fieldId];
    const newState = {
      ...state,
      fieldValues: {
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
      },
      lastUpdated: Date.now(),
    };

    // A skipped field is intentionally empty -- clear any stale validation error.
    if (newState.validationErrors[fieldId]) {
      const { [fieldId]: _removed, ...rest } = newState.validationErrors;
      newState.validationErrors = rest;
    }

    // A skipped pinned field releases the pin, same as a confirm
    // (bd polyglot-pdf-jnjj.36).
    if (newState.pinnedFieldId === fieldId) {
      newState.pinnedFieldId = null;
    }

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
      fieldValues[key] = { ...fv, steered: true };
      changed = true;
    }
    if (!changed) return state;
    const newState = { ...state, fieldValues, lastUpdated: Date.now() };
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
   * Update selected language (for language change after disclaimer)
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
