import React from 'react';
import type {
  FormField,
  FieldType,
  FormSchema,
  ConditionalControl,
  ConditionalOperator,
  ControlActionKey,
} from '../types/schema';
import {
  canUngroup,
  mintOptionSlug,
  mintUniqueSlugs,
  optionValueReferencedBy,
  retargetOptionValueReferences,
} from '../utils/fieldGrouping';
import { ConditionBuilder } from './ConditionBuilder';
import type { UnclaimedWidget } from '../utils/remoteKitStore';

interface FieldEditorProps {
  field: FormField | null;
  schema: FormSchema;
  onUpdateField: (field: FormField) => void;
  // Un-merge a consolidated options[] field back into separate per-widget fields
  // (bd polyglot-pdf-s4dp.1). Optional so the editor still renders without it.
  onUnmergeField?: (fieldId: string) => void;
  // Commit a schema-wide field list, e.g. after retargeting dependents' show_if
  // / require_if to an option's freshly-renamed slug (bd polyglot-pdf-432u).
  // Separate from onUpdateField, which can only patch the SINGLE field being
  // edited -- a rename can touch OTHER fields' conditions too. Optional so the
  // editor still renders without it (falls back to leaving dependents
  // unretargeted, same as before this fix).
  onUpdateFields?: (fields: FormField[]) => void;
  // Update form-level metadata (version/edition/OMB/expiration -- bd
  // polyglot-pdf-s4dp.2). Optional; when absent the metadata panel is read-only.
  onUpdateMetadata?: (patch: Partial<FormSchema['form_metadata']>) => void;
  // Author-tier surfaces (bd h76m.10): per-option PDF-widget mapping lives
  // under an Advanced disclosure only authors see. Editor-tier contractors see
  // the option value as a read-only chip but not the widget plumbing. Defaults
  // true so local (non-hosted) editing is full author tier.
  authorTier?: boolean;
  // "Add from PDF widgets" picker (bd polyglot-pdf-nivy, P5.3c): fetch the kit's
  // unclaimed PDF button widgets so the author can add a missed checkbox/radio
  // box to a group. Optional -- provided only in hosted author mode on an open
  // kit; when absent the picker is not offered (local mode has no backend dump).
  onLoadUnclaimedWidgets?: () => Promise<UnclaimedWidget[]>;
}

// The editable form-metadata panel (bd polyglot-pdf-s4dp.2). Shown when no field
// is selected, so a human can correct an auto-extracted version -- or fill one a
// version-less form lacked (version defaults to "unknown", never blank). Each
// input commits a single-key patch through onUpdateMetadata.
const FormMetadataEditor: React.FC<{
  schema: FormSchema;
  onUpdateMetadata?: (patch: Partial<FormSchema['form_metadata']>) => void;
}> = ({ schema, onUpdateMetadata }) => {
  const meta = schema.form_metadata;
  const set = (key: keyof FormSchema['form_metadata']) => (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const raw = e.target.value;
    // `version` is REQUIRED on the schema: clearing it must degrade to the
    // "unknown" sentinel, never undefined -- a save serializes with JSON.stringify
    // which drops undefined keys, which would strip the required field and fail
    // backend validation (Codex PR #263). Optional fields clear to undefined.
    const value = key === 'version' ? (raw || 'unknown') : (raw || undefined);
    const patch = { [key]: value } as Partial<FormSchema['form_metadata']>;
    // A MANUAL version edit makes the stale auto-extracted version_confidence
    // meaningless -- leaving the old 0/0.4 would keep the "(verify)" hint with no
    // way to clear it. Clear it on any non-empty version edit (a human-entered
    // version is authoritative); a cleared-to-"unknown" version keeps low
    // confidence via the "unknown" branch of the lowConfidence check (Codex r2).
    if (key === 'version') {
      patch.version_confidence = raw ? undefined : 0;
    }
    onUpdateMetadata?.(patch);
  };
  const lowConfidence =
    meta?.version === 'unknown' ||
    (typeof meta?.version_confidence === 'number' && meta.version_confidence <= 0.5);

  const rows: { key: keyof FormSchema['form_metadata']; label: string; placeholder: string }[] = [
    { key: 'version', label: 'Version / Revision', placeholder: 'e.g., December 2024 or 01/20/25' },
    { key: 'edition_date', label: 'Edition date', placeholder: 'e.g., 01/20/25' },
    { key: 'omb_number', label: 'OMB number', placeholder: 'e.g., 1615-0082' },
    { key: 'expiration_date', label: 'Expiration date', placeholder: 'e.g., 02/28/2027' },
  ];

  return (
    <div className="h-full overflow-auto custom-scrollbar">
      <div className="p-4 space-y-4">
        <div className="border-b border-gray-200 pb-3">
          <h3 className="text-lg font-semibold text-gray-900">Form metadata</h3>
          <p className="text-sm text-gray-500">{meta?.form_number || meta?.title || 'Form'}</p>
        </div>

        {lowConfidence && (
          <div className="text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded p-2">
            The form version could not be confidently detected -- please verify and
            correct it below.
          </div>
        )}

        {rows.map(({ key, label, placeholder }) => (
          <div key={key}>
            <label className="label">{label}</label>
            <input
              type="text"
              className="input"
              aria-label={label}
              value={(meta?.[key] as string) ?? ''}
              onChange={set(key)}
              placeholder={placeholder}
              disabled={!onUpdateMetadata}
            />
          </div>
        ))}

        <p className="text-xs text-gray-400">
          Select a field on the left to edit its properties.
        </p>
      </div>
    </div>
  );
};

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
  'checkbox_group',
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

// "Add from PDF widgets" picker (bd polyglot-pdf-nivy, P5.3c). A self-contained
// sub-component (own hooks) so it can live inside the options section without
// tangling FieldEditor's early `if (!field)` return. Lists the kit's unclaimed
// PDF button widgets; selecting one appends an option (a slug minted from the
// widget's tooltip/leaf label, the widget name on option.pdf_field_name, and its
// on-state on option.pdf_on_value).
const WidgetPicker: React.FC<{
  // The field's EXISTING option VALUES (not labels): the new slug must be unique
  // against these, since option.value is what the lint duplicate-value rule keys
  // on. Minting against labels would miss a hand-edited value that collides
  // (fresh-eyes) -> an option-value-duplicate ERROR, breaking the lint-clean
  // exit criterion.
  existingValues: string[];
  onLoad: () => Promise<UnclaimedWidget[]>;
  // Append the picked widget as an option. For a SHARED-name group kid, the
  // caller must also set the field-level pdf_field_name (carried in
  // fieldPdfFieldName) and the option carries only pdf_on_value; for a distinct
  // widget the option carries pdf_field_name and fieldPdfFieldName is undefined.
  onPick: (opt: { label: string; value: string;
                  pdf_field_name?: string; pdf_on_value?: string },
           fieldPdfFieldName?: string) => void;
}> = ({ existingValues, onLoad, onPick }) => {
  const [open, setOpen] = React.useState(false);
  const [widgets, setWidgets] = React.useState<UnclaimedWidget[] | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const openPicker = React.useCallback(async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    try {
      setWidgets(await onLoad());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load PDF widgets');
    } finally {
      setLoading(false);
    }
  }, [onLoad]);

  // A readable default label from the tooltip, else the widget's leaf name.
  const labelFor = (w: UnclaimedWidget): string => {
    if (w.tooltip && w.tooltip.trim()) return w.tooltip.trim();
    const leaf = w.name.split('.').pop() || w.name;
    return leaf;
  };

  const pick = (w: UnclaimedWidget) => {
    const label = labelFor(w);
    // Mint the slug from the label, then bump it past every EXISTING option value
    // (option-value-duplicate keys on value, not label) so adding a widget can
    // never manufacture a duplicate -- even against a hand-edited value.
    const used = new Set(existingValues);
    const base = mintOptionSlug(label);
    let value = base;
    let n = 1;
    while (used.has(value)) value = `${base}_${++n}`;
    if (w.shared_name) {
      // Shared-name group kid: the option carries ONLY pdf_on_value; the field
      // carries pdf_field_name=name. Putting the shared name on each option's
      // pdf_field_name would trip dump-widget-multiclaim (Opus fallback).
      onPick(
        { label, value, ...(w.on_value ? { pdf_on_value: w.on_value } : {}) },
        w.name,
      );
    } else {
      // Distinct-name widget: the option carries its own pdf_field_name.
      onPick({
        label, value, pdf_field_name: w.name,
        ...(w.on_value ? { pdf_on_value: w.on_value } : {}),
      });
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        className="btn btn-secondary w-full text-sm"
        onClick={() => void openPicker()}
      >
        + Add from PDF widgets
      </button>
    );
  }

  return (
    <div className="border border-gray-200 rounded-md p-2 space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-700">
          Unclaimed PDF widgets
        </span>
        <button
          type="button"
          className="text-xs text-gray-500 hover:text-gray-700"
          onClick={() => setOpen(false)}
        >
          Close
        </button>
      </div>
      {loading && <p className="text-xs text-gray-500">Loading...</p>}
      {error && <p className="text-xs text-red-600" role="alert">{error}</p>}
      {!loading && !error && widgets && widgets.length === 0 && (
        <p className="text-xs text-gray-500">
          No unclaimed PDF widgets -- every button is already mapped.
        </p>
      )}
      {!loading && widgets && widgets.map((w) => (
        <button
          // A shared-name group returns N candidates with the SAME name (differing
          // only by on_value), so key on name+on_value to avoid duplicate React
          // keys (Opus fallback).
          key={`${w.name}|${w.on_value ?? ''}`}
          type="button"
          className="w-full text-left text-xs p-1.5 rounded hover:bg-gray-100 flex items-center justify-between gap-2"
          onClick={() => pick(w)}
          title={`Add ${w.name} as an option`}
        >
          <span className="truncate">{labelFor(w)}</span>
          <span className="font-mono text-gray-400 shrink-0">
            {w.type}{w.page != null ? ` p${w.page + 1}` : ''}
          </span>
        </button>
      ))}
    </div>
  );
};

export const FieldEditor: React.FC<FieldEditorProps> = ({
  field,
  schema,
  onUpdateField,
  onUnmergeField,
  onUpdateMetadata,
  onUpdateFields,
  authorTier = true,
  onLoadUnclaimedWidgets,
}) => {
  if (!field) {
    // No field selected -> show the editable form-metadata panel (bd s4dp.2), so
    // version/edition/OMB/expiration are reachable without picking a field.
    return <FormMetadataEditor schema={schema} onUpdateMetadata={onUpdateMetadata} />;
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

          {/* Field Type. A field that already carries options[] is a GROUP
              (checkbox_group / a consolidated radio); raw-switching its type
              would strand the options or mint a model-invalid group, so the
              picker is read-only for groups -- change the group via Merge /
              Ungroup instead. checkbox_group is only OFFERED as a target to
              authors, since building a valid one requires per-option PDF
              mapping (Codex PR #310 round 2). */}
          {(() => {
            const isGroup = !!field.options && field.options.length > 0;
            const typeChoices = FIELD_TYPES.filter(
              t => t !== 'checkbox_group' || authorTier || field.type === 'checkbox_group',
            );
            return (
              <div>
                <label className="label">Field Type</label>
                <select
                  className="input disabled:opacity-60"
                  aria-label="Field Type"
                  value={field.type}
                  disabled={isGroup}
                  title={isGroup
                    ? 'This is a group (has options). Change it via Merge / Ungroup, not a type switch.'
                    : undefined}
                  onChange={(e) => updateField({ type: e.target.value as FieldType })}
                >
                  {typeChoices.map(type => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
                {isGroup && (
                  <p className="text-xs text-gray-500 mt-1">
                    Group type is set by Merge (several = checkbox group, exactly
                    one = radio) and reversed by Ungroup.
                  </p>
                )}
              </div>
            );
          })()}

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

        {/* Conditional Logic (bd h76m.9): composite builder cards for
            show_if ("Shown when") and require_if ("Required when"). */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">
            Conditional Logic
          </h4>

          <ConditionBuilder
            title="Shown when"
            condition={field.show_if}
            selfId={field.id}
            schema={schema}
            onChange={(next) => updateField({ show_if: next })}
          />

          <ConditionBuilder
            title="Required when"
            condition={field.require_if}
            selfId={field.id}
            schema={schema}
            onChange={(next) => updateField({ require_if: next })}
          />
        </div>

        {/* Controls Fields (trigger-side: this field's value affects others).
            HIDDEN for a checkbox_group (Codex PR #310 round 3): this legacy
            editor writes {operator:'equals', value:''} and offers no membership
            operators, which is v2-invalid on a group trigger (the registry
            allows only includes/not_includes/emptiness there). controls_fields
            is deprecated (deleted at P6.2), so hiding it beats teaching a
            dead editor group semantics. */}
        {field.type !== 'checkbox_group' && (
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
        )}

        {/* Un-group: split a consolidated options[] field back into one field
            per widget (bd polyglot-pdf-s4dp.1). Rendered for ANY consolidated
            field whose options each carry a pdf_field_name -- including CHECKBOX
            groups (e.g. I-90 p3_race), not just select/radio, so the control is
            not half-wired (Codex PR #256). */}
        {onUnmergeField && canUngroup(field) && (
          <div className="flex items-center justify-between border-t border-gray-200 pt-4">
            <span className="text-sm font-semibold text-gray-900">Consolidated group</span>
            <button
              className="btn-sm btn-secondary"
              onClick={() => onUnmergeField(field.id)}
              title="Split this consolidated field back into separate per-widget fields"
            >
              Ungroup
            </button>
          </div>
        )}

        {/* Field Options (select / radio / checkbox_group). The option VALUE
            is a read-only slug chip -- an internal join key minted from the
            label, never free-typed (bd h76m.10); editing the label is how an
            author renames an option. Per-option PDF-widget mapping is
            author-tier only, under an Advanced disclosure. */}
        {(field.type === 'select' || field.type === 'radio' || field.type === 'checkbox_group') && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-gray-900">Options</h4>
            </div>

            {field.options && field.options.length > 0 ? (
              <div className="space-y-2">
                {field.options.map((option, idx) => (
                  <div key={idx} className="space-y-1 border-l-2 border-gray-100 pl-2">
                    <div className="flex gap-2 items-center">
                      <input
                        type="text"
                        className="input flex-1"
                        value={option.label}
                        onChange={(e) => {
                          const label = e.target.value;
                          const newOptions = [...(field.options || [])];
                          // Re-mint the slug from the new label, unique across
                          // the OTHER options (the value is a read-only chip;
                          // renaming the label is how it changes). bd h76m.10.
                          const otherLabels = newOptions
                            .filter((_, i) => i !== idx)
                            .map(o => o.label || '');
                          const oldValue = option.value;
                          const value = mintUniqueSlugs([...otherLabels, label]).slice(-1)[0];
                          newOptions[idx] = { ...option, label, value };
                          const updatedField = { ...field, options: newOptions };
                          // A dependent's show_if/require_if can reference this
                          // option by its OLD slug. Unlike Remove (which BLOCKS
                          // deleting a referenced option), rename can't block --
                          // this onChange fires on every keystroke, and typing a
                          // new label necessarily passes through intermediate
                          // slugs, so a per-keystroke block would make a
                          // referenced option's label un-editable. Instead,
                          // retarget every referencing condition to the new slug
                          // atomically with the rename, keeping the schema
                          // ref-clean without freezing the field (bd
                          // polyglot-pdf-432u). Both the field's own rename AND
                          // the dependents' retarget must land in ONE commit --
                          // two separate onUpdateField/onUpdateFields calls would
                          // race (the second overwrites the first's result via
                          // the undo history's functional setState) -- so when
                          // onUpdateFields is available, splice the renamed field
                          // into the retargeted list and commit once; only fall
                          // back to the single-field path when it is absent (no
                          // dependents can be retargeted without it anyway).
                          if (onUpdateFields && oldValue && oldValue !== value) {
                            const withRename = schema.fields.map(f =>
                              f.id === field.id ? updatedField : f,
                            );
                            const retargeted = retargetOptionValueReferences(
                              withRename, field.id, String(oldValue), value,
                            );
                            onUpdateFields(retargeted);
                          } else {
                            updateField({ options: newOptions });
                          }
                        }}
                        placeholder="Option label"
                      />
                      {option.value && (
                        <span
                          className="text-xs font-mono text-gray-500 bg-gray-100 rounded px-1.5 py-0.5"
                          title="Internal value (slug) -- minted from the label, not editable"
                        >
                          {option.value}
                        </span>
                      )}
                      {(() => {
                        // A dependent gated on this option's slug would dangle
                        // (or, if silently stripped, flip from hidden to
                        // shown-for-everyone). Block the delete and name the
                        // dependents so the author retargets them first
                        // (Codex PR #310 round 2).
                        const referencedBy = option.value
                          ? optionValueReferencedBy(schema, field.id, String(option.value))
                          : [];
                        // A choice field (select/radio/checkbox_group) needs >= 2
                        // options in v2; removing at the floor would make a valid
                        // group unsaveable/unpromotable in one click. Structural
                        // splits go through Ungroup, not option-by-option Remove
                        // (Codex PR #310 round 3).
                        const atFloor =
                          field.type !== 'checkbox' &&
                          (field.options?.length ?? 0) <= 2;
                        const blocked = referencedBy.length > 0 || atFloor;
                        const reason = referencedBy.length > 0
                          ? `Used by a condition on: ${referencedBy.join(', ')}. Retarget those first.`
                          : atFloor
                            ? 'A group needs at least two options. Ungroup to split it instead.'
                            : undefined;
                        return (
                          <button
                            className="btn-sm btn-secondary disabled:opacity-50"
                            disabled={blocked}
                            title={reason}
                            onClick={() => {
                              const newOptions = (field.options || []).filter((_, i) => i !== idx);
                              updateField({ options: newOptions });
                            }}
                          >
                            Remove
                          </button>
                        );
                      })()}
                    </div>
                    {authorTier && (
                      <details className="text-xs pl-1">
                        <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
                          Advanced: PDF widget
                        </summary>
                        <input
                          type="text"
                          className="input input-sm mt-1 w-full font-mono"
                          value={option.pdf_field_name || ''}
                          onChange={(e) => {
                            const newOptions = [...(field.options || [])];
                            newOptions[idx] = { ...option, pdf_field_name: e.target.value };
                            updateField({ options: newOptions });
                          }}
                          placeholder="pdf_field_name (widget backing this option)"
                          aria-label={`Option ${idx + 1} PDF widget`}
                        />
                      </details>
                    )}
                  </div>
                ))}
                {(authorTier || field.type === 'select') && (
                  <button
                    className="btn btn-secondary w-full text-sm"
                    onClick={() => {
                      const opts = field.options || [];
                      const value = mintUniqueSlugs(
                        [...opts.map(o => o.label || ''), 'option'],
                      ).slice(-1)[0];
                      updateField({ options: [...opts, { label: '', value }] });
                    }}
                  >
                    + Add Option
                  </button>
                )}
                {/* Add a missed checkbox/radio box from the PDF's unclaimed
                    widgets (bd nivy). Author-tier hosted only (the callback is
                    provided then); group fields only (a select's options are not
                    per-widget). */}
                {onLoadUnclaimedWidgets
                  && (field.type === 'checkbox_group' || field.type === 'radio') && (
                  <WidgetPicker
                    existingValues={(field.options || []).map(o => o.value || '')}
                    onLoad={onLoadUnclaimedWidgets}
                    onPick={(opt, fieldPdfFieldName) =>
                      updateField({
                        options: [...(field.options || []), opt],
                        // A shared-name group carries the widget name on the
                        // FIELD. Gate on type=radio: v2 FORBIDS a field-level
                        // pdf_field_name on a checkbox_group (form_models
                        // rejects it at the promotion gate), and a shared-name
                        // CHECKBOX matrix (widget_count>1) would otherwise lift
                        // one here -> an un-promotable schema (Opus fallback).
                        ...(fieldPdfFieldName && field.type === 'radio'
                            && !field.pdf_field_name
                          ? { pdf_field_name: fieldPdfFieldName }
                          : {}),
                      })
                    }
                  />
                )}
              </div>
            ) : (authorTier || field.type === 'select') ? (
              <button
                className="btn btn-secondary w-full"
                onClick={() =>
                  updateField({
                    options: [{ label: '', value: mintUniqueSlugs(['option'])[0] }],
                  })
                }
              >
                + Add Option
              </button>
            ) : (
              <p className="text-xs text-gray-500">No options.</p>
            )}
          </div>
        )}

        {/* Debug Info -- author-tier only: the raw dump exposes every
            option's pdf_field_name (the widget plumbing the per-option
            Advanced disclosure gates), so an editor-tier contractor must not
            see it either (Codex PR #310). */}
        {authorTier && (
          <details className="text-xs">
            <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
              Advanced / Debug
            </summary>
            <pre className="mt-2 p-2 bg-gray-100 rounded overflow-auto text-xs">
              {JSON.stringify(field, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
};
