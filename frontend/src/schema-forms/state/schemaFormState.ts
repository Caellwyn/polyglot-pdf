/**
 * SchemaFormState - State manager for schema-driven form filling
 *
 * Manages form state in sessionStorage for PDF schema-based forms.
 * Compatible with existing WebFormStateManager pattern.
 *
 * Features:
 * - Persistent state across page reloads (sessionStorage)
 * - Section-based navigation
 * - Validation state tracking
 * - Field value management
 */

import type { FormSchema, FormSection, FormField } from "../types/schema";

export interface SchemaFormState {
  schema: FormSchema;
  fieldValues: Record<string, any>; // field_id → value
  currentSectionId: string;
  completedSections: Set<string>;
  validationErrors: Record<string, string>; // field_id → error message
  lastUpdated: number;
  sessionId?: string; // For backend integration (future)
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

    // New session - initialize with first section
    const firstSection = this.getFirstSection(cleanedSchema);

    const newState: SchemaFormState = {
      schema: cleanedSchema,
      fieldValues: {},
      currentSectionId: firstSection?.id || "",
      completedSections: new Set(),
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
        console.log('[SchemaFormStateManager] load() - No stored state found');
        return null;
      }

      console.log('[SchemaFormStateManager] load() - Found stored state, length:', stored.length);
      const parsed = JSON.parse(stored);
      console.log('[SchemaFormStateManager] load() - Parsed fieldValues:', parsed.fieldValues);

      // Restore Set from array
      if (parsed.completedSections) {
        parsed.completedSections = new Set(parsed.completedSections);
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
        completedSections: Array.from(state.completedSections),
        lastUpdated: Date.now(),
      };

      console.log('[SchemaFormStateManager] save() - About to save fieldValues:', toStore.fieldValues);
      const jsonString = JSON.stringify(toStore);
      console.log('[SchemaFormStateManager] save() - JSON string length:', jsonString.length);
      sessionStorage.setItem(this.STORAGE_KEY, jsonString);

      // Verify it was saved
      const verified = sessionStorage.getItem(this.STORAGE_KEY);
      const parsed = JSON.parse(verified!);
      console.log('[SchemaFormStateManager] save() - Verified fieldValues after save:', parsed.fieldValues);
    } catch (error) {
      console.error("[SchemaFormState] Failed to save state:", error);
    }
  }

  /**
   * Update a field value
   */
  static updateField(state: SchemaFormState, fieldId: string, value: any): SchemaFormState {
    console.log(`[SchemaFormStateManager] updateField: ${fieldId} = ${JSON.stringify(value)}`);
    console.log(`[SchemaFormStateManager] Current state.fieldValues:`, state.fieldValues);

    const newState = {
      ...state,
      fieldValues: {
        ...state.fieldValues,
        [fieldId]: value,
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
   * Mark current section as completed
   */
  static markSectionComplete(state: SchemaFormState, sectionId: string): SchemaFormState {
    const newState = {
      ...state,
      completedSections: new Set([...state.completedSections, sectionId]),
      lastUpdated: Date.now(),
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
   * Deduplicate sections (e.g., Part 7 with different capitalization)
   * Merges duplicate sections by combining their fields
   */
  private static deduplicateSections(schema: FormSchema): FormSchema {
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
      (fieldId) => state.fieldValues[fieldId] !== null && state.fieldValues[fieldId] !== ""
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
        const value = state.fieldValues[field.id];
        if (value === null || value === undefined || value === "") {
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
}
