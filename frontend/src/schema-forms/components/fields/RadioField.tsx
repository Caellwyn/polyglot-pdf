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
  confirmed?: boolean; // AI voice confirmation status
  // Dynamic required state from isFieldRequired (bd eaof); falls back to the
  // field's static validation.required when omitted.
  required?: boolean;
}

export function RadioField({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
  confirmed = false,
  required,
}: RadioFieldProps) {
  if (!field.options) {
    console.error(`[RadioField] Field ${field.id} has no options`);
    return null;
  }

  // Bug Fix: Unwrap FieldValue objects to get primitive value
  const currentValue = unwrapToString(value);

  const handleChange = (newValue: string) => {
    onChange(newValue);
    if (onBlur) onBlur();
  };

  return (
    <div className={`form-field ${confirmed ? 'form-field--confirmed' : ''}`}>
      <fieldset className="form-field__fieldset">
        <legend className="form-field__label">
          {field.name}
          {(required ?? field.validation?.required) && <span className="form-field__required">*</span>}
          {confirmed && (
            <span className="form-field__confirmed-badge" title="Confirmed by AI assistant">
              ✓
            </span>
          )}
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
