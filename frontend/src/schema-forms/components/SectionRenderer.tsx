/**
 * SectionRenderer - Renders a single section with all its fields
 */

import type { FormSection, FormField } from "../types/schema";
import { FieldRenderer } from "./FieldRenderer";
import { isFieldRequired, shouldShowField } from "../utils/validation";
import { unwrapFieldValue } from "../utils/fieldValue";

export interface SectionRendererProps {
  section: FormSection;
  fields: FormField[];
  fieldValues: Record<string, any>;
  validationErrors: Record<string, string>;
  onFieldChange: (fieldId: string, value: any) => void;
  onFieldBlur: (fieldId: string) => void;
  // 4dxt: force-skip a required-but-unanswered field. Optional so existing
  // callers/tests that do not wire skipping still render.
  onFieldSkip?: (fieldId: string) => void;
  disabled?: boolean;
}

// Whether a value counts as "empty" for the skip affordance (mirrors the
// isSectionValid empty check).
function isEmptyValue(raw: any): boolean {
  return (
    raw === null ||
    raw === undefined ||
    raw === "" ||
    (Array.isArray(raw) && raw.length === 0)
  );
}

export function SectionRenderer({
  section,
  fields,
  fieldValues,
  validationErrors,
  onFieldChange,
  onFieldBlur,
  onFieldSkip,
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
          const skipped = fieldValue?.skipped === true;

          // 4dxt: offer a "Skip" affordance only for a field that is currently
          // shown, currently required, still empty, and not already skipped -- the
          // exact case isSectionValid would otherwise block on. A skipped field
          // instead shows a distinct "needs follow-up" badge.
          const shown = !field.hidden && shouldShowField(field, fieldValues, fields);
          const required = shown && isFieldRequired(field, fieldValues, fields);
          const empty = isEmptyValue(unwrapFieldValue(fieldValue));
          const canSkip = !!onFieldSkip && required && empty && !skipped && !disabled;

          return (
            <div key={field.id} className="section__field">
              <FieldRenderer
                field={field}
                value={fieldValue}
                onChange={(value) => onFieldChange(field.id, value)}
                onBlur={onFieldBlur}
                error={validationErrors[field.id] || null}
                disabled={disabled}
                allFieldValues={fieldValues}
                confirmed={confirmed}
              />
              {skipped && (
                <p className="form-field__skipped" role="status">
                  <span className="form-field__skipped-badge">Skipped</span>
                  <span className="form-field__skipped-note">
                    marked as needs follow-up -- this required question was left
                    unanswered on purpose. Enter a value above to answer it.
                  </span>
                </p>
              )}
              {canSkip && (
                <button
                  type="button"
                  className="form-field__skip-button"
                  onClick={() => onFieldSkip!(field.id)}
                  title="Mark this required question as intentionally unanswered (e.g. to ask a translator later). You can still answer it afterward."
                >
                  Skip for now
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
