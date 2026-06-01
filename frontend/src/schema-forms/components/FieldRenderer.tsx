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
  confirmed?: boolean; // Field confirmation status from AI voice
}

export function FieldRenderer({
  field,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
  allFieldValues = {},
  confirmed = false,
}: FieldRendererProps) {
  // Check if field should be shown based on conditional logic
  const isShown = shouldShowField(field, allFieldValues);

  if (!isShown) {
    return null; // Hide field
  }

  // Check if field should be unlocked when shown conditionally.
  // Checks both the canonical key (conditional_behavior) and the legacy alias
  // (conditional_logic) still emitted by generated form-kit schemas (e.g. i-90).
  const shouldUnlock =
    field.conditional_behavior?.unlock_method === "flip_readonly_bit" ||
    field.conditional_logic?.unlock_method === "flip_readonly_bit";

  // Debug conditional unlocking
  if (field.read_only && shouldUnlock) {
    console.log(`[FieldRenderer] 🔓 Unlocking field ${field.id}:`, {
      read_only: field.read_only,
      shouldUnlock,
      show_if: field.show_if,
      triggerField: field.show_if?.field,
      triggerValue: field.show_if?.field ? allFieldValues[field.show_if.field] : undefined,
      expectedValue: field.show_if?.value
    });
  }

  // Override disabled state for fields that unlock when shown
  // When a field has unlock behavior and is shown (condition met), it should be editable
  const isDisabled = shouldUnlock ? disabled : (disabled || field.read_only);

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
          disabled={isDisabled}
          confirmed={confirmed}
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
          disabled={isDisabled}
          confirmed={confirmed}
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
          disabled={isDisabled}
          confirmed={confirmed}
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
          disabled={isDisabled}
          confirmed={confirmed}
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
          disabled={isDisabled}
          confirmed={confirmed}
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
          disabled={isDisabled}
          confirmed={confirmed}
        />
      );

    case "number":
      // Number fields render as a plain text input. TextField only special-cases
      // email/tel for its HTML input type; everything else (incl. this) is type="text".
      return (
        <TextField
          field={{ ...field, type: "text" }}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          error={error}
          disabled={isDisabled}
          confirmed={confirmed}
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
