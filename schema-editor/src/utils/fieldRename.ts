/**
 * Field-id rename with atomic reference retargeting (bd polyglot-pdf-0x10.1).
 *
 * A field's id is the join key everything else in the schema hangs off:
 * other fields' show_if/require_if atoms (legacy single-atom AND composite
 * all_of/any_of/none_of shapes), section-level show_if, section fields[]
 * membership arrays, copy_to lists, and untyped pass-through structures
 * (supplements[].fields survives load -> save without the editor's types
 * knowing it). Renaming must move ALL of them in ONE commit, or the schema
 * dangles -- so the public API returns a fully-rewritten schema the caller
 * commits once (one undo step).
 *
 * The in-session _ungroup stash is the one structure NOT retargeted: it
 * holds verbatim pre-merge snapshots, and rewriting history is worse than
 * losing it. Any stash that mentions the old id is dropped, so a later
 * ungroup takes the documented lossy reconstruction fallback instead of
 * restoring stale ids.
 */
import type { FormSchema, FormField, FormSection } from '../types/schema';

// Mirrors the backend option-slug convention (conditional_vocabulary):
// lowercase snake_case, starting with a letter.
const ID_PATTERN = /^[a-z][a-z0-9_]*$/;

/** Why this rename cannot happen, or null when it is allowed. An unchanged
 * id returns null (callers treat it as a no-op). */
export function renameBlockReason(
  schema: FormSchema,
  oldId: string,
  newId: string,
): string | null {
  const trimmed = newId.trim();
  if (!trimmed) return 'Field ID cannot be empty.';
  if (trimmed === oldId) return null;
  if (!ID_PATTERN.test(trimmed)) {
    return 'Use snake_case: lowercase letters, digits and underscores, starting with a letter.';
  }
  if (schema.fields.some(f => f.id === trimmed)) {
    return `A field with the ID "${trimmed}" already exists.`;
  }
  return null;
}

const CONDITION_BUCKETS = ['all_of', 'any_of', 'none_of'] as const;

// Retarget every atom of a legacy-or-composite condition whose `field`
// references oldId. Preserves the stored shape; returns the SAME object when
// nothing referenced the old id.
function retargetCondition(cond: unknown, oldId: string, newId: string): unknown {
  if (!cond || typeof cond !== 'object') return cond;
  const c = cond as Record<string, unknown>;
  const isComposite = CONDITION_BUCKETS.some(b => c[b] !== undefined);
  const retargetAtom = (atom: unknown): unknown => {
    if (!atom || typeof atom !== 'object') return atom;
    const a = atom as Record<string, unknown>;
    return a.field === oldId ? { ...a, field: newId } : atom;
  };
  if (isComposite) {
    let touched = false;
    const out: Record<string, unknown> = { ...c };
    for (const bucket of CONDITION_BUCKETS) {
      const members = c[bucket];
      if (Array.isArray(members)) {
        const next = members.map(retargetAtom);
        if (next.some((m, i) => m !== members[i])) {
          out[bucket] = next;
          touched = true;
        }
      }
    }
    return touched ? out : cond;
  }
  return retargetAtom(cond);
}

function mentionsId(value: unknown, id: string): boolean {
  // Conservative deep scan (stash snapshots are small, session-only).
  try {
    return JSON.stringify(value).includes(`"${id}"`);
  } catch {
    return true;
  }
}

/**
 * Rename `oldId` -> `newId`, rewriting every in-schema reference. The caller
 * must have cleared renameBlockReason first; an unchanged/blocked rename
 * returns the schema untouched. Returns a new schema object (one commit).
 */
export function renameFieldId(
  schema: FormSchema,
  oldId: string,
  newId: string,
): FormSchema {
  newId = newId.trim();
  if (newId === oldId || renameBlockReason(schema, oldId, newId) !== null) {
    return schema;
  }

  const fields: FormField[] = schema.fields.map(f => {
    let out = f as FormField & Record<string, unknown>;
    const patch: Record<string, unknown> = {};

    if (out.id === oldId) patch.id = newId;

    for (const kind of ['show_if', 'require_if'] as const) {
      const cond = out[kind];
      if (cond) {
        const next = retargetCondition(cond, oldId, newId);
        if (next !== cond) patch[kind] = next;
      }
    }

    const copyTo = out.copy_to;
    if (Array.isArray(copyTo) && copyTo.includes(oldId)) {
      patch.copy_to = copyTo.map(id => (id === oldId ? newId : id));
    }

    // copy_from is copy_to's untyped symmetric twin: a SINGLE field-id string
    // real kits carry (the i-90 page-header repeats), declared in neither the
    // editor's FormField type nor the backend model -- it survives save
    // untouched, so a missed retarget dangles silently (Opus review finding).
    if ((out as Record<string, unknown>).copy_from === oldId) {
      patch.copy_from = newId;
    }

    // address_fields is another untyped pass-through (backend AddressFields:
    // a flat slot -> field-id map, street/apt/city/...). The backend integrity
    // check does not walk it, so a missed slot would dangle SILENTLY on save
    // (Opus review finding on bd 0x10.1).
    const addr = (out as Record<string, unknown>).address_fields;
    if (addr && typeof addr === 'object' && !Array.isArray(addr)) {
      const entries = Object.entries(addr as Record<string, unknown>);
      if (entries.some(([, v]) => v === oldId)) {
        patch.address_fields = Object.fromEntries(
          entries.map(([k, v]) => [k, v === oldId ? newId : v]),
        );
      }
    }

    // The session-only merge stash holds verbatim pre-merge snapshots; a
    // stash mentioning the renamed id would restore stale references on
    // ungroup, so it is dropped (ungroup then takes the documented
    // reconstruction fallback).
    const stash = (out as Record<string, unknown>)['_ungroup'];
    if (stash !== undefined && mentionsId(stash, oldId)) {
      const rest = { ...(out as Record<string, unknown>), ...patch };
      delete rest['_ungroup'];
      return rest as unknown as FormField;
    }

    return Object.keys(patch).length > 0
      ? ({ ...(out as Record<string, unknown>), ...patch } as unknown as FormField)
      : f;
  });

  const sections: FormSection[] = schema.sections.map(s => {
    const patch: Record<string, unknown> = {};
    if (Array.isArray(s.fields) && s.fields.includes(oldId)) {
      patch.fields = s.fields.map(id => (id === oldId ? newId : id));
    }
    if (s.show_if) {
      const next = retargetCondition(s.show_if, oldId, newId);
      if (next !== s.show_if) patch.show_if = next;
    }
    return Object.keys(patch).length > 0 ? { ...s, ...patch } : s;
  });

  const out: FormSchema = { ...schema, fields, sections };

  // Untyped pass-through: supplements[].fields is a field-id list the backend
  // integrity-checks, but the editor's FormSchema type does not declare it --
  // it survives load -> {...schema} -> save, so the rename must chase it too.
  const supplements = (schema as unknown as Record<string, unknown>).supplements;
  if (Array.isArray(supplements)) {
    (out as unknown as Record<string, unknown>).supplements = supplements.map(s => {
      if (!s || typeof s !== 'object') return s;
      const supp = s as Record<string, unknown>;
      if (Array.isArray(supp.fields) && supp.fields.includes(oldId)) {
        return { ...supp, fields: supp.fields.map(id => (id === oldId ? newId : id)) };
      }
      return s;
    });
  }

  return out;
}
