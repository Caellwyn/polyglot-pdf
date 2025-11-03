/**
 * RadioField Component - Renders radio button groups
 */

import type { FormField } from "../../types/schema";

export interface RadioFieldProps {
  field: FormField;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: string | null;
  disabled?: boolean;
}

export function RadioField({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
}: RadioFieldProps) {
  if (!field.options) {
    console.error(`[RadioField] Field ${field.id} has no options`);
    return null;
  }

  return (
    <div className="form-field">
      <fieldset className="form-field__fieldset">
        <legend className="form-field__label">
          {field.name}
          {field.validation?.required && <span className="form-field__required">*</span>}
        </legend>

        {field.help?.inline && (
          <span className="form-field__help-inline">{field.help.inline}</span>
        )}

        <div className="form-field__radio-group">
          {field.options.map((option) => (
            <label key={option.value} className="form-field__radio-label">
              <input
                type="radio"
                name={field.id}
                value={option.value}
                checked={value === option.value}
                onChange={(e) => {
                  onChange(e.target.value);
                  if (onBlur) onBlur();
                }}
                disabled={disabled || field.read_only}
                className="form-field__radio-input"
              />
              <span className="form-field__radio-text">{option.label}</span>
            </label>
          ))}
        </div>

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
      </fieldset>
    </div>
  );
}
