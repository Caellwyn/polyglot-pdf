import React from 'react';
import type {
  FormField,
  FieldType,
  FormSchema,
  ConditionalControl,
  ConditionalOperator,
  ControlActionKey,
} from '../types/schema';
import { canUngroup } from '../utils/fieldGrouping';

interface FieldEditorProps {
  field: FormField | null;
  schema: FormSchema;
  onUpdateField: (field: FormField) => void;
  // Un-merge a consolidated options[] field back into separate per-widget fields
  // (bd polyglot-pdf-s4dp.1). Optional so the editor still renders without it.
  onUnmergeField?: (fieldId: string) => void;
}

const FIELD_TYPES: FieldType[] = [
  'text',
  'textarea',
  'date',
  'number',
  'tel',
  'email',
  'select',
  'radio',
  'checkbox',
  'signature',
];

// Operators offered in the editor dropdowns. `in`/`not_in` are valid in the
// schema/type but need an ARRAY value; both editors here write `value` from a
// plain text (scalar) input, so offering them would save a string the runtime
// never matches. They are intentionally excluded until a list-value editor
// exists (bd polyglot-pdf-jplx); existing data using them still loads and
// validates -- only authoring is restricted.
const CONDITIONAL_OPERATORS: ConditionalOperator[] = [
  'equals',
  'not_equals',
  'contains',
  'greater_than',
  'less_than',
  'is_checked',
  'is_empty',
  'is_not_empty',
];

// Operator options to render for a dropdown currently set to `current`. We don't
// OFFER in/not_in for fresh authoring (no array-value editor, bd jplx), but an
// existing rule already using them must still display its own operator -- else
// the select falls back to its first option and merely touching it silently
// rewrites a valid rule. So include `current` if it's outside the authoring set.
function operatorOptionsFor(current: ConditionalOperator): ConditionalOperator[] {
  return CONDITIONAL_OPERATORS.includes(current)
    ? CONDITIONAL_OPERATORS
    : [...CONDITIONAL_OPERATORS, current];
}

// `in`/`not_in` take an ARRAY value. The editors here only have a scalar (text)
// value input, so a rule using these operators is shown READ-ONLY: editing the
// operator or value through a scalar control would silently flatten the array to
// a string and break the runtime membership check. Authoring these is gated on a
// real list-value editor (bd polyglot-pdf-jplx).
const ARRAY_VALUED_OPERATORS: ConditionalOperator[] = ['in', 'not_in'];
function isArrayValuedOperator(op: ConditionalOperator): boolean {
  return ARRAY_VALUED_OPERATORS.includes(op);
}

// The action kinds a controls_fields entry can apply to its target fields.
// `key` matches the ConditionalControl array property; mirrors backend
// ConditionalControl (backend/models/form_models.py).
const CONTROL_ACTIONS: { key: ControlActionKey; label: string }[] = [
  { key: 'shows', label: 'Shows' },
  { key: 'hides', label: 'Hides' },
  { key: 'unlocks', label: 'Unlocks' },
  { key: 'locks', label: 'Locks' },
  { key: 'makes_required', label: 'Makes required' },
  { key: 'makes_optional', label: 'Makes optional' },
];

export const FieldEditor: React.FC<FieldEditorProps> = ({
  field,
  schema,
  onUpdateField,
  onUnmergeField,
}) => {
  if (!field) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400">
        <div className="text-center">
          <svg
            className="w-16 h-16 mx-auto mb-4 text-gray-300"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <p>Select a field to edit</p>
        </div>
      </div>
    );
  }

  const updateField = (updates: Partial<FormField>) => {
    onUpdateField({ ...field, ...updates });
  };

  // --- controls_fields helpers (list of trigger-side conditional controls) --- //
  const controls = field.controls_fields || [];

  const updateControls = (next: ConditionalControl[]) => {
    // Drop the key entirely when empty so the exported schema stays clean.
    updateField({ controls_fields: next.length > 0 ? next : undefined });
  };

  const updateControlAt = (idx: number, updates: Partial<ConditionalControl>) => {
    updateControls(controls.map((c, i) => (i === idx ? { ...c, ...updates } : c)));
  };

  // Toggle a target field id within one action array of one control.
  const toggleControlTarget = (
    idx: number,
    action: ControlActionKey,
    fieldId: string,
  ) => {
    const current = controls[idx][action] || [];
    const next = current.includes(fieldId)
      ? current.filter(id => id !== fieldId)
      : [...current, fieldId];
    // Drop the action key when its list goes empty (keeps the shape minimal).
    const updates: Partial<ConditionalControl> = {
      [action]: next.length > 0 ? next : undefined,
    };
    updateControlAt(idx, updates);
  };

  return (
    <div className="h-full overflow-auto custom-scrollbar">
      <div className="p-4 space-y-6">
        {/* Header */}
        <div className="border-b border-gray-200 pb-4">
          <h3 className="text-lg font-semibold text-gray-900">{field.id}</h3>
          <p className="text-sm text-gray-500 font-mono">{field.pdf_field_name}</p>
        </div>

        {/* Basic Properties */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">Basic Properties</h4>

          {/* Field Type */}
          <div>
            <label className="label">Field Type</label>
            <select
              className="input"
              value={field.type}
              onChange={(e) => updateField({ type: e.target.value as FieldType })}
            >
              {FIELD_TYPES.map(type => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>

          {/* Spoken Name */}
          <div>
            <label className="label">Spoken Name</label>
            <input
              type="text"
              className="input"
              value={field.spoken_name || ''}
              onChange={(e) => updateField({ spoken_name: e.target.value })}
              placeholder="e.g., alien registration number"
            />
            <p className="text-xs text-gray-500 mt-1">
              User-friendly name for voice AI
            </p>
          </div>

          {/* Section */}
          <div>
            <label className="label">Section</label>
            <select
              className="input"
              value={field.section_id || ''}
              onChange={(e) => updateField({ section_id: e.target.value || undefined })}
            >
              <option value="">No section</option>
              {schema.sections.map(section => (
                <option key={section.id} value={section.id}>
                  {section.label}
                </option>
              ))}
            </select>
          </div>

          {/* Checkboxes */}
          <div className="space-y-2">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={field.required}
                onChange={(e) => updateField({ required: e.target.checked })}
                className="rounded"
              />
              <span className="text-sm text-gray-700">Required</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={field.read_only}
                onChange={(e) => updateField({ read_only: e.target.checked })}
                className="rounded"
              />
              <span className="text-sm text-gray-700">Read Only</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={field.hidden || false}
                onChange={(e) => updateField({ hidden: e.target.checked })}
                className="rounded"
              />
              <span className="text-sm text-gray-700">Hidden</span>
            </label>
          </div>
        </div>

        {/* Help Text */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">Help & Guidance</h4>

          <div>
            <label className="label">Instructions</label>
            <textarea
              className="input"
              rows={3}
              value={field.help?.instructions || ''}
              onChange={(e) =>
                updateField({
                  help: { ...field.help, instructions: e.target.value },
                })
              }
              placeholder="Instructions for filling out this field..."
            />
          </div>

          <div>
            <label className="label">Format Hint</label>
            <input
              type="text"
              className="input"
              value={field.help?.format_hint || ''}
              onChange={(e) =>
                updateField({
                  help: { ...field.help, format_hint: e.target.value },
                })
              }
              placeholder="e.g., 7-9 digits, MM/DD/YYYY"
            />
          </div>
        </div>

        {/* Validation */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">Validation</h4>

          <div>
            <label className="label">Format Preset</label>
            <input
              type="text"
              className="input"
              value={field.validation?.format_preset || ''}
              onChange={(e) =>
                updateField({
                  validation: { ...field.validation, format_preset: e.target.value },
                })
              }
              placeholder="e.g., a_number, ssn, email"
            />
          </div>

          <div>
            <label className="label">Pattern (Regex)</label>
            <input
              type="text"
              className="input font-mono text-sm"
              value={field.validation?.pattern || ''}
              onChange={(e) =>
                updateField({
                  validation: { ...field.validation, pattern: e.target.value },
                })
              }
              placeholder="e.g., ^\d{7,9}$"
            />
          </div>

          {field.type === 'text' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Min Length</label>
                <input
                  type="number"
                  className="input"
                  value={field.validation?.min_length || ''}
                  onChange={(e) =>
                    updateField({
                      validation: {
                        ...field.validation,
                        min_length: e.target.value ? parseInt(e.target.value) : undefined,
                      },
                    })
                  }
                />
              </div>
              <div>
                <label className="label">Max Length</label>
                <input
                  type="number"
                  className="input"
                  value={field.max_length || field.validation?.max_length || ''}
                  onChange={(e) => {
                    const val = e.target.value ? parseInt(e.target.value) : undefined;
                    updateField({
                      max_length: val,
                      validation: { ...field.validation, max_length: val },
                    });
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Conditional Logic */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">
            Conditional Logic
            <span className="text-xs text-gray-500 ml-2">(Show If)</span>
          </h4>

          {field.show_if ? (
            <div className="space-y-3 p-3 bg-gray-50 rounded-md">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-700">Show this field when:</span>
                <button
                  className="btn-sm btn-secondary"
                  onClick={() => updateField({ show_if: undefined })}
                >
                  Remove
                </button>
              </div>

              {isArrayValuedOperator(field.show_if.operator) && (
                <p className="text-xs text-amber-600">
                  This condition uses the "{field.show_if.operator.replace(/_/g, ' ')}"
                  operator (a list value) and is read-only here until a list-value
                  editor exists. Remove and re-add it to change it.
                </p>
              )}

              <div>
                <label className="label">Trigger Field</label>
                <select
                  className="input"
                  value={field.show_if.field}
                  disabled={isArrayValuedOperator(field.show_if.operator)}
                  onChange={(e) =>
                    updateField({
                      show_if: { ...field.show_if!, field: e.target.value },
                    })
                  }
                >
                  <option value="">Select field...</option>
                  {schema.fields.map(f => (
                    <option key={f.id} value={f.id}>
                      {f.spoken_name || f.id}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">Operator</label>
                <select
                  className="input"
                  value={field.show_if.operator}
                  disabled={isArrayValuedOperator(field.show_if.operator)}
                  onChange={(e) =>
                    updateField({
                      show_if: { ...field.show_if!, operator: e.target.value as any },
                    })
                  }
                >
                  {operatorOptionsFor(field.show_if.operator).map(op => (
                    <option key={op} value={op}>
                      {op.replace(/_/g, ' ')}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">Value</label>
                <input
                  type="text"
                  className="input"
                  value={
                    Array.isArray(field.show_if.value)
                      ? field.show_if.value.join(', ')
                      : field.show_if.value ?? ''
                  }
                  disabled={isArrayValuedOperator(field.show_if.operator)}
                  onChange={(e) =>
                    updateField({
                      show_if: { ...field.show_if!, value: e.target.value },
                    })
                  }
                  placeholder="Expected value"
                />
              </div>
            </div>
          ) : (
            <button
              className="btn btn-secondary w-full"
              onClick={() =>
                updateField({
                  show_if: {
                    field: '',
                    operator: 'equals',
                    value: '',
                  },
                })
              }
            >
              + Add Conditional Logic
            </button>
          )}
        </div>

        {/* Controls Fields (trigger-side: this field's value affects others) */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">
            Controls Fields
            <span className="text-xs text-gray-500 ml-2">
              (this field's value affects others)
            </span>
          </h4>

          {controls.length > 0 && (
            <div className="space-y-4">
              {controls.map((control, idx) => (
                <div key={idx} className="space-y-3 p-3 bg-gray-50 rounded-md">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-700">When this field:</span>
                    <button
                      className="btn-sm btn-secondary"
                      onClick={() =>
                        updateControls(controls.filter((_, i) => i !== idx))
                      }
                    >
                      Remove
                    </button>
                  </div>

                  {(() => {
                    // A rule using an array-valued operator (in/not_in) is shown
                    // read-only: the scalar editors here can't safely edit it
                    // without flattening the array (bd jplx for a real editor).
                    const locked = isArrayValuedOperator(control.operator);
                    return (
                  <>
                  {locked && (
                    <p className="text-xs text-amber-600">
                      This rule uses the "{control.operator.replace(/_/g, ' ')}"
                      operator (a list value) and is read-only here until a
                      list-value editor exists. Remove and re-add the control to
                      change it.
                    </p>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">Operator</label>
                      <select
                        className="input"
                        value={control.operator}
                        disabled={locked}
                        onChange={(e) =>
                          updateControlAt(idx, {
                            operator: e.target.value as ConditionalOperator,
                          })
                        }
                      >
                        {operatorOptionsFor(control.operator).map(op => (
                          <option key={op} value={op}>
                            {op.replace(/_/g, ' ')}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="label">Value</label>
                      <input
                        type="text"
                        className="input"
                        // value can be scalar or (for in/not_in) an array; show
                        // arrays comma-joined. Array-valued rules are read-only
                        // (see `locked`) so editing can't flatten the array (bd jplx).
                        value={
                          Array.isArray(control.value)
                            ? control.value.join(', ')
                            : control.value == null
                            ? ''
                            : String(control.value)
                        }
                        disabled={locked}
                        onChange={(e) =>
                          updateControlAt(idx, { value: e.target.value })
                        }
                        placeholder="Trigger value"
                      />
                    </div>
                  </div>

                  {/* Per-action target-field pickers */}
                  <div className="space-y-3">
                    {CONTROL_ACTIONS.map(action => {
                      const selected =
                        control[action.key] || [];
                      // Include selected-but-missing ids so a stale target can be
                      // unchecked in place (it would otherwise never render).
                      const presentIds = new Set(schema.fields.map(f => f.id));
                      const missingSelected = selected.filter(id => !presentIds.has(id));
                      return (
                        <div key={action.key}>
                          <label className="label">
                            {action.label}
                            {selected.length > 0 && (
                              <span className="text-xs text-gray-400 ml-1">
                                ({selected.length})
                              </span>
                            )}
                          </label>
                          <div className="max-h-32 overflow-auto border border-gray-200 rounded-md bg-white p-1 space-y-1">
                            {schema.fields
                              .filter(f => f.id !== field.id)
                              .map(f => (
                                <label
                                  key={f.id}
                                  className="flex items-center gap-2 px-1 text-xs text-gray-700 hover:bg-gray-50 rounded cursor-pointer"
                                >
                                  <input
                                    type="checkbox"
                                    className="rounded"
                                    checked={selected.includes(f.id)}
                                    disabled={locked}
                                    onChange={() =>
                                      toggleControlTarget(idx, action.key, f.id)
                                    }
                                  />
                                  <span className="truncate">
                                    {f.spoken_name || f.id}
                                  </span>
                                </label>
                              ))}
                            {/* Stale (missing) targets: shown so they can be removed. */}
                            {missingSelected.map(id => (
                              <label
                                key={id}
                                className="flex items-center gap-2 px-1 text-xs text-red-600 hover:bg-gray-50 rounded cursor-pointer"
                              >
                                <input
                                  type="checkbox"
                                  className="rounded"
                                  checked={true}
                                  disabled={locked}
                                  onChange={() =>
                                    toggleControlTarget(idx, action.key, id)
                                  }
                                />
                                <span className="truncate">{id} (missing)</span>
                              </label>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  </>
                    );
                  })()}
                </div>
              ))}
            </div>
          )}

          <button
            className="btn btn-secondary w-full"
            onClick={() =>
              updateControls([
                ...controls,
                { operator: 'equals', value: '' },
              ])
            }
          >
            + Add Control
          </button>
        </div>

        {/* Field Options (for select/radio) */}
        {(field.type === 'select' || field.type === 'radio') && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-gray-900">Options</h4>
              {/* Un-group: split a consolidated options[] field back into one
                  field per widget (bd polyglot-pdf-s4dp.1). Only shown for a
                  field whose options each carry a pdf_field_name. */}
              {onUnmergeField && canUngroup(field) && (
                <button
                  className="btn-sm btn-secondary"
                  onClick={() => onUnmergeField(field.id)}
                  title="Split this consolidated field back into separate per-widget fields"
                >
                  Ungroup
                </button>
              )}
            </div>

            {field.options && field.options.length > 0 ? (
              <div className="space-y-2">
                {field.options.map((option, idx) => (
                  <div key={idx} className="flex gap-2">
                    <input
                      type="text"
                      className="input flex-1"
                      value={option.label}
                      onChange={(e) => {
                        const newOptions = [...(field.options || [])];
                        newOptions[idx] = { ...option, label: e.target.value };
                        updateField({ options: newOptions });
                      }}
                      placeholder="Option label"
                    />
                    <button
                      className="btn-sm btn-secondary"
                      onClick={() => {
                        const newOptions = (field.options || []).filter((_, i) => i !== idx);
                        updateField({ options: newOptions });
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  className="btn btn-secondary w-full text-sm"
                  onClick={() => {
                    const newOptions = [...(field.options || []), { label: '', value: '' }];
                    updateField({ options: newOptions });
                  }}
                >
                  + Add Option
                </button>
              </div>
            ) : (
              <button
                className="btn btn-secondary w-full"
                onClick={() => updateField({ options: [{ label: '', value: '' }] })}
              >
                + Add Options
              </button>
            )}
          </div>
        )}

        {/* Debug Info */}
        <details className="text-xs">
          <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
            Advanced / Debug
          </summary>
          <pre className="mt-2 p-2 bg-gray-100 rounded overflow-auto text-xs">
            {JSON.stringify(field, null, 2)}
          </pre>
        </details>
      </div>
    </div>
  );
};
