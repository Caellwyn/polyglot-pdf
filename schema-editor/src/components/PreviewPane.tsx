// Interactive PREVIEW pane for the schema editor (bd polyglot-pdf-s4dp.4).
//
// The author can edit a form's logic but has no way to TEST it: are radios
// actually mutually exclusive? do checkboxes multi-select? does a show_if-gated
// field hide/show as its controlling field changes? A read-only PDF + JSON give
// no behavioral feedback. This pane renders the loaded schema as live, clickable
// inputs and exercises that behavior.
//
// COMPLETELY INDEPENDENT of the voice app (maintainer steer): it imports nothing
// from frontend/src/schema-forms (the WS/state/connection layer) -- only the
// editor's own types and a self-contained shouldShowField port
// (conditionalVisibility.ts). It owns its field-value state locally; there is no
// backend call, no WS, no SchemaFormStateManager. It is the seed of a potential
// standalone product.
//
// Scope (per the bead): interactive enough to test (a) radios mutually exclusive,
// (b) checkboxes multi-select, (c) show_if / controls_fields visibility as the
// controlling field changes. NOT full form validation/submission.

import { useMemo, useState } from 'react';
import type { FormField, FormSchema, FormSection } from '../types/schema';
import { shouldShowField } from '../utils/conditionalVisibility';

interface PreviewPaneProps {
  schema: FormSchema;
}

// Local preview value shapes (mirroring the runtime):
//   radio / select      -> selected option value (string)
//   checkbox WITH options (group) -> string[] of selected values (multi-select)
//   single checkbox (no options)  -> boolean
//   everything else               -> string
type PreviewValue = string | string[] | boolean | undefined;

// Section-ordered field list (falls back to schema.fields order for fields not in
// any section). Sections are the editor's navigation unit; preview mirrors them.
function orderedSections(schema: FormSchema): Array<{ section: FormSection | null; fields: FormField[] }> {
  const byId = new Map(schema.fields.map(f => [f.id, f]));
  const placed = new Set<string>();
  const groups: Array<{ section: FormSection | null; fields: FormField[] }> = [];

  const sortedSections = [...(schema.sections || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  for (const section of sortedSections) {
    const fields: FormField[] = [];
    for (const fid of section.fields || []) {
      const f = byId.get(fid);
      if (f && !placed.has(fid)) {
        fields.push(f);
        placed.add(fid);
      }
    }
    if (fields.length > 0) groups.push({ section, fields });
  }

  // Any field not referenced by a section (defensive) goes in a trailing group.
  const orphans = schema.fields.filter(f => !placed.has(f.id));
  if (orphans.length > 0) groups.push({ section: null, fields: orphans });

  return groups;
}

export default function PreviewPane({ schema }: PreviewPaneProps) {
  // The pane's OWN local value state -- no voice/WS/connection dependency.
  const [values, setValues] = useState<Record<string, PreviewValue>>({});

  const sections = useMemo(() => orderedSections(schema), [schema]);

  const setValue = (fieldId: string, value: PreviewValue) => {
    setValues(prev => ({ ...prev, [fieldId]: value }));
  };

  // Toggle one option in a checkbox group's selected-value array (multi-select).
  const toggleCheckboxOption = (field: FormField, optionValue: string) => {
    setValues(prev => {
      const current = prev[field.id];
      const arr = Array.isArray(current) ? current : [];
      const next = arr.includes(optionValue)
        ? arr.filter(v => v !== optionValue)
        : [...arr, optionValue];
      return { ...prev, [field.id]: next };
    });
  };

  const resetValues = () => setValues({});

  // Visible fields only (a show_if-gated field appears/disappears as values
  // change). schema.fields is the trigger-lookup list for the evaluator.
  const isVisible = (field: FormField) => shouldShowField(field, values, schema.fields);

  return (
    <div className="h-full overflow-auto custom-scrollbar bg-gray-50">
      <div className="p-4 space-y-6">
        <div className="flex items-center justify-between border-b border-gray-200 pb-3">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Interactive Preview</h3>
            <p className="text-xs text-gray-500">
              Click fields to test radio exclusivity, checkbox multi-select, and
              show/hide logic. Values are local to this preview.
            </p>
          </div>
          <button className="btn-sm btn-secondary" onClick={resetValues} title="Clear all preview values">
            Reset values
          </button>
        </div>

        {sections.map(({ section, fields }, si) => {
          const visibleFields = fields.filter(isVisible);
          if (visibleFields.length === 0) return null;
          return (
            <div key={section?.id ?? `__orphans_${si}`} className="panel p-4 space-y-4">
              {section && (
                <h4 className="text-sm font-semibold text-gray-900 border-b border-gray-100 pb-2">
                  {section.label || section.id}
                </h4>
              )}
              {visibleFields.map(field => (
                <PreviewField
                  key={field.id}
                  field={field}
                  value={values[field.id]}
                  onSetValue={v => setValue(field.id, v)}
                  onToggleOption={optValue => toggleCheckboxOption(field, optValue)}
                />
              ))}
            </div>
          );
        })}

        {sections.every(({ fields }) => fields.filter(isVisible).length === 0) && (
          <p className="text-sm text-gray-500 italic">No visible fields to preview.</p>
        )}
      </div>
    </div>
  );
}

interface PreviewFieldProps {
  field: FormField;
  value: PreviewValue;
  onSetValue: (value: PreviewValue) => void;
  onToggleOption: (optionValue: string) => void;
}

// Field types that render a SINGLE labelable control (so the field-level caption
// can be a real <label htmlFor>). Radio/checkbox GROUPS instead carry per-option
// labels, so their caption stays plain text and is not associated to one input.
function rendersSingleControl(field: FormField): boolean {
  const hasOptions = !!field.options && field.options.length > 0;
  if (field.type === 'radio') return false;
  if (field.type === 'checkbox') return !hasOptions; // lone checkbox is single
  if (field.type === 'signature' || field.type === 'table') return false;
  return true; // text/textarea/select/date/number/tel/email
}

function PreviewField({ field, value, onSetValue, onToggleOption }: PreviewFieldProps) {
  const label = field.label || field.spoken_name || field.name || field.id;
  const disabled = field.read_only;
  const single = rendersSingleControl(field);
  const inputId = single ? `preview-${field.id}` : undefined;

  const caption = (
    <>
      <span>{label}</span>
      {field.required && <span className="text-red-500" title="required">*</span>}
      {field.read_only && <span className="text-xs text-gray-400">(read-only)</span>}
    </>
  );

  return (
    <div>
      {single ? (
        <label className="label flex items-center gap-2" htmlFor={inputId}>{caption}</label>
      ) : (
        // group caption: plain text, since there is no single input to bind to.
        <div className="label flex items-center gap-2">{caption}</div>
      )}
      <PreviewInput
        field={field}
        value={value}
        disabled={disabled}
        inputId={inputId}
        onSetValue={onSetValue}
        onToggleOption={onToggleOption}
      />
      {field.help?.instructions && (
        <p className="text-xs text-gray-500 mt-1">{field.help.instructions}</p>
      )}
    </div>
  );
}

interface PreviewInputProps extends PreviewFieldProps {
  disabled: boolean;
  inputId?: string;
}

function PreviewInput({ field, value, disabled, inputId, onSetValue, onToggleOption }: PreviewInputProps) {
  const options = field.options || [];

  // RADIO (and a select-as-radio consolidated group): mutually exclusive -- a
  // single selected value. Clicking another option replaces the prior one.
  if (field.type === 'radio') {
    return (
      <div className="space-y-1">
        {options.length === 0 ? (
          <p className="text-xs text-gray-400 italic">No options defined.</p>
        ) : (
          options.map(opt => (
            <label key={opt.value} className="flex items-center gap-2 text-sm text-gray-800">
              <input
                type="radio"
                name={field.id}
                checked={value === opt.value}
                disabled={disabled}
                onChange={() => onSetValue(opt.value)}
              />
              <span>{opt.label || opt.value}</span>
            </label>
          ))
        )}
      </div>
    );
  }

  // CHECKBOX: a group (options[]) multi-selects into an array; a lone checkbox
  // (no options) is a single boolean.
  if (field.type === 'checkbox') {
    if (options.length > 0) {
      const selected = Array.isArray(value) ? value : [];
      return (
        <div className="space-y-1">
          {options.map(opt => (
            <label key={opt.value} className="flex items-center gap-2 text-sm text-gray-800">
              <input
                type="checkbox"
                checked={selected.includes(opt.value)}
                disabled={disabled}
                onChange={() => onToggleOption(opt.value)}
              />
              <span>{opt.label || opt.value}</span>
            </label>
          ))}
        </div>
      );
    }
    // The outer PreviewField caption (a <label htmlFor={inputId}>) already names
    // this field, so the lone checkbox renders just the input + a neutral "Yes"
    // affordance -- NOT the field label again (which would render it twice;
    // fresh-eyes finding 3).
    return (
      <div className="flex items-center gap-2 text-sm text-gray-800">
        <input
          id={inputId}
          type="checkbox"
          checked={value === true}
          disabled={disabled}
          onChange={e => onSetValue(e.target.checked)}
        />
        <span className="text-gray-500">Yes</span>
      </div>
    );
  }

  // SELECT: single-value dropdown.
  if (field.type === 'select') {
    return (
      <select
        id={inputId}
        className="input"
        value={typeof value === 'string' ? value : ''}
        disabled={disabled}
        onChange={e => onSetValue(e.target.value)}
      >
        <option value="">-- select --</option>
        {options.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label || opt.value}</option>
        ))}
      </select>
    );
  }

  // SIGNATURE / TABLE: no meaningful interactive input in preview; show a stub so
  // the field still participates in layout (and any show_if it controls works via
  // a text proxy is unnecessary -- these rarely gate other fields).
  if (field.type === 'signature' || field.type === 'table') {
    return (
      <div className="input bg-gray-100 text-gray-400 text-sm italic">
        ({field.type} -- not interactive in preview)
      </div>
    );
  }

  // TEXTAREA / multiline text.
  if (field.type === 'textarea' || (field.type === 'text' && field.multiline)) {
    return (
      <textarea
        id={inputId}
        className="input"
        rows={3}
        maxLength={field.max_length}
        value={typeof value === 'string' ? value : ''}
        disabled={disabled}
        placeholder={field.help?.format_hint}
        onChange={e => onSetValue(e.target.value)}
      />
    );
  }

  // Default: a single-line input. Map the field type to the closest HTML input
  // type so date/number/tel/email get appropriate UI.
  const inputType =
    field.type === 'date' ? 'date' :
    field.type === 'number' ? 'number' :
    field.type === 'tel' ? 'tel' :
    field.type === 'email' ? 'email' :
    'text';
  return (
    <input
      id={inputId}
      type={inputType}
      className="input"
      maxLength={field.max_length}
      value={typeof value === 'string' ? value : ''}
      disabled={disabled}
      placeholder={field.help?.format_hint}
      onChange={e => onSetValue(e.target.value)}
    />
  );
}
