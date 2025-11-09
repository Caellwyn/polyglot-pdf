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

export interface SchemaFormState {
  schema: FormSchema;
  fieldValues: Record<string, FieldValue>; // field_id → FieldValue (with confirmed flag)
  currentPartId: string; // Part ID like "part_1" (renamed from currentSectionId for clarity)
  completedParts: Set<string>; // Track completed parts (renamed from completedSections)
  validationErrors: Record<string, string>; // field_id → error message
  lastUpdated: number;
  sessionId?: string; // Set by backend during handshake
}

export class SchemaFormStateManager {
  private static readonly STORAGE_KEY = "schema_form_state";

  /**
   * Initialize or load existing form state
   */
  static init(schema: FormSchema): SchemaFormState {
    console.log('[SchemaFormStateManager] init() called');
    const existing = this.load();
    console.log('[SchemaFormStateManager] Loaded existing state:', existing ? `has ${Object.keys(existing.fieldValues).length} field values` : 'NULL');

    // Clean up duplicate sections (e.g., Part 7 appears twice with different capitalization)
    const cleanedSchema = this.deduplicateSections(schema);

    // If schema matches and it's recent (< 1 hour), reuse state
    if (
      existing &&
      existing.schema.form_metadata.form_number === cleanedSchema.form_metadata.form_number &&
      existing.schema.form_metadata.version === cleanedSchema.form_metadata.version &&
      Date.now() - existing.lastUpdated < 60 * 60 * 1000
    ) {
      console.log('[SchemaFormStateManager] Returning EXISTING state with', Object.keys(existing.fieldValues).length, 'field values');
      console.log('[SchemaFormStateManager] existing.fieldValues:', existing.fieldValues);
      return existing;
    }

    console.log('[SchemaFormStateManager] Creating NEW empty state');

    // New session - initialize with first part (or first section if no parts)
    const firstPart = this.getFirstPart(cleanedSchema);
    const firstSection = this.getFirstSection(cleanedSchema);

    // currentPartId can be either a part ID or section ID depending on schema structure
    const initialId = firstPart?.id || firstSection?.id || "";

    const newState: SchemaFormState = {
      schema: cleanedSchema,
      fieldValues: {},
      currentPartId: initialId, // Can be part_1 or section ID
      completedParts: new Set(),
      validationErrors: {},
      lastUpdated: Date.now(),
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
      if (parsed.completedParts) {
        parsed.completedParts = new Set(parsed.completedParts);
      } else if (parsed.completedSections) {
        // Backwards compatibility: migrate completedSections → completedParts
        parsed.completedParts = new Set(parsed.completedSections);
        delete parsed.completedSections;
      }

      // Backwards compatibility: migrate currentSectionId → currentPartId
      if (parsed.currentSectionId && !parsed.currentPartId) {
        parsed.currentPartId = parsed.currentSectionId;
        delete parsed.currentSectionId;
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
      // Convert Set to array for JSON serialization
      const toStore = {
        ...state,
        completedParts: Array.from(state.completedParts),
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
    options?: { confirmed?: boolean }
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
   * Navigate to a different part (renamed from navigateToSection)
   */
  static navigateToPart(state: SchemaFormState, partId: string): SchemaFormState {
    const newState = {
      ...state,
      currentPartId: partId,
      lastUpdated: Date.now(),
    };

    this.save(newState);
    return newState;
  }

  /**
   * Navigate to a different section (backwards compatibility wrapper)
   * @deprecated Use navigateToPart() instead
   */
  static navigateToSection(state: SchemaFormState, sectionId: string): SchemaFormState {
    return this.navigateToPart(state, sectionId);
  }

  /**
   * Mark section as completed (backwards compatibility wrapper)
   * @deprecated Use markPartComplete() instead
   */
  static markSectionComplete(state: SchemaFormState, sectionId: string): SchemaFormState {
    return this.markPartComplete(state, sectionId);
  }

  /**
   * Get current section from schema (finds section in current part)
   */
  static getCurrentSection(state: SchemaFormState): FormSection | null {
    const currentPart = this.getCurrentPart(state);
    if (!currentPart) return null;

    // Find first section in this part
    const sectionId = currentPart.section_ids[0];
    return state.schema.sections.find((s) => s.id === sectionId) || null;
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
   * Get next part (for navigation)
   */
  static getNextPart(state: SchemaFormState): FormPart | null {
    const currentPart = this.getCurrentPart(state);
    if (!currentPart) return null;

    const sortedParts = [...(state.schema.parts || [])].sort((a, b) => a.order - b.order);
    const currentIndex = sortedParts.findIndex((p) => p.id === currentPart.id);

    if (currentIndex === -1 || currentIndex === sortedParts.length - 1) {
      return null; // No next part
    }

    return sortedParts[currentIndex + 1];
  }

  /**
   * Get previous part (for navigation)
   */
  static getPreviousPart(state: SchemaFormState): FormPart | null {
    const currentPart = this.getCurrentPart(state);
    if (!currentPart) return null;

    const sortedParts = [...(state.schema.parts || [])].sort((a, b) => a.order - b.order);
    const currentIndex = sortedParts.findIndex((p) => p.id === currentPart.id);

    if (currentIndex <= 0) {
      return null; // No previous part
    }

    return sortedParts[currentIndex - 1];
  }

  /**
   * Get first part from schema
   */
  private static getFirstPart(schema: FormSchema) {
    if (!schema.parts || schema.parts.length === 0) return null;
    const sortedParts = [...schema.parts].sort((a, b) => a.order - b.order);
    return sortedParts[0] || null;
  }

  /**
   * Get first section from schema
   */
  private static getFirstSection(schema: FormSchema): FormSection | null {
    const sortedSections = [...schema.sections].sort((a, b) => a.order - b.order);
    return sortedSections[0] || null;
  }

  /**
   * Deduplicate sections (e.g., Part 7 with different capitalization)
   * Merges duplicate sections by combining their fields
   */
  private static deduplicateSections(schema: FormSchema): FormSchema {
    // Check if any sections match the "Part N" pattern
    const hasPartPattern = schema.sections.some(s => /^Part\s+\d+/i.test(s.id));

    // If no sections match the pattern, skip deduplication
    if (!hasPartPattern) {
      return schema;
    }

    const seenParts = new Map<string, FormSection>();
    const deduplicatedSections: FormSection[] = [];

    // Extract part number from section ID (e.g., "Part 7" from "Part 7 - Some Title")
    const getPartNumber = (sectionId: string): number => {
      const match = sectionId.match(/^Part\s+(\d+)/i);
      return match ? parseInt(match[1], 10) : 999;
    };

    for (const section of schema.sections) {
      const partNumber = getPartNumber(section.id);
      const partKey = `part_${partNumber}`;

      if (seenParts.has(partKey)) {
        // Merge fields into existing section
        const existing = seenParts.get(partKey)!;
        existing.fields = [...existing.fields, ...section.fields];
      } else {
        // First occurrence of this part
        const newSection = { ...section, fields: [...section.fields] };
        seenParts.set(partKey, newSection);
        deduplicatedSections.push(newSection);
      }
    }

    // Sort by part number (extracted from ID), not by original order field
    deduplicatedSections.sort((a, b) => {
      const aNum = getPartNumber(a.id);
      const bNum = getPartNumber(b.id);
      return aNum - bNum;
    });

    // Re-number sections to be sequential
    deduplicatedSections.forEach((section, index) => {
      section.order = index + 1;
    });

    console.log(`[SchemaFormState] Deduplicated ${schema.sections.length} sections -> ${deduplicatedSections.length} sections`);
    deduplicatedSections.forEach((section, i) => {
      console.log(`  ${i + 1}. ${section.id} (order: ${section.order}, ${section.fields.length} fields)`);
    });

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
   * Get current part number (for WebSocket section_number field)
   * Maps parts[].order to section_number
   */
  static getCurrentPartNumber(state: SchemaFormState): number {
    const part = state.schema.parts?.find(p => p.id === state.currentPartId);
    return part?.order ?? 1;
  }

  /**
   * Switch to a different part by ID
   * Used for section switching via WebSocket
   */
  static switchToPart(state: SchemaFormState, partId: string): SchemaFormState {
    // Only mark current part as completed if switching to a different part
    const completedParts = partId !== state.currentPartId
      ? new Set([...state.completedParts, state.currentPartId])
      : state.completedParts;

    const newState = {
      ...state,
      currentPartId: partId,
      completedParts,
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  /**
   * Complete current part and add to completed set
   */
  static completePart(state: SchemaFormState, partId: string): SchemaFormState {
    const newState = {
      ...state,
      completedParts: new Set([...state.completedParts, partId]),
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }

  /**
   * Extract fields for a specific part (for WebSocket handshake)
   * Returns schema with only fields from the specified part
   */
  static extractPartFields(schema: FormSchema, partId: string): FormSchema {
    // Handle schemas without parts (legacy web forms) - treat sectionId as partId
    if (!schema.parts || schema.parts.length === 0) {
      const section = schema.sections.find(s => s.id === partId);
      if (!section) {
        console.warn(`[SchemaFormStateManager] Part ${partId} not found in schema`);
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

    const part = schema.parts?.find(p => p.id === partId);
    if (!part) {
      console.warn(`[SchemaFormStateManager] Part ${partId} not found in schema`);
      // Return schema with empty fields and sections
      return {
        ...schema,
        fields: [],
        sections: []
      };
    }

    // Find sections in this part
    const partSections = schema.sections.filter(s => part.section_ids.includes(s.id));

    // Collect all field IDs from these sections
    const partFieldIds = new Set<string>();
    partSections.forEach(section => {
      section.fields.forEach(fieldId => partFieldIds.add(fieldId));
    });

    // Filter fields to only those in this part
    const partFields = schema.fields.filter(f => partFieldIds.has(f.id));

    return {
      ...schema,
      fields: partFields,
      sections: partSections
    };
  }

  /**
   * Get spoken names from completed parts (for WebSocket previous_spoken_names)
   * Returns array of spoken names from all completed parts
   */
  static getPreviousSpokenNames(state: SchemaFormState): string[] {
    const spokenNames: string[] = [];

    for (const partId of state.completedParts) {
      const part = state.schema.parts?.find(p => p.id === partId);
      if (!part) continue;

      // Find sections in this part
      const partSections = state.schema.sections.filter(s => part.section_ids.includes(s.id));

      // Collect spoken names from all fields in these sections
      partSections.forEach(section => {
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
      });
    }

    return spokenNames;
  }

  /**
   * Generate WebSocket handshake payload
   * Used when connecting to backend or switching sections
   */
  static getHandshakePayload(state: SchemaFormState, fillLanguage: string = 'English') {
    const currentPart = state.schema.parts?.find(p => p.id === state.currentPartId);

    // Extract schema for current part only
    const partSchema = this.extractPartFields(state.schema, state.currentPartId);

    // Get previous spoken names from completed parts
    const previousSpokenNames = this.getPreviousSpokenNames(state);

    return {
      schema: partSchema,
      current_values: state.fieldValues, // Already in FieldValue format
      section_number: currentPart?.order ?? 1, // Use order as section_number
      section_label: currentPart?.label ?? '',
      total_sections: state.schema.parts?.length ?? 1,
      previous_spoken_names: previousSpokenNames,
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
   * Searches current part + completed parts for field with matching spoken_name or alias
   */
  static getFieldBySpokenName(state: SchemaFormState, spokenName: string): string | null {
    const lowerSpokenName = spokenName.toLowerCase();

    // Get all parts to search (current + completed)
    const partsToSearch = new Set([state.currentPartId, ...state.completedParts]);

    for (const partId of partsToSearch) {
      const part = state.schema.parts?.find(p => p.id === partId);
      if (!part) continue;

      // Get sections in this part
      const partSections = state.schema.sections.filter(s => part.section_ids.includes(s.id));

      // Search fields in these sections
      for (const section of partSections) {
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
    }

    return null;
  }

  /**
   * Get part label by order number
   */
  static getPartLabel(state: SchemaFormState, orderNumber: number): string {
    const part = state.schema.parts?.find(p => p.order === orderNumber);
    return part?.label || '';
  }

  /**
   * Find part ID by label (case-insensitive)
   */
  static findPartByLabel(state: SchemaFormState, label: string): string | null {
    const lowerLabel = label.toLowerCase();
    const part = state.schema.parts?.find(p =>
      p.label.toLowerCase() === lowerLabel
    );
    return part?.id || null;
  }

  /**
   * Get current part from state
   */
  static getCurrentPart(state: SchemaFormState) {
    return state.schema.parts?.find(p => p.id === state.currentPartId) || null;
  }

  /**
   * Mark a part as completed
   */
  static markPartComplete(state: SchemaFormState, partId: string): SchemaFormState {
    const newState = {
      ...state,
      completedParts: new Set([...state.completedParts, partId]),
      lastUpdated: Date.now()
    };
    this.save(newState);
    return newState;
  }
}
