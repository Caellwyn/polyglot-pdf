// Composite condition builder (bd polyglot-pdf-h76m.9, epic h76m P4.1): the
// contractor-facing editor for a field's show_if ("Shown when") and require_if
// ("Required when") conditions. Up to three labeled buckets -- ALL of / AT
// LEAST ONE of / NONE of -- of sentence-style atomic rows. There is NO nesting
// control by design: the one-level ceiling is unrepresentable in this UI, not
// merely validated (plan risk item).
//
// Value controls adapt to the trigger so no UI path can emit a value outside
// the trigger's option set (exit criterion 3):
//   - choice trigger (select / radio / checkbox_group / legacy
//     checkbox-with-options) + single-value operator -> option DROPDOWN;
//   - choice trigger + in/not_in -> option multi-select CHECKLIST (this
//     absorbs bd polyglot-pdf-jplx -- the missing array-value editor);
//   - free-text/number/date trigger -> plain input (in/not_in: comma-split);
//   - no-value operators (is_checked / is_empty / is_not_empty) -> none.
//
// Wire-shape rule: exactly ONE atom, living in ALL-of -> emit the LEGACY
// single {field, operator, value} condition (keeps v1 kits v1 on round-trip);
// anything else -> the v2 composite with only its non-empty buckets; zero
// atoms -> the key is removed. The evaluators consume either dialect through
// normalizeToComposite (P3.0/P3.1), and PreviewPane obeys live.

import type {
  CompositeConditionalDisplay,
  ConditionalDisplay,
  ConditionalOperator,
  FieldCondition,
  FormField,
  FormSchema,
} from '../types/schema';
import { normalizeToComposite } from '../utils/normalizeToComposite';
import { safeOptions } from '../utils/validation';

interface ConditionBuilderProps {
  /** Card heading, e.g. "Shown when" / "Required when". */
  title: string;
  /** The field's current condition (either wire dialect), if any. */
  condition?: FieldCondition;
  /** The field being edited -- excluded from trigger choices (self-gating). */
  selfId: string;
  schema: FormSchema;
  /** Emits the next wire value; undefined removes the condition entirely. */
  onChange: (next: FieldCondition | undefined) => void;
}

type BucketKey = 'all_of' | 'any_of' | 'none_of';

const BUCKETS: { key: BucketKey; label: string; hint: string }[] = [
  { key: 'all_of', label: 'ALL of these are true', hint: 'every row must hold' },
  { key: 'any_of', label: 'AT LEAST ONE of these is true', hint: 'one matching row is enough' },
  { key: 'none_of', label: 'NONE of these are true', hint: 'any matching row hides/blocks' },
];

// Field types that may trigger a condition at all (mirrors the backend
// registry's CONDITION_TRIGGER_TYPES -- backend/models/conditional_vocabulary.py).
const TRIGGERABLE_TYPES = new Set<FormField['type']>([
  'text', 'textarea', 'date', 'number', 'tel', 'email',
  'select', 'radio', 'checkbox', 'checkbox_group',
]);

// A trigger whose value is constrained to its options[] (choice fields). The
// legacy checkbox-with-options shape is a checkbox GROUP in all but type (the
// pre-v2 modeling still shipping in kits) and gets the same option controls.
// safeOptions().length, not `!!field.options && field.options.length > 0` (bd
// polyglot-pdf-yb41u): the raw check is TRUE for a non-array `options` (a
// string has a .length) and for an array of nulls, and every caller then does
// `trigger!.options!.some(...)` / `.map(...)` / `[0].value` -- which throws and
// blanks the whole show_if/require_if panel for the field being edited, because
// some OTHER field in the schema has malformed options. Counting only real
// option objects makes these predicates false for both malformed shapes, so the
// callers take their existing no-options branch instead.
function realOptionCount(field: FormField | undefined): number {
  return field ? safeOptions(field).length : 0;
}

function isChoiceTrigger(field: FormField | undefined): boolean {
  if (!field) return false;
  if (field.type === 'select' || field.type === 'radio' || field.type === 'checkbox_group') {
    return realOptionCount(field) > 0;
  }
  return field.type === 'checkbox' && realOptionCount(field) > 0;
}

function isGroupTrigger(field: FormField | undefined): boolean {
  if (!field) return false;
  if (field.type === 'checkbox_group') return true;
  return field.type === 'checkbox' && realOptionCount(field) > 0;
}

// The v2 operator/trigger compatibility matrix, editor side (mirrors
// backend/models/conditional_vocabulary.py OPERATORS -- keep in sync; the
// P2.1 lint re-checks server-side, this just keeps the dropdown honest).
// Deliberate widening vs the backend registry (fresh-eyes round 1): a LEGACY
// checkbox-with-options trigger also gets includes/not_includes. The backend
// scopes those to type=checkbox_group, but a v2-stamped schema cannot carry a
// checkbox-with-options field AT ALL (v2 forbids options on checkbox), so the
// pairing can never reach v2 validation -- while in v1 schemas membership is
// exactly what the P3.1 evaluators implement for that shape.
export function operatorsForTrigger(field: FormField | undefined): ConditionalOperator[] {
  if (!field) return ['is_empty', 'is_not_empty'];
  if (isGroupTrigger(field)) {
    return ['includes', 'not_includes', 'is_empty', 'is_not_empty'];
  }
  switch (field.type) {
    case 'checkbox':
      return ['is_checked', 'equals', 'not_equals', 'is_empty', 'is_not_empty'];
    case 'number':
    case 'date':
      return ['equals', 'not_equals', 'greater_than', 'less_than', 'in', 'not_in', 'is_empty', 'is_not_empty'];
    case 'select':
    case 'radio':
      return ['equals', 'not_equals', 'in', 'not_in', 'is_empty', 'is_not_empty'];
    default: // text, textarea, tel, email
      return ['equals', 'not_equals', 'contains', 'in', 'not_in', 'is_empty', 'is_not_empty'];
  }
}

const NO_VALUE_OPERATORS = new Set<ConditionalOperator>(['is_checked', 'is_empty', 'is_not_empty']);
const LIST_VALUED_OPERATORS = new Set<ConditionalOperator>(['in', 'not_in']);

const OPERATOR_LABELS: Record<string, string> = {
  equals: 'is',
  not_equals: 'is not',
  contains: 'contains',
  greater_than: 'is greater than',
  less_than: 'is less than',
  is_checked: 'is checked',
  is_empty: 'is empty',
  is_not_empty: 'is not empty',
  in: 'is one of',
  not_in: 'is none of',
  includes: 'has selected',
  not_includes: 'has NOT selected',
};

function operatorLabel(op: string): string {
  return OPERATOR_LABELS[op] ?? op.replace(/_/g, ' ');
}

// --- canonical edit model -------------------------------------------------

interface Canon {
  all_of: ConditionalDisplay[];
  any_of: ConditionalDisplay[];
  none_of: ConditionalDisplay[];
}

function toCanon(condition: FieldCondition | undefined): Canon | null {
  if (condition === undefined || condition === null) {
    return { all_of: [], any_of: [], none_of: [] };
  }
  const group = normalizeToComposite(condition);
  if (!group) return null; // malformed -- surfaced read-only, never edited blind
  return {
    all_of: (group.all_of ?? []) as ConditionalDisplay[],
    any_of: (group.any_of ?? []) as ConditionalDisplay[],
    none_of: (group.none_of ?? []) as ConditionalDisplay[],
  };
}

function fromCanon(canon: Canon): FieldCondition | undefined {
  const total = canon.all_of.length + canon.any_of.length + canon.none_of.length;
  if (total === 0) return undefined;
  if (total === 1 && canon.all_of.length === 1) {
    return canon.all_of[0]; // legacy single shape: keeps v1 kits v1
  }
  const out: CompositeConditionalDisplay = {};
  if (canon.all_of.length > 0) out.all_of = canon.all_of;
  if (canon.any_of.length > 0) out.any_of = canon.any_of;
  if (canon.none_of.length > 0) out.none_of = canon.none_of;
  return out;
}

// Default atom for a freshly-added row: first triggerable field, its first
// valid operator, and (for choice triggers) its FIRST OPTION SLUG -- so even
// the untouched default never carries a value outside the option set.
function defaultAtom(schema: FormSchema, selfId: string): ConditionalDisplay {
  const trigger = schema.fields.find(f => f.id !== selfId && TRIGGERABLE_TYPES.has(f.type));
  const operator = operatorsForTrigger(trigger)[0];
  const atom: ConditionalDisplay = { field: trigger?.id ?? '', operator };
  if (!NO_VALUE_OPERATORS.has(operator)) {
    if (isChoiceTrigger(trigger)) {
      // Seed from the first option with a NON-EMPTY value. A select option
      // now starts with an empty PDF export code for the author to fill in
      // (bd polyglot-pdf-alzbr), and seeding "" here would be invisible:
      // schema_lint deliberately skips "" as the v1 "field is empty" idiom,
      // so `equals ""` publishes clean while comparing live against the voice
      // SelectField's own empty placeholder -- the dependent would flip
      // visible whenever the user simply has not answered yet.
      const seed = safeOptions(trigger!).find(o => o.value !== '' && o.value != null);
      atom.value = LIST_VALUED_OPERATORS.has(operator)
        ? []
        : (seed?.value ?? safeOptions(trigger!)[0].value);
    } else {
      atom.value = LIST_VALUED_OPERATORS.has(operator) ? [] : '';
    }
  }
  return atom;
}

// Re-shape an atom's value after its trigger or operator changed, keeping it
// inside the new trigger's option set (or clearing it).
function coerceAtom(atom: ConditionalDisplay, trigger: FormField | undefined): ConditionalDisplay {
  const next: ConditionalDisplay = { field: atom.field, operator: atom.operator };
  if (NO_VALUE_OPERATORS.has(atom.operator)) return next;
  const options = isChoiceTrigger(trigger) ? safeOptions(trigger!) : null;
  if (LIST_VALUED_OPERATORS.has(atom.operator)) {
    const current = Array.isArray(atom.value) ? atom.value : [];
    next.value = options
      ? current.filter((v: unknown) => options.some(o => o.value === v))
      : current;
    return next;
  }
  if (options) {
    // Same empty-value reasoning as defaultAtom above: fall back to the first
    // option that actually carries a value, never to an unfilled export code.
    // Reads through safeOptions (not the local alias) so the options-consumer
    // guard test can see the read is protected.
    const seed = safeOptions(trigger!).find(o => o.value !== '' && o.value != null);
    // An empty incoming value must NOT be kept just because a half-authored
    // option happens to carry '' -- that is the invisible-condition case
    // (schema_lint skips "" as the v1 emptiness idiom, so `equals ""` publishes
    // clean while matching an unanswered dropdown live). It is reachable by
    // switching a row's trigger from a text field, whose value is '', onto a
    // select with an unfilled export code. Treat '' as "no value carried over"
    // and re-seed; only a NON-empty in-set value is preserved.
    const keep = atom.value !== '' && atom.value != null
      && options.some(o => o.value === atom.value);
    next.value = keep ? atom.value : (seed?.value ?? options[0].value);
  } else {
    next.value = Array.isArray(atom.value) ? '' : atom.value ?? '';
  }
  return next;
}

// Plain-language one-line summary of the whole condition.
function summarize(canon: Canon, schema: FormSchema): string {
  const nameOf = (id: string) =>
    schema.fields.find(f => f.id === id)?.spoken_name ?? id;
  const atomText = (a: ConditionalDisplay) => {
    const base = `${nameOf(a.field)} ${operatorLabel(a.operator)}`;
    if (NO_VALUE_OPERATORS.has(a.operator)) return base;
    const v = Array.isArray(a.value) ? a.value.join("', '") : a.value;
    return `${base} '${v}'`;
  };
  const parts: string[] = [];
  if (canon.all_of.length) parts.push(canon.all_of.map(atomText).join(' AND '));
  if (canon.any_of.length) parts.push(`(${canon.any_of.map(atomText).join(' OR ')})`);
  if (canon.none_of.length) parts.push(`NOT (${canon.none_of.map(atomText).join(' OR ')})`);
  return parts.join(' AND ');
}

// --- component --------------------------------------------------------------

export function ConditionBuilder({ title, condition, selfId, schema, onChange }: ConditionBuilderProps) {
  const canon = toCanon(condition);

  // Malformed condition (normalize failed): show it read-only rather than
  // silently rewriting data we do not understand; Remove is the only edit.
  if (canon === null) {
    return (
      <div className="space-y-3 p-3 bg-gray-50 rounded-md">
        <div className="flex justify-between items-center">
          <span className="text-sm font-semibold text-gray-900">{title}</span>
          <button className="btn-sm btn-secondary" onClick={() => onChange(undefined)}>
            Remove
          </button>
        </div>
        <p className="text-xs text-amber-600">
          This condition has an unrecognized shape and is shown read-only; the
          form treats it as always-on (fail-open). Remove it to author a new one.
        </p>
        <pre className="text-xs text-gray-600 whitespace-pre-wrap break-all">
          {JSON.stringify(condition, null, 2)}
        </pre>
      </div>
    );
  }

  const emit = (next: Canon) => onChange(fromCanon(next));

  const updateBucket = (bucket: BucketKey, rows: ConditionalDisplay[]) =>
    emit({ ...canon, [bucket]: rows });

  const totalAtoms = canon.all_of.length + canon.any_of.length + canon.none_of.length;

  if (totalAtoms === 0) {
    return (
      <div className="space-y-2">
        <span className="text-sm font-semibold text-gray-900">{title}</span>
        <button
          className="btn btn-secondary w-full"
          onClick={() => updateBucket('all_of', [defaultAtom(schema, selfId)])}
        >
          + Add condition ({title.toLowerCase()}...)
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3 p-3 bg-gray-50 rounded-md">
      <div className="flex justify-between items-center">
        <span className="text-sm font-semibold text-gray-900">{title}</span>
        <button className="btn-sm btn-secondary" onClick={() => onChange(undefined)}>
          Remove all
        </button>
      </div>

      {BUCKETS.map(({ key, label, hint }) => (
        <div key={key} className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-xs font-semibold text-gray-700" title={hint}>
              {label}
            </span>
            <button
              className="btn-sm btn-secondary"
              aria-label={`Add row: ${label}`}
              onClick={() => updateBucket(key, [...canon[key], defaultAtom(schema, selfId)])}
            >
              + Add
            </button>
          </div>
          {canon[key].map((atom, idx) => (
            <ConditionRow
              key={`${key}-${idx}`}
              atom={atom}
              bucket={key}
              index={idx}
              selfId={selfId}
              schema={schema}
              onChangeRow={(next) =>
                updateBucket(key, canon[key].map((a, i) => (i === idx ? next : a)))
              }
              onRemoveRow={() =>
                updateBucket(key, canon[key].filter((_, i) => i !== idx))
              }
            />
          ))}
        </div>
      ))}

      <p className="text-xs text-gray-600 italic" data-testid={`condition-summary-${title}`}>
        {title}: {summarize(canon, schema)}
      </p>
    </div>
  );
}

interface ConditionRowProps {
  atom: ConditionalDisplay;
  bucket: BucketKey;
  index: number;
  selfId: string;
  schema: FormSchema;
  onChangeRow: (next: ConditionalDisplay) => void;
  onRemoveRow: () => void;
}

function ConditionRow({ atom, bucket, index, selfId, schema, onChangeRow, onRemoveRow }: ConditionRowProps) {
  const trigger = schema.fields.find(f => f.id === atom.field);
  const validOperators = operatorsForTrigger(trigger);
  // A stored value can reference an option that no longer exists on the
  // trigger (its options were edited AFTER this rule was authored). The
  // builder never EMITS such a value, but it must SURFACE a stored one
  // loudly instead of rendering an unresolvable select (fresh-eyes round 1;
  // the P2.1 server-side lint flags the same orphan at promotion).
  const choice = isChoiceTrigger(trigger) && !NO_VALUE_OPERATORS.has(atom.operator);
  const staleScalar =
    choice && !LIST_VALUED_OPERATORS.has(atom.operator) &&
    !safeOptions(trigger!).some(o => o.value === atom.value)
      ? String(atom.value ?? '')
      : null;
  const staleListMembers =
    choice && LIST_VALUED_OPERATORS.has(atom.operator) && Array.isArray(atom.value)
      ? atom.value.filter((v: string) => !safeOptions(trigger!).some(o => o.value === v))
      : [];
  // An existing rule with an off-matrix operator (legacy data) still displays
  // itself -- else the select silently falls back and rewrites a stored rule.
  const operatorChoices = validOperators.includes(atom.operator)
    ? validOperators
    : [...validOperators, atom.operator];
  const rowLabel = `${bucket} row ${index + 1}`;

  return (
    <div className="flex flex-wrap gap-2 items-center pl-2 border-l-2 border-gray-200">
      <select
        className="input input-sm flex-1 min-w-[10rem]"
        aria-label={`${rowLabel}: trigger field`}
        value={atom.field}
        onChange={(e) => {
          const nextTrigger = schema.fields.find(f => f.id === e.target.value);
          const nextOps = operatorsForTrigger(nextTrigger);
          const operator = nextOps.includes(atom.operator) ? atom.operator : nextOps[0];
          onChangeRow(coerceAtom({ ...atom, field: e.target.value, operator }, nextTrigger));
        }}
      >
        <option value="">Select field...</option>
        {schema.fields
          .filter(f => f.id !== selfId && TRIGGERABLE_TYPES.has(f.type))
          .map(f => (
            <option key={f.id} value={f.id}>
              {f.spoken_name || f.id}
            </option>
          ))}
      </select>

      <select
        className="input input-sm w-40"
        aria-label={`${rowLabel}: operator`}
        value={atom.operator}
        onChange={(e) =>
          onChangeRow(coerceAtom({ ...atom, operator: e.target.value as ConditionalOperator }, trigger))
        }
      >
        {operatorChoices.map(op => (
          <option key={op} value={op}>
            {operatorLabel(op)}
          </option>
        ))}
      </select>

      {!NO_VALUE_OPERATORS.has(atom.operator) && (
        isChoiceTrigger(trigger) ? (
          LIST_VALUED_OPERATORS.has(atom.operator) ? (
            <div
              className="flex flex-wrap gap-2 w-full pl-2"
              role="group"
              aria-label={`${rowLabel}: options`}
            >
              {[
                ...safeOptions(trigger!),
                ...staleListMembers.map(v => ({ value: v, label: `(missing option) ${v}` })),
              ].map(opt => {
                const selected = Array.isArray(atom.value) && atom.value.includes(opt.value);
                return (
                  <label key={opt.value} className="text-xs flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={selected}
                      aria-label={`${rowLabel}: option ${opt.label}`}
                      onChange={() => {
                        const current: string[] = Array.isArray(atom.value) ? atom.value : [];
                        const next = selected
                          ? current.filter(v => v !== opt.value)
                          : [...current, opt.value];
                        onChangeRow({ ...atom, value: next });
                      }}
                    />
                    {opt.label}
                  </label>
                );
              })}
            </div>
          ) : (
            <>
              <select
                className="input input-sm w-40"
                aria-label={`${rowLabel}: value`}
                value={String(atom.value ?? '')}
                onChange={(e) => onChangeRow({ ...atom, value: e.target.value })}
              >
                {staleScalar !== null && (
                  <option value={staleScalar}>{`(missing option) ${staleScalar}`}</option>
                )}
                {safeOptions(trigger!).map(opt => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {staleScalar !== null && (
                <p className="text-xs text-amber-600 w-full pl-2" role="alert">
                  This rule references option '{staleScalar}', which no longer
                  exists on the trigger field -- pick a current option.
                </p>
              )}
            </>
          )
        ) : LIST_VALUED_OPERATORS.has(atom.operator) ? (
          <input
            type="text"
            className="input input-sm w-40"
            aria-label={`${rowLabel}: values (comma-separated)`}
            placeholder="a, b, c"
            value={Array.isArray(atom.value) ? atom.value.join(', ') : ''}
            onChange={(e) =>
              onChangeRow({
                ...atom,
                value: e.target.value
                  .split(',')
                  .map(s => s.trim())
                  .filter(s => s.length > 0),
              })
            }
          />
        ) : (
          <input
            type="text"
            className="input input-sm w-40"
            aria-label={`${rowLabel}: value`}
            placeholder="Expected value"
            value={String(atom.value ?? '')}
            onChange={(e) => onChangeRow({ ...atom, value: e.target.value })}
          />
        )
      )}

      <button className="btn-sm btn-secondary" aria-label={`Remove ${rowLabel}`} onClick={onRemoveRow}>
        x
      </button>
    </div>
  );
}
