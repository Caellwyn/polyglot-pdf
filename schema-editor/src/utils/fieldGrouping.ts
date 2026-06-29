// Pure merge/split (group/ungroup) helpers for the schema editor (bd
// polyglot-pdf-s4dp.1). A real form's "check one box" radio group arrives from
// extraction as N separate radio/checkbox fields; the human must be able to
// MERGE them into one consolidated options[] field (each option carrying its
// source widget's pdf_field_name) and UN-merge back. The backend model + runtime
// already consume this consolidated shape (FieldOption.pdf_field_name,
// consolidated_widgets[]); this module is purely an editor-side mutation.
//
// LOSSLESS, SEMANTICS-AWARE design (Codex review on PR #256):
//   - Merge STASHES each source field's complete original FormField, plus the
//     original conditional references it rewrites, under a private _ungroup key
//     on the merged field. Un-merge restores them verbatim -- so help, validation,
//     hidden, show_if, controls_fields and every other per-field property survive
//     a merge -> un-merge round-trip (NOT a lossy whitelist rebuild). The backend
//     and runtime ignore the extra _ungroup key.
//   - Merge REWRITES dependent conditionals with the CORRECT runtime semantics:
//     a reference that selected a now-merged-away widget ("is_checked" on that
//     widget) becomes "equals <that widget's option value>" on the consolidated
//     radio, because the merged field's runtime value is the selected option's
//     value (see frontend shouldShowField). A bare id swap would leave an
//     is_checked condition that never fires against a radio. Un-merge restores the
//     original conditions from the stash.
//   - Guards: only radio/checkbox fields that (a) are not already consolidated and
//     (b) carry a pdf_field_name are groupable; a merge is rejected if the
//     selection spans more than one section (which would silently move a field
//     across the Form > Parts > Sections hierarchy).
//
// SHAPE (same structure as i-90's hand-built consolidated fields): the merged
// field is a radio with options[] (each { value, label, pdf_field_name }) +
// consolidated_widgets[]. option.value is the source field's id; the runtime
// matches on option.value regardless of the token it holds.

import type {
  FormField,
  FormSchema,
  FieldOption,
  ControlActionKey,
  ConditionalDisplay,
  ConditionalControl,
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

// The controls_fields action arrays whose entries are target field ids that a
// merge must rewrite when a referenced field is merged away.
const CONTROL_ACTION_KEYS: ControlActionKey[] = [
  'shows', 'hides', 'unlocks', 'locks', 'makes_required', 'makes_optional',
];

// "Selection" operators -- conditions that test whether a (checkbox/radio) widget
// is the selected one. When that widget is merged into a consolidated radio, the
// runtime value becomes the selected option's value, so these must convert to
// `equals <option value>` rather than keep a widget-level is_checked/equals.
const SELECTION_OPERATORS = new Set(['is_checked', 'equals', 'is_not_empty']);

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
  // Dependent fields whose show_if / controls_fields this merge rewrote, with
  // their pre-merge values, so un-merge can restore them verbatim.
  rewrites: Array<{
    fieldId: string;
    show_if?: ConditionalDisplay;
    controls_fields?: ConditionalControl[];
    copy_to?: string[];
    // sentinels distinguishing "had no key" from "key not rewritten" on restore.
    had_show_if: boolean;
    had_controls: boolean;
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
): ConditionalDisplay | null {
  if (!mergedAwayToValue.has(cond.field)) return null; // not pointing at a merged-away field
  const optionValue = mergedAwayToValue.get(cond.field)!;
  if (SELECTION_OPERATORS.has(cond.operator)) {
    return { field: primaryId, operator: 'equals', value: optionValue };
  }
  // A non-selection operator (e.g. is_empty) keeps its operator but retargets.
  return { ...cond, field: primaryId };
}

// Rewrite every dependent field's show_if / controls_fields that referenced a
// merged-away field. Returns the rewritten fields AND a record of what changed
// (so un-merge can restore the originals). mergedAwayToValue maps each
// merged-away field id to its option value on the consolidated radio.
function rewriteReferences(
  fields: FormField[],
  mergedAwayToValue: Map<string, string>,
  primaryId: string,
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
      fieldId: f.id, had_show_if: !!f.show_if, had_controls: !!f.controls_fields,
      had_copy_to: !!f.copy_to,
    };
    let recorded = false;

    if (f.show_if && mergedAway.has(f.show_if.field)) {
      const rewritten = rewriteShowIf(f.show_if, mergedAwayToValue, primaryId);
      if (rewritten) {
        record.show_if = f.show_if; // original
        next.show_if = rewritten;
        changed = true;
        recorded = true;
      }
    }

    // copy_to is a plain string[] of target field ids (unused in current real
    // schemas, but rewritten for completeness so no reference list dangles).
    if (f.copy_to && f.copy_to.some(id => mergedAway.has(id))) {
      record.copy_to = f.copy_to; // original
      next.copy_to = remapControlList(f.copy_to);
      changed = true;
      recorded = true;
    }

    if (f.controls_fields) {
      let controlsChanged = false;
      const newControls = f.controls_fields.map(ctrl => {
        const c = { ...ctrl };
        for (const key of CONTROL_ACTION_KEYS) {
          const list = ctrl[key];
          if (list && list.some(id => mergedAway.has(id))) {
            c[key] = remapControlList(list);
            controlsChanged = true;
          }
        }
        return c;
      });
      if (controlsChanged) {
        record.controls_fields = f.controls_fields; // original
        next.controls_fields = newControls;
        changed = true;
        recorded = true;
      }
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
export function mergeFields(schema: FormSchema, fieldIds: string[]): MergeResult {
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

  // option.value = source id (stable/unique); each merged-away id maps to its
  // option value so dependent conditionals can be rewritten with correct semantics.
  const mergedAwayToValue = new Map<string, string>();
  for (const f of distinct.slice(1)) mergedAwayToValue.set(f.id, f.id);

  const options: FieldOption[] = distinct.map(f => ({
    value: f.id,
    label: optionLabelFor(f),
    pdf_field_name: f.pdf_field_name,
    source_type: f.type,
  }));

  // Remap merged-away ids -> primary across a control rule's action-target arrays
  // (a rule pointing at a sibling that is now only an option must not dangle).
  const remapControlTargets = (ctrl: ConditionalControl): ConditionalControl => {
    const c = { ...ctrl };
    for (const key of CONTROL_ACTION_KEYS) {
      const list = ctrl[key];
      if (list && list.some(id => mergedAwayToValue.has(id))) {
        const out: string[] = [];
        for (const id of list) {
          const r = mergedAwayToValue.has(id) ? primary.id : id;
          if (!out.includes(r)) out.push(r);
        }
        c[key] = out;
      }
    }
    return c;
  };

  // Carry each NON-PRIMARY source's own trigger-side controls onto the merged
  // radio, re-keyed to fire when that option is selected (operator: equals,
  // value: the option value). Otherwise merging A+B would drop the rule by which
  // selecting B unlocked/showed follow-up fields (Codex PR #256). Each carried
  // rule's TARGET arrays are also remapped, so a rule that targeted another
  // merged-away sibling does not dangle (Opus fallback review).
  const carriedControls: ConditionalControl[] = [];
  for (const f of distinct.slice(1)) {
    for (const ctrl of f.controls_fields || []) {
      carriedControls.push({ ...remapControlTargets(ctrl), operator: 'equals', value: f.id });
    }
  }

  // Replace the primary in place; drop the other merged fields. Rewrite dependent
  // conditionals on the SURVIVING fields, recording originals for a lossless undo.
  const survivors: FormField[] = [];
  for (const f of schema.fields) {
    if (f.id === primary.id) continue; // primary re-added below as the merged field
    if (!mergedIds.has(f.id)) survivors.push(f);
  }
  const { fields: rewrittenSurvivors, rewrites } = rewriteReferences(
    survivors, mergedAwayToValue, primary.id,
  );

  // The PRIMARY's own references to merged-away siblings must be rewritten too
  // (it is excluded from `survivors`). show_if / copy_to retarget to the primary;
  // its own controls' target arrays are remapped (Opus fallback review).
  let primaryShowIf = primary.show_if;
  if (primaryShowIf && mergedAwayToValue.has(primaryShowIf.field)) {
    const rw = rewriteShowIf(primaryShowIf, mergedAwayToValue, primary.id);
    // A primary gated on a sibling option would become self-referential (the
    // radio shown only when it equals one of its own option values -- an
    // unreachable field, since it is hidden until set). Drop it instead of
    // emitting an unsatisfiable condition (Opus fallback review, round 2).
    primaryShowIf = rw && rw.field !== primary.id ? rw : undefined;
  }
  let primaryCopyTo = primary.copy_to;
  if (primaryCopyTo && primaryCopyTo.some(id => mergedAwayToValue.has(id))) {
    const out: string[] = [];
    for (const id of primaryCopyTo) {
      const r = mergedAwayToValue.has(id) ? primary.id : id;
      if (!out.includes(r)) out.push(r);
    }
    primaryCopyTo = out;
  }
  // The primary's own trigger-side controls fire on its (now radio) value. A
  // widget-level selection operator (is_checked) would never fire against a
  // radio, so re-key it to "equals the primary's option value" -- the same fix
  // applied to carried non-primary controls (Opus fallback review, round 2).
  const primaryControls = (primary.controls_fields || []).map(ctrl => {
    const remapped = remapControlTargets(ctrl);
    return SELECTION_OPERATORS.has(ctrl.operator)
      ? { ...remapped, operator: 'equals' as const, value: primary.id }
      : remapped;
  });

  // The merged field carries the primary's identity + the stash for un-merge.
  // show_if / copy_to / controls_fields are set EXPLICITLY (not via a conditional
  // spread) so a dropped/rewritten value OVERRIDES the one inherited from
  // {...primary} -- a conditional spread would silently keep the stale inherited
  // value (e.g. a dropped self-referential show_if would survive). Round 2 fix.
  const stash: UngroupStash = { sources: distinct, rewrites };
  const mergedControls = [...primaryControls, ...carriedControls];
  const mergedField = {
    ...primary,
    type: 'radio',
    options,
    consolidated_widgets: distinct.map(f => f.id),
    [STASH_KEY]: stash,
  } as unknown as Record<string, unknown>;
  if (primaryShowIf) mergedField.show_if = primaryShowIf;
  else delete mergedField.show_if;
  if (primaryCopyTo) mergedField.copy_to = primaryCopyTo;
  else delete mergedField.copy_to;
  if (mergedControls.length > 0) mergedField.controls_fields = mergedControls;
  else delete mergedField.controls_fields;
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
        const restored = { ...f };
        if (r.had_show_if) restored.show_if = r.show_if;
        else delete (restored as Record<string, unknown>).show_if;
        if (r.had_controls) restored.controls_fields = r.controls_fields;
        else delete (restored as Record<string, unknown>).controls_fields;
        if (r.had_copy_to) restored.copy_to = r.copy_to;
        else delete (restored as Record<string, unknown>).copy_to;
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
    if (opt.value !== undefined && opt.value !== null) {
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
//     or an equals whose value matches no option is retargeted to the primary
//     reconstructed field so it does not dangle; other operators retarget but keep
//     their operator (best effort).
//   - controls_fields / copy_to target arrays containing C are EXPANDED to all
//     reconstructed ids (the rule acted on the whole former group), de-duped.
//
// Returns the same object reference when nothing referenced fieldId (no-op).
function remapFallbackDependent(
  f: FormField,
  fieldId: string,
  valueToReconstructedId: Map<string, string>,
  rebuiltIds: string[],
  primaryReconstructedId: string,
): FormField {
  let changed = false;
  const next: FormField = { ...f };

  if (f.show_if && f.show_if.field === fieldId) {
    const cond = f.show_if;
    if (SELECTION_OPERATORS.has(cond.operator) && cond.value !== undefined &&
        valueToReconstructedId.has(String(cond.value))) {
      next.show_if = {
        field: valueToReconstructedId.get(String(cond.value))!,
        operator: 'is_checked',
      };
    } else {
      // whole-group / unmatched: retarget to the primary so it does not dangle.
      next.show_if = { ...cond, field: primaryReconstructedId };
    }
    changed = true;
  }

  // copy_to / controls_fields target arrays: a single consolidated id expands to
  // the full set of split ids (the rule covered the whole former group).
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

  if (f.controls_fields) {
    let controlsChanged = false;
    const newControls = f.controls_fields.map(ctrl => {
      const c = { ...ctrl };
      for (const key of CONTROL_ACTION_KEYS) {
        const list = ctrl[key];
        if (list && list.includes(fieldId)) {
          c[key] = expand(list);
          controlsChanged = true;
        }
      }
      return c;
    });
    if (controlsChanged) {
      next.controls_fields = newControls;
      changed = true;
    }
  }

  return changed ? next : f;
}
