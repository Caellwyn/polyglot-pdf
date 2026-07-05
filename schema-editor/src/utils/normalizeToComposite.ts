// normalizeToComposite -- the schema-v2 coexistence contract (bd
// polyglot-pdf-h76m.7, P3.0 of epic h76m). Normalizes a field-level condition
// (show_if / require_if) from EITHER wire dialect to ONE canonical shape the
// evaluators consume, so the P3.1 composite evaluators need exactly one code
// path while v1 and v2 schemas coexist (until the P6.2 strictness flip).
//
// THIS FILE IS DUPLICATED VERBATIM in frontend/src/schema-forms/utils/ and
// schema-editor/src/utils/ (no shared package by design -- the two islands
// build independently). It is deliberately self-contained (local structural
// types, zero imports) so the copies stay byte-identical; the shared vector
// suite (shared/conditional-vectors.json, `normalize` section) pins both, and
// the schema-editor runner additionally asserts the two files are identical.
//
// The contract (plan P3.0; do not extend without updating the vectors):
//   - null / undefined            -> null ("always shown")
//   - legacy single condition     -> { all_of: [atom] }
//       {field, operator, value?}    (atom passed through UNTOUCHED -- no
//                                     operator rewriting, no value coercion;
//                                     the vq4m equals-membership hack stays in
//                                     the LEAF evaluator until P6.2. Stray
//                                     non-contract keys are dropped.)
//   - v2 ConditionGroup           -> passthrough (empty buckets dropped;
//       {all_of/any_of/none_of}      members must be atomic -- depth <= 1)
//   - anything else / malformed   -> null + console.warn (FAIL-OPEN: the
//                                     field renders visible, mirroring the
//                                     runtime's unknown-operator fallback --
//                                     never throw on schema data)
//
// Normalize is pure SHAPE, zero semantics: for every pinned v0 vector,
// evaluate(normalize(show_if)) === evaluate(show_if) (the property test in
// both vector runners).

export interface AtomicCondition {
  field: string;
  operator: string;
  value?: unknown;
}

export interface CompositeCondition {
  all_of?: AtomicCondition[];
  any_of?: AtomicCondition[];
  none_of?: AtomicCondition[];
}

const BUCKETS = ['all_of', 'any_of', 'none_of'] as const;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

// An atomic condition has string field + operator and carries NO bucket keys
// (a dict mixing both dialects is ambiguous -- the backend model rejects it
// loudly at parse; here we fail open like every other malformed shape).
function toAtom(v: unknown): AtomicCondition | null {
  if (!isPlainObject(v)) return null;
  if (BUCKETS.some((b) => b in v)) return null;
  if (typeof v.field !== 'string' || typeof v.operator !== 'string') return null;
  const atom: AtomicCondition = { field: v.field, operator: v.operator };
  if ('value' in v) atom.value = v.value;
  return atom;
}

function warnMalformed(reason: string, condition: unknown): null {
  // eslint-disable-next-line no-console
  console.warn(
    `normalizeToComposite: ${reason} -- treating the condition as ` +
      'absent (field stays visible). Offending shape:',
    condition,
  );
  return null;
}

export function normalizeToComposite(condition: unknown): CompositeCondition | null {
  if (condition === null || condition === undefined) return null;
  if (!isPlainObject(condition)) {
    return warnMalformed('condition is not an object', condition);
  }

  const presentBuckets = BUCKETS.filter((b) => condition[b] !== null && condition[b] !== undefined);

  if (presentBuckets.length > 0) {
    if ('field' in condition || 'operator' in condition) {
      return warnMalformed(
        'condition mixes atomic keys (field/operator) with composite buckets',
        condition,
      );
    }
    const out: CompositeCondition = {};
    let totalAtoms = 0;
    for (const bucket of presentBuckets) {
      const members = condition[bucket];
      if (!Array.isArray(members)) {
        return warnMalformed(`bucket '${bucket}' is not an array`, condition);
      }
      const atoms: AtomicCondition[] = [];
      for (const member of members) {
        const atom = toAtom(member);
        if (atom === null) {
          return warnMalformed(
            `bucket '${bucket}' contains a non-atomic member (nested groups ` +
              'are not allowed -- depth <= 1)',
            condition,
          );
        }
        atoms.push(atom);
      }
      if (atoms.length > 0) {
        out[bucket] = atoms;
        totalAtoms += atoms.length;
      }
    }
    if (totalAtoms === 0) {
      return warnMalformed('composite condition has only empty buckets', condition);
    }
    return out;
  }

  const atom = toAtom(condition);
  if (atom !== null) return { all_of: [atom] };

  return warnMalformed(
    'condition is neither an atomic {field, operator, value} nor a ' +
      '{all_of/any_of/none_of} group',
    condition,
  );
}
