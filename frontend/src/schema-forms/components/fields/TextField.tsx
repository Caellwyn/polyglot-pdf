/**
 * TextField Component - Renders text/email/tel input fields
 */

import type { FormField } from "../../types/schema";
import { unwrapToString } from "../../utils/fieldValue";

export interface TextFieldProps {
  field: FormField;
  value: any; // Accept any type (primitive or FieldValue wrapper)
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: string | null;
  disabled?: boolean;
  confirmed?: boolean; // AI voice confirmation status
  // Dynamic required state from isFieldRequired (bd eaof); falls back to the
  // field's static validation.required when omitted.
  required?: boolean;
}

export function TextField({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
  confirmed = false,
  required,
}: TextFieldProps) {
  // ALWAYS "text" (bd polyglot-pdf-md20o). These are PDF AcroForm fields: the
  // kit schema's format_hint is the authority on a value's shape, not an HTML
  // input type's built-in behavior. type="email" applies the browser's own
  // validity check, which can reject a value the KIT considers valid, and the
  // w7 tel fields declare no layout constraint at all, so the browser's notion
  // would win by default. Matches FieldRenderer's `case "number"`, which
  // already downgrades to text for the same coercion reason.
  const inputType = "text";

  // Bug Fix: Unwrap FieldValue objects to get primitive value
  const displayValue = unwrapToString(value);

  // A field's top-level max_length is the PDF widget's COMB CELL COUNT, which
  // is NOT always a text limit (bd polyglot-pdf-md20o). W-7's date fields are
  // comb-8 while their declared format "MM/DD/YYYY" is 10 chars, so wiring the
  // cell count to the DOM maxLength TRUNCATES a correct value -- "10/26/1980"
  // becomes "10/26/19", a wrong year on a filed form, silently, as the user
  // types. Over-long values are handled at RENDER by clearing the comb flag
  // (pdf_fill_routes.py), which prints un-combed but CORRECT.
  //
  // So only enforce the cap when the field's own declared format can actually
  // fit inside it. A nested validation.max_length is a real author-set text
  // limit and is honored as-is.
  const combCap = field.max_length;
  const declaredFormat = field.help?.format_hint;
  const capWouldTruncateDeclaredFormat =
    combCap !== undefined &&
    declaredFormat !== undefined &&
    declaredFormat.length > combCap;
  const effectiveMaxLength = capWouldTruncateDeclaredFormat
    ? field.validation?.max_length
    : combCap || field.validation?.max_length;

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
        type={inputType}
        id={field.id}
        name={field.id}
        value={displayValue}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={field.placeholder}
        maxLength={effectiveMaxLength}
        disabled={disabled}
        className={`form-field__input ${error ? "form-field__input--error" : ""}`}
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
