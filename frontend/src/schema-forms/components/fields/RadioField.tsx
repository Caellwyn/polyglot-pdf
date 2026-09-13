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

export function RadioField({
  field,
  value,
  onChange,
  onBlur,
  onFocus,
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
          {/* The FIRST option carries id={field.id}: one id per FIELD, never per
              option (duplicates are invalid HTML and break label targeting). Without
              it a radio group has no id at all, so getElementById and the
              Enter->verify gesture cannot reach it -- 30 of 323 fields across the
              shipped kits (bd polyglot-pdf-96um6, cross-surface finding). */}
          {field.options.map((option, idx) => (
            <label key={option.value} className="form-field__radio-label">
              <input
                type="radio"
                id={idx === 0 ? field.id : undefined}
                name={field.id}
                value={option.value}
                checked={currentValue === option.value}
                onChange={(e) => handleChange(e.target.value)}
                onFocus={onFocus}
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
