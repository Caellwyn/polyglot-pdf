/**
 * DateField Component - Renders date input fields
 */

import type { FormField } from "../../types/schema";
import { unwrapToString } from "../../utils/fieldValue";

export interface DateFieldProps {
  field: FormField;
  value: any; // Accept any type (primitive or FieldValue wrapper)
  onChange: (value: string) => void;
  onBlur?: () => void;
  // Cursor entered this field (bd polyglot-pdf-a08po) -- moves the next-field
  // search origin; never makes the model speak.
  onFocus?: () => void;
  error?: string | null;
  disabled?: boolean;
  confirmed?: boolean; // AI voice confirmation status
  // Dynamic required state from isFieldRequired (bd eaof); falls back to the
  // field's static validation.required when omitted.
  required?: boolean;
}

export function DateField({
  field,
  value,
  onChange,
  onBlur,
  onFocus,
  error,
  disabled = false,
  confirmed = false,
  required,
}: DateFieldProps) {
  // ALWAYS a plain text input -- never <input type="date"> (bd polyglot-pdf-md20o).
  //
  // These are PDF AcroForm fields, not web-form fields: the KIT SCHEMA's
  // help.format_hint is the authority on a value's shape, and the PDF layer
  // writes the stored string VERBATIM (pdf_fill_routes.py never rewrites a
  // value). A native date input's `.value` is ALWAYS yyyy-mm-dd per the HTML
  // spec, so it physically cannot hold a W-7 date's declared MM/DD/YYYY -- it
  // silently coerced every date to ISO, which then reached storage and the PDF.
  //
  // That is not cosmetic. An ISO string in a comb-8 date box renders as a
  // plausible-looking WRONG date (the '1990-03-14' -> month=19 class documented
  // at pdf_fill_routes.py:200-236), i.e. a wrong date of birth on a filed form.
  // It also fed the voice model: it reads the stored value back, sees ISO, and
  // learns the wrong format.
  //
  // Same reasoning as FieldRenderer's `case "number"`, which already renders
  // number fields as text for the identical coercion reason.
  //
  // KNOWN PRIORITY-CHAIN GAP (bd polyglot-pdf-vs15o), deliberately left as a
  // documented gap rather than a behavior change: the BACKEND's
  // _resolve_date_format (backend/utils/field_validator.py) reads a field's
  // flat `format` key FIRST, ahead of help.format_hint. This frontend never
  // reads `field.format` at all -- a date field declaring only a flat
  // `format` (no help.format_hint) gets no placeholder/layout affordance here
  // while the backend still validates against that flat format. Across all 8
  // shipped date fields (form-kits/i-90, /w7, /f1040), NONE sets the flat
  // `format` key, so this specific priority-inversion is latent, not a live
  // bug -- 2 of those 8 (f1040's fld_deceased_date, fld_spouse_deceased_date)
  // set NEITHER key and get no placeholder on either surface, a separate,
  // pre-existing gap this bead does not address. Fixing the priority chain
  // to match the backend is out of scope for this bead and left for whoever
  // changes DateField's placeholder logic next.
  const placeholder = field.help?.format_hint || field.placeholder;

  // Bug Fix: Unwrap FieldValue objects to get primitive value
  const displayValue = unwrapToString(value);

  return (
    <div className={`form-field ${confirmed ? 'form-field--confirmed' : ''}`}>
      <label htmlFor={field.id} className="form-field__label">
        {field.name}
        {(required ?? field.validation?.required) && <span className="form-field__required">*</span>}
        {confirmed && (
          <span className="form-field__confirmed-badge" title="Confirmed by AI assistant">
            ✓
          </span>
        )}
      </label>

      {field.help?.inline && (
        <span className="form-field__help-inline">{field.help.inline}</span>
      )}

      <input
        type="text"
        // NOT inputMode="numeric": a correct value carries "/" separators, and
        // a numeric keypad buries or omits them on mobile.
        id={field.id}
        name={field.id}
        value={displayValue}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        onFocus={onFocus}
        placeholder={placeholder}
        // NO maxLength. field.max_length on a date is the PDF widget's COMB
        // CELL COUNT (W-7 dates are comb-8), not a text limit -- and
        // "MM/DD/YYYY" is 10 chars, so wiring it here would TRUNCATE a correct
        // date to "10/26/19", a wrong year on a filed form. Over-long values
        // are handled at render by clearing the comb flag (pdf_fill_routes.py),
        // which prints the date un-combed but CORRECT.
        //
        // NO min/max either: those are native date-input attributes and are
        // inert on a text input. min_date/max_date bounds are enforced by
        // validateDateValue, which reads them from the field directly.
        disabled={disabled}
        className={`form-field__input form-field__input--date ${
          error ? "form-field__input--error" : ""
        }`}
        aria-invalid={error ? "true" : "false"}
        aria-describedby={error ? `${field.id}-error` : undefined}
      />

      {field.help?.example && (
        <p className="form-field__example">Example: {field.help.example}</p>
      )}

      {error && (
        <p id={`${field.id}-error`} className="form-field__error" role="alert">
          {error}
        </p>
      )}

      {field.help?.warning && (
        <p className="form-field__warning">{field.help.warning}</p>
      )}
    </div>
  );
}
