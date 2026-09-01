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
import { normalizeToComposite } from "../utils/normalizeToComposite";

export interface FieldRendererProps {
  field: FormField;
  value: any;
  onChange: (value: any) => void;
  onBlur?: (fieldId: string) => void;
  // The user put the cursor in this field (bd polyglot-pdf-a08po). Moves the
  // next-field search origin only -- it never makes the model speak.
  onFocus?: (fieldId: string) => void;
  error?: string | null;
  disabled?: boolean;
  allFieldValues?: Record<string, any>; // For conditional logic
  confirmed?: boolean; // Field confirmation status from AI voice
  // Dynamic required state from isFieldRequired (bd eaof); falls back to the
  // field's static validation.required when omitted.
  required?: boolean;
}

export function FieldRenderer({
  field,
  value,
  onChange,
  onBlur,
  onFocus,
  error,
  disabled = false,
  allFieldValues = {},
  confirmed = false,
  required,
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

  // Debug conditional unlocking. show_if may be a legacy single condition OR
  // a v2 composite group (bd h76m.8) -- log its atoms with current values.
  if (field.read_only && shouldUnlock) {
    const group = normalizeToComposite(field.show_if);
    const atoms = group
      ? [...(group.all_of ?? []), ...(group.any_of ?? []), ...(group.none_of ?? [])]
      : [];
    console.log(`[FieldRenderer] [unlock] Unlocking field ${field.id}:`, {
      read_only: field.read_only,
      shouldUnlock,
      show_if: field.show_if,
      conditions: atoms.map((atom) => ({
        triggerField: atom.field,
        triggerValue: allFieldValues[atom.field],
        operator: atom.operator,
        expectedValue: atom.value,
      })),
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

  const handleFocus = () => {
    if (onFocus) {
      onFocus(field.id);
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
          onFocus={handleFocus}
          error={error}
          disabled={isDisabled}
          confirmed={confirmed}
          required={required}
        />
      );

    case "textarea":
      return (
        <TextAreaField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          onFocus={handleFocus}
          error={error}
          disabled={isDisabled}
          confirmed={confirmed}
          required={required}
        />
      );

    case "radio":
      return (
        <RadioField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          onFocus={handleFocus}
          error={error}
          disabled={isDisabled}
          confirmed={confirmed}
          required={required}
        />
      );

    case "checkbox":
    case "checkbox_group":
      // Both the v2 multi-select group (checkbox_group) and a standalone/legacy
      // options-bearing checkbox render through CheckboxField (it branches on
      // options[] internally). Without the checkbox_group case a migrated group
      // field (i-90 race, W-7-2 doc type) falls to the "Unknown field type"
      // default and is unfillable (Codex PR #346).
      return (
        <CheckboxField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          onFocus={handleFocus}
          error={error}
          disabled={isDisabled}
          confirmed={confirmed}
          required={required}
        />
      );

    case "date":
      return (
        <DateField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          onFocus={handleFocus}
          error={error}
          disabled={isDisabled}
          confirmed={confirmed}
          required={required}
        />
      );

    case "select":
      return (
        <SelectField
          field={field}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          onFocus={handleFocus}
          error={error}
          disabled={isDisabled}
          confirmed={confirmed}
          required={required}
        />
      );

    case "number":
      // Number fields render as a plain text input. TextField's own inputType
      // is now unconditionally "text" for every field it renders (bd
      // polyglot-pdf-md20o), so this {...field, type: "text"} rewrite is
      // redundant for the HTML input type specifically -- it is passed only
      // to TextField's own props, not written back to the field in state, so
      // callers that still read the ORIGINAL field.type (e.g. validation.ts)
      // are unaffected either way.
      return (
        <TextField
          field={{ ...field, type: "text" }}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          onFocus={handleFocus}
          error={error}
          disabled={isDisabled}
          confirmed={confirmed}
          required={required}
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
