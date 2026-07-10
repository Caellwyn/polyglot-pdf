/**
 * CheckboxField Component - Renders checkbox fields (single or multi)
 */

import type { FormField } from "../../types/schema";
import { unwrapFieldValue, unwrapToBoolean } from "../../utils/fieldValue";

export interface CheckboxFieldProps {
  field: FormField;
  value: any;
  onChange: (value: boolean | string[]) => void;
  onBlur?: () => void;
  error?: string | null;
  disabled?: boolean;
  confirmed?: boolean; // AI voice confirmation status
  // Dynamic required state from isFieldRequired (bd eaof); falls back to the
  // field's static validation.required when omitted.
  required?: boolean;
}

export function CheckboxField({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
  confirmed = false,
  required,
}: CheckboxFieldProps) {
  // Single checkbox (no options)
  if (!field.options) {
    // Bug Fix: Unwrap FieldValue objects for boolean fields
    const isChecked = unwrapToBoolean(value);

    const handleChange = (checked: boolean) => {
      console.log(`[CheckboxField] ${field.id} changed to:`, checked);
      onChange(checked);
      if (onBlur) onBlur();
    };

    return (
      <div className={`form-field ${confirmed ? 'form-field--confirmed' : ''}`}>
        <label className="form-field__checkbox-label">
          <input
            type="checkbox"
            id={field.id}
            name={field.id}
            checked={isChecked}
            onChange={(e) => handleChange(e.target.checked)}
            disabled={disabled}
            className="form-field__checkbox-input"
          />
          <span className="form-field__checkbox-text">
            {field.name}
            {(required ?? field.validation?.required) && <span className="form-field__required">*</span>}
            {confirmed && (
              <span className="form-field__confirmed-badge" title="Confirmed by AI assistant">
                ✓
              </span>
            )}
          </span>
        </label>

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

  // Multi-checkbox group
  // Bug Fix: Unwrap FieldValue if needed, then ensure it's an array
  const unwrappedValue = unwrapFieldValue(value);
  const selectedValues = Array.isArray(unwrappedValue) ? unwrappedValue : [];

  const handleToggle = (optionValue: string) => {
    const newValues = selectedValues.includes(optionValue)
      ? selectedValues.filter((v) => v !== optionValue)
      : [...selectedValues, optionValue];

    console.log(`[CheckboxField] ${field.id} changed to:`, newValues);
    onChange(newValues);
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

        <div className="form-field__checkbox-group">
          {field.options.map((option) => (
            <label key={option.value} className="form-field__checkbox-label">
              <input
                type="checkbox"
                name={`${field.id}[]`}
                value={option.value}
                checked={selectedValues.includes(option.value)}
                onChange={() => handleToggle(option.value)}
                disabled={disabled}
                className="form-field__checkbox-input"
              />
              <span className="form-field__checkbox-text">{option.label}</span>
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
