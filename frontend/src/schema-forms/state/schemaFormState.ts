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
    const existing = this.load();

    // If schema matches and it's recent (< 1 hour), reuse state
    if (
      existing &&
      existing.schema.form_metadata.form_number === schema.form_metadata.form_number &&
      existing.schema.form_metadata.version === schema.form_metadata.version &&
      Date.now() - existing.lastUpdated < 60 * 60 * 1000
    ) {
      return existing;
    }

    // New session - initialize with first section
    const firstSection = this.getFirstSection(schema);

    const newState: SchemaFormState = {
      schema,
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
      if (!stored) return null;

      const parsed = JSON.parse(stored);

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

      sessionStorage.setItem(this.STORAGE_KEY, JSON.stringify(toStore));
    } catch (error) {
      console.error("[SchemaFormState] Failed to save state:", error);
    }
  }

  /**
   * Update a field value
   */
  static updateField(state: SchemaFormState, fieldId: string, value: any): SchemaFormState {
    const newState = {
      ...state,
      fieldValues: {
        ...state.fieldValues,
        [fieldId]: value,
      },
      lastUpdated: Date.now(),
    };

    // Clear validation error for this field
    if (newState.validationErrors[fieldId]) {
      const { [fieldId]: removed, ...rest } = newState.validationErrors;
      newState.validationErrors = rest;
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
    if (!currentSection) return null;

    const sortedSections = [...state.schema.sections].sort((a, b) => a.order - b.order);
    const currentIndex = sortedSections.findIndex((s) => s.id === currentSection.id);

    if (currentIndex === -1 || currentIndex === sortedSections.length - 1) {
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
