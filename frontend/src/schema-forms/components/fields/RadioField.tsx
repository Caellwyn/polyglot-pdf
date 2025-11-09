/**
 * RadioField Component - Renders radio button groups
 */

import type { FormField } from "../../types/schema";
import { unwrapToString } from "../../utils/fieldValue";

export interface RadioFieldProps {
  field: FormField;
  value: any;
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

  // Bug Fix: Unwrap FieldValue objects to get primitive value
  const currentValue = unwrapToString(value);

  const handleChange = (newValue: string) => {
    console.log(`[RadioField] ${field.id} changed to:`, newValue, `(previous: ${currentValue})`);
    onChange(newValue);
    if (onBlur) onBlur();
  };

  // Debug: log what value we received and what we're comparing
  console.log(`[RadioField] ${field.id} RENDER - received value prop:`, JSON.stringify(value), `-> currentValue="${currentValue}"`);

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
                checked={currentValue === option.value}
                onChange={(e) => handleChange(e.target.value)}
                disabled={disabled}
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
