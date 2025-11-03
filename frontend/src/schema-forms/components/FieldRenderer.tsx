/**
 * FieldRenderer - Factory component that renders the appropriate field type
 *
 * Routes to specific field components based on FormField.type
 */

import type { FormField } from "../types/schema";
import { TextField } from "./fields/TextField";
import { TextAreaField } from "./fields/TextAreaField";
import { RadioField } from "./fields/RadioField";
import { CheckboxField } from "./fields/CheckboxField";
import { DateField } from "./fields/DateField";
import { SelectField } from "./fields/SelectField";
import { validateField, shouldShowField } from "../utils/validation";

export interface FieldRendererProps {
  field: FormField;
  value: any;
  onChange: (value: any) => void;
  onBlur?: (fieldId: string) => void;
  error?: string | null;
  disabled?: boolean;
  allFieldValues?: Record<string, any>; // For conditional logic
}

export function FieldRenderer({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
  allFieldValues = {},
}: FieldRendererProps) {
  // Check if field should be shown based on conditional logic
  if (!shouldShowField(field, allFieldValues)) {
    return null; // Hide field
  }

  const handleBlur = () => {
    if (onBlur) {
      onBlur(field.id);
    }
  };

  // Route to appropriate field component based on type
  switch (field.type) {
    case "text":
    case "email":
    case "tel":
      return (
        <TextField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          error={error}
          disabled={disabled}
        />
      );

    case "textarea":
      return (
        <TextAreaField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          error={error}
          disabled={disabled}
        />
      );

    case "radio":
      return (
        <RadioField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          error={error}
          disabled={disabled}
        />
      );

    case "checkbox":
      return (
        <CheckboxField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          error={error}
          disabled={disabled}
        />
      );

    case "date":
      return (
        <DateField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          error={error}
          disabled={disabled}
        />
      );

    case "select":
      return (
        <SelectField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          error={error}
          disabled={disabled}
        />
      );

    case "number":
      // Number field uses TextField with type="number" (HTML5)
      return (
        <TextField
          field={{ ...field, type: "text" }}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          error={error}
          disabled={disabled}
        />
      );

    // Not yet implemented field types
    case "signature":
    case "address_group":
    case "table":
      return (
        <div className="form-field form-field--not-implemented">
          <label className="form-field__label">{field.name}</label>
          <p className="form-field__warning">
            Field type "{field.type}" is not yet implemented. This will be added in a future
            update.
          </p>
        </div>
      );

    default:
      console.warn(`[FieldRenderer] Unknown field type: ${field.type}`);
      return (
        <div className="form-field form-field--unknown">
          <label className="form-field__label">{field.name}</label>
          <p className="form-field__error">Unknown field type: {field.type}</p>
        </div>
      );
  }
}
