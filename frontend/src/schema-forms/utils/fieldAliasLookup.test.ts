/**
 * The `[]`-alias SCHEMA lookup: behavior + the SET of legitimate exact-only sites.
 *
 * bd polyglot-pdf-una9. Gemini drops or adds the trailing `[]` on a
 * checkbox-group id inconsistently (bd polyglot-pdf-5k52), so a model-supplied
 * `field_id` can name the variant the schema does not declare. The VALUE side of
 * that (readFieldEntryWithAlias) was closed earlier; the SCHEMA side was not,
 * and the asymmetry is what una9 reports.
 *
 * The second half of this file is the scar-#8 guard. The same three-line
 * fallback had been hand-written FOUR times and skipped in a fifth place -- so
 * pinning only the confirm handler would leave the next omission to be found by
 * a reviewer, one round at a time. Instead we enumerate every
 * `fields.find(f => f.id === <id>)` over a model-supplied identifier and assert
 * the complete allowlist of sites that may legitimately stay exact-only.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';
import { findFieldWithAlias } from './fieldValue';
import type { FormField } from '../types/schema';

const field = (id: string, extra: Partial<FormField> = {}): FormField =>
  ({ id, name: id, type: 'text', ...extra } as FormField);

describe('findFieldWithAlias', () => {
  const bracketed = field('race[]', { spoken_name: 'race' });
  const plain = field('country', { spoken_name: 'country' });
  const fields = [plain, bracketed];

  it('resolves an exact id', () => {
    expect(findFieldWithAlias(fields, 'country')).toBe(plain);
    expect(findFieldWithAlias(fields, 'race[]')).toBe(bracketed);
  });

  it('resolves a model-supplied id that DROPPED the brackets', () => {
    // The una9 case: schema declares `race[]`, Gemini sends `race`.
    expect(findFieldWithAlias(fields, 'race')).toBe(bracketed);
  });

  it('resolves a model-supplied id that ADDED brackets', () => {
    expect(findFieldWithAlias(fields, 'country[]')).toBe(plain);
  });

  it('prefers an EXACT match over the alias variant when both are declared', () => {
    // Precedence matters: if a schema genuinely declares both variants as
    // separate fields, the id the caller asked for must win, or a confirm
    // aimed at one group would read the other group's requiredness.
    const both = [field('x'), field('x[]')];
    expect(findFieldWithAlias(both, 'x')?.id).toBe('x');
    expect(findFieldWithAlias(both, 'x[]')?.id).toBe('x[]');
  });

  it('returns undefined when neither variant exists, and on empty input', () => {
    expect(findFieldWithAlias(fields, 'nope')).toBeUndefined();
    expect(findFieldWithAlias(fields, '')).toBeUndefined();
    expect(findFieldWithAlias(undefined, 'country')).toBeUndefined();
  });
});

/**
 * THE SET (CLAUDE.md scar #8).
 *
 * Every exact-only schema lookup keyed on an identifier that can arrive FROM THE
 * MODEL must go through findFieldWithAlias. This scan enumerates them from
 * source rather than trusting a hand-typed list, so a NEW exact-only lookup
 * fails here instead of shipping as the next una9.
 *
 * The allowlist below is the complete set of sites that may legitimately stay
 * exact-only, each with the reason it is safe. Adding an entry is a deliberate
 * act that must carry a justification.
 */
describe('the set of exact-only schema lookups on a model-supplied id', () => {
  const SCANNED_FILES = [
    'webFormConnection.ts',
    'schema-forms/state/schemaFormState.ts',
  ];

  // id -> why an exact-only lookup is correct here.
  const ALLOWED: Record<string, string> = {
    // handleSwitchFieldRequest resolves the model's identifier through
    // SchemaFormStateManager.resolveFieldForNavigation FIRST (which is itself
    // alias- and spoken-name-aware) and re-reads by the SCHEMA's own id. The
    // non-null assertion on that line encodes exactly that precondition, so an
    // alias fallback here would be dead code.
    'const field = this.state.schema.fields.find(f => f.id === fieldId)!;':
      'post-resolution read of a schema-owned id (resolveFieldForNavigation)',
  };

  it('every model-facing lookup is alias-aware, or is an allowlisted exception', () => {
    const srcRoot = join(__dirname, '..', '..');
    const offenders: string[] = [];

    for (const rel of SCANNED_FILES) {
      const text = readFileSync(join(srcRoot, rel), 'utf-8');
      text.split(/\r?\n/).forEach((line, i) => {
        // Exact-only lookups keyed on a request/model identifier. Deliberately
        // narrow: `field_id` and `fieldId` are the names this repo uses for an
        // id that came off the wire. Lookups by `f.name` / spoken_name are a
        // different contract and are not in scope.
        const isExactOnlyIdLookup =
          /fields\s*\.find\(\s*\(?\s*f\s*\)?\s*=>\s*f\.id\s*===\s*(field_id|fieldId)\s*\)/.test(line);
        if (!isExactOnlyIdLookup) return;
        const trimmed = line.trim();
        if (ALLOWED[trimmed]) return;
        offenders.push(`${rel}:${i + 1}  ${trimmed}`);
      });
    }

    expect(
      offenders,
      'Exact-only schema lookup on a model-supplied field id. Gemini drops/adds ' +
        'the checkbox-group `[]` (bd polyglot-pdf-5k52), so this can miss a field ' +
        'that exists. Use findFieldWithAlias, or add the line to ALLOWED above ' +
        'with the reason it is safe (bd polyglot-pdf-una9).'
    ).toEqual([]);
  });

  it('the allowlist itself is live -- every entry still exists in source', () => {
    // A stale allowlist silently re-opens the hole it was excusing: if the
    // allowlisted line is edited or deleted, the entry must go too, or it sits
    // there ready to excuse a DIFFERENT line that happens to match it later.
    const srcRoot = join(__dirname, '..', '..');
    const all = SCANNED_FILES.map((rel) =>
      readFileSync(join(srcRoot, rel), 'utf-8')
    ).join('\n');
    for (const allowed of Object.keys(ALLOWED)) {
      expect(all, `stale ALLOWED entry: ${allowed}`).toContain(allowed);
    }
  });
});
