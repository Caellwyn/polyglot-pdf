// Pure merge/split (group/ungroup) helpers for the schema editor (bd
// polyglot-pdf-s4dp.1). A real form's "check one box" radio group arrives from
// extraction as N separate radio/checkbox fields; the human must be able to
// MERGE them into one consolidated options[] field (each option carrying its
// source widget's pdf_field_name) and UN-merge back. The backend model + runtime
// already consume this consolidated shape (FieldOption.pdf_field_name,
// consolidated_widgets[]); this module is purely an editor-side mutation.
//
// SHAPE (same STRUCTURE as the real consolidated fields in
// schemas/i-90/i-90_schema.json -- a radio field with options[] +
// consolidated_widgets[]):
//   - each option is { value, label, pdf_field_name, source_type } -- pdf_field_name
//     is the source widget's full name; source_type records the widget's original
//     type for a lossless un-merge.
//   - value is the source field's id (a stable, unique token). NOTE this differs
//     in CONTENT from i-90's hand-built consolidated fields, where option.value is
//     the PDF widget's short name (e.g. "P1_checkbox4[0]"); the structure is the
//     same and the runtime matches on option.value regardless of what token it
//     holds, but a newly-merged field's option.value is the schema field id.
//   - consolidated_widgets[] mirrors each option.value, so the runtime can map a
//     selected option back to its PDF widget.
//
// MERGE SEMANTICS (the care is here, not the UI -- per the bead):
//   - the FIRST field in the selection is the PRIMARY: its id, section_id,
//     spoken_name, help, validation, and section slot all survive. The merged
//     field keeps the primary's id so existing show_if / controls_fields
//     references to it stay valid; references to MERGED-AWAY fields are rewritten
//     to point at the primary (so none dangle).
//   - every selected field (primary included) contributes one option. Already-
//     consolidated fields are NOT groupable (would drop their existing options).
//   - un-merge is RECONSTRUCTIVE: it rebuilds one separate field per option from
//     the option's value (-> id), pdf_field_name, label, and source_type. This
//     keeps the saved schema clean (no private stash object) at the cost of not
//     restoring rich per-source metadata (help/validation) that simple
//     radio/checkbox widgets do not carry. Each field's id and TYPE round-trip
//     through a merge -> un-merge.

import type { FormField, FormSchema, FieldOption, ControlActionKey } from '../types/schema';

// Field types that can participate in a merge group. A consolidated options[]
// field is a single-select group, so only radio/checkbox source fields qualify.
const GROUPABLE_TYPES = new Set<FormField['type']>(['radio', 'checkbox']);

// A field is groupable if it is a radio/checkbox AND is not itself already a
// consolidated options group. Excluding already-consolidated fields prevents a
// "merge of a merged field" that would silently drop its existing options[]
// (the {...primary, options} spread in mergeFields would overwrite them) --
// bd polyglot-pdf-s4dp.1, fresh-eyes finding.
export function isGroupableField(field: FormField): boolean {
  if (!GROUPABLE_TYPES.has(field.type)) return false;
  return !(field.options && field.options.length > 0);
}

// The controls_fields action arrays whose entries are target field ids that a
// merge must rewrite when a referenced field is merged away.
const CONTROL_ACTION_KEYS: ControlActionKey[] = [
  'shows', 'hides', 'unlocks', 'locks', 'makes_required', 'makes_optional',
];

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

export interface MergeResult {
  schema: FormSchema;
  // id of the merged (primary) field, so the caller can re-select it. null when
  // the merge was a no-op (invalid selection) AND no usable primary id exists
  // (e.g. an empty fieldIds list) -- the caller treats schema-unchanged as the
  // no-op signal and does not re-select on null.
  mergedFieldId: string | null;
}

// Rewrite every reference to a merged-away (non-primary) field id so it points
// at the surviving primary instead. After a merge, the merged-away fields no
// longer exist, so any field whose show_if / controls_fields targeted one would
// be left dangling (validateSchema would warn, and the runtime's conditional
// engine could misbehave). Pointing those references at the primary keeps the
// conditional logic intact -- the primary now carries those widgets as options.
function rewriteReferences(
  fields: FormField[],
  mergedAway: Set<string>,
  primaryId: string,
): FormField[] {
  const remap = (id: string): string => (mergedAway.has(id) ? primaryId : id);
  const remapList = (ids?: string[]): string[] | undefined => {
    if (!ids) return ids;
    // remap then de-dupe (two merged-away ids could both map to the primary).
    const out: string[] = [];
    for (const id of ids) {
      const r = remap(id);
      if (!out.includes(r)) out.push(r);
    }
    return out;
  };

  return fields.map(f => {
    let changed = false;
    const next: FormField = { ...f };

    if (f.show_if && mergedAway.has(f.show_if.field)) {
      next.show_if = { ...f.show_if, field: primaryId };
      changed = true;
    }

    // copy_to is a plain string[] of target field ids (unused in current real
    // schemas, but rewritten for completeness so no reference list is skipped).
    if (f.copy_to && f.copy_to.some(id => mergedAway.has(id))) {
      next.copy_to = remapList(f.copy_to);
      changed = true;
    }

    if (f.controls_fields) {
      // Track controls changes separately so a show_if/copy_to-only change does
      // NOT trigger a spurious rewrite of an otherwise-untouched controls array.
      let controlsChanged = false;
      const newControls = f.controls_fields.map(ctrl => {
        const c = { ...ctrl };
        for (const key of CONTROL_ACTION_KEYS) {
          const list = ctrl[key];
          if (list && list.some(id => mergedAway.has(id))) {
            c[key] = remapList(list);
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
  });
}

// Merge the given fields (by id, in selection order) into one consolidated
// options[] field. Returns the original schema unchanged if the selection is
// invalid (fewer than 2 resolvable groupable fields). The first id is the
// primary whose identity survives.
export function mergeFields(schema: FormSchema, fieldIds: string[]): MergeResult {
  const byId = new Map(schema.fields.map(f => [f.id, f]));
  const selected = fieldIds
    .map(id => byId.get(id))
    .filter((f): f is FormField => f !== undefined && isGroupableField(f));

  // Need at least two distinct groupable fields to form a group.
  const distinct = Array.from(new Set(selected.map(f => f.id)))
    .map(id => byId.get(id)!)
    // preserve selection order
    .sort((a, b) => fieldIds.indexOf(a.id) - fieldIds.indexOf(b.id));

  if (distinct.length < 2) {
    // No-op: signal via unchanged schema; mergedFieldId is the first selected id
    // if one exists, else null (empty/invalid selection) -- never undefined.
    return { schema, mergedFieldId: fieldIds[0] ?? null };
  }

  const primary = distinct[0];
  const mergedIds = new Set(distinct.map(f => f.id));
  const mergedAway = new Set(distinct.slice(1).map(f => f.id)); // non-primary

  // Build one option per source field. value = source id (stable/unique);
  // pdf_field_name carried from the source widget; label best-effort human text;
  // source_type records the widget's original type so un-merge can restore it.
  const options: FieldOption[] = distinct.map(f => ({
    value: f.id,
    label: optionLabelFor(f),
    pdf_field_name: f.pdf_field_name,
    source_type: f.type,
  }));

  const mergedField: FormField = {
    ...primary,
    // A consolidated group is single-select; present it as a radio.
    type: 'radio',
    options,
    consolidated_widgets: distinct.map(f => f.id),
  };

  // Replace the primary in place; drop the other merged fields. Keeping the
  // primary's position means the field list / section order barely shifts.
  const replacedFields: FormField[] = [];
  for (const f of schema.fields) {
    if (f.id === primary.id) {
      replacedFields.push(mergedField);
    } else if (!mergedIds.has(f.id)) {
      replacedFields.push(f);
    }
    // merged-away (non-primary) fields are dropped
  }

  // Rewrite any show_if / controls_fields references to a merged-away id so they
  // point at the surviving primary instead of dangling (fresh-eyes finding).
  const newFields = rewriteReferences(replacedFields, mergedAway, primary.id);

  // Remove merged-away ids from every section's field list so section ordering
  // stays valid (validateSchema flags a section referencing a missing field).
  const newSections = schema.sections.map(section => {
    const fields = section.fields.filter(id => id === primary.id || !mergedIds.has(id));
    return fields.length === section.fields.length ? section : { ...section, fields };
  });

  return {
    schema: { ...schema, fields: newFields, sections: newSections },
    mergedFieldId: primary.id,
  };
}

// Un-merge a consolidated field back into one standalone field per option. The
// first reconstructed field reuses the merged field's id/section/type so the
// primary's identity round-trips; the rest derive their id from option.value.
// Returns the schema unchanged if the field is not un-groupable.
export function ungroupField(schema: FormSchema, fieldId: string): FormSchema {
  const field = schema.fields.find(f => f.id === fieldId);
  if (!field || !field.options || !canUngroup(field)) return schema;

  // Ids that already exist OTHER than this consolidated field -- a reconstructed
  // id must not collide with one of these (that would silently merge two fields
  // back together). The consolidated field id itself is excluded: option 0
  // legitimately reclaims it as the primary.
  const otherIds = new Set(
    schema.fields.map(f => f.id).filter(id => id !== fieldId)
  );

  // Reconstruct one field per option. Option 0 keeps the primary id; the rest
  // derive their id from option.value, de-duped against surviving fields AND
  // already-rebuilt ids.
  const usedIds = new Set<string>();
  const rebuilt: FormField[] = field.options.map((opt, idx) => {
    let id: string;
    if (idx === 0) {
      id = fieldId; // primary keeps its id
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

    return {
      id,
      name: opt.label || id,
      // Restore the source widget's original type recorded at merge time; fall
      // back to checkbox for options merged before source_type was tracked (or
      // hand-authored consolidated fields).
      type: opt.source_type || 'checkbox',
      section_id: field.section_id,
      pdf_field_name: opt.pdf_field_name || '',
      label: opt.label,
      spoken_name: idx === 0 ? field.spoken_name : undefined,
      read_only: field.read_only,
      required: field.required,
    };
  });

  // Splice the rebuilt fields in where the consolidated field was.
  const newFields: FormField[] = [];
  for (const f of schema.fields) {
    if (f.id === fieldId) {
      newFields.push(...rebuilt);
    } else {
      newFields.push(f);
    }
  }

  // Restore the rebuilt ids into the consolidated field's section slot (replace
  // the single primary id with the full rebuilt id list, in order).
  const rebuiltIds = rebuilt.map(f => f.id);
  const newSections = schema.sections.map(section => {
    const pos = section.fields.indexOf(fieldId);
    if (pos === -1) return section;
    const fields = [...section.fields];
    fields.splice(pos, 1, ...rebuiltIds);
    return { ...section, fields };
  });

  return { ...schema, fields: newFields, sections: newSections };
}
