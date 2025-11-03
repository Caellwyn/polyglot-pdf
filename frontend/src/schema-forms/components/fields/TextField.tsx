/**
 * TextField Component - Renders text/email/tel input fields
 */

import type { FormField } from "../../types/schema";

export interface TextFieldProps {
  field: FormField;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: string | null;
  disabled?: boolean;
}

export function TextField({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
}: TextFieldProps) {
  const inputType = field.type === "email" ? "email" : field.type === "tel" ? "tel" : "text";

  return (
    <div className="form-field">
      <label htmlFor={field.id} className="form-field__label">
        {field.name}
        {field.validation?.required && <span className="form-field__required">*</span>}
      </label>

      {field.help?.inline && (
        <span className="form-field__help-inline">{field.help.inline}</span>
      )}

      <input
        type={inputType}
        id={field.id}
        name={field.id}
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={field.placeholder}
        maxLength={field.max_length || field.validation?.max_length}
        disabled={disabled || field.read_only}
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
