// TypeScript types for PDF schema (matching form_models.py)

export interface FormSchema {
  source: 'pdf';
  form_metadata: FormMetadata;
  parts: FormPart[];
  sections: FormSection[];
  fields: FormField[];
  extraction_notes?: any;
}

export interface FormMetadata {
  title: string;
  form_number: string;
  edition_date?: string;
  total_widgets: number;
  total_fields: number;
  version: string;
  language: string;
  extraction_date?: string;
  extraction_method?: string;
  // Version metadata recovered at extraction (bd polyglot-pdf-s4dp.2). Mirrors the
  // backend FormMetadata fields; kept on the editor type so a load -> edit -> save
  // round-trip does not strip them.
  omb_number?: string;
  expiration_date?: string;
  agency?: string;
  // 0-1 confidence in the auto-extracted version (high for a specific Edition/Rev
  // pattern, low for a generic year/OMB fallback, 0 when version is "unknown").
  version_confidence?: number;
}

export interface FormPart {
  id: string;
  label: string;
  order: number;
  section_ids: string[];
}

export interface FormSection {
  id: string;
  label: string;
  order: number;
  fields: string[];
}

export interface FormField {
  id: string;
  name: string;
  type: FieldType;
  section_id?: string;
  pdf_field_name: string;
  consolidated_widgets?: string[];
  label?: string;
  read_only: boolean;
  required: boolean;
  multiline?: boolean;
  is_comb?: boolean;
  hidden?: boolean;
  max_length?: number;
  spoken_name?: string;
  help?: FieldHelp;
  validation?: ValidationRules;
  options?: FieldOption[];
  show_if?: ConditionalDisplay;
  controls_fields?: ConditionalControl[];
  conditional_logic?: any;
  conditional_behavior?: any;
  copy_to?: string[];
  pdf_position?: PDFPosition;
  question_number?: string;
}

export type FieldType =
  | 'text'
  | 'textarea'
  | 'date'
  | 'number'
  | 'tel'
  | 'email'
  | 'select'
  | 'radio'
  | 'checkbox'
  | 'signature'
  | 'table';

export interface FieldHelp {
  instructions?: string;
  format_hint?: string;
}

export interface ValidationRules {
  pattern?: string;
  format_preset?: string;
  min_length?: number;
  max_length?: number;
}

export interface FieldOption {
  label: string;
  value: string;
  // Original PDF widget backing this option. Set when a consolidated options[]
  // field is built by merging separate radio/checkbox fields (bd
  // polyglot-pdf-s4dp.1) -- mirrors backend FieldOption.pdf_field_name
  // (backend/models/form_models.py) and the runtime FieldOption.
  pdf_field_name?: string;
  // Optional backend-side option metadata, kept so a load -> edit -> save
  // round-trip does not strip them (backend FieldOption.spoken_label /
  // label_translations).
  spoken_label?: string;
  label_translations?: Record<string, string>;
  // The field type of the separate widget this option was merged FROM (bd
  // polyglot-pdf-s4dp.1). Recorded at merge time so un-merge can restore each
  // source field's original type (radio vs checkbox) instead of guessing --
  // without it, un-grouping a merged radio would come back as checkbox. The
  // backend/runtime ignore this extra option key.
  source_type?: FieldType;
}

export interface ConditionalDisplay {
  field: string;
  operator: ConditionalOperator;
  value?: any;
}

export type ConditionalOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'greater_than'
  | 'less_than'
  | 'is_checked'
  | 'is_empty'
  | 'is_not_empty'
  | 'in'
  | 'not_in';

// A single conditional-control rule. controls_fields is an ARRAY of these on a
// field -- matching the real schema data (e.g. schemas/i-90/i-90_schema.json:488),
// the runtime contract (frontend/src/schema-forms/types/schema.ts
// ConditionalControl), and backend ConditionalControl
// (backend/models/form_models.py). The previous single-object shape with a
// `when_value` key did NOT match any real data, so validateSchema's
// controlled-id reference check silently did nothing on real form kits
// (Codex review, bd polyglot-pdf-y61i).
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

// The action keys of ConditionalControl (the string[] target lists only --
// excludes operator/value). Editing UI iterates over these.
export type ControlActionKey =
  | 'shows'
  | 'hides'
  | 'unlocks'
  | 'locks'
  | 'makes_required'
  | 'makes_optional';

export interface PDFPosition {
  page: number;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}

// UI-specific types

export interface FieldStatus {
  isComplete: boolean;
  needsReview: boolean;
  errors: string[];
}

export interface ValidationError {
  field_id: string;
  message: string;
  type: 'error' | 'warning';
}

export interface FormConfig {
  name: string;
  pdfPath: string;
  schemaPath: string;
}
