/**
 * Polyglot PDF Form Schema - Type Definitions
 *
 * Unified schema supporting both web forms and PDF forms.
 * Designed to handle USCIS immigration forms with complex structures.
 *
 * @version 1.1.0
 * @date 2025-10-26
 *
 * Version 1.1.0 Enhancements:
 * - Added 'static_text' field type for informational content
 * - Extended ConditionalDisplay to support AND/OR logic for complex conditions
 * - Enhanced TableColumn with conditional display, options, and format support
 * - Changed FormSection.page_number to page_numbers array for multi-page sections
 * - Added FormPart interface for hierarchical form organization
 * - Added read_only, default_value, and overflow_to_supplement to FormField
 * - Added format_preset validation option for common formats (SSN, A-Number, etc.)
 * - Made FormSupplement fields optional for flexibility
 */

/**
 * Form source type - determines which additional metadata is required
 */
export type FormSource = 'web' | 'pdf';

/**
 * Date precision levels for different field requirements
 */
export type DatePrecision = 'full' | 'month_year' | 'year_only';

/**
 * Date format specifications
 */
export type DateFormat = 'mm/dd/yyyy' | 'Mo/Yr' | 'yyyy' | 'YYYY-MM-DD';

/**
 * Field types supported by the system
 */
export type FieldType =
  | 'text'           // Single-line text input
  | 'textarea'       // Multi-line text input
  | 'date'           // Date picker with format specification
  | 'number'         // Numeric input with optional min/max
  | 'tel'            // Phone number with format mask
  | 'email'          // Email with validation
  | 'select'         // Dropdown with options
  | 'radio'          // Radio button group
  | 'checkbox'       // Single checkbox or checkbox group
  | 'signature'      // Signature capture field
  | 'static_text'    // Read-only informational text (not user input)
  | 'address_group'  // Composite address field group
  | 'table';         // Repeating row structure

/**
 * Signature capture methods
 */
export type SignatureMethod = 'draw' | 'upload' | 'type';

/**
 * Textarea size presets
 */
export type TextareaSize = 'small' | 'medium' | 'large';

/**
 * Conditional operator types for show_if logic
 */
export type ConditionalOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'greater_than'
  | 'less_than'
  | 'is_checked'
  | 'is_empty';

/**
 * Form-level metadata
 */
export interface FormMetadata {
  // Common to all forms
  title: string;
  description?: string;
  version: string;
  language: string; // ISO 639-1 code (e.g., 'en', 'es', 'zh')

  // Web-specific
  url?: string;

  // PDF-specific
  form_number?: string;        // e.g., "I-589"
  edition_date?: string;        // e.g., "01/20/25"
  omb_number?: string;          // e.g., "1615-0067"
  expiration_date?: string;     // e.g., "2027-09-30"
  page_count?: number;          // Total pages in PDF
  instructions_url?: string;    // Link to separate instructions PDF
  agency?: string;              // e.g., "U.S. Citizenship and Immigration Services"
}

/**
 * PDF-specific positioning information
 */
export interface PDFPosition {
  page: number;           // Page number (1-indexed)
  x: number;              // X coordinate in points
  y: number;              // Y coordinate in points
  width: number;          // Width in points
  height: number;         // Height in points
}

/**
 * Common format presets for validation
 */
export type FormatPreset = 'ssn' | 'a_number' | 'zip' | 'phone' | 'email' | 'date' | 'uscis_account';

/**
 * Validation rules for a field
 */
export interface ValidationRules {
  required?: boolean;
  min_length?: number;
  max_length?: number;
  min?: number;           // For numeric fields
  max?: number;           // For numeric fields
  pattern?: string;       // Regex pattern
  format_preset?: FormatPreset;  // Predefined format validation
  custom_error?: string;  // Custom error message
}

/**
 * Conditional display logic
 * Supports both simple single-field conditions and complex AND/OR logic
 */
export interface ConditionalDisplay {
  // Simple condition (for single field check)
  field?: string;                    // Field ID to check
  operator?: ConditionalOperator;
  value?: string | number | boolean;

  // Complex conditions (for multiple field checks)
  condition?: 'AND' | 'OR';          // Logical operator for combining rules
  rules?: ConditionalDisplay[];      // Array of conditions to combine
}

/**
 * Field-level help and instruction text
 */
export interface FieldHelp {
  inline?: string;        // Inline hint text like "(if any)"
  tooltip?: string;       // Hover tooltip
  instructions?: string;  // Longer instructions below field
  warning?: string;       // Legal warning or important note
  example?: string;       // Example value
}

/**
 * Options for select, radio, and checkbox fields
 */
export interface FieldOption {
  value: string;
  label: string;
  spoken_label?: string;  // Alternative label for voice input
}

/**
 * Table column definition for repeating rows
 */
export interface TableColumn {
  id: string;
  label: string;
  type: FieldType;
  width?: number;                  // Percentage or pixels
  validation?: ValidationRules;
  help?: FieldHelp;

  // Conditional display for columns
  show_if?: ConditionalDisplay;    // Column appears based on other column values

  // Options for select/radio/checkbox columns
  options?: FieldOption[];

  // Format for date columns
  format?: DateFormat;

  // PDF mapping for this column's cells
  pdf_field_name?: string;
}

/**
 * Multi-entry configuration for tables and repeating fields
 */
export interface MultiEntryConfig {
  min_entries: number;         // Minimum required entries
  max_entries?: number;        // Maximum allowed (undefined = unlimited)
  initial_rows: number;        // How many rows to show initially
  add_button_label?: string;   // Label for "Add" button
  remove_button_label?: string; // Label for "Remove" button
  overflow_instruction?: string; // Instructions when max reached (e.g., "Use Supplement A")
}

/**
 * Address group sub-fields
 */
export interface AddressFields {
  street: string;          // Field ID for street address
  apt?: string;            // Field ID for apartment number
  city: string;            // Field ID for city
  state: string;           // Field ID for state
  zip: string;             // Field ID for ZIP code
  country?: string;        // Field ID for country (international addresses)
}

/**
 * Core field definition
 */
export interface FormField {
  // Identity
  id: string;                     // Unique field identifier
  name: string;                   // Display label
  spoken_name: string;            // Name for voice interaction
  spoken_aliases?: string[];      // Alternative names for voice input

  // Type and behavior
  type: FieldType;
  validation?: ValidationRules;

  // Organization
  section_id: string;             // Which section this belongs to
  section_label?: string;         // Section display name
  group_id?: string | null;       // Grouping within section (e.g., "full-name")
  group_label?: string | null;    // Group display name
  group_kind?: 'checkbox' | 'radio' | null; // Type of group if applicable

  // Conditional display
  show_if?: ConditionalDisplay;

  // Help and guidance
  help?: FieldHelp;
  placeholder?: string;
  description?: string;           // Field description

  // PDF-specific
  pdf_position?: PDFPosition;     // Position in original PDF
  pdf_field_name?: string;        // Original PDF field name

  // Behavior modifiers
  read_only?: boolean;            // Field cannot be edited (e.g., for government-only sections)
  default_value?: string;         // Default or pre-filled value
  overflow_to_supplement?: string; // ID of supplement to use for overflow content

  // Type-specific properties

  // Date fields
  date_precision?: DatePrecision;
  format?: DateFormat;
  min_date?: string;              // ISO date string
  max_date?: string;              // ISO date string

  // Text/Textarea fields
  max_length?: number;
  textarea_size?: TextareaSize;
  rows?: number;                  // Specific row count for textarea

  // Numeric fields
  min?: number;
  max?: number;
  step?: number;                  // Increment for number spinners

  // Select/Radio/Checkbox fields
  options?: FieldOption[];

  // Signature fields
  signature_method?: SignatureMethod;
  signature_box_style?: string;   // e.g., "bracketed" for I-589 Part D

  // Address group fields
  address_fields?: AddressFields;

  // Table fields
  columns?: TableColumn[];
  multi_entry?: MultiEntryConfig;
}

/**
 * Form section definition
 */
export interface FormSection {
  id: string;
  label: string;
  description?: string;
  order: number;              // Display order
  fields: string[];           // Field IDs in this section
  page_numbers?: number[];    // PDF page numbers (PDF only) - sections can span multiple pages
  required?: boolean;         // Can this section be skipped?
  show_if?: ConditionalDisplay;
}

/**
 * Supplement definition for overflow content
 */
export interface FormSupplement {
  id: string;                 // e.g., "supplement_a"
  label?: string;             // Alternative to name (for compatibility)
  name?: string;              // e.g., "Supplement A - Additional Children" (preferred)
  purpose?: string;           // What this supplement is for
  trigger_condition?: string; // When to use this supplement
  fields?: string[];          // Field IDs available in supplement
  page_number?: number;       // PDF page number
}

/**
 * Form part definition (optional organizational layer above sections)
 * Used for complex forms like I-589 that have major divisions
 */
export interface FormPart {
  id: string;                 // e.g., "part_a"
  label: string;              // e.g., "Part A: Information About Applicant"
  order: number;              // Display order
  section_ids: string[];      // Section IDs within this part
  description?: string;       // Optional description of this part
}

/**
 * Complete form schema
 */
export interface FormSchema {
  // Metadata
  source: FormSource;
  form_metadata: FormMetadata;

  // Structure
  parts?: FormPart[];         // Optional: High-level organizational structure
  sections: FormSection[];
  fields: FormField[];

  // Optional components
  supplements?: FormSupplement[];

  // Extraction metadata (for PDF forms)
  extraction_info?: {
    extracted_at: string;       // ISO timestamp
    extraction_confidence: number; // 0-1 score
    extractor_version: string;  // Version of extraction tool
    manual_review_required: boolean;
    manual_review_completed?: boolean;
    approved_by?: string;
    approved_at?: string;
  };
}

/**
 * Form session state (for saving/loading)
 */
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
  status: 'in_progress' | 'completed' | 'exported' | 'expired';
}

/**
 * WebSocket event for field updates
 */
export interface FieldUpdateEvent {
  event_type: 'field_update';
  session_id: string;
  field_id: string;
  value: any;
  timestamp: string;
}

/**
 * WebSocket event for section navigation
 */
export interface SectionNavigateEvent {
  event_type: 'section_navigate';
  session_id: string;
  from_section: string;
  to_section: string;
  timestamp: string;
}

/**
 * WebSocket event for validation error
 */
export interface ValidationErrorEvent {
  event_type: 'validation_error';
  session_id: string;
  field_id: string;
  error_message: string;
  timestamp: string;
}

/**
 * Tool response from Gemini function calls
 */
export interface ToolResponse {
  status: 'ok' | 'error';
  field?: string;
  message: string;
  data?: any;
}
