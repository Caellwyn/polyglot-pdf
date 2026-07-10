// Pure merge/split (group/ungroup) helpers for the schema editor (bd
// polyglot-pdf-s4dp.1). A real form's "check one box" radio group arrives from
// extraction as N separate radio/checkbox fields; the human must be able to
// MERGE them into one consolidated options[] field (each option carrying its
// source widget's pdf_field_name) and UN-merge back. The backend model + runtime
// already consume this consolidated shape (FieldOption.pdf_field_name); this
// module is purely an editor-side mutation.
//
// LOSSLESS, SEMANTICS-AWARE design (Codex review on PR #256):
//   - Merge STASHES each source field's complete original FormField, plus the
//     original conditional references it rewrites, under a private _ungroup key
//     on the merged field. Un-merge restores them verbatim -- so help, validation,
//     hidden, show_if and every other per-field property survive a merge ->
//     un-merge round-trip (NOT a lossy whitelist rebuild). The backend and runtime
//     ignore the extra _ungroup key.
//   - Merge REWRITES dependent conditionals with the CORRECT runtime semantics:
//     a reference that selected a now-merged-away widget ("is_checked" on that
//     widget) becomes a reference to that widget's option slug on the group --
//     "includes <slug>" for a checkbox_group (multi-select) or "equals <slug>"
//     for a radio (single-select), because the group's runtime value is its
//     selected option(s). A bare id swap would leave an is_checked condition
//     that never fires against a group. Un-merge restores the originals.
//   - Guards: only radio/checkbox fields that (a) are not already consolidated and
//     (b) carry a pdf_field_name are groupable; a merge is rejected if the
//     selection spans more than one section (which would silently move a field
//     across the Form > Parts > Sections hierarchy).
//
// SHAPE (schema v2, bd h76m.10): the merged field is a checkbox_group (multi-
// select) or radio (single-select) with options[] (each
// { value, label, pdf_field_name }). option.value is a SEMANTIC slug minted
// from the label -- unique per field, lowercase-ascii; widget identity lives
// ONLY on option.pdf_field_name, and the group carries NO field-level
// pdf_field_name (the backend model rejects one on a group).

import type {
  FormField,
  FormSchema,
  FieldOption,
  CompositeConditionalDisplay,
  ConditionalDisplay,
  FieldCondition,
} from '../types/schema';

// Field types that can participate in a merge group. A consolidated options[]
// field is a single-select group, so only radio/checkbox source fields qualify.
const GROUPABLE_TYPES = new Set<FormField['type']>(['radio', 'checkbox']);

// A field is groupable if it is a radio/checkbox, is not itself already a
// consolidated options group, AND carries a pdf_field_name. Excluding
// already-consolidated fields prevents a re-merge that would drop their options;
// requiring a pdf_field_name prevents producing an unfillable, non-reversible
// option (canUngroup needs every option to have one) -- Codex PR #256.
export function isGroupableField(field: FormField): boolean {
  if (!GROUPABLE_TYPES.has(field.type)) return false;
  if (field.options && field.options.length > 0) return false;
  return !!field.pdf_field_name;
}

// "Selection" operators -- conditions that test whether a (checkbox/radio) widget
// is the selected one. When that widget is merged into a consolidated group, the
// runtime value becomes the selected option(s), so these must convert to a
// membership/equality reference on the group rather than keep a widget-level op.
const SELECTION_OPERATORS = new Set(['is_checked', 'equals', 'is_not_empty']);

// The NEGATIVE selection predicates -- "this widget is NOT selected" on a source
// checkbox. On the merged group these must become the NEGATIVE reference
// (not_includes <slug> for a checkbox_group, not_equals <slug> for a radio),
// NOT be left as a widget-level not_equals/is_empty that is either v2-invalid on
// a group or silently re-scoped to "no options selected" (Codex PR #310 round 3).
//   not_equals true  -> box is unchecked
//   not_equals <on>  -> box is unchecked (widget on-value form)
//   is_empty         -> box is unchecked
const NEGATIVE_SELECTION_OPERATORS = new Set(['not_equals', 'is_empty']);

// v2 option-slug minting (bd h76m.10): mirror backend
// conditional_vocabulary.mint_option_slug / mint_unique_slugs. Merge mints
// SEMANTIC slugs from labels (lowercase ascii [a-z0-9_-], unique per field)
// instead of the old source-field-id convention, so the consolidated group is
// v2-lint-clean (option-value-slug rule) and its widget identity lives only in
// option.pdf_field_name.
export function mintOptionSlug(label: string, fallback = 'option'): string {
  const ascii = (label || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '') // strip combining accents
    // eslint-disable-next-line no-control-regex
    .replace(/[^\x00-\x7f]/g, '') // drop remaining non-ascii
    .toLowerCase();
  const slug = ascii.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return slug || fallback;
}

export function mintUniqueSlugs(labels: string[]): string[] {
  const used = new Set<string>();
  return labels.map(label => {
    const base = mintOptionSlug(label);
    let candidate = base;
    let n = 1;
    while (used.has(candidate)) candidate = `${base}_${++n}`;
    used.add(candidate);
    return candidate;
  });
}

// The kind of consolidated group a merge produces (bd h76m.10): a
// checkbox_group is multi-select (membership conditionals), a radio is
// single-select (equality conditionals).
export type MergeKind = 'checkbox_group' | 'radio';

// Best human-readable label for a source field becoming one option.
function optionLabelFor(field: FormField): string {
  return field.label || field.spoken_name || field.name || field.id;
}

// True when this consolidated field can be un-merged: it has 2+ options that each
// carry a pdf_field_name (so each can be reconstructed into a standalone field).
export function canUngroup(field: FormField): boolean {
  const opts = field.options || [];
  return opts.length >= 2 && opts.every(o => !!o.pdf_field_name);
}

// Stash written on the merged field so un-merge is a lossless inverse. Held under
// a private key; the backend/runtime ignore unknown field keys.
interface UngroupStash {
  // Each source field's complete original object, in option order. sources[0] is
  // the primary (its id == the merged field id).
  sources: FormField[];
  // Dependent fields whose show_if / require_if / copy_to this merge rewrote, with
  // their pre-merge values, so un-merge can restore them verbatim.
  rewrites: Array<{
    fieldId: string;
    show_if?: FieldCondition;
    require_if?: FieldCondition;
    copy_to?: string[];
    // sentinels distinguishing "had no key" from "key not rewritten" on restore.
    had_show_if: boolean;
    had_require_if: boolean;
    had_copy_to: boolean;
  }>;
}

// FormField does not declare the private stash key, so read/write it through a
// narrow cast kept in one place.
const STASH_KEY = '_ungroup';
function readStash(field: FormField): UngroupStash | undefined {
  return (field as unknown as Record<string, unknown>)[STASH_KEY] as UngroupStash | undefined;
}

// Strip editor-only state (the _ungroup stash) from a schema before it is
// serialized to disk, so the saved artifact stays the clean consolidated shape
// (Opus fallback review). The stash exists only to make an in-SESSION un-merge a
// lossless inverse; persisting full duplicate source objects would bloat and
// pollute the canonical form-kit JSON. Trade-off: un-merging a field that was
// merged, SAVED, and RELOADED takes the (lossy) reconstruction fallback -- but
// simple radio/checkbox widgets carry little metadata to lose, and within a
// session the round-trip stays lossless. Returns a shallow-cloned schema; the
// in-memory editor schema keeps its stash so a later same-session ungroup is
// still lossless.
export function stripEditorState(schema: FormSchema): FormSchema {
  let touched = false;
  const fields = schema.fields.map(f => {
    if ((f as unknown as Record<string, unknown>)[STASH_KEY] === undefined) return f;
    touched = true;
    const copy = { ...f } as Record<string, unknown>;
    delete copy[STASH_KEY];
    return copy as unknown as FormField;
  });
  return touched ? { ...schema, fields } : schema;
}

export interface MergeResult {
  schema: FormSchema;
  // id of the merged (primary) field, so the caller can re-select it. null when
  // the merge was a no-op (invalid selection) AND no usable primary id exists.
  mergedFieldId: string | null;
}

// Why a merge could not proceed (for surfacing a reason in the UI). null = ok.
export type MergeBlockReason = 'too-few' | 'cross-section' | 'missing-pdf-name';

// Validate a selection without mutating: returns the block reason, or null if the
// fields can be merged. The UI uses this to enable/disable + explain the control.
export function mergeBlockReason(schema: FormSchema, fieldIds: string[]): MergeBlockReason | null {
  const byId = new Map(schema.fields.map(f => [f.id, f]));
  const picked = Array.from(new Set(fieldIds))
    .map(id => byId.get(id))
    .filter((f): f is FormField => f !== undefined);

  const groupable = picked.filter(f => GROUPABLE_TYPES.has(f.type) && !(f.options && f.options.length > 0));
  if (groupable.length < 2) return 'too-few';
  if (groupable.some(f => !f.pdf_field_name)) return 'missing-pdf-name';
  // All selected groupable fields must live in the same section, else a merge
  // would silently move fields across the hierarchy (Codex PR #256).
  const sections = new Set(groupable.map(f => f.section_id ?? '__none__'));
  if (sections.size > 1) return 'cross-section';
  return null;
}

// Convert ONE conditional value reference from a merged-away widget to the
// consolidated radio. For a selection-style operator, the condition "this widget
// is selected" maps to "primary equals <the merged-away widget's option value>".
function rewriteShowIf(
  cond: ConditionalDisplay,
  mergedAwayToValue: Map<string, string>,
  primaryId: string,
  membership: boolean,
): ConditionalDisplay | null {
  if (!mergedAwayToValue.has(cond.field)) return null; // not pointing at a merged-away field
  const optionValue = mergedAwayToValue.get(cond.field)!;
  if (SELECTION_OPERATORS.has(cond.operator)) {
    // "this widget is selected" -> the group holds the widget's option slug.
    // checkbox_group is multi-select, so membership (includes) is the correct
    // operator; a radio is single-select, so equality (bd h76m.10).
    return membership
      ? { field: primaryId, operator: 'includes', value: optionValue }
      : { field: primaryId, operator: 'equals', value: optionValue };
  }
  if (NEGATIVE_SELECTION_OPERATORS.has(cond.operator)) {
    // "this widget is NOT selected" -> the group does NOT hold the slug.
    // checkbox_group -> not_includes <slug>; radio -> not_equals <slug>
    // (Codex PR #310 round 3). Leaving the widget-level not_equals/is_empty
    // would be v2-invalid on a group or silently mean "no options selected".
    return membership
      ? { field: primaryId, operator: 'not_includes', value: optionValue }
      : { field: primaryId, operator: 'not_equals', value: optionValue };
  }
  // A genuinely non-selection operator (contains/greater_than/...) keeps its
  // operator but retargets. These do not arise from a checkbox source in
  // practice; preserved best-effort.
  return { ...cond, field: primaryId };
}

// v2 composite awareness (bd h76m.8): a condition on the wire is either the
// legacy single shape or a {all_of/any_of/none_of} group; merge rewriting must
// walk both WITHOUT changing the stored shape (legacy stays legacy, composite
// stays composite -- normalization is the evaluators' job, not the editor's).
const CONDITION_BUCKETS = ['all_of', 'any_of', 'none_of'] as const;

function isCompositeCondition(cond: FieldCondition): cond is CompositeConditionalDisplay {
  return CONDITION_BUCKETS.some(
    b => (cond as CompositeConditionalDisplay)[b] !== undefined,
  );
}

// True when any atom of the (legacy or composite) condition references one of
// the given field ids.
function conditionReferencesAny(cond: FieldCondition, ids: Set<string>): boolean {
  if (isCompositeCondition(cond)) {
    return CONDITION_BUCKETS.some(
      b => (cond[b] ?? []).some(atom => ids.has(atom.field)),
    );
  }
  return ids.has(cond.field);
}

// Rewrite a legacy-or-composite condition atom-wise, preserving its shape.
function rewriteCondition(
  cond: FieldCondition,
  mergedAwayToValue: Map<string, string>,
  primaryId: string,
  membership: boolean,
): FieldCondition {
  if (isCompositeCondition(cond)) {
    const out: CompositeConditionalDisplay = {};
    for (const bucket of CONDITION_BUCKETS) {
      const members = cond[bucket];
      if (members) {
        out[bucket] = members.map(
          atom => rewriteShowIf(atom, mergedAwayToValue, primaryId, membership) ?? atom,
        );
      }
    }
    return out;
  }
  return rewriteShowIf(cond, mergedAwayToValue, primaryId, membership) ?? cond;
}

// Field IDs of dependents whose show_if / require_if references a specific
// option slug of `triggerFieldId` (bd h76m.10, Codex PR #310). Deleting such an
// option must NOT silently strip the condition -- for a positive trigger
// (includes/equals) that would flip the dependent from correctly-hidden to
// shown-for-everyone (round-2 finding). So the editor BLOCKS the delete and
// tells the author to retarget the dependent first, keeping the schema
// ref-clean without a silent semantic change. Returns the referencing field
// ids (empty = safe to delete).
export function optionValueReferencedBy(
  schema: FormSchema,
  triggerFieldId: string,
  optionSlug: string,
): string[] {
  const refs = (cond: FieldCondition | undefined): boolean => {
    for (const atom of conditionAtomsOf(cond)) {
      if (atom.field === triggerFieldId && String(atom.value) === optionSlug) {
        return true;
      }
    }
    return false;
  };
  return schema.fields
    .filter(f => f.id !== triggerFieldId && (refs(f.show_if) || refs(f.require_if)))
    .map(f => f.id);
}

// Flatten a legacy-or-composite condition to its atomic conditions.
function conditionAtomsOf(cond: FieldCondition | undefined): ConditionalDisplay[] {
  if (!cond) return [];
  if (isCompositeCondition(cond)) {
    return CONDITION_BUCKETS.flatMap(b => cond[b] ?? []);
  }
  return [cond];
}

// Rewrite a single legacy-or-composite condition, retargeting any atom that
// points at (triggerFieldId, oldSlug) to (triggerFieldId, newSlug). Preserves
// the condition's shape (legacy stays legacy, composite stays composite);
// returns the SAME object if nothing in it referenced the old slug (so callers
// can skip a field-level update when unchanged).
function retargetCondition(
  cond: FieldCondition,
  triggerFieldId: string,
  oldSlug: string,
  newSlug: string,
): FieldCondition {
  const retargetAtom = (atom: ConditionalDisplay): ConditionalDisplay =>
    atom.field === triggerFieldId && String(atom.value) === oldSlug
      ? { ...atom, value: newSlug }
      : atom;
  if (isCompositeCondition(cond)) {
    const out: CompositeConditionalDisplay = {};
    for (const bucket of CONDITION_BUCKETS) {
      const members = cond[bucket];
      if (members) out[bucket] = members.map(retargetAtom);
    }
    return out;
  }
  return retargetAtom(cond);
}

// Renaming an option's LABEL re-mints its slug (option.value) from the new
// label on every keystroke (bd h76m.10) -- but unlike the Remove button
// (guarded by optionValueReferencedBy, which BLOCKS deleting a referenced
// option), a per-keystroke BLOCK on rename is unworkable: typing a new label
// necessarily passes through intermediate slugs, and blocking would make a
// referenced option's label impossible to edit at all (bd polyglot-pdf-432u).
// So rename REWRITES every dependent's show_if/require_if (legacy or
// composite) that pointed at the old slug to the new one, atomically with the
// rename -- keeping the schema ref-clean without freezing the label. Mirrors
// optionValueReferencedBy's scan (show_if + require_if only, matching the
// delete guard's scope) but retargets instead of merely detecting. Returns the
// SAME array (identity-stable) when no field referenced the old slug, so
// callers can skip a no-op schema commit; otherwise a new array with only the
// retargeted fields replaced (untouched fields keep their original identity).
export function retargetOptionValueReferences(
  fields: FormField[],
  triggerFieldId: string,
  oldSlug: string,
  newSlug: string,
): FormField[] {
  if (oldSlug === newSlug) return fields;
  let anyChanged = false;
  const next = fields.map(f => {
    if (f.id === triggerFieldId) return f;
    let changed = false;
    const updated: FormField = { ...f };
    if (f.show_if && conditionAtomsOf(f.show_if).some(
      a => a.field === triggerFieldId && String(a.value) === oldSlug,
    )) {
      updated.show_if = retargetCondition(f.show_if, triggerFieldId, oldSlug, newSlug);
      changed = true;
    }
    if (f.require_if && conditionAtomsOf(f.require_if).some(
      a => a.field === triggerFieldId && String(a.value) === oldSlug,
    )) {
      updated.require_if = retargetCondition(f.require_if, triggerFieldId, oldSlug, newSlug);
      changed = true;
    }
    if (changed) anyChanged = true;
    return changed ? updated : f;
  });
  return anyChanged ? next : fields;
}

// Rewrite every dependent field's show_if / require_if / copy_to that referenced
// a merged-away field. Returns the rewritten fields AND a record of what changed
// (so un-merge can restore the originals). mergedAwayToValue maps each
// merged-away field id to its option value on the consolidated radio.
function rewriteReferences(
  fields: FormField[],
  mergedAwayToValue: Map<string, string>,
  primaryId: string,
  membership: boolean,
): { fields: FormField[]; rewrites: UngroupStash['rewrites'] } {
  const rewrites: UngroupStash['rewrites'] = [];
  const mergedAway = new Set(mergedAwayToValue.keys());

  const remapControlList = (ids?: string[]): string[] | undefined => {
    if (!ids) return ids;
    const out: string[] = [];
    for (const id of ids) {
      const r = mergedAway.has(id) ? primaryId : id;
      if (!out.includes(r)) out.push(r);
    }
    return out;
  };

  const newFields = fields.map(f => {
    let changed = false;
    const next: FormField = { ...f };
    const record: UngroupStash['rewrites'][number] = {
      fieldId: f.id, had_show_if: !!f.show_if, had_require_if: !!f.require_if,
      had_copy_to: !!f.copy_to,
    };
    let recorded = false;

    if (f.show_if && conditionReferencesAny(f.show_if, mergedAway)) {
      record.show_if = f.show_if; // original
      next.show_if = rewriteCondition(f.show_if, mergedAwayToValue, primaryId, membership);
      changed = true;
      recorded = true;
    }

    if (f.require_if && conditionReferencesAny(f.require_if, mergedAway)) {
      record.require_if = f.require_if; // original
      next.require_if = rewriteCondition(f.require_if, mergedAwayToValue, primaryId, membership);
      changed = true;
      recorded = true;
    }

    // copy_to is a plain string[] of target field ids (unused in current real
    // schemas, but rewritten for completeness so no reference list dangles).
    if (f.copy_to && f.copy_to.some(id => mergedAway.has(id))) {
      record.copy_to = f.copy_to; // original
      next.copy_to = remapControlList(f.copy_to);
      changed = true;
      recorded = true;
    }

    if (recorded) rewrites.push(record);
    return changed ? next : f;
  });

  return { fields: newFields, rewrites };
}

// Merge the given fields (by id, in selection order) into one consolidated
// options[] field. Returns the original schema unchanged if the selection is
// invalid (see mergeBlockReason). The first id is the primary whose identity
// survives.
export function mergeFields(
  schema: FormSchema,
  fieldIds: string[],
  kind: MergeKind = 'radio',
): MergeResult {
  if (mergeBlockReason(schema, fieldIds) !== null) {
    return { schema, mergedFieldId: fieldIds[0] ?? null };
  }

  const byId = new Map(schema.fields.map(f => [f.id, f]));
  const distinct = Array.from(new Set(fieldIds))
    .map(id => byId.get(id)!)
    .filter(f => isGroupableField(f))
    .sort((a, b) => fieldIds.indexOf(a.id) - fieldIds.indexOf(b.id));

  const primary = distinct[0];
  const mergedIds = new Set(distinct.map(f => f.id));
  // checkbox_group is multi-select -> membership (includes) conditionals;
  // radio is single-select -> equality (bd h76m.10).
  const membership = kind === 'checkbox_group';

  // option.value = a SEMANTIC slug minted from each source's label (v2
  // convention, bd h76m.10), unique per field. Widget identity moves to
  // option.pdf_field_name only. Each merged-away id maps to ITS slug so
  // dependent conditionals rewrite to the correct option reference.
  const slugs = mintUniqueSlugs(distinct.map(f => optionLabelFor(f)));
  const idToSlug = new Map(distinct.map((f, i) => [f.id, slugs[i]]));
  const mergedAwayToValue = new Map<string, string>();
  for (const f of distinct.slice(1)) mergedAwayToValue.set(f.id, idToSlug.get(f.id)!);

  const options: FieldOption[] = distinct.map((f, i) => ({
    value: slugs[i],
    label: optionLabelFor(f),
    pdf_field_name: f.pdf_field_name,
    source_type: f.type,
  }));

  // Replace the primary in place; drop the other merged fields. Rewrite dependent
  // conditionals on the SURVIVING fields, recording originals for a lossless undo.
  const survivors: FormField[] = [];
  for (const f of schema.fields) {
    if (f.id === primary.id) continue; // primary re-added below as the merged field
    if (!mergedIds.has(f.id)) survivors.push(f);
  }
  const { fields: rewrittenSurvivors, rewrites } = rewriteReferences(
    survivors, mergedAwayToValue, primary.id, membership,
  );

  // The PRIMARY's own references to merged-away siblings must be rewritten too
  // (it is excluded from `survivors`). show_if / require_if / copy_to retarget
  // to the primary; its own controls' target arrays are remapped (Opus
  // fallback review; require_if parity from fresh-eyes bd polyglot-pdf-319g).
  //
  // A primary gated on a sibling option would become self-referential (the
  // radio shown/required only when it equals one of its own option values --
  // unreachable, since it is hidden/unset until set). Drop the
  // self-referential part instead of emitting an unsatisfiable condition
  // (Opus fallback review, round 2). For a composite (bd h76m.8) that means
  // dropping self-referential ATOMS bucket-wise; a group left with no atoms
  // (or a legacy condition that became self-referential) drops entirely.
  const rewritePrimaryCondition = (
    condition: FieldCondition | undefined,
  ): FieldCondition | undefined => {
    if (!condition || !conditionReferencesAny(condition, new Set(mergedAwayToValue.keys()))) {
      return condition;
    }
    const rewritten = rewriteCondition(condition, mergedAwayToValue, primary.id, membership);
    if (isCompositeCondition(rewritten)) {
      const pruned: CompositeConditionalDisplay = {};
      let atomCount = 0;
      for (const bucket of CONDITION_BUCKETS) {
        const kept = (rewritten[bucket] ?? []).filter(atom => atom.field !== primary.id);
        if (kept.length > 0) {
          pruned[bucket] = kept;
          atomCount += kept.length;
        }
      }
      return atomCount > 0 ? pruned : undefined;
    }
    return rewritten.field !== primary.id ? rewritten : undefined;
  };
  const primaryShowIf = rewritePrimaryCondition(primary.show_if);
  const primaryRequireIf = rewritePrimaryCondition(primary.require_if);
  let primaryCopyTo = primary.copy_to;
  if (primaryCopyTo && primaryCopyTo.some(id => mergedAwayToValue.has(id))) {
    const out: string[] = [];
    for (const id of primaryCopyTo) {
      const r = mergedAwayToValue.has(id) ? primary.id : id;
      if (!out.includes(r)) out.push(r);
    }
    primaryCopyTo = out;
  }

  // The merged field carries the primary's identity + the stash for un-merge.
  // show_if / copy_to are set EXPLICITLY (not via a conditional spread) so a
  // dropped/rewritten value OVERRIDES the one inherited from {...primary} -- a
  // conditional spread would silently keep the stale inherited value (e.g. a
  // dropped self-referential show_if would survive). Round 2 fix.
  const stash: UngroupStash = { sources: distinct, rewrites };
  const mergedField = {
    ...primary,
    type: kind,
    options,
    [STASH_KEY]: stash,
  } as unknown as Record<string, unknown>;
  // A v2 group carries NO field-level pdf_field_name -- per-box identity lives
  // on option.pdf_field_name (backend model rejects a group with one). The
  // primary's own widget became options[0].pdf_field_name above.
  delete mergedField.pdf_field_name;
  // consolidated_widgets is a deleted-in-v2 legacy key (derivable, inconsistent
  // even in gold); do not carry it onto the merged group (bd h76m.10).
  delete mergedField.consolidated_widgets;
  if (primaryShowIf) mergedField.show_if = primaryShowIf;
  else delete mergedField.show_if;
  if (primaryRequireIf) mergedField.require_if = primaryRequireIf;
  else delete mergedField.require_if;
  if (primaryCopyTo) mergedField.copy_to = primaryCopyTo;
  else delete mergedField.copy_to;
  const mergedFieldTyped = mergedField as unknown as FormField;

  // Reassemble fields, putting the merged field where the primary was.
  const newFields: FormField[] = [];
  const survivorById = new Map(rewrittenSurvivors.map(f => [f.id, f]));
  for (const f of schema.fields) {
    if (f.id === primary.id) {
      newFields.push(mergedFieldTyped);
    } else if (survivorById.has(f.id)) {
      newFields.push(survivorById.get(f.id)!);
    }
    // merged-away (non-primary) fields are dropped
  }

  // Remove merged-away ids from the (single) section's field list.
  const newSections = schema.sections.map(section => {
    const fields = section.fields.filter(id => id === primary.id || !mergedIds.has(id));
    return fields.length === section.fields.length ? section : { ...section, fields };
  });

  return {
    schema: { ...schema, fields: newFields, sections: newSections },
    mergedFieldId: primary.id,
  };
}

// Whether an existing consolidated group can be flipped to `kind` and stay a
// VALID v2 group (bd polyglot-pdf-8qfj, fresh-eyes gap). The two kinds are NOT
// symmetric in the backend model (form_models.py group-validity rules):
//   - A checkbox_group's boxes are independent widgets: it carries NO
//     field-level pdf_field_name, and EVERY option must carry its OWN
//     pdf_field_name.
//   - A radio IS a shared AcroForm field: an option is fillable via its own
//     pdf_field_name OR the shared-name shape (a field-level pdf_field_name +
//     option pdf_on_value).
// So a shared-name radio (field-level pdf_field_name, options carrying
// pdf_on_value but no per-option pdf_field_name) has no valid checkbox_group
// form -- flipping it would mint a schema the backend rejects at promotion.
// changeGroupKind only changes type + dependent operators; it does NOT
// re-plumb widget identity, so it must REFUSE a flip that would produce an
// invalid group. Flipping TO radio is always valid (radio accepts either
// per-option pdf_field_name or the shared-name shape, and a checkbox_group's
// per-option names satisfy the former). Returns true if the flip is safe.
export function canChangeGroupKind(field: FormField, kind: MergeKind): boolean {
  const isGroup = !!field.options && field.options.length > 0;
  if (!isGroup) return false;
  if (field.type !== 'checkbox_group' && field.type !== 'radio') return false;
  if (field.type === kind) return false; // already that kind -- nothing to flip
  if (kind === 'radio') return true; // any existing group is a valid radio
  // kind === 'checkbox_group': forbid a field-level pdf_field_name, and require
  // every option to carry its own pdf_field_name (pdf_on_value is NOT enough).
  if (field.pdf_field_name) return false;
  return (field.options || []).every(o => !!o.pdf_field_name);
}

// Flip an EXISTING consolidated group between its two kinds -- checkbox_group
// (multi-select) and radio (single-select) -- WITHOUT going through an
// ungroup/re-merge round trip (bd polyglot-pdf-checkbox-radio). A group that
// extraction produced (e.g. W-7 reason_for_submission arriving as a
// checkbox_group that should be a radio) otherwise has no reachable path to the
// other kind: the Field Type picker is read-only for a group, and Merge only
// offers the kind choice when combining >=2 loose widgets, not on an existing
// group.
//
// The two kinds share option identity byte-for-byte -- the same options[], the
// same slugs, the same per-option pdf_field_name; the group carries no
// field-level pdf_field_name either way. The ONLY runtime-meaningful difference
// is how dependents reference a selected option: a checkbox_group is
// multi-select so membership (includes/not_includes) is correct, a radio is
// single-select so equality (equals/not_equals). So the flip is: set the type,
// and rewrite every dependent's show_if/require_if atom that targets one of
// THIS group's option slugs across that membership boundary. Nothing else in the
// schema changes.
//
// Returns the schema unchanged (same reference) if the field is not a
// consolidated group, or is already the requested kind (a no-op the caller can
// detect to skip a commit).
export function changeGroupKind(
  schema: FormSchema,
  fieldId: string,
  kind: MergeKind,
): FormSchema {
  const field = schema.fields.find(f => f.id === fieldId);
  // Only a real consolidated group can flip, only to the OTHER kind, and only
  // when the target kind stays a VALID v2 group (canChangeGroupKind rejects a
  // shared-name radio -> checkbox_group flip that the backend would reject).
  // Anything else is a no-op the caller can detect via the returned reference.
  if (!field || !canChangeGroupKind(field, kind)) return schema;

  const membership = kind === 'checkbox_group';
  // The option slugs a dependent could reference on THIS group. Only atoms whose
  // .field is this group AND whose value is one of these slugs get rewritten; a
  // whole-group operator (is_checked/is_empty on the group, no value) is
  // kind-agnostic and left untouched.
  const optionSlugs = new Set(
    (field.options || []).map(o => String(o.value)).filter(v => v !== ''),
  );

  // Map ONE atom targeting this group across the membership boundary. Positive
  // selection (equals/includes) -> includes (multi) or equals (single); negative
  // (not_equals/not_includes) -> not_includes or not_equals. Any other operator
  // (a whole-group is_checked/is_empty, or a non-selection op) is preserved.
  const flipAtom = (atom: ConditionalDisplay): ConditionalDisplay => {
    if (atom.field !== fieldId) return atom;
    if (atom.value === undefined || !optionSlugs.has(String(atom.value))) return atom;
    if (atom.operator === 'equals' || atom.operator === 'includes') {
      return { ...atom, operator: membership ? 'includes' : 'equals' };
    }
    if (atom.operator === 'not_equals' || atom.operator === 'not_includes') {
      return { ...atom, operator: membership ? 'not_includes' : 'not_equals' };
    }
    return atom;
  };

  const flipCondition = (cond: FieldCondition): FieldCondition => {
    if (isCompositeCondition(cond)) {
      const out: CompositeConditionalDisplay = {};
      for (const bucket of CONDITION_BUCKETS) {
        const members = cond[bucket];
        if (members) out[bucket] = members.map(flipAtom);
      }
      return out;
    }
    return flipAtom(cond);
  };

  const newFields = schema.fields.map(f => {
    if (f.id === fieldId) return { ...f, type: kind };
    // A dependent's show_if/require_if that selects one of this group's options
    // must move across the membership boundary too, else a checkbox_group ->
    // radio flip would strand an `includes` op that never fires on a
    // single-select value (and vice versa).
    let changed = false;
    const next: FormField = { ...f };
    if (f.show_if && conditionReferencesAny(f.show_if, new Set([fieldId]))) {
      next.show_if = flipCondition(f.show_if);
      changed = true;
    }
    if (f.require_if && conditionReferencesAny(f.require_if, new Set([fieldId]))) {
      next.require_if = flipCondition(f.require_if);
      changed = true;
    }
    return changed ? next : f;
  });

  return { ...schema, fields: newFields };
}

// Un-merge a consolidated field back into its separate per-widget fields. When a
// stash is present (a field merged in-editor), it is a LOSSLESS inverse: the
// original source fields and rewritten dependent conditionals are restored
// verbatim. Without a stash (a hand-authored consolidated field loaded from
// disk), it falls back to reconstructing each option into a standalone field.
// Returns the schema unchanged if the field is not un-groupable.
export function ungroupField(schema: FormSchema, fieldId: string): FormSchema {
  const field = schema.fields.find(f => f.id === fieldId);
  if (!field || !field.options || !canUngroup(field)) return schema;

  const stash = readStash(field);

  if (stash) {
    // Lossless path: restore the stashed source fields verbatim (minus the stash
    // key itself) and revert the rewritten dependents.
    const rebuilt = stash.sources.map(src => {
      const copy = { ...src } as Record<string, unknown>;
      delete copy[STASH_KEY];
      return copy as unknown as FormField;
    });
    const rebuiltIds = rebuilt.map(f => f.id);
    const restoreById = new Map(stash.rewrites.map(r => [r.fieldId, r]));

    const newFields: FormField[] = [];
    for (const f of schema.fields) {
      if (f.id === fieldId) {
        newFields.push(...rebuilt);
        continue;
      }
      const r = restoreById.get(f.id);
      if (r) {
        // Restore ONLY the keys the merge actually rewrote (the record holds
        // their pre-merge originals). A key that was present but untouched has
        // its had_* sentinel true with no recorded value -- assigning that
        // undefined would clobber the field's live value (bd h76m.8); a key
        // the field never had is deleted defensively.
        const restored = { ...f };
        if (r.show_if !== undefined) restored.show_if = r.show_if;
        else if (!r.had_show_if) delete (restored as Record<string, unknown>).show_if;
        if (r.require_if !== undefined) restored.require_if = r.require_if;
        else if (!r.had_require_if) delete (restored as Record<string, unknown>).require_if;
        if (r.copy_to !== undefined) restored.copy_to = r.copy_to;
        else if (!r.had_copy_to) delete (restored as Record<string, unknown>).copy_to;
        newFields.push(restored);
      } else {
        newFields.push(f);
      }
    }

    const newSections = schema.sections.map(section => {
      const pos = section.fields.indexOf(fieldId);
      if (pos === -1) return section;
      const fields = [...section.fields];
      fields.splice(pos, 1, ...rebuiltIds);
      return { ...section, fields };
    });

    return { ...schema, fields: newFields, sections: newSections };
  }

  // Fallback path (no stash -- hand-authored consolidated field). Reconstruct one
  // field per option. This cannot recover metadata the source never had on the
  // option, but it does preserve each option's pdf_field_name + source_type.
  const otherIds = new Set(schema.fields.map(f => f.id).filter(id => id !== fieldId));
  const usedIds = new Set<string>();
  // option.value -> reconstructed field id, so dependents that referenced the
  // consolidated field can be remapped to the right split field (bd
  // polyglot-pdf-v444 -- inverse of mergeFields' rewriteReferences).
  const valueToReconstructedId = new Map<string, string>();
  const rebuilt: FormField[] = field.options.map((opt, idx) => {
    let id: string;
    if (idx === 0) {
      id = fieldId;
    } else {
      const base = String(opt.value || `${fieldId}_${idx}`);
      let candidate = base;
      let n = 1;
      while (usedIds.has(candidate) || otherIds.has(candidate)) {
        candidate = `${base}_${n++}`;
      }
      id = candidate;
    }
    usedIds.add(id);
    // Exclude an empty-string option value: a dependent's `equals ''` / `not_equals
    // ''` is a whole-group populated/empty check (handled by
    // normalizeWholeGroupOperator), NOT a reference to a degenerate ''-valued
    // option. Admitting '' here would mis-route it to the specific-option branch
    // (fresh-eyes r3). Empty/null option values never identify a real option.
    if (opt.value !== undefined && opt.value !== null && opt.value !== '') {
      valueToReconstructedId.set(String(opt.value), id);
    }

    return {
      id,
      name: opt.label || id,
      type: opt.source_type || 'checkbox',
      section_id: field.section_id,
      pdf_field_name: opt.pdf_field_name || '',
      label: opt.label,
      spoken_name: idx === 0 ? field.spoken_name : undefined,
      read_only: field.read_only,
      required: field.required,
    };
  });

  const rebuiltIds = rebuilt.map(f => f.id);
  const primaryReconstructedId = rebuiltIds[0];

  const newFields: FormField[] = [];
  for (const f of schema.fields) {
    if (f.id === fieldId) {
      newFields.push(...rebuilt);
    } else {
      newFields.push(remapFallbackDependent(f, fieldId, valueToReconstructedId, rebuiltIds, primaryReconstructedId));
    }
  }

  const newSections = schema.sections.map(section => {
    const pos = section.fields.indexOf(fieldId);
    if (pos === -1) return section;
    const fields = [...section.fields];
    fields.splice(pos, 1, ...rebuiltIds);
    return { ...section, fields };
  });

  return { ...schema, fields: newFields, sections: newSections };
}

// Rewrite ONE dependent field that referenced a now-split consolidated field
// (fallback ungroup, bd polyglot-pdf-v444). The inverse of mergeFields'
// rewriteReferences: where merge collapsed N source widgets into option values on
// one consolidated field and retargeted dependents onto it, ungroup must point
// dependents back at the specific reconstructed split fields.
//
//   - show_if `{field: C, operator: equals, value: <optValue>}` -> the dependent
//     fired when the consolidated radio held that option's value. After the split
//     that option is its own field, so this becomes `is_checked` on that field
//     (the runtime value of a standalone checkbox/radio is truthy when selected).
//     A whole-group condition (is_checked/is_not_empty on C, no specific option)
//     or an unmatched value is retargeted to the primary reconstructed field so it
//     does not dangle, with its operator NORMALIZED (see
//     normalizeWholeGroupOperator) so it still fires correctly against a standalone
//     boolean checkbox.
//   - copy_to target arrays containing C are EXPANDED to all reconstructed ids
//     (the rule acted on the whole former group), de-duped.
//
// Returns the same object reference when nothing referenced fieldId (no-op).

// Map a whole-group / unmatched show_if operator (one that tested the
// consolidated field's populated-ness, not a specific option) to an operator that
// evaluates correctly once retargeted to a single standalone BOOLEAN checkbox.
// Without this, the original operator misfires: a checkbox's value is `false` when
// unchecked, so `not_equals ''` / `is_not_empty` is permanently TRUE (false is not
// '' / "" / null), and `equals ''` would never be true. The runtime
// (shouldShowField) reads `is_checked` as truthy-when-true and `is_empty` as
// true-when-false/empty, which IS the populated/empty intent. A genuine
// `equals <non-empty-unmatched>` is left as-is: it stays unsatisfiable (hidden),
// which is the correct "no such option" outcome rather than a spurious show.
function normalizeWholeGroupOperator(cond: ConditionalDisplay): ConditionalDisplay['operator'] {
  const emptyValue = cond.value === undefined || cond.value === null || cond.value === '';
  switch (cond.operator) {
    case 'is_not_empty':
    case 'is_checked':
      return 'is_checked'; // "group populated" -> primary checkbox is checked
    case 'is_empty':
      return 'is_empty'; // "group empty" -> primary checkbox is empty/unchecked
    case 'not_equals':
      // Only UNMATCHED values reach here (a value matching an option is handled
      // exactly in remapFallbackDependent's IF branch). `not_equals <empty>` means
      // "populated" -> is_checked. `not_equals <non-empty-unmatched>` was always
      // true originally (the consolidated never holds a non-option value), and a
      // bare `not_equals <X>` on a boolean checkbox is likewise always true
      // (false !== X, true !== X) -> preserve it to replicate "always show".
      return emptyValue ? 'is_checked' : 'not_equals';
    case 'equals':
      // Only UNMATCHED values reach here. `equals <empty>` means "empty" ->
      // is_empty; an unmatched non-empty equals stays equals (unsatisfiable ->
      // hidden, the correct "no such option" result).
      return emptyValue ? 'is_empty' : 'equals';
    case 'includes':
      // Only an UNMATCHED includes reaches here (a matched one is exact in the
      // remapFallbackAtom IF branch). Membership on a now-standalone boolean
      // checkbox is meaningless; an unmatched option can never be selected, so
      // the intent is unsatisfiable -> hidden. `equals <value>` on a boolean is
      // never true (the box holds true/false, not the slug) -> hidden, correct.
      return 'equals';
    case 'not_includes':
      // Symmetric: an unmatched not_includes was always true (the option can
      // never be present). `not_equals <value>` on a boolean is always true ->
      // always show, replicating the original semantics.
      return 'not_equals';
    default:
      return cond.operator; // comparison/contains operators: preserve (best effort)
  }
}

// Remap ONE atomic condition that referenced the consolidated field to the
// reconstructed split fields (the inverse of mergeFields' rewriteShowIf).
// Returns the remapped atom; callers only invoke it for atoms whose .field is
// the consolidated id.
function remapFallbackAtom(
  cond: ConditionalDisplay,
  valueToReconstructedId: Map<string, string>,
  primaryReconstructedId: string,
): ConditionalDisplay {
  const matchedOptionId = cond.value !== undefined && cond.value !== null
    ? valueToReconstructedId.get(String(cond.value))
    : undefined;
  // Operators that reference a SPECIFIC option by value: equals/not_equals
  // (radio single-select) AND includes/not_includes (checkbox_group
  // membership, bd h76m.10). All four un-merge to the same per-option
  // checkbox condition -- omitting includes/not_includes left a dangling
  // membership op on a now-standalone boolean checkbox that never fired
  // (fresh-eyes P4.2).
  const positiveOption = cond.operator === 'equals' || cond.operator === 'includes';
  const negativeOption = cond.operator === 'not_equals' || cond.operator === 'not_includes';
  if (matchedOptionId && (positiveOption || negativeOption)) {
    // A SPECIFIC option: the inverse for a single option is exact, targeting that
    // option's reconstructed checkbox.
    //   selected(option)     -> is_checked        (shown when that option is set)
    //   NOT selected(option) -> not_equals true   (shown UNLESS that option is set)
    // not_equals must use `not_equals true`, NOT `is_empty`: shouldShowField's
    // is_empty is true only for null/undefined/'' -- an EXPLICITLY unchecked
    // checkbox stores `false`, which is_empty reads as false, so the dependent
    // would be permanently hidden once the box is touched. `not_equals true`
    // reads false===checked, true===unchecked-or-absent -- the correct inverse
    // (bd polyglot-pdf-cjby, fresh-eyes r3).
    return positiveOption
      ? { field: matchedOptionId, operator: 'is_checked' }
      : { field: matchedOptionId, operator: 'not_equals', value: true };
  }
  // Whole-group / unmatched: retarget to the primary so it does not dangle,
  // and NORMALIZE the operator so it fires correctly against a standalone
  // BOOLEAN checkbox. Preserving the original operator silently misfires:
  // `not_equals ''` / `is_not_empty` on an unchecked checkbox (value false)
  // is `false !== '' ` / `false !== ""` == always TRUE, so the dependent
  // would show permanently (real i-90 case: p1_line6c_aptsteflrnumber's
  // `not_equals ''` on the consolidated p1_unit_type6c_unit). Map the intent
  // to a checkbox-sane operator instead (bd polyglot-pdf-v444, fresh-eyes).
  const normalizedOp = normalizeWholeGroupOperator(cond);
  // is_checked / is_empty are value-less operators (shouldShowField ignores
  // value for them); a value-carrying operator (equals/not_equals/...) keeps
  // its original value so the comparison is unchanged.
  const valueLess = normalizedOp === 'is_checked' || normalizedOp === 'is_empty';
  return valueLess
    ? { field: primaryReconstructedId, operator: normalizedOp }
    : { ...cond, field: primaryReconstructedId, operator: normalizedOp };
}

function remapFallbackDependent(
  f: FormField,
  fieldId: string,
  valueToReconstructedId: Map<string, string>,
  rebuiltIds: string[],
  primaryReconstructedId: string,
): FormField {
  let changed = false;
  const next: FormField = { ...f };

  // Remap a show_if/require_if that referenced the now-split consolidated
  // field, atom-wise, preserving the stored shape (legacy or v2 composite --
  // bd h76m.8). show_if AND require_if get the SAME treatment (Codex PR #310
  // round 2: require_if was previously left dangling).
  const remapCond = (cond: FieldCondition): FieldCondition => {
    if (isCompositeCondition(cond)) {
      const out: CompositeConditionalDisplay = {};
      for (const bucket of CONDITION_BUCKETS) {
        const members = cond[bucket];
        if (members) {
          out[bucket] = members.map(atom =>
            atom.field === fieldId
              ? remapFallbackAtom(atom, valueToReconstructedId, primaryReconstructedId)
              : atom,
          );
        }
      }
      return out;
    }
    return remapFallbackAtom(cond, valueToReconstructedId, primaryReconstructedId);
  };

  if (f.show_if && conditionReferencesAny(f.show_if, new Set([fieldId]))) {
    next.show_if = remapCond(f.show_if);
    changed = true;
  }
  if (f.require_if && conditionReferencesAny(f.require_if, new Set([fieldId]))) {
    next.require_if = remapCond(f.require_if);
    changed = true;
  }

  // copy_to target arrays: a single consolidated id expands to the full set of
  // split ids (the rule covered the whole former group).
  const expand = (ids?: string[]): string[] | undefined => {
    if (!ids || !ids.includes(fieldId)) return ids;
    const out: string[] = [];
    for (const id of ids) {
      const repl = id === fieldId ? rebuiltIds : [id];
      for (const r of repl) if (!out.includes(r)) out.push(r);
    }
    return out;
  };

  if (f.copy_to && f.copy_to.includes(fieldId)) {
    next.copy_to = expand(f.copy_to);
    changed = true;
  }

  return changed ? next : f;
}
