/**
 * The Ignored (grey) field status -- a human ESCAPE HATCH (bd polyglot-pdf-mzkw).
 *
 * Why it exists: a field with no real PDF widget behind it cannot be fixed by a
 * human at all -- there is nothing to bind it to -- so without a way to set it
 * aside, one un-fixable field blocks a whole form from ever being completed.
 * Ignoring parks it: out of the validators, out of the counts, out of the voice
 * app, but NOT deleted and fully reversible.
 *
 * Maintainer framing (2026-07-27), which shapes every decision below:
 *   - This is an escape hatch, NOT a primary tool. It leaves cruft in the
 *     schema; the extraction invariant (bd l1a9) should make it rarely needed.
 *   - Human-only and fully reversible: if an ignored field turns out to be a
 *     legitimate field with a fixable error, un-ignoring restores it exactly.
 *   - Gated: a field other fields depend on, or a field still marked required,
 *     must be sorted out FIRST -- ignoring must never silently break a
 *     conditional or drop a required answer.
 *
 * MECHANISM -- quarantine, not a flag. Ignoring MOVES the field object out of
 * `schema.fields` into a top-level `_ignored_fields` stash and removes its id
 * from its section. That choice (over an in-place `_review.status='ignored'`)
 * buys correctness for free: everything downstream -- the Pydantic model, the
 * backend lint, the mark-complete gate, the translation-coverage sweep, the
 * voice app's field lookups, the PDF filler -- reads `schema.fields`, so a
 * quarantined field is invisible to all of them with ZERO changes on those
 * paths. An in-place flag would have required every one of them to learn to
 * skip it. The stash key survives every save path (stripEditorState strips only
 * the per-field `_ungroup` key) and the backend tolerates it (FormSchema uses
 * Pydantic's default extra="ignore", and the draft-save route stores the raw
 * dict verbatim).
 *
 * The restore snapshot mirrors the `_ungroup` stash precedent in
 * fieldGrouping.ts: keep the field object verbatim plus enough structural
 * context to put it back exactly where it was.
 */
import type { FormField, FormSchema, FormSection } from '../types/schema';
import { conditionAtoms } from './validation';

/** Top-level stash key. Underscore-prefixed like `_review` / `_ungroup` /
 * `_bakeoff` -- the convention for editor-and-provenance data the runtime
 * ignores. */
const STASH_KEY = '_ignored_fields';

/** One quarantined field plus what it takes to restore it exactly. */
export interface IgnoredFieldEntry {
  /** The complete original field object, verbatim (including any `_review`
   * note explaining WHY it was ignored, and any `_ungroup` merge stash). */
  field: FormField;
  /** The section it lived in, or null if it was already unsectioned. */
  sectionId: string | null;
  /** Its index within that section's fields[] at ignore time, so restore puts
   * it back in place rather than appending it to the end. -1 when it was not
   * listed in any section. */
  index: number;
  /** ISO timestamp, for the grey row's tooltip and any future audit. */
  ignoredAt: string;
}

/** Every quarantined field on this schema (empty when none / malformed). */
export function getIgnoredFields(schema: FormSchema): IgnoredFieldEntry[] {
  const stash = (schema as unknown as Record<string, unknown>)[STASH_KEY];
  if (!Array.isArray(stash)) return [];
  // Defensive: a hand-edited kit could carry junk here. Keep only entries that
  // can actually be restored (a field object with an id).
  return stash.filter(
    (e): e is IgnoredFieldEntry =>
      !!e && typeof e === 'object'
      && !!(e as IgnoredFieldEntry).field
      && typeof (e as IgnoredFieldEntry).field?.id === 'string',
  );
}

/** True when this field id is currently quarantined. */
export function isIgnored(schema: FormSchema, fieldId: string): boolean {
  return getIgnoredFields(schema).some(e => e.field.id === fieldId);
}

/**
 * Every field id currently in use, LIVE OR PARKED (bd polyglot-pdf-mzkw).
 *
 * Quarantining creates a second id namespace: `schema.fields` no longer holds
 * every id the schema owns. Anything that mints or validates an id must consult
 * both, or a parked id can be handed to a live field and then collide the
 * moment the parked one is restored -- e.g. park a broken `date_of_birth`,
 * rename its replacement to `date_of_birth`, un-ignore, and the schema now has
 * two fields with one id (fresh-eyes).
 */
export function allFieldIds(schema: FormSchema): Set<string> {
  const ids = new Set<string>();
  for (const f of (Array.isArray(schema?.fields) ? schema.fields : [])) {
    if (typeof f?.id === 'string') ids.add(f.id);
  }
  for (const e of getIgnoredFields(schema)) ids.add(e.field.id);
  return ids;
}

// --------------------------------------------------------------------------
// Dependents: what would break if this field vanished?
// --------------------------------------------------------------------------

/** Where a field id can be referenced from. Each kind maps to a DIFFERENT fix
 * the author has to make, so the block message names it. */
export type DependentKind =
  | 'show_if'
  | 'require_if'
  | 'section_show_if'
  | 'copy_to'
  | 'copy_from'
  | 'address_fields'
  | 'supplement_fields';

export interface FieldDependent {
  kind: DependentKind;
  /** The referencing field's or section's id. */
  ownerId: string;
  /** Human-readable owner (spoken name / section label), for the dialog. */
  ownerLabel: string;
}

/**
 * Every in-schema reference TO `fieldId`, across all the surfaces a field id
 * can hide in (bd polyglot-pdf-mzkw).
 *
 * The surface list is taken from fieldRename.ts's retarget walk -- the one
 * place that already had to know every reference site. This is its read-only
 * twin: fieldRename REWRITES references when an id changes; ignore must REFUSE
 * while any exist, because there is no correct automatic rewrite for "this
 * trigger is going away".
 *
 * NOTE section.fields[] membership is deliberately NOT a dependent: that is the
 * field's own home, which ignoring relocates by design (and restore puts back).
 *
 * NOTE a live merged field's `_ungroup` stash can itself hold a pre-merge
 * `show_if` naming this field, and that surface is deliberately NOT scanned.
 * It is session-only -- stripEditorState removes it on save from BOTH live
 * fields and parked ones (the parked half was a real leak until bd mzkw's
 * review; the premise is now true on every path) -- so it never reaches a
 * stored kit. The exposure needs merge -> ignore -> ungroup all in one
 * session, and the outcome is a dangling condition the `ref-unresolved-field`
 * lint ERROR catches: visible, not silent. Scanning transient session state
 * would put the gate's correctness at the mercy of a key that vanishes on
 * save; the durable reference surfaces above are what it guards.
 *
 * NOTE `_bakeoff.authoring.<stage>.provenance` -- the field-id-keyed authoring
 * ownership map fieldRename re-keys -- is ALSO deliberately not a dependent,
 * and ignoring deliberately leaves its entry in place. Rename must re-key it
 * because the field persists under a new id; ignoring is TEMPORARY and
 * reversible, so the entry must survive for restore to bring the field back
 * with its guidance-authorship record intact. Dropping it would be exactly the
 * silent data loss the no-delete rule exists to prevent. A stale entry under a
 * parked id is inert: every consumer looks provenance UP by a live field id.
 *
 * Id matching is exact-string, matching every other reference walker in the
 * editor (fieldRename's retargetAtom included). Do not add bracket-alias
 * cleverness here: that class of bug lives in runtime VALUE lookups, not in
 * schema reference resolution, and diverging would make this detector disagree
 * with the rename path.
 */
export function dependentsOf(schema: FormSchema, fieldId: string): FieldDependent[] {
  const deps: FieldDependent[] = [];
  const labelOfField = (f: FormField) => f.spoken_name || f.id;
  // A partially-loaded or hand-edited schema can be missing either array (the
  // editor renders mid-load states, and this runs on every FieldEditor render
  // via the ignore gate) -- never throw on shape, like every other walker here.
  const fields = Array.isArray(schema?.fields) ? schema.fields : [];
  const sections = Array.isArray(schema?.sections) ? schema.sections : [];

  for (const f of fields) {
    if (!f || typeof f !== 'object') continue;
    if (f.id === fieldId) continue; // a self-reference cannot block itself
    const raw = f as unknown as Record<string, unknown>;

    for (const kind of ['show_if', 'require_if'] as const) {
      const atoms = conditionAtoms(raw[kind]);
      if (atoms.some(a => a && (a as { field?: unknown }).field === fieldId)) {
        deps.push({ kind, ownerId: f.id, ownerLabel: labelOfField(f) });
      }
    }

    const copyTo = raw.copy_to;
    if (Array.isArray(copyTo) && copyTo.includes(fieldId)) {
      deps.push({ kind: 'copy_to', ownerId: f.id, ownerLabel: labelOfField(f) });
    }

    if (raw.copy_from === fieldId) {
      deps.push({ kind: 'copy_from', ownerId: f.id, ownerLabel: labelOfField(f) });
    }

    const addr = raw.address_fields;
    if (addr && typeof addr === 'object' && !Array.isArray(addr)
        && Object.values(addr as Record<string, unknown>).includes(fieldId)) {
      deps.push({ kind: 'address_fields', ownerId: f.id, ownerLabel: labelOfField(f) });
    }
  }

  for (const s of sections) {
    if (!s || typeof s !== 'object') continue;
    const atoms = conditionAtoms((s as unknown as Record<string, unknown>).show_if);
    if (atoms.some(a => a && (a as { field?: unknown }).field === fieldId)) {
      deps.push({
        kind: 'section_show_if', ownerId: s.id, ownerLabel: s.label || s.id,
      });
    }
  }

  const supplements = (schema as unknown as Record<string, unknown>).supplements;
  if (Array.isArray(supplements)) {
    for (const sup of supplements) {
      if (!sup || typeof sup !== 'object') continue;
      const s = sup as Record<string, unknown>;
      if (Array.isArray(s.fields) && s.fields.includes(fieldId)) {
        deps.push({
          kind: 'supplement_fields',
          ownerId: String(s.id ?? '?'),
          ownerLabel: String(s.name ?? s.id ?? 'supplement'),
        });
      }
    }
  }

  return deps;
}

// --------------------------------------------------------------------------
// Gates
// --------------------------------------------------------------------------

export type IgnoreBlockReason = 'still-required' | 'has-dependents' | 'not-found';

/**
 * Why this field may NOT be ignored yet, or null when it may (maintainer's
 * gates, bd mzkw). Mirrors the renameBlockReason / mergeBlockReason convention:
 * a pure predicate the UI uses to disable the control AND explain why.
 */
export function ignoreBlockReason(
  schema: FormSchema, fieldId: string,
): IgnoreBlockReason | null {
  const field = (Array.isArray(schema?.fields) ? schema.fields : [])
    .find(f => f?.id === fieldId);
  if (!field) return 'not-found';
  // Required first: a required field carries an answer the form needs, so
  // parking it would silently drop that answer. Clearing the flag is a
  // deliberate act the author makes first.
  if (field.validation?.required === true) return 'still-required';
  // Then dependents: ignoring a trigger would strand every condition on it.
  if (dependentsOf(schema, fieldId).length > 0) return 'has-dependents';
  return null;
}

/** The block reason as a sentence for the UI (dialog / disabled option). */
export function describeIgnoreBlock(
  reason: IgnoreBlockReason, deps: FieldDependent[] = [],
): string {
  if (reason === 'still-required') {
    return 'This field is marked required. Clear "Required" first -- ignoring '
      + 'it would silently drop an answer the form needs.';
  }
  if (reason === 'has-dependents') {
    // Compare against DISTINCT owners, not raw entries: one field can depend
    // through two surfaces at once (e.g. both show_if and copy_to), which used
    // to make deps.length exceed the name list and print a "..." promising
    // more affected fields than exist (fresh-eyes). The author fixes owners,
    // so owners are what the message counts.
    const owners = Array.from(new Set(deps.map(d => d.ownerLabel)));
    const names = owners.slice(0, 5);
    const more = owners.length > names.length ? ', ...' : '';
    return 'Other parts of the form depend on this field '
      + `(${names.join(', ')}${more}). Retarget or remove those references `
      + 'first -- ignoring it would strand them.';
  }
  return 'This field is no longer in the form.';
}

// --------------------------------------------------------------------------
// The operations (pure: return a NEW schema, caller commits once)
// --------------------------------------------------------------------------

/**
 * Quarantine a field: move it out of fields[] into the stash and drop its id
 * from its section, in ONE new schema object. A no-op (returns the input) when
 * the field is missing or a gate blocks it -- the UI checks ignoreBlockReason
 * first, and this second check keeps the operation safe under any caller.
 *
 * Returning one object matters: App commits it through useSchemaHistory, which
 * snapshots whole schemas, so the whole move is a single Cmd+Z step.
 */
export function ignoreField(
  schema: FormSchema, fieldId: string, now: string = new Date().toISOString(),
): FormSchema {
  if (ignoreBlockReason(schema, fieldId) !== null) return schema;
  const allFields = Array.isArray(schema?.fields) ? schema.fields : [];
  const allSections = Array.isArray(schema?.sections) ? schema.sections : [];
  const field = allFields.find(f => f?.id === fieldId);
  if (!field) return schema;

  const sectionId = field.section_id ?? null;
  const section = sectionId
    ? allSections.find(s => s?.id === sectionId)
    : undefined;
  const index = Array.isArray(section?.fields)
    ? section!.fields.indexOf(fieldId)
    : -1;

  const entry: IgnoredFieldEntry = { field, sectionId, index, ignoredAt: now };

  return {
    ...schema,
    fields: allFields.filter(f => f?.id !== fieldId),
    sections: allSections.map(s =>
      Array.isArray(s?.fields) && s.fields.includes(fieldId)
        ? { ...s, fields: s.fields.filter(id => id !== fieldId) }
        : s,
    ),
    [STASH_KEY]: [...getIgnoredFields(schema), entry],
  } as FormSchema;
}

/**
 * Un-ignore: put the field back exactly where it was, in ONE new schema.
 *
 * Restore-to-orphan fallback: if the section it came from no longer exists (the
 * author deleted or merged it while the field sat quarantined), the field comes
 * back WITHOUT a section_id rather than pointing at a dead section -- a dangling
 * section reference is a validation error, while an unsectioned field simply
 * appears in the editor's "Uncategorized" bucket where a human can re-file it.
 */
export function restoreField(schema: FormSchema, fieldId: string): FormSchema {
  const stash = getIgnoredFields(schema);
  const entry = stash.find(e => e.field.id === fieldId);
  if (!entry) return schema;

  const allFields = Array.isArray(schema?.fields) ? schema.fields : [];
  const allSections = Array.isArray(schema?.sections) ? schema.sections : [];
  const targetSection = entry.sectionId
    ? allSections.find(s => s?.id === entry.sectionId)
    : undefined;

  // Section gone -> restore unsectioned (see the fallback note above).
  const restored: FormField = targetSection
    ? entry.field
    : (() => {
        const { section_id, ...rest } = entry.field;
        return rest as FormField;
      })();

  const sections: FormSection[] = targetSection
    ? allSections.map(s => {
        if (s?.id !== entry.sectionId) return s;
        const fields = Array.isArray(s.fields) ? [...s.fields] : [];
        // Clamp: the section may have shrunk while the field was away.
        const at = Math.min(Math.max(entry.index, 0), fields.length);
        fields.splice(at, 0, fieldId);
        return { ...s, fields };
      })
    : allSections;

  return {
    ...schema,
    fields: [...allFields, restored],
    sections,
    [STASH_KEY]: stash.filter(e => e.field.id !== fieldId),
  } as FormSchema;
}
