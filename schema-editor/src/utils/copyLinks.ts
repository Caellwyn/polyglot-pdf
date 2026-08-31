/**
 * Auto-populate ("copy") links, editable from BOTH ends (bd polyglot-pdf-g33y2).
 *
 * STORAGE: `copy_to` on the SOURCE field -- a list of target field ids. That is
 * the only representation, and it is the one the voice runtime actually reads
 * (SchemaForm's handleFieldChange fans a value out to every copy_to target and
 * stamps them confirmed).
 *
 * UI: the maintainer asked to see and edit the relationship from either side --
 * standing on A, "copies to B"; standing on B, "copied from A". So the
 * target-side view is DERIVED by scanning fields[] rather than stored. One
 * source of truth means the two directions can never disagree, and no migration
 * is needed for kits already carrying copy_to.
 *
 * Not to be confused with `copy_from`, an untyped key some code retargets but
 * which no model declares, no lint checks, and the runtime IGNORES -- authoring
 * one would produce a link that populates nothing (bd polyglot-pdf-nkhca).
 *
 * Every helper here is pure and total: a malformed `copy_to` (absent, not an
 * array, carrying non-strings or ids no field has) degrades to "no link" rather
 * than throwing, because these run inside render.
 */
import type { FormField, FormSchema } from '../types/schema';

/** The copy_to list of `field`, with malformed entries dropped. */
export function copyTargets(field: FormField | undefined): string[] {
  const raw = (field as { copy_to?: unknown } | undefined)?.copy_to;
  if (!Array.isArray(raw)) return [];
  return raw.filter((id): id is string => typeof id === 'string' && !!id);
}

/** Field ids that copy INTO `fieldId` -- the derived reverse view. */
export function copySources(schema: FormSchema, fieldId: string): string[] {
  const out: string[] = [];
  for (const f of schema.fields || []) {
    if (!f || f.id === fieldId) continue;            // never self
    if (copyTargets(f).includes(fieldId)) out.push(f.id);
  }
  return out;
}

/**
 * Why `fieldId` may not copy into `targetId`, or null if it may.
 *
 * Refusals, in the order a user would hit them:
 *  - self-reference: a field cannot populate itself;
 *  - unknown target: the id names no field;
 *  - already linked: the pair exists (adding twice would duplicate the id in
 *    copy_to and fan the value out twice at runtime);
 *  - a CYCLE: target already reaches fieldId through other links, so a value
 *    would chase its own tail. Depth-limited, so a pre-existing cycle in a
 *    hand-edited kit cannot hang the editor.
 */
export function whyNotLinkable(
  schema: FormSchema, fieldId: string, targetId: string,
): string | null {
  if (fieldId === targetId) return 'A field cannot copy into itself.';
  const target = (schema.fields || []).find(f => f?.id === targetId);
  if (!target) return 'That field no longer exists.';
  const source = (schema.fields || []).find(f => f?.id === fieldId);
  if (source && copyTargets(source).includes(targetId)) {
    return 'These fields are already linked.';
  }
  if (reaches(schema, targetId, fieldId)) {
    return 'That would make a loop: the other field already copies back here.';
  }
  const mismatch = whyIncompatible(source, target);
  if (mismatch) return mismatch;
  return null;
}

/**
 * Whether a field's value must be one of its own options.
 *
 * Derived from the DATA (does it carry options?), not from a hardcoded type
 * list. An earlier cut listed select/radio/checkbox_group by name and so
 * disagreed with the runtime's own predicate (schema-forms' isStringEnumField),
 * which also counts a `type: "checkbox"` carrying options[] -- a real shape,
 * 27 fields in the adult-intake demo and 59 in the i-589 draft. That mismatch
 * both UNDER-refused (text -> options-bearing checkbox was allowed, the exact
 * defect this guard exists to stop) and OVER-refused (that same checkbox as a
 * SOURCE was wrongly rejected). Reading the options makes a new field type
 * correct here for free (bd polyglot-pdf-g33y2, cross-surface round 2).
 */
function isOptionBacked(field: FormField): boolean {
  const t = String(field.type);
  if (t === 'select' || t === 'radio' || t === 'checkbox_group') return true;
  // A standalone boolean checkbox is NOT option-backed; one carrying options is
  // a group in all but name, and the runtime treats it as an enum field.
  return t === 'checkbox' && rawOptionCount(field) > 0;
}

/**
 * How many entries `options` holds, RAW.
 *
 * Deliberately NOT safeOptions() from utils/validation, despite looking like a
 * duplicate of it. safeOptions DROPS unreadable entries; the runtime predicate
 * this mirrors counts them (`(field.options?.length ?? 0) > 0`). So for an
 * options array of nulls or numbers, safeOptions says 0 and the runtime says
 * "enum field" -- reusing it would reintroduce the editor-vs-runtime
 * divergence this whole guard exists to close. Verified across 120
 * type x options-shape cells in cross-surface review.
 */
function rawOptionCount(field: FormField): number {
  const raw = (field as { options?: unknown }).options;
  return Array.isArray(raw) ? raw.length : 0;
}

/**
 * Why a value copied from `source` would not be a legal value for `target`.
 *
 * The runtime fan-out copies the RAW value and stamps it confirmed WITHOUT
 * validating (SchemaForm's handleFieldChange), so a mismatched link produces a
 * field that looks answered, satisfies the required gate, and then prints BLANK
 * on the draft a human reviews -- the PDF filler skips an option value it
 * cannot match. Refusing at authoring time is the only place this is visible.
 *
 * Deliberately narrow: it refuses only what is provably wrong -- copying INTO an
 * option-backed field from something that has no options to draw on. Loose pairs
 * (text -> date, number -> text) are left alone, because a form legitimately
 * repeats one answer in differently-typed boxes and over-refusing would block
 * real authoring. Two option-backed fields are left alone too: whether their
 * option SETS line up is the author's judgment, not something to guess from
 * types.
 */
function whyIncompatible(
  source: FormField | undefined, target: FormField | undefined,
): string | null {
  if (!source || !target) return null;
  if (!isOptionBacked(target)) return null;   // free-text target: anything goes
  if (isOptionBacked(source)) return null;    // both option-backed: the author's call
  return `"${target.spoken_name || target.name || target.id}" only accepts `
    + 'its own answer choices, so a typed value copied into it would not '
    + 'match any of them and would print blank.';
}

/** Whether `from` reaches `to` by following copy_to. Depth-limited. */
function reaches(schema: FormSchema, from: string, to: string): boolean {
  const seen = new Set<string>();
  const stack = [from];
  let guard = 0;
  while (stack.length && guard++ < 10000) {
    const id = stack.pop()!;
    if (id === to) return true;
    if (seen.has(id)) continue;                       // tolerate an existing cycle
    seen.add(id);
    const f = (schema.fields || []).find(x => x?.id === id);
    for (const t of copyTargets(f)) stack.push(t);
  }
  return false;
}

/**
 * Add the link source -> target, returning the fields array to commit.
 *
 * Returns the ORIGINAL array reference when the link is not addable, so a
 * caller can skip a no-op commit (and its undo entry).
 *
 * READ-ONLY COUPLING (maintainer requirement): a copy target is set read_only
 * in the same patch. A field that is populated from another AND freely editable
 * invites an author to type a value the next source edit silently overwrites.
 * Coupling on ADD (rather than refusing the link unless already read-only)
 * keeps the author in one step; unlinking does NOT clear read_only, since a
 * field can be legitimately read-only for its own reasons.
 */
export function addCopyLink(
  schema: FormSchema, sourceId: string, targetId: string,
): FormField[] {
  const fields = schema.fields || [];
  if (whyNotLinkable(schema, sourceId, targetId)) return fields;
  return fields.map(f => {
    if (!f) return f;
    if (f.id === sourceId) {
      return { ...f, copy_to: [...copyTargets(f), targetId] };
    }
    if (f.id === targetId && !f.read_only) {
      return { ...f, read_only: true };
    }
    return f;
  });
}

/**
 * Remove the link source -> target, returning the fields array to commit.
 *
 * Drops `copy_to` entirely when it empties, rather than leaving `[]` -- an
 * empty array is a meaningless key that would show up as a diff on every kit
 * ever unlinked. read_only is deliberately LEFT SET (see addCopyLink).
 */
export function removeCopyLink(
  schema: FormSchema, sourceId: string, targetId: string,
): FormField[] {
  const fields = schema.fields || [];
  return fields.map(f => {
    if (!f || f.id !== sourceId) return f;
    const next = copyTargets(f).filter(id => id !== targetId);
    const out = { ...f } as FormField & { copy_to?: string[] };
    if (next.length) out.copy_to = next;
    else delete out.copy_to;
    return out;
  });
}

/** Fields that could legally become a copy TARGET of `fieldId`. */
export function linkableTargets(schema: FormSchema, fieldId: string): FormField[] {
  return (schema.fields || []).filter(
    f => f && !whyNotLinkable(schema, fieldId, f.id),
  );
}

/** Fields that could legally become a copy SOURCE for `fieldId`. */
export function linkableSources(schema: FormSchema, fieldId: string): FormField[] {
  return (schema.fields || []).filter(
    f => f && !whyNotLinkable(schema, f.id, fieldId),
  );
}
