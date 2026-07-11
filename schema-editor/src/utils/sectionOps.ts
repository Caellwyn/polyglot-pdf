// Section CRUD for the schema editor (bd polyglot-pdf-6cfu.3).
//
// Pure functions over the loaded schema: each op returns a NEW
// {fields, sections, parts} triple for App.handleUpdateDivisions to commit
// atomically (one undo step). Invariants every op preserves:
//   - section.fields[] and field.section_id stay bidirectionally consistent;
//   - parts[].section_ids never reference a removed section (a part left
//     empty is dropped);
//   - section `order` is renumbered 1..n to match array order (FieldList
//     renders array order; the persisted `order` must agree);
//   - a manually minted section id never squats on the `sec_to_review`
//     review-gate prefix (the publish gate keys on it, backend
//     schema_lint.TO_REVIEW_PREFIX);
//   - section-level show_if survives untouched on every section the op does
//     not remove (removal drops the removed section's own show_if with it --
//     nothing else references a section id from a condition).

import type { FormField, FormPart, FormSection } from '../types/schema';

// Mirrors backend/services/schema_lint.py TO_REVIEW_PREFIX (the review gate).
export const TO_REVIEW_PREFIX = 'sec_to_review';

export interface DivisionsPatch {
  fields: FormField[];
  sections: FormSection[];
  parts?: FormPart[];
}

/** True for a section the deterministic derivation filed for human review. */
export function isToReviewSection(sectionId: string | undefined | null): boolean {
  return !!sectionId && sectionId.startsWith(TO_REVIEW_PREFIX);
}

function slugify(label: string): string {
  const ascii = label
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '') // strip combining accents
    // eslint-disable-next-line no-control-regex
    .replace(/[^\x00-\x7f]/g, '')
    .toLowerCase();
  return ascii.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'section';
}

/** Mint a unique section id from a label; never squats the review prefix. */
export function mintSectionId(label: string, existing: FormSection[]): string {
  let base = `sec_${slugify(label)}`;
  if (base.startsWith(TO_REVIEW_PREFIX)) base = `sec_x_${slugify(label)}`;
  const used = new Set(existing.map(s => s.id));
  let candidate = base;
  let n = 1;
  while (used.has(candidate)) candidate = `${base}_${++n}`;
  return candidate;
}

function renumber(sections: FormSection[]): FormSection[] {
  return sections.map((s, i) => (s.order === i + 1 ? s : { ...s, order: i + 1 }));
}

/** Drop a section id from every part; drop parts left with no sections. */
function pruneParts(parts: FormPart[] | undefined, removedId: string):
    FormPart[] | undefined {
  if (!parts) return parts;
  const next = parts
    .map(p => (p.section_ids.includes(removedId)
      ? { ...p, section_ids: p.section_ids.filter(id => id !== removedId) }
      : p))
    .filter(p => p.section_ids.length > 0);
  return next;
}

/** Add a new empty section at the end. */
export function addSection(
  fields: FormField[], sections: FormSection[], parts: FormPart[] | undefined,
  label: string,
): DivisionsPatch {
  const trimmed = label.trim() || 'New section';
  const section: FormSection = {
    id: mintSectionId(trimmed, sections),
    label: trimmed,
    order: sections.length + 1,
    fields: [],
  };
  return { fields, sections: renumber([...sections, section]), parts };
}

/** Rename a section's LABEL (the id stays stable: session state, parts and
 *  the review gate all key on ids). */
export function renameSection(
  fields: FormField[], sections: FormSection[], parts: FormPart[] | undefined,
  sectionId: string, newLabel: string,
): DivisionsPatch {
  const trimmed = newLabel.trim();
  if (!trimmed) return { fields, sections, parts };
  return {
    fields,
    sections: sections.map(s => (s.id === sectionId ? { ...s, label: trimmed } : s)),
    parts,
  };
}

/**
 * Remove a section. Its fields re-file to `destinationId`, or -- when null --
 * become uncategorized (section_id cleared; FieldList's "_orphan" bucket).
 * The removed section's own show_if disappears with it; every other
 * section is untouched.
 */
export function removeSection(
  fields: FormField[], sections: FormSection[], parts: FormPart[] | undefined,
  sectionId: string, destinationId: string | null,
): DivisionsPatch {
  const source = sections.find(s => s.id === sectionId);
  if (!source || destinationId === sectionId) return { fields, sections, parts };
  // The moved set is the fields that POINT AT the section (field.section_id
  // is authoritative), not the section's fields[] listing: a loaded kit can
  // carry drift between the two (the pre-existing FieldEditor section
  // dropdown rewrites only section_id -- bd polyglot-pdf-w7rg), and trusting
  // the listing would double-list a drifted-away field or strand a
  // drifted-in one. Order: the listing's order first for ids that point
  // back, then any pointing-but-unlisted fields in schema order -- so the
  // op also HEALS the drift it touches.
  const pointing = new Set(
    fields.filter(f => f.section_id === sectionId).map(f => f.id));
  const moved = [
    ...source.fields.filter(id => pointing.has(id)),
    ...fields.filter(f => pointing.has(f.id) && !source.fields.includes(f.id))
      .map(f => f.id),
  ];
  const nextFields = moved.length === 0 ? fields : fields.map(f => {
    if (f.section_id !== sectionId) return f;
    return { ...f, section_id: destinationId ?? '' };
  });
  const nextSections = renumber(
    sections
      .filter(s => s.id !== sectionId)
      .map(s => (destinationId && s.id === destinationId && moved.length > 0
        ? { ...s, fields: [...s.fields, ...moved.filter(id => !s.fields.includes(id))] }
        : s)),
  );
  return { fields: nextFields, sections: nextSections, parts: pruneParts(parts, sectionId) };
}

/** The count a remove/merge will actually move (matches removeSection). */
export function movedFieldCount(fields: FormField[], sectionId: string): number {
  return fields.reduce((n, f) => n + (f.section_id === sectionId ? 1 : 0), 0);
}

/**
 * Merge `sourceId` into `targetId`: the source's fields append to the target
 * (order preserved) and the source section disappears. The exact workflow
 * that empties a 'To review' section. The source's own show_if is discarded
 * with it (the target keeps its own).
 */
export function mergeSections(
  fields: FormField[], sections: FormSection[], parts: FormPart[] | undefined,
  sourceId: string, targetId: string,
): DivisionsPatch {
  if (sourceId === targetId) return { fields, sections, parts };
  const source = sections.find(s => s.id === sourceId);
  const target = sections.find(s => s.id === targetId);
  if (!source || !target) return { fields, sections, parts };
  return removeSection(fields, sections, parts, sourceId, targetId);
}

/** Field ids still sitting in 'To review' sections (the review-gate count). */
export function toReviewFieldIds(fields: FormField[]): string[] {
  return fields.filter(f => isToReviewSection(f.section_id)).map(f => f.id);
}
