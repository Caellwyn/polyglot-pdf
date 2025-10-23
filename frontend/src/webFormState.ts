/**
 * WebFormState - Client-side state manager for web form filling
 *
 * Manages form state in sessionStorage for stateless backend architecture.
 * Handles reconnects by preserving schema + current values.
 *
 * Features:
 * - Persistent state across page reloads (sessionStorage)
 * - Optimistic updates for user edits
 * - Confirmed flag preservation for AI-filled fields
 * - Schema caching for reconnects
 */

import { computeNextField, formatNextFieldHint } from './navigation'

export interface FieldValue {
  value: string | boolean | null;
  confirmed?: boolean;  // Set to true when AI fills the field
  lastModified?: number;  // Timestamp for conflict resolution
}

export interface FormSchema {
  source: "web";
  form_metadata: {
    title: string;
    url: string;
  };
  fields: Array<{
    id: string;
    name: string;
    type: string;
    required?: boolean;
    options?: string[];
    value?: string | boolean | null;
    meta?: Record<string, any>;
    spoken_name?: string;  // Phase 3: For section navigation
    spoken_aliases?: string[];  // Phase 3: Alternative names
    // Validation constraints (passed to Gemini for guidance)
    format?: string;  // e.g., "YYYY-MM-DD", "MM/DD/YYYY", "###-##-####"
    pattern?: string;  // Regex pattern for validation
    min?: number;  // Min value (number) or min length (text)
    max?: number;  // Max value (number) or max length (text)
    minLength?: number;  // Min length for text
    maxLength?: number;  // Max length for text
    placeholder?: string;  // Example value
    description?: string;  // Additional guidance for Gemini
  }>;
}

export interface SectionInfo {
  section_number: number;
  section_id: string;
  section_label: string;
  field_indices: number[];
  field_count: number;
}

export interface SectionIndex {
  form_id: string;
  full_schema_path: string;
  total_sections: number;
  sections: SectionInfo[];
}

export interface WebFormState {
  schema: FormSchema;
  current_values: Record<string, FieldValue>;
  session_id?: string;  // Ephemeral ID from backend (for logging)
  last_updated: number;
  
  // Phase 3: Section-based flow
  current_section?: number;  // 1-9
  completed_sections?: Set<number>;  // Sections marked complete
  section_index?: SectionIndex;  // Full section index
  full_schema?: FormSchema;  // All 174 fields (schema = current section only)
}

export class WebFormStateManager {
  private static readonly STORAGE_KEY = "web_form_state";
  private static readonly SECTION_KEY = "vff_current_section";
  private static readonly COMPLETED_SECTIONS_KEY = "vff_completed_sections";
  private static readonly SPOKEN_NAME_MAP_KEY = "vff_spoken_name_map";
  
  /**
   * Initialize or load existing form state
   */
  static init(schema: FormSchema): WebFormState {
    const existing = this.load();
    
    // If schema URL matches and it's recent (< 1 hour), reuse state
    if (
      existing &&
      existing.schema.form_metadata.url === schema.form_metadata.url &&
      Date.now() - existing.last_updated < 60 * 60 * 1000
    ) {
      return existing;
    }
    
    // New session
    const newState: WebFormState = {
      schema,
      current_values: {},
      last_updated: Date.now(),
    };
    
    this.save(newState);
    
    return newState;
  }
  
  /**
   * Load state from sessionStorage
   */
  static load(): WebFormState | null {
    try {
      const json = sessionStorage.getItem(this.STORAGE_KEY);
      if (!json) return null;
      
      const parsed = JSON.parse(json);
      
      // Deserialize Set objects
      if (parsed.completed_sections && Array.isArray(parsed.completed_sections)) {
        parsed.completed_sections = new Set(parsed.completed_sections);
      }
      
      return parsed as WebFormState;
    } catch (err) {
      return null;
    }
  }
  
  /**
   * Save state to sessionStorage
   */
  static save(state: WebFormState): void {
    try {
      state.last_updated = Date.now();
      
      // Serialize Set to Array for JSON
      const serialized = {
        ...state,
        completed_sections: state.completed_sections 
          ? Array.from(state.completed_sections)
          : undefined,
      };
      
      sessionStorage.setItem(this.STORAGE_KEY, JSON.stringify(serialized));
    } catch (err) {
      // Silently fail - will retry on next save
    }
  }
  
  /**
   * Update a field value (user edit or AI update)
   */
  static updateFieldValue(
    state: WebFormState,
    fieldId: string,
    value: string | boolean | null,
    options?: { confirmed?: boolean }
  ): WebFormState {
    const previous: FieldValue = state.current_values[fieldId] || { value: null, confirmed: false };
    const confirmed = options?.confirmed !== undefined
      ? options.confirmed
      : (typeof previous.confirmed === "boolean" ? previous.confirmed : false);

    const updated: WebFormState = {
      ...state,
      current_values: {
        ...state.current_values,
        [fieldId]: {
          ...previous,
          value,
          confirmed,
          lastModified: Date.now(),
        },
      },
    };

    this.save(updated);
    return updated;
  }
  
  /**
   * Mark multiple fields as confirmed (AI filled them)
   */
  static markConfirmed(
    state: WebFormState,
    fieldIds: string[]
  ): WebFormState {
    const updated: WebFormState = {
      ...state,
      current_values: { ...state.current_values },
    };
    
    for (const fieldId of fieldIds) {
      if (updated.current_values[fieldId]) {
        updated.current_values[fieldId] = {
          ...updated.current_values[fieldId],
          confirmed: true,
        };
      }
    }
    
    this.save(updated);
    return updated;
  }
  
  /**
   * Get handshake payload for WebSocket connection
   * Phase 3: Includes section metadata for section-based flow
   */
  static getHandshakePayload(state: WebFormState, fillLanguage: string = "English"): {
    type: "handshake";
    schema: FormSchema;
    current_values: Record<string, FieldValue>;
    fill_language: string;
    section_number?: number;
    section_label?: string;
    total_sections?: number;
    previous_spoken_names?: string[];
    initial_field_hint?: string;
  } {
    const payload: any = {
      type: "handshake",
      schema: state.schema,
      current_values: state.current_values,
      fill_language: fillLanguage,
    };

    // Compute initial field hint for Gemini to know where to start
    const nextField = computeNextField(state);
    if (nextField) {
      payload.initial_field_hint = formatNextFieldHint(nextField, state.schema);
    }

    // Phase 3: Add section metadata if this is a section-based session
    if (state.section_index) {
      payload.section_number = state.current_section;
      payload.total_sections = state.section_index.total_sections;

      // Get section label
      const section = state.section_index.sections.find(s => s.section_number === state.current_section);
      if (section) {
        payload.section_label = section.section_label;
      }

      // Get previous spoken names from completed sections (as array, not Map!)
      const spokenNameMap = this.getSpokenNameMap(state);
      payload.previous_spoken_names = Array.from(spokenNameMap.keys());
    }

    return payload;
  }
  
  /**
   * Set ephemeral session ID from backend
   */
  static setSessionId(state: WebFormState, sessionId: string): WebFormState {
    const updated = { ...state, session_id: sessionId };
    this.save(updated);
    return updated;
  }
  
  /**
   * Clear state (logout, form complete, etc.)
   */
  static clear(): void {
    sessionStorage.removeItem(this.STORAGE_KEY);
  }
  
  /**
   * Get fields that need AI attention (not confirmed)
   */
  static getUnconfirmedFields(state: WebFormState): string[] {
    return state.schema.fields
      .filter((field) => {
        const currentValue = state.current_values[field.id];
        return !currentValue || !currentValue.confirmed;
      })
      .map((field) => field.id);
  }
  
  /**
   * Get form completion percentage
   */
  static getCompletionPercentage(state: WebFormState): number {
    const total = state.schema.fields.length;
    if (total === 0) return 100;
    
    const filled = state.schema.fields.filter((field) => {
      const currentValue = state.current_values[field.id];
      return currentValue && currentValue.value !== null && currentValue.value !== "";
    }).length;
    
    return Math.round((filled / total) * 100);
  }
  
  /**
   * Export state for debugging (kept for development use)
   */
  static debug(state: WebFormState): void {
    // Reserved for manual debugging - no-op in production
  }
  
  /**
   * Phase 3: Initialize section-based state
   */
  static initWithSections(fullSchema: FormSchema, sectionIndex: SectionIndex): WebFormState {
    const existing = this.load();
    
    // Check if we can resume existing session
    if (
      existing &&
      existing.full_schema &&
      existing.section_index &&
      existing.full_schema.form_metadata.url === fullSchema.form_metadata.url &&
      Date.now() - existing.last_updated < 60 * 60 * 1000
    ) {
      return existing;
    }
    
    // New section-based session - start at section 1
    const section1Schema = this.getSectionSchema(fullSchema, sectionIndex, 1);
    const newState: WebFormState = {
      schema: section1Schema,
      current_values: {},
      last_updated: Date.now(),
      current_section: 1,
      completed_sections: new Set<number>(),
      section_index: sectionIndex,
      full_schema: fullSchema,
    };
    
    this.save(newState);
    
    return newState;
  }
  
  /**
   * Phase 3: Get schema for a specific section
   */
  static getSectionSchema(fullSchema: FormSchema, sectionIndex: SectionIndex, sectionNumber: number): FormSchema {
    const section = sectionIndex.sections.find(s => s.section_number === sectionNumber);
    if (!section) {
      throw new Error(`Section ${sectionNumber} not found in index`);
    }
    
    const sectionFields = section.field_indices.map(idx => fullSchema.fields[idx]);
    
    return {
      ...fullSchema,
      fields: sectionFields,
    };
  }
  
  /**
   * Phase 3: Switch to a different section
   */
  static switchSection(state: WebFormState, sectionNumber: number): WebFormState {
    if (!state.section_index || !state.full_schema) {
      throw new Error("Cannot switch sections: section_index or full_schema not initialized");
    }
    
    if (sectionNumber < 1 || sectionNumber > state.section_index.total_sections) {
      throw new Error(`Invalid section number: ${sectionNumber}`);
    }
    
    const sectionSchema = this.getSectionSchema(state.full_schema, state.section_index, sectionNumber);
    
    const updated: WebFormState = {
      ...state,
      schema: sectionSchema,
      current_section: sectionNumber,
    };
    
    this.save(updated);
    
    return updated;
  }
  
  /**
   * Phase 3: Mark current section as complete
   */
  static completeSection(state: WebFormState, sectionNumber: number): WebFormState {
    const completedSections = state.completed_sections || new Set<number>();
    
    const updated: WebFormState = {
      ...state,
      completed_sections: new Set([...completedSections, sectionNumber]),
    };
    
    this.save(updated);
    
    return updated;
  }
  
  /**
   * Phase 3: Get spoken name map (accumulated across completed sections)
   */
  static getSpokenNameMap(state: WebFormState): Map<string, string> {
    const map = new Map<string, string>();
    
    if (!state.full_schema || !state.section_index || !state.completed_sections) {
      return map;
    }
    
    // Include current section + completed sections
    const sectionsToInclude = new Set([
      ...state.completed_sections,
      state.current_section || 1,
    ]);
    
    for (const sectionNum of sectionsToInclude) {
      const section = state.section_index.sections.find(s => s.section_number === sectionNum);
      if (!section) continue;
      
      for (const fieldIdx of section.field_indices) {
        const field = state.full_schema.fields[fieldIdx];
        if (!field) continue;
        
        // Add spoken_name
        if (field.spoken_name) {
          map.set(field.spoken_name.toLowerCase(), field.id);
        }
        
        // Add spoken_aliases
        const aliases = (field as any).spoken_aliases;
        if (Array.isArray(aliases)) {
          for (const alias of aliases) {
            map.set(alias.toLowerCase(), field.id);
          }
        }
      }
    }
    
    return map;
  }
  
  /**
   * Phase 3: Get section label by number
   */
  static getSectionLabel(state: WebFormState, sectionNumber: number): string | null {
    if (!state.section_index) return null;
    const section = state.section_index.sections.find(s => s.section_number === sectionNumber);
    return section?.section_label || null;
  }
  
  /**
   * Phase 3: Find section number by label (case-insensitive)
   */
  static findSectionByLabel(state: WebFormState, label: string): number | null {
    if (!state.section_index) return null;
    const normalized = label.toLowerCase().trim();
    const section = state.section_index.sections.find(
      s => s.section_label.toLowerCase() === normalized
    );
    return section?.section_number || null;
  }
  
  /**
   * Phase 3: Get field count for current section
   */
  static getSectionFieldCount(state: WebFormState): { filled: number; total: number } {
    if (!state.section_index || !state.current_section) {
      return { filled: 0, total: state.schema.fields.length };
    }
    
    const section = state.section_index.sections.find(s => s.section_number === state.current_section);
    if (!section) {
      return { filled: 0, total: state.schema.fields.length };
    }
    
    const filled = state.schema.fields.filter((field) => {
      const currentValue = state.current_values[field.id];
      return currentValue && currentValue.value !== null && currentValue.value !== "";
    }).length;
    
    return { filled, total: section.field_count };
  }
}
