/**
 * SectionRenderer - Renders a single section with all its fields
 */

import type { FormSection, FormField } from "../types/schema";
import { FieldRenderer } from "./FieldRenderer";

export interface SectionRendererProps {
  section: FormSection;
  fields: FormField[];
  fieldValues: Record<string, any>;
  validationErrors: Record<string, string>;
  onFieldChange: (fieldId: string, value: any) => void;
  onFieldBlur: (fieldId: string) => void;
  disabled?: boolean;
}

export function SectionRenderer({
  section,
  fields,
  fieldValues,
  validationErrors,
  onFieldChange,
  onFieldBlur,
  disabled = false,
}: SectionRendererProps) {
  return (
    <div className="section" id={`section-${section.id}`}>
      <div className="section__header">
        <h2 className="section__title">{section.label}</h2>
        {section.description && <p className="section__description">{section.description}</p>}
      </div>

      <div className="section__fields">
        {fields.map((field) => {
          const fieldValue = fieldValues[field.id];
          // Extract confirmation status from FieldValue object
          const confirmed = fieldValue?.confirmed === true;
          return (
            <FieldRenderer
              key={field.id}
              field={field}
              value={fieldValue}
              onChange={(value) => onFieldChange(field.id, value)}
              onBlur={onFieldBlur}
              error={validationErrors[field.id] || null}
              disabled={disabled}
              allFieldValues={fieldValues}
              confirmed={confirmed}
            />
          );
        })}
      </div>
    </div>
  );
}
