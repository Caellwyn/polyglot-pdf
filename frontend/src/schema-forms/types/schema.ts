/**
 * TypeScript types for FormSchema (mirrors backend/models/form_models.py)
 *
 * These types are generated from the Pydantic models to ensure
 * frontend-backend type consistency.
 *
 * @version 1.1.0 (matches form_models.py)
 */

// ============================================================================
// Enums and Type Definitions
// ============================================================================

export type FormSource = "web" | "pdf";

export type DatePrecision = "full" | "month_year" | "year_only";

export type DateFormat = "mm/dd/yyyy" | "Mo/Yr" | "yyyy" | "YYYY-MM-DD";

export type FieldType =
  | "text"
  | "textarea"
  | "date"
  | "number"
  | "tel"
  | "email"
  | "select"
  | "radio"
  | "checkbox"
  | "signature"
  | "address_group"
  | "table";

export type SignatureMethod = "draw" | "upload" | "type";

export type TextareaSize = "small" | "medium" | "large" | "xlarge";

export type ConditionalOperator =
  | "equals"
  | "not_equals"
  | "contains"
  | "greater_than"
  | "less_than"
  | "is_checked"
  | "is_empty"
  | "is_not_empty"
  | "in"
  | "not_in";

export type GroupKind = "checkbox" | "radio";

export type SessionStatus = "in_progress" | "completed" | "exported" | "expired";

// ============================================================================
// Supporting Interfaces
// ============================================================================

export interface FormMetadata {
  // Common to all forms
  title: string;
  description?: string;
  version: string;
  language: string; // ISO 639-1 code (e.g., 'en', 'es', 'zh')

  // Web-specific
  url?: string;

  // PDF-specific
  form_number?: string; // e.g., "I-589"
  edition_date?: string; // e.g., "01/20/25"
  omb_number?: string; // e.g., "1615-0067"
  expiration_date?: string; // e.g., "2027-09-30"
  page_count?: number;
  instructions_url?: string;
  agency?: string; // e.g., "U.S. Citizenship and Immigration Services"
}

export interface PDFPosition {
  page: number; // 1-indexed
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ValidationRules {
  required?: boolean;
  min_length?: number;
  max_length?: number;
  min?: number; // For numeric fields
  max?: number; // For numeric fields
  pattern?: string; // Regex pattern
  custom_error?: string;
  digits_only?: boolean; // Only allow numeric digits (0-9)
  date_constraint?: "past_only" | "future_only" | "within_5_years";
  format_preset?: "ssn" | "a_number" | "phone" | "email" | "zip" | "uscis_account";
}

export interface ConditionalDisplay {
  field: string; // Field ID to check
  operator: ConditionalOperator;
  value: string | number | boolean | Array<string | number | boolean>;
}

export interface ConditionalControl {
  operator: ConditionalOperator;
  value: string | number | boolean | Array<string | number | boolean>;
  shows?: string[];
  hides?: string[];
  unlocks?: string[];
  locks?: string[];
  makes_required?: string[];
  makes_optional?: string[];
}

export interface ConditionalBehavior {
  unlock_method?: "flip_readonly_bit" | "set_property";
  show_method?: "remove_hidden_flag" | "set_property";
  pdf_field_flag_change?: Record<string, any>;
}

export interface FieldHelp {
  inline?: string; // Inline hint text like "(if any)"
  tooltip?: string; // Hover tooltip
  instructions?: string; // Longer instructions below field
  format_hint?: string; // Short input-format hint, e.g. "7-9 digits" / "YYYY-MM-DD" (rendered into the SI; bd polyglot-pdf-jnjj.23)
  warning?: string; // Legal warning or important note
  example?: string; // Example value
  legal_reference?: string; // Legal reference (e.g., "INA 241(b)(3)")
}

export interface FieldOption {
  value: string;
  label: string;
  spoken_label?: string;
  label_translations?: Record<string, string>;
  pdf_field_name?: string;
}

export interface TableColumn {
  id: string;
  label: string;
  type: FieldType;
  width?: number;
  validation?: ValidationRules;
  help?: FieldHelp;
  pdf_field_name?: string;
  options?: FieldOption[];
}

export interface MultiEntryConfig {
  min_entries: number;
  max_entries?: number;
  initial_rows: number;
  add_button_label?: string;
  remove_button_label?: string;
  overflow_instruction?: string;
  overflow_to_supplement?: string;
}

export interface AddressFields {
  street: string;
  apt?: string;
  city: string;
  state: string;
  zip: string;
  province?: string;
  postal_code?: string;
  country?: string;
}

// ============================================================================
// Core Field Interface
// ============================================================================

export interface FormField {
  // Identity
  id: string;
  name: string;
  spoken_name: string;
  spoken_aliases?: string[];

  // Type and behavior
  type: FieldType;
  validation?: ValidationRules;
  read_only?: boolean;
  hidden?: boolean;

  // Organization
  section_id: string;
  section_label?: string;
  group_id?: string;
  group_label?: string;
  group_kind?: GroupKind;

  // Conditional display
  show_if?: ConditionalDisplay;
  controls_fields?: ConditionalControl[];
  conditional_behavior?: ConditionalBehavior;
  /** Legacy alias for conditional_behavior; still emitted by generated form-kit schemas. */
  conditional_logic?: ConditionalBehavior;
  conditional_fields?: string[]; // DEPRECATED: Use controls_fields

  // Help and guidance
  help?: FieldHelp;
  placeholder?: string;
  description?: string;

  // PDF-specific
  pdf_position?: PDFPosition;
  pdf_field_name?: string;

  // Type-specific properties - Date fields
  date_precision?: DatePrecision;
  format?: DateFormat;
  min_date?: string;
  max_date?: string;

  // Type-specific properties - Text/Textarea fields
  max_length?: number;
  textarea_size?: TextareaSize;
  rows?: number;

  // Type-specific properties - Numeric fields
  min?: number;
  max?: number;
  step?: number;

  // Type-specific properties - Select/Radio/Checkbox fields
  options?: FieldOption[];

  // Type-specific properties - Signature fields
  signature_method?: SignatureMethod;
  signature_box_style?: string;

  // Type-specific properties - Address group fields
  address_fields?: AddressFields;

  // Type-specific properties - Table fields
  columns?: TableColumn[];
  multi_entry?: MultiEntryConfig;

  // Auto-fill logic
  auto_fill_na?: boolean;
  copy_to?: string[]; // Auto-copy this field's value to these target field IDs

  // Supplement overflow
  overflow_to_supplement?: string;
}

// ============================================================================
// Section and Part Interfaces
// ============================================================================

export interface FormSection {
  id: string;
  label: string;
  description?: string;
  order: number;
  fields: string[]; // Field IDs
  page_number?: number;
  page_numbers?: number[];
  required?: boolean;
  show_if?: ConditionalDisplay;
}

export interface FormPart {
  id: string;
  label: string;
  description?: string;
  order: number;
  section_ids: string[];
  required?: boolean;
}

export interface FormSupplement {
  id: string;
  name: string;
  purpose: string;
  trigger_condition?: string;
  fields: string[];
  page_number?: number;
  supplement_type?: string;
}

export interface ExtractionInfo {
  extracted_at: string;
  extraction_confidence: number; // 0-1
  extractor_version: string;
  manual_review_required: boolean;
  manual_review_completed?: boolean;
  approved_by?: string;
  approved_at?: string;
}

// ============================================================================
// Complete Form Schema Interface
// ============================================================================

export interface FormSchema {
  source: FormSource;
  form_metadata: FormMetadata;
  sections: FormSection[];
  fields: FormField[];
  parts?: FormPart[];
  supplements?: FormSupplement[];
  extraction_info?: ExtractionInfo;
  legal_warnings?: string[];
}

// ============================================================================
// Session Interfaces
// ============================================================================

export interface FormSession {
  session_id: string;
  form_schema_id: string;
  form_version: string;
  created_at: string;
  updated_at: string;
  expires_at: string;

  // Form data
  field_values: Record<string, any>;
  current_section: string;
  completed_sections: string[];

  // Metadata
  language: string;
  user_id?: string;

  // Status
  status: SessionStatus;
}

// ============================================================================
// WebSocket Integration Types
// ============================================================================

/**
 * Field value wrapper for WebSocket compatibility
 * Used to track AI-filled vs user-filled fields and confirmation status
 */
/**
 * Field availability state
 * - available: Field can be filled (no dependencies blocking it)
 * - locked: Dependencies not met (e.g., parent field needs to be filled first)
 * - hidden: Conditional logic says field should be hidden
 */
export type FieldAvailability = 'available' | 'locked' | 'hidden';

export interface FieldValue {
  value: string | boolean | null;
  confirmed?: boolean;  // User has confirmed this field value (explicit or implicit)
  confirmedAt?: string;  // ISO timestamp when field was confirmed
  confirmationMethod?: 'ai_voice' | 'manual_edit';  // How the field was confirmed
  lastModified?: number;  // Timestamp for conflict resolution

  // Field state (Nov 22, 2025 - Dependency tracking)
  availability?: FieldAvailability;  // Whether field is available, locked, or hidden
  lockedReason?: string;  // Human-readable reason if locked (e.g., "Complete 'name changed' field first")
}
