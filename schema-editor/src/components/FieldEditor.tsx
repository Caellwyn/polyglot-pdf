import React from 'react';
import type { FormField, FieldType, FormSchema } from '../types/schema';

interface FieldEditorProps {
  field: FormField | null;
  schema: FormSchema;
  onUpdateField: (field: FormField) => void;
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

const CONDITIONAL_OPERATORS = [
  'equals',
  'not_equals',
  'contains',
  'is_checked',
  'is_empty',
  'is_not_empty',
];

export const FieldEditor: React.FC<FieldEditorProps> = ({
  field,
  schema,
  onUpdateField,
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

              <div>
                <label className="label">Trigger Field</label>
                <select
                  className="input"
                  value={field.show_if.field}
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
                  onChange={(e) =>
                    updateField({
                      show_if: { ...field.show_if!, operator: e.target.value as any },
                    })
                  }
                >
                  {CONDITIONAL_OPERATORS.map(op => (
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
                  value={field.show_if.value || ''}
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

        {/* Field Options (for select/radio) */}
        {(field.type === 'select' || field.type === 'radio') && (
          <div className="space-y-4">
            <h4 className="text-sm font-semibold text-gray-900">Options</h4>

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
