// Pure merge/split (group/ungroup) helpers for the schema editor (bd
// polyglot-pdf-s4dp.1). A real form's "check one box" radio group arrives from
// extraction as N separate radio/checkbox fields; the human must be able to
// MERGE them into one consolidated options[] field (each option carrying its
// source widget's pdf_field_name) and UN-merge back. The backend model + runtime
// already consume this consolidated shape (FieldOption.pdf_field_name,
// consolidated_widgets[]); this module is purely an editor-side mutation.
//
// SHAPE (matches the real consolidated fields in schemas/i-90/i-90_schema.json):
//   - the merged field has options[] where each option is
//     { value, label, pdf_field_name } -- value is the source field's id (a
//     stable, unique token), pdf_field_name is the source widget's full name.
//   - consolidated_widgets[] mirrors each option.value, so the runtime can map a
//     selected option back to its PDF widget.
//
// MERGE SEMANTICS (the care is here, not the UI -- per the bead):
//   - the FIRST field in the selection is the PRIMARY: its id, section_id,
//     spoken_name, help, validation, and section slot all survive. The merged
//     field keeps the primary's id so existing show_if / controls_fields
//     references to it stay valid.
//   - every selected field (primary included) contributes one option.
//   - un-merge is RECONSTRUCTIVE: it rebuilds one separate field per option from
//     the option's value (-> id), pdf_field_name, and label. This keeps the saved
//     schema clean (no private stash keys; byte-for-byte the runtime's real
//     consolidated shape) at the cost of not restoring rich per-source metadata
//     that simple radio/checkbox widgets do not carry. The primary's id/type are
//     preserved so a merge -> un-merge of the primary round-trips its identity.

import type { FormField, FormSchema, FieldOption } from '../types/schema';

// Field types that can participate in a merge group. A consolidated options[]
// field is a single-select group, so only radio/checkbox source fields qualify.
const GROUPABLE_TYPES = new Set<FormField['type']>(['radio', 'checkbox']);

export function isGroupableField(field: FormField): boolean {
  return GROUPABLE_TYPES.has(field.type);
}

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
  // id of the merged (primary) field, so the caller can re-select it.
  mergedFieldId: string;
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
    return { schema, mergedFieldId: fieldIds[0] };
  }

  const primary = distinct[0];
  const mergedIds = new Set(distinct.map(f => f.id));

  // Build one option per source field. value = source id (stable/unique);
  // pdf_field_name carried from the source widget; label best-effort human text.
  const options: FieldOption[] = distinct.map(f => ({
    value: f.id,
    label: optionLabelFor(f),
    pdf_field_name: f.pdf_field_name,
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
  const newFields: FormField[] = [];
  for (const f of schema.fields) {
    if (f.id === primary.id) {
      newFields.push(mergedField);
    } else if (!mergedIds.has(f.id)) {
      newFields.push(f);
    }
    // merged-away (non-primary) fields are dropped
  }

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
      type: 'checkbox',
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
