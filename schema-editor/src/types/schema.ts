// TypeScript types for PDF schema (matching form_models.py)

export interface FormSchema {
  source: 'pdf';
  form_metadata: FormMetadata;
  parts: FormPart[];
  sections: FormSection[];
  fields: FormField[];
  extraction_notes?: any;
  // Authoring provenance written by extraction/translation bakes (opaque to the
  // editor). Kept on the type so a load -> edit -> save round-trip visibly
  // preserves it: the backend linter re-emits the translation verify flags
  // stored at _bakeoff.authoring.option_translation.flags (bd polyglot-pdf-9djc),
  // so dropping this key would silently erase the human-review worklist.
  _bakeoff?: Record<string, any>;
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
  // Form-level guidance + whole-booklet reference floor (bd wsao.1). Mirrors the
  // backend FormMetadata fields; kept on the editor type so a load -> edit -> save
  // round-trip does not strip them. AI-facing only, never rendered.
  details?: string;
  booklet_text?: string;
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
  // Session-language translations of label (lowercase language-name keys) --
  // same convention as option label_translations (bd polyglot-pdf-tupu.2).
  // Kept on the editor type so a load -> edit -> save round-trip does not
  // strip them.
  label_translations?: Record<string, string>;
  order: number;
  fields: string[];
  // The backend only accepts the LEGACY single-atom shape on a section
  // (form_models.py FormSection.show_if, ~line 627) -- a section can never
  // carry the composite all_of/any_of/none_of shape. The editor never AUTHORS
  // a section show_if; this typing exists so the group mutations (merge /
  // ungroup / change-kind / retarget) can REWRITE a loaded kit's section
  // condition instead of stranding it when its referenced field's group kind
  // changes (bd polyglot-pdf-6b7z). Typed as the full union (not just
  // ConditionalDisplay) so a malformed/composite value from a hand-edited kit
  // is still representable; the rewrite helpers handle both shapes
  // defensively even though a backend-valid kit only ever carries a single
  // atom here.
  show_if?: FieldCondition;
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
  multiline?: boolean;
  is_comb?: boolean;
  hidden?: boolean;
  max_length?: number;
  spoken_name?: string;
  // Session-language translations of spoken_name, keyed by lowercase English
  // language name ("spanish", "chinese") -- same convention as option
  // label_translations (bd polyglot-pdf-tupu.1).
  spoken_name_translations?: Record<string, string>;
  help?: FieldHelp;
  validation?: ValidationRules;
  options?: FieldOption[];
  show_if?: FieldCondition;
  // v2 (bd h76m.8): condition under which this field becomes REQUIRED --
  // same shape and evaluator machinery as show_if.
  require_if?: FieldCondition;
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
  // v2 (bd h76m.3/h76m.9): ONE logical multi-select question whose options[]
  // carry per-box PDF identity; value shape is a list of option slugs.
  | 'checkbox_group'
  | 'signature'
  | 'table';

export interface FieldHelp {
  instructions?: string;
  // Verbatim official-booklet excerpts for this field (bd wsao.1). AI-guidance
  // only (voice guidance block + secretary catalog) -- never rendered to users.
  details?: string;
  format_hint?: string;
}

export interface ValidationRules {
  // Canonical required signal (mirrors backend ValidationRules.required, bd
  // polyglot-pdf-a1ql) -- every runtime consumer reads validation.required, never
  // a top-level field.required (bd polyglot-pdf-8n2s).
  required?: boolean;
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
  // The PDF 'on' state name that selects this option (v2, bd h76m.3): for a
  // shared-name radio group the kids share ONE field name and differ only by
  // this state. Mirrors backend FieldOption.pdf_on_value. The widget picker (bd
  // nivy) sets it from the dump's on_value so a picked box round-trips fillable.
  pdf_on_value?: string;
  // Optional backend-side option metadata, kept so a load -> edit -> save
  // round-trip does not strip them (backend FieldOption.spoken_label /
  // label_translations / pdf_position).
  spoken_label?: string;
  label_translations?: Record<string, string>;
  // This option's own widget rect (mirrors backend FieldOption.pdf_position,
  // bd polyglot-pdf-5f41; backfilled into the kit schemas from the AcroForm
  // dump). Round-trip contract: editor saves must not strip it.
  pdf_position?: PDFPosition;
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

// v2 composite condition (bd h76m.8): ONE level of all_of/any_of/none_of
// buckets of atomic conditions. Evaluators consume conditions ONLY through
// normalizeToComposite (which lifts the legacy single shape to a one-atom
// group). Mirrors frontend/src/schema-forms/types/schema.ts.
export interface CompositeConditionalDisplay {
  all_of?: ConditionalDisplay[];
  any_of?: ConditionalDisplay[];
  none_of?: ConditionalDisplay[];
}

// What a schema may carry on show_if / require_if: either wire dialect.
export type FieldCondition = ConditionalDisplay | CompositeConditionalDisplay;

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
  | 'not_in'
  // v2 group-membership operators (bd h76m.8): "option slug is (not) in the
  // checkbox_group trigger's selected set". Mirror backend ConditionalOperator.
  | 'includes'
  | 'not_includes';

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
  // Plain-language reasons a field is amber (needs review), so the UI can show
  // WHY instead of a bare status icon (bd polyglot-pdf-0x10.6).
  reviewReasons: string[];
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
