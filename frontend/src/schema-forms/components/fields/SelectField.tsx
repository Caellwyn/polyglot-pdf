/**
 * SelectField Component - Renders select dropdown fields
 */

import type { FormField } from "../../types/schema";

export interface SelectFieldProps {
  field: FormField;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: string | null;
  disabled?: boolean;
}

export function SelectField({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
}: SelectFieldProps) {
  if (!field.options) {
    console.error(`[SelectField] Field ${field.id} has no options`);
    return null;
  }

  return (
    <div className="form-field">
      <label htmlFor={field.id} className="form-field__label">
        {field.name}
        {field.validation?.required && <span className="form-field__required">*</span>}
      </label>

      {field.help?.inline && (
        <span className="form-field__help-inline">{field.help.inline}</span>
      )}

      <select
        id={field.id}
        name={field.id}
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        disabled={disabled || field.read_only}
        className={`form-field__select ${error ? "form-field__select--error" : ""}`}
        aria-invalid={error ? "true" : "false"}
        aria-describedby={error ? `${field.id}-error` : undefined}
      >
        <option value="">-- Please select --</option>
        {field.options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      {field.help?.instructions && (
        <p className="form-field__instructions">{field.help.instructions}</p>
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
