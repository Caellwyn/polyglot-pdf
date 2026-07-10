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
  const inputType = field.type === "email" ? "email" : field.type === "tel" ? "tel" : "text";

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
        type={inputType}
        id={field.id}
        name={field.id}
        value={displayValue}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={field.placeholder}
        maxLength={field.max_length || field.validation?.max_length}
        disabled={disabled}
        className={`form-field__input ${error ? "form-field__input--error" : ""}`}
        aria-invalid={error ? "true" : "false"}
        aria-describedby={error ? `${field.id}-error` : undefined}
      />

      {field.help?.instructions && (
        <p className="form-field__instructions">{field.help.instructions}</p>
      )}

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
