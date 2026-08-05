/**
 * Utility functions for handling FieldValue wrappers
 *
 * Bug Fix: Manual Entry Shows [object Object]
 * Root Cause: FieldValue wrapper objects are displayed directly instead of unwrapped
 * Solution: Unwrap FieldValue objects to get primitive values for display
 */

import type { FieldValue } from '../types/schema';

/**
 * Whether a FieldValue entry actually carries an answer (not a hollow
 * placeholder). Empty string, null/undefined value, and an empty array all count
 * as "no answer".
 */
function entryHasValue(entry: FieldValue | undefined): boolean {
  if (!entry) return false;
  const v = entry.value as unknown;
  if (v === null || v === undefined || v === '') return false;
  if (Array.isArray(v) && v.length === 0) return false;
  return true;
}

/**
 * Read a field's FieldValue entry with the checkbox-group `[]`-alias
 * fallback: a group's value may sit under the bracketed OR unbracketed key
 * variant (Gemini drops/adds the bracket, bd polyglot-pdf-5k52), so an
 * exact-key-only read silently misses a real entry. Same convention as the
 * confirm/update/skip/validator paths; use this instead of a bare
 * `fieldValues[fieldId]` wherever a miss would change behavior.
 *
 * Precedence (bd polyglot-pdf-luju nit 2): a MEANINGFUL exact-key entry wins;
 * otherwise a meaningful alias-key entry wins. A plain `??` would stop at a
 * HOLLOW exact-key entry (e.g. `{value: null, confirmed: false}`) and shadow a
 * real confirmed answer sitting under the alias key -- so hollow exact-key
 * entries fall through to the alias. Only when neither key has a real answer do
 * we return the exact-key entry (else the alias) so a caller inspecting flags on
 * an unanswered field still gets a stable entry.
 */
export function readFieldEntryWithAlias(
  fieldValues: Record<string, FieldValue>,
  fieldId: string
): FieldValue | undefined {
  const aliasKey = fieldId.endsWith('[]') ? fieldId.slice(0, -2) : fieldId + '[]';
  const exact = fieldValues[fieldId];
  const alias = fieldValues[aliasKey];
  if (entryHasValue(exact)) return exact;
  if (entryHasValue(alias)) return alias;
  return exact ?? alias;
}

/**
 * Reconcile the persisted fieldValues map with an in-memory copy that may have
 * diverged, resolving each field to a single winning entry.
 *
 * WHY THIS EXISTS. WebFormConnection holds `this.state` across turns while the
 * React UI (SchemaForm.tsx handleFieldChange / handleFieldSkip) writes through
 * SchemaFormStateManager WITHOUT touching that object -- two independent writers
 * of the same map. Handlers that end in save(this.state) therefore persist their
 * in-memory copy over anything the UI wrote since the last sync. The previous
 * guard was a raw key union (`{...persisted, ...inMemory}`), which made the
 * in-memory side win UNCONDITIONALLY and had two failure modes:
 *   - a value the user cleared on screen was revived (and then confirmed, so it
 *     never re-prompted and printed on the PDF) -- bd polyglot-pdf-uw3w;
 *   - a key union re-added an `[]`-alias key that updateField had deliberately
 *     DELETED on migration, leaving two live entries for one field and breaking
 *     the one-entry invariant -- bd polyglot-pdf-got6 / bd polyglot-pdf-3irc.
 *
 * RULES.
 *  - Reconcile per LOGICAL FIELD, collapsing the `p1_grp` / `p1_grp[]` alias
 *    pair into one decision, so a union can never resurrect a deleted variant.
 *    The surviving key is the one the SCHEMA declares when `knownFieldIds` is
 *    supplied (callers should always supply it); otherwise it falls back to the
 *    winning side's variant. Getting that choice wrong is destructive, not
 *    cosmetic -- see the note on `schemaIds` below.
 *  - Within a field, the entry with the newer `lastModified` wins (the field the
 *    type comment calls "Timestamp for conflict resolution"). updateField and
 *    markFieldSkipped both stamp it; confirmField deliberately does NOT, because
 *    confirming changes only confirmation metadata, never the value -- so the
 *    value's timestamp correctly stays put.
 *  - A stamped entry beats an unstamped one: a write we can date is provably
 *    newer than one of unknown age.
 *  - On a same-millisecond TIE the PERSISTED side wins. Both tie directions are
 *    unsafe if the stale in-memory copy wins, so this is not a "meaningful entry
 *    wins" rule -- see the tie branch below for why that only covers one of them.
 *    This does mean a tie between two DIFFERENT meaningful values resolves
 *    arbitrarily (persisted). That is safe only because it is unreachable: every
 *    connection write goes through updateField, which stamps lastModified AND
 *    save()s in one step, so an equal stamp means both sides hold the same
 *    write. Adding a path that mutates this.state.fieldValues WITHOUT persisting
 *    would break that assumption and this rule would need revisiting.
 *  - When NEITHER side is stamped, the in-memory entry wins. This preserves the
 *    conservative pre-existing direction (bd polyglot-pdf-pjws) so an entry that
 *    exists only in memory stays visible to the confirm handler's usable-value
 *    gate and the skip handler's already-filled guard.
 *  - An entry present on only one side is kept as-is.
 *  - The SAME newer-stamp rule applies WITHIN one side when it illegally holds
 *    both variants (see pickWithinSide) -- otherwise a fresher hollow write would
 *    lose to a staler answer on one side while winning across sides, which is the
 *    same data resolving two different ways.
 */
export function reconcileFieldValues(
  persisted: Record<string, FieldValue>,
  inMemory: Record<string, FieldValue>,
  knownFieldIds?: Iterable<string>
): Record<string, FieldValue> {
  const baseKeyOf = (k: string) => (k.endsWith('[]') ? k.slice(0, -2) : k);
  const stampOf = (e: FieldValue | undefined) =>
    typeof e?.lastModified === 'number' ? e.lastModified : undefined;

  // The SCHEMA's own field ids, when the caller can supply them. Collapsing an
  // alias pair means keeping one key and dropping the other, and that choice is
  // only safe if the surviving key is the one the schema uses: SchemaForm.tsx,
  // getProgress and isSectionValid all index fieldValues[field.id] EXACTLY. A
  // shipped kit really does use bracketed ids (adult_intake_demo_schema.json has
  // race[], reason[], risk_concerns[] and three more), so re-keying `race[]` ->
  // `race` would leave the answer live but invisible: the field renders blank,
  // progress drops, and a required section stops validating.
  const schemaIds = knownFieldIds ? new Set(knownFieldIds) : undefined;
  /** The variant the schema actually declares, when we can tell. */
  const schemaKeyFor = (base: string, bracket: string): string | undefined => {
    if (!schemaIds) return undefined;
    if (schemaIds.has(base)) return base;
    if (schemaIds.has(bracket)) return bracket;
    return undefined;
  };

  // Group both maps by logical field so an alias pair resolves as ONE decision.
  const baseKeys = new Set<string>();
  for (const k of Object.keys(persisted)) baseKeys.add(baseKeyOf(k));
  for (const k of Object.keys(inMemory)) baseKeys.add(baseKeyOf(k));

  const out: Record<string, FieldValue> = {};

  for (const base of baseKeys) {
    const bracket = base + '[]';
    // The key each side actually used for this field. A side that (illegally)
    // holds both variants is read through the established alias precedence.
    const persistedKey = persisted[base] !== undefined ? base
      : persisted[bracket] !== undefined ? bracket : undefined;
    const memoryKey = inMemory[base] !== undefined ? base
      : inMemory[bracket] !== undefined ? bracket : undefined;

    const persistedEntry = pickWithinSide(persisted, base, bracket, persistedKey);
    const memoryEntry = pickWithinSide(inMemory, base, bracket, memoryKey);

    if (persistedEntry === undefined && memoryEntry === undefined) continue;

    // Prefer the SCHEMA's own variant when we know it; otherwise keep the key
    // the winning side used (the pre-schema-aware behaviour).
    const preferred = schemaKeyFor(base, bracket);

    // Present on one side only -- keep it under the key that side used.
    if (memoryEntry === undefined) {
      out[preferred ?? (persistedKey as string)] = persistedEntry as FieldValue;
      continue;
    }
    if (persistedEntry === undefined) {
      out[preferred ?? (memoryKey as string)] = memoryEntry;
      continue;
    }

    const persistedStamp = stampOf(persistedEntry);
    const memoryStamp = stampOf(memoryEntry);

    // Which side wins, and the merge, are BOTH delegated to the shared helpers
    // below -- the same ones pickWithinSide uses. Three review rounds found the
    // intra-side path drifting from this one (stamps, then dated-vs-undated,
    // then equal stamps and the marker carry), so the rule now lives in ONE
    // place and divergence is structurally impossible rather than a thing to
    // remember.
    const persistedWins = firstWins(persistedEntry, memoryEntry);
    const merged = mergeEntries(
      persistedWins ? persistedEntry : memoryEntry,
      persistedWins ? memoryEntry : persistedEntry
    );

    out[preferred ?? ((persistedWins ? persistedKey : memoryKey) as string)] =
      merged as FieldValue;
  }

  return out;
}

/**
 * Resolve ONE side that (illegally) holds both `p1_grp` and `p1_grp[]`.
 *
 * `readFieldEntryWithAlias` alone is wrong here: its rule is "meaningful entry
 * wins", which IGNORES lastModified, so a fresher HOLLOW write -- a skip, or the
 * user clearing the field -- loses to a staler answer. That is the uw3w harm
 * (worse for a skip, since markFieldSkipped also sets confirmed:true, so the
 * revived value never re-prompts), and it contradicted how the SAME data
 * resolves when the two variants happen to land on opposite sides, where the
 * cross-side rule below compares stamps.
 *
 * So: when both variants are present on one side and BOTH are dated, the newer
 * wins -- the same rule the cross-side comparison uses. Otherwise fall back to
 * the established meaningful-wins precedence, which is right when there is no
 * ordering information to use.
 */
function pickWithinSide(
  map: Record<string, FieldValue>,
  base: string,
  bracket: string,
  presentKey: string | undefined
): FieldValue | undefined {
  if (presentKey === undefined) return undefined;
  const a = map[base];
  const b = map[bracket];
  if (a === undefined || b === undefined) {
    return readFieldEntryWithAlias(map, presentKey);
  }
  // Both variants present on this ONE side. Resolve with the SAME rule and the
  // SAME marker carry as the cross-side comparison -- `a` (the bare key) plays
  // the "first" role, mirroring persisted-wins on an equal stamp. Using
  // readFieldEntryWithAlias here instead would be meaningful-wins, which ignores
  // stamps entirely and silently reverts a fresh skip.
  const aWins = firstWins(a, b);
  return mergeEntries(aWins ? a : b, aWins ? b : a);
}

/**
 * Does `first` beat `second`? The single ordering rule, used for both the
 * cross-side comparison and the intra-side collapse.
 *
 * Newer `lastModified` wins; a dated entry beats an undated one; an equal or
 * absent stamp goes to `first`. Callers put the more authoritative side first:
 * the PERSISTED map cross-side (the durable path both writers share), and the
 * bare key intra-side.
 */
function firstWins(first: FieldValue | undefined, second: FieldValue | undefined): boolean {
  const sf = typeof first?.lastModified === 'number' ? first.lastModified : undefined;
  const ss = typeof second?.lastModified === 'number' ? second.lastModified : undefined;
  if (sf !== undefined && ss !== undefined) return sf >= ss;
  if (sf !== undefined) return true;
  if (ss !== undefined) return false;
  // Neither dated: keep the pre-existing conservative direction (bd
  // polyglot-pdf-pjws) -- cross-side that means the in-memory entry, which is
  // `second` there, so `first` loses.
  return false;
}

/**
 * The winner decides the VALUE; sticky markers carry from the loser when the two
 * agree on the value.
 *
 * `confirmField` sets `confirmed` WITHOUT bumping `lastModified`, so the loser
 * can be the only side holding it, and dropping it would cause a spurious re-ask
 * of an already-confirmed field. `skipped` is load-bearing the same way
 * (`isSectionValid` and `getProgress` both honour it).
 *
 * The gate is VALUE AGREEMENT, not a stamp tie -- deliberately. A marker
 * describes the answer it was attached to, so it may follow that answer no
 * matter which side is newer, and must NEVER follow a DIFFERENT answer (that
 * would mark a value confirmed nobody confirmed -- the uw3w harm).
 */
function mergeEntries(
  winner: FieldValue | undefined,
  loser: FieldValue | undefined
): FieldValue | undefined {
  if (!winner || !loser || !sameValue(winner.value, loser.value)) return winner;

  type Sticky = FieldValue & { skipped?: boolean };
  const w = winner as Sticky;
  const l = loser as Sticky;
  const carried: Partial<Sticky> = {};

  if (w.confirmed === undefined && l.confirmed !== undefined) {
    carried.confirmed = l.confirmed;
    if (w.confirmedAt === undefined) carried.confirmedAt = l.confirmedAt;
    if (w.confirmationMethod === undefined) carried.confirmationMethod = l.confirmationMethod;
  }
  if (w.steered === undefined && l.steered !== undefined) carried.steered = l.steered;
  if (w.skipped === undefined && l.skipped !== undefined) carried.skipped = l.skipped;

  return Object.keys(carried).length > 0 ? { ...w, ...carried } : winner;
}

/** Structural equality for FieldValue.value, including checkbox-group arrays. */
function sameValue(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((v, i) => v === b[i]);
  }
  return a === b;
}

/**
 * Type guard to check if a value is a FieldValue object
 */
export function isFieldValue(value: any): value is FieldValue {
  return (
    value !== null &&
    typeof value === 'object' &&
    'value' in value &&
    !Array.isArray(value)
  );
}

/**
 * Unwrap a FieldValue object to get the primitive value
 *
 * @param value - Primitive value or FieldValue wrapper
 * @returns Primitive value (string, boolean, string[], null)
 *
 * @example
 * unwrapFieldValue('hello') // => 'hello'
 * unwrapFieldValue({ value: 'hello', confirmed: true }) // => 'hello'
 * unwrapFieldValue({ value: ['Male'], confirmed: true }) // => ['Male'] (checkbox group)
 * unwrapFieldValue({ value: null }) // => null
 * unwrapFieldValue(null) // => null
 */
export function unwrapFieldValue(value: any): string | boolean | string[] | null {
  if (isFieldValue(value)) {
    return value.value;
  }
  return value;
}

/**
 * Unwrap and convert to string for text inputs
 * Handles null/undefined by returning empty string
 *
 * @param value - Any value (primitive, FieldValue, null, undefined)
 * @returns String value suitable for text input
 *
 * @example
 * unwrapToString('hello') // => 'hello'
 * unwrapToString({ value: 'world' }) // => 'world'
 * unwrapToString(null) // => ''
 * unwrapToString(undefined) // => ''
 * unwrapToString({ value: true }) // => 'true'
 */
export function unwrapToString(value: any): string {
  const unwrapped = unwrapFieldValue(value);

  if (unwrapped === null || unwrapped === undefined) {
    return '';
  }

  return String(unwrapped);
}

/**
 * Unwrap and convert to boolean for checkbox inputs
 *
 * @param value - Any value (primitive, FieldValue, null, undefined)
 * @returns Boolean value
 *
 * @example
 * unwrapToBoolean(true) // => true
 * unwrapToBoolean({ value: true }) // => true
 * unwrapToBoolean('true') // => true
 * unwrapToBoolean(null) // => false
 */
export function unwrapToBoolean(value: any): boolean {
  const unwrapped = unwrapFieldValue(value);

  if (unwrapped === null || unwrapped === undefined) {
    return false;
  }

  if (typeof unwrapped === 'boolean') {
    return unwrapped;
  }

  // Handle string/number representations. Coerce to string so a numeric 1
  // (which can arrive since the input is `any`) still maps to true, without a
  // `=== 1` comparison the unwrap return type rules out as unreachable.
  if (typeof unwrapped === 'string' || typeof unwrapped === 'number') {
    return String(unwrapped) === 'true' || String(unwrapped) === '1';
  }
  return false;
}
