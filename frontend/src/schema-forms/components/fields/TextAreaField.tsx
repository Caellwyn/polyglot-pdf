/**
 * TextAreaField Component - Renders textarea fields
 */

import type { FormField } from "../../types/schema";
import { unwrapToString } from "../../utils/fieldValue";

export interface TextAreaFieldProps {
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

export function TextAreaField({
  field,
  value,
  onChange,
  onBlur,
  onFocus,
  error,
  disabled = false,
  confirmed = false,
  required,
}: TextAreaFieldProps) {
  // Determine rows based on textarea size
  const getRows = (): number => {
    if (field.rows) return field.rows;

    switch (field.textarea_size) {
      case "small":
        return 2;
      case "medium":
        return 5;
      case "large":
        return 10;
      case "xlarge":
        return 20;
      default:
        return 5;
    }
  };

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

      <textarea
        id={field.id}
        name={field.id}
        value={displayValue}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        onFocus={onFocus}
        placeholder={field.placeholder}
        maxLength={field.max_length || field.validation?.max_length}
        rows={getRows()}
        disabled={disabled}
        className={`form-field__textarea ${error ? "form-field__textarea--error" : ""}`}
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
