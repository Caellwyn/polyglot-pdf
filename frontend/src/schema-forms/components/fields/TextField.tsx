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

export function TextField({
  field,
  value,
  onChange,
  onBlur,
  onFocus,
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
  // The suppression is gated on the hint being an actual LAYOUT LITERAL -- a
  // string that IS the value's shape, so its length is the value's length.
  //
  // Gating on raw hint length instead is wrong and was caught in review: most
  // shipped hints are PROSE, not literals ("5 digits", "Alphanumeric postal
  // code", "9 digits (XXX-XX-XXXX)"), and prose is nearly always longer than
  // the cap it describes. Across the shipped kits that mistake fired on 26
  // fields when only 2 are dates -- it would have uncapped SSN, ZIP, phone and
  // ITIN inputs, none of which carry a validation.max_length fallback, on a
  // download path that runs no validation at all.
  //
  // A layout literal is made only of format placeholder characters and
  // separators (MM/DD/YYYY, YYYY-MM-DD, MM/YYYY). Anything containing a letter
  // that is not a placeholder token, or any digit, is prose.
  const combCap = field.max_length;
  const declaredFormat = field.help?.format_hint;
  const isLayoutLiteral =
    declaredFormat !== undefined && /^[MDYmdy]+([/\-.][MDYmdy]+)+$/.test(declaredFormat.trim());
  const capWouldTruncateDeclaredFormat =
    combCap !== undefined &&
    isLayoutLiteral &&
    declaredFormat!.trim().length > combCap;
  // `??` not `||`: a cap of 0 is falsy but MEANINGFUL (a zero-width widget),
  // and `||` would silently swap it for an unrelated validation.max_length or
  // drop it entirely.
  const effectiveMaxLength = capWouldTruncateDeclaredFormat
    ? field.validation?.max_length
    : combCap ?? field.validation?.max_length;

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
        onFocus={onFocus}
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
