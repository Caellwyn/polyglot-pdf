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
import { buildHandshakeManifest, getFieldSchema } from "../utils/manifestUtils";

export interface SchemaFormState {
  schema: FormSchema;
  fieldValues: Record<string, FieldValue>; // field_id → FieldValue (with confirmed flag)
  currentSectionId: string; // Section ID (e.g., "part_1_2_addresses")
  completedSections: Set<string>; // Track completed sections
  validationErrors: Record<string, string>; // field_id → error message
  lastUpdated: number;
  sessionId?: string; // Set by backend during handshake (Gemini session ID)
  formSessionId: string; // Persistent ID for this form filling session (survives reconnects)

  // Phase 3: JIT (Just-In-Time) Schema Loading - Token Reduction
  loadedFieldIds: Set<string>; // Field IDs where Gemini has received full schema
  jitModeEnabled: boolean; // Whether JIT mode is active (from backend feature flag)

  // Disclaimer acceptance tracking
  disclaimerAccepted: boolean; // Whether user has accepted disclaimer
  disclaimerAcceptedAt?: number; // Timestamp of disclaimer acceptance
  selectedLanguage?: string; // User's selected spoken language
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
      // Disclaimer acceptance
      disclaimerAccepted: false,
      disclaimerAcceptedAt: undefined,
      selectedLanguage: undefined,
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
        // Backwards compatibility: migrate completedParts → completedSections
        parsed.completedSections = new Set(parsed.completedParts);
        delete parsed.completedParts;
      }

      // Backwards compatibility: migrate currentPartId → currentSectionId
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

    // If value is already a FieldValue, use it directly
    // Otherwise, wrap it
    let fieldValue: FieldValue;
    if (value && typeof value === 'object' && 'value' in value) {
      // Already a FieldValue object
      fieldValue = value as FieldValue;
    } else {
      // Wrap raw value in FieldValue
      fieldValue = {
        value: value,
        confirmed: options?.confirmed,
        confirmedAt: options?.confirmed ? new Date().toISOString() : undefined,
        confirmationMethod: options?.confirmationMethod,
        lastModified: Date.now()
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
      console.log('[getNextSection] currentSection is NULL');
      return null;
    }

    const sortedSections = [...state.schema.sections].sort((a, b) => a.order - b.order);
    console.log('[getNextSection] All sections after sort:', sortedSections.map(s => `${s.id} (order: ${s.order})`));
    console.log('[getNextSection] Looking for currentSection.id:', currentSection.id);

    const currentIndex = sortedSections.findIndex((s) => s.id === currentSection.id);
    console.log('[getNextSection] currentIndex:', currentIndex, 'out of', sortedSections.length, 'sections');

    if (currentIndex === -1) {
      console.error('[getNextSection] Current section ID not found in sorted sections! This means state.currentSectionId does not match any section ID.');
      return null;
    }

    if (currentIndex === sortedSections.length - 1) {
      console.log('[getNextSection] Already at last section');
      return null; // No next section
    }

    const nextSection = sortedSections[currentIndex + 1];
    console.log('[getNextSection] Returning next section:', nextSection.id);
    return nextSection;
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
   * Check if current section is valid (all required fields filled)
   */
  static isSectionValid(state: SchemaFormState, sectionId: string): boolean {
    const section = state.schema.sections.find((s) => s.id === sectionId);
    if (!section) return false;

    const sectionFields = section.fields
      .map((fieldId) => state.schema.fields.find((f) => f.id === fieldId))
      .filter((f): f is FormField => f !== undefined);

    for (const field of sectionFields) {
      // Check if required field is filled
      if (field.validation?.required) {
        const fieldValue = state.fieldValues[field.id];
        const actualValue = fieldValue?.value;
        if (actualValue === null || actualValue === undefined || actualValue === "") {
          return false;
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
  static extractSectionFields(schema: FormSchema, sectionId: string): FormSchema {
    const section = schema.sections.find(s => s.id === sectionId);
    if (!section) {
      console.warn(`[SchemaFormStateManager] Section ${sectionId} not found in schema`);
      return {
        ...schema,
        fields: [],
        sections: []
      };
    }

    // Extract fields for this section
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
  static getHandshakePayload(state: SchemaFormState, fillLanguage: string = 'English') {
    // Check if JIT mode is enabled
    if (state.jitModeEnabled) {
      return this.getJITHandshakePayload(state, fillLanguage);
    }

    // Legacy mode: send full schema for current section
    const currentSection = state.schema.sections.find(s => s.id === state.currentSectionId);

    // Extract schema for current section only
    const sectionSchema = this.extractSectionFields(state.schema, state.currentSectionId);

    // Get previous spoken names from completed sections
    const previousSpokenNames = this.getPreviousSpokenNames(state);

    return {
      form_session_id: state.formSessionId, // Persistent ID for logging/metrics
      schema: sectionSchema,
      current_values: state.fieldValues, // Already in FieldValue format
      section_number: currentSection?.order ?? 1, // Use order as section_number
      section_label: currentSection?.label ?? '',
      total_sections: state.schema.sections.length,
      previous_spoken_names: previousSpokenNames,
      fill_language: fillLanguage
    };
  }

  /**
   * Generate JIT mode handshake payload with manifest
   * Only sends field_id|spoken_name pairs, not full schemas
   */
  static getJITHandshakePayload(state: SchemaFormState, fillLanguage: string = 'English') {
    const currentSection = state.schema.sections?.find(s => s.id === state.currentSectionId);

    // Build manifest with current + previous sections
    const manifest = buildHandshakeManifest(state.currentSectionId, state.schema, state);

    // Get first field schema for current section
    let firstFieldSchema = null;
    const sectionSchema = this.extractSectionFields(state.schema, state.currentSectionId);
    if (sectionSchema.fields.length > 0) {
      const firstFieldId = sectionSchema.fields[0].id;
      firstFieldSchema = getFieldSchema(firstFieldId, state.schema);
    }

    return {
      type: 'handshake_jit',
      form_session_id: state.formSessionId, // Persistent ID for logging/metrics
      manifest: manifest,
      first_field_schema: firstFieldSchema,
      loaded_field_ids: Array.from(state.loadedFieldIds),
      current_values: state.fieldValues,
      section_number: currentSection?.order ?? 1,
      section_label: currentSection?.label ?? '',
      total_sections: state.schema.sections?.length ?? 1,
      fill_language: fillLanguage
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
   * Get field ID by spoken name (for WebSocket field lookups)
   * Searches current section + completed sections for field with matching spoken_name or alias
   */
  static getFieldBySpokenName(state: SchemaFormState, spokenName: string): string | null {
    const lowerSpokenName = spokenName.toLowerCase();

    // Get all sections to search (current + completed)
    const sectionsToSearch = new Set([state.currentSectionId, ...state.completedSections]);

    for (const sectionId of sectionsToSearch) {
      const section = state.schema.sections.find(s => s.id === sectionId);
      if (!section) continue;

      // Search fields in this section
      for (const fieldId of section.fields) {
        const field = state.schema.fields.find(f => f.id === fieldId);
        if (!field) continue;

        // Check spoken_name
        if (field.spoken_name?.toLowerCase() === lowerSpokenName) {
          return field.id;
        }

        // Check spoken_aliases
        if (field.spoken_aliases) {
          for (const alias of field.spoken_aliases) {
            if (alias.toLowerCase() === lowerSpokenName) {
              return field.id;
            }
          }
        }
      }
    }

    return null;
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
   * - From get_field_value (if schema not already sent)
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
   * Phase 3: JIT Schema Loading - Enable/disable JIT mode
   *
   * Called during handshake based on backend USE_JIT_SCHEMA flag
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
   * Phase 3: JIT Schema Loading - Clear loaded field IDs
   *
   * Called when switching parts/sections to reset tracking
   */
  static clearLoadedFieldIds(state: SchemaFormState): SchemaFormState {
    const newState = {
      ...state,
      loadedFieldIds: new Set(),
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  // ============================================================================
  // Confirmation Status Management
  // ============================================================================

  /**
   * Check if a field is confirmed
   */
  static isFieldConfirmed(state: SchemaFormState, fieldId: string): boolean {
    const fieldValue = state.fieldValues[fieldId];
    return fieldValue?.confirmed === true;
  }

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
      return state; // Field doesn't exist
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
      lastUpdated: Date.now()
    };

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
