/**
 * SelectField Component - Renders select dropdown fields
 */

import type { FormField } from "../../types/schema";
import { unwrapToString } from "../../utils/fieldValue";

export interface SelectFieldProps {
  field: FormField;
  value: any;
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: string | null;
  disabled?: boolean;
  confirmed?: boolean; // AI voice confirmation status
}

export function SelectField({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
  confirmed = false,
}: SelectFieldProps) {
  // Fallback: if select field has no options, render as text field
  if (!field.options || field.options.length === 0) {
    console.warn(`[SelectField] Field ${field.id} has no options - rendering as text input instead`);

    // Bug Fix: Unwrap FieldValue objects in fallback case too
    const displayValue = unwrapToString(value);

    return (
      <div className={`form-field ${confirmed ? 'form-field--confirmed' : ''}`}>
        <label htmlFor={field.id} className="form-field__label">
          {field.name}
          {field.validation?.required && <span className="form-field__required">*</span>}
          {confirmed && (
            <span className="form-field__confirmed-badge" title="Confirmed by AI assistant">
              ✓
            </span>
          )}
        </label>
        <input
          type="text"
          id={field.id}
          name={field.id}
          value={displayValue}
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

  // Bug Fix: Unwrap FieldValue objects to get primitive value
  const currentValue = unwrapToString(value);

  const handleChange = (newValue: string) => {
    onChange(newValue);
  };

  return (
    <div className={`form-field ${confirmed ? 'form-field--confirmed' : ''}`}>
      <label htmlFor={field.id} className="form-field__label">
        {field.name}
        {field.validation?.required && <span className="form-field__required">*</span>}
        {confirmed && (
          <span className="form-field__confirmed-badge" title="Confirmed by AI assistant">
            ✓
          </span>
        )}
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
