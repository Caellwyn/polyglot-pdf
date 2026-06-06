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
  controls_fields?: ControlsFields;
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
  | 'is_checked'
  | 'is_empty'
  | 'is_not_empty';

export interface ControlsFields {
  when_value: any;
  shows?: string[];
  unlocks?: string[];
  makes_required?: string[];
}

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
