/**
 * SelectField Component - Renders select dropdown fields
 */

import type { FormField } from "../../types/schema";

export interface SelectFieldProps {
  field: FormField;
  value: any;
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
  // Fallback: if select field has no options, render as text field
  if (!field.options || field.options.length === 0) {
    console.warn(`[SelectField] Field ${field.id} has no options - rendering as text input instead`);
    return (
      <div className="form-field">
        <label htmlFor={field.id} className="form-field__label">
          {field.name}
          {field.validation?.required && <span className="form-field__required">*</span>}
        </label>
        <input
          type="text"
          id={field.id}
          name={field.id}
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          disabled={disabled}
          className={`form-field__input ${error ? "form-field__input--error" : ""}`}
          placeholder={field.help?.format_hint || ""}
        />
        {field.help?.instructions && (
          <p className="form-field__instructions">{field.help.instructions}</p>
        )}
        {error && (
          <p id={`${field.id}-error`} className="form-field__error" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  // Normalize value to string (handle undefined/null)
  const currentValue = value !== null && value !== undefined ? String(value) : "";

  // Debug: Log value being rendered
  console.log(`[SelectField] ${field.id} rendering with value:`, {
    rawValue: value,
    currentValue,
    hasOptions: field.options && field.options.length > 0,
    optionCount: field.options?.length || 0
  });

  // Debug: Check if current value matches any option
  const matchingOption = field.options.find(opt => opt.value === currentValue);
  if (value && !matchingOption) {
    console.warn(`[SelectField] ${field.id} value "${currentValue}" doesn't match any option:`,
      field.options.map(o => o.value));
  }

  const handleChange = (newValue: string) => {
    console.log(`[SelectField] ${field.id} changed to:`, newValue);
    onChange(newValue);
  };

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
        value={currentValue}
        onChange={(e) => handleChange(e.target.value)}
        onBlur={onBlur}
        disabled={disabled}
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
