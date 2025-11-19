/**
 * DateField Component - Renders date input fields
 */

import type { FormField } from "../../types/schema";
import { unwrapToString } from "../../utils/fieldValue";

export interface DateFieldProps {
  field: FormField;
  value: any; // Accept any type (primitive or FieldValue wrapper)
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: string | null;
  disabled?: boolean;
  confirmed?: boolean; // AI voice confirmation status
}

export function DateField({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
  confirmed = false,
}: DateFieldProps) {
  // Determine input type based on date precision
  const getInputType = (): string => {
    if (field.date_precision === "month_year") return "month";
    return "date"; // Default to full date
  };

  // Bug Fix: Unwrap FieldValue objects to get primitive value
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

      {field.help?.inline && (
        <span className="form-field__help-inline">{field.help.inline}</span>
      )}

      <input
        type={getInputType()}
        id={field.id}
        name={field.id}
        value={displayValue}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        min={field.min_date}
        max={field.max_date}
        disabled={disabled}
        className={`form-field__input form-field__input--date ${
          error ? "form-field__input--error" : ""
        }`}
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
