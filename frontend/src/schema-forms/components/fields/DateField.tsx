/**
 * DateField Component - Renders date input fields
 */

import type { FormField } from "../../types/schema";

export interface DateFieldProps {
  field: FormField;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: string | null;
  disabled?: boolean;
}

export function DateField({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
}: DateFieldProps) {
  // Determine input type based on date precision
  const getInputType = (): string => {
    if (field.date_precision === "month_year") return "month";
    return "date"; // Default to full date
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

      <input
        type={getInputType()}
        id={field.id}
        name={field.id}
        value={value || ""}
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
