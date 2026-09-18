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
import { readFileSync, readdirSync, statSync } from 'fs';
import { join, relative } from 'path';
import { findFieldWithAlias, sectionDeclaresField } from './fieldValue';
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
 * The scan runs TREE-WIDE over frontend/src, and the allowlist below is the
 * complete set of sites that stay exact-only -- each with the reason it is
 * safe. Adding an entry is a deliberate act that must carry a justification.
 * (An entry may also record a KNOWN GAP rather than a safe site, so this guard
 * does not fail on a pre-existing defect it did not introduce -- say which in
 * the comment. There are none today: the one such entry, bd
 * polyglot-pdf-mwgim's navigation resolver, is now FIXED and its entry removed.)
 *
 * SECOND SHAPE, same hazard (bd polyglot-pdf-db1en): a section's `fields` array
 * holds field IDS, and an entry there can carry a different bracket form from
 * the `field.id` it names. That is a MEMBERSHIP test, not a `.find`, so the
 * lookup scan above cannot see it -- it is guarded separately at the bottom of
 * this file via sectionDeclaresField.
 */
describe('the set of exact-only schema lookups on a model-supplied id', () => {
  // Scanned TREE-WIDE, not over a hand-listed pair of files. Limiting the scan
  // to the two files this bead happened to touch would make the guard's own
  // completeness claim rest on a hand-typed list -- the exact rot it exists to
  // prevent, one level up (fresh-eyes finding). `identifier` is included
  // alongside field_id/fieldId because the navigation resolver names its
  // model-supplied argument that, and keying the pattern only on the two names
  // this bead touched is how resolveFieldForNavigation stayed invisible.
  const ID_VARS = 'field_id|fieldId|identifier';
  const LOOKUP_RE = new RegExp(
    String.raw`fields\s*\.find\(\s*\(?\s*f\s*\)?\s*=>\s*f\.id\s*===\s*(${ID_VARS})\s*\)`
  );

  // exact source line -> why an exact-only lookup is tolerated here.
  const ALLOWED: Record<string, string> = {
    // handleSwitchFieldRequest re-reads by the SCHEMA's OWN id, AFTER
    // resolveFieldForNavigation has already mapped the model's identifier to
    // it. The non-null assertion encodes that precondition, so an alias
    // fallback here would be dead code. This is genuinely SAFE.
    'const field = this.state.schema.fields.find(f => f.id === fieldId)!;':
      'post-resolution read of a schema-owned id (resolveFieldForNavigation)',

    // findFieldWithAlias's OWN implementation -- it IS the alias fallback, so
    // routing it through itself would be infinite recursion.
    'const exact = fields.find((f) => f.id === fieldId);':
      'the helper implementing the fallback',

    // UI-SUPPLIED ids, not model-supplied. These take fieldId from a DOM event
    // (onChange / onBlur / a keydown target's own id or name attribute) or from
    // the local onManualEdit closure -- i.e. from the element the form itself
    // rendered, which carries the SCHEMA's id by construction. The model never
    // reaches them, so there is no bracket to drift.
    'const field = prevState.schema.fields.find(f => f.id === fieldId);':
      'UI-supplied id (SchemaForm onChange / copy_to fan-out)',
    'const field = prevState.schema.fields.find((f) => f.id === fieldId);':
      'UI-supplied id (SchemaForm onBlur validation)',
    'const field = state.schema.fields.find(f => f.id === fieldId);':
      'UI-supplied id (SchemaForm keydown target)',
    'const field = next.schema.fields.find(f => f.id === fieldId);':
      'UI-supplied id (SchemaForm state transition)',
    'const field = schema.fields.find(f => f.id === fieldId)':
      'UI-supplied id (connection.ts onManualEdit -- the USER typed it)',

    // A generic accessor whose caller owns the id's provenance. Callers that
    // pass a model-supplied id are themselves in scope for this scan.
    'return schema.fields.find(f => f.id === fieldId);':
      'generic getFieldSchema accessor -- provenance belongs to the caller',
  };

  /** Every .ts/.tsx source file under frontend/src, excluding tests. */
  function sourceFiles(root: string): string[] {
    const out: string[] = [];
    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir)) {
        if (entry === 'node_modules' || entry === 'dist') continue;
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          walk(full);
          continue;
        }
        if (!/\.tsx?$/.test(entry) || /\.test\.tsx?$/.test(entry)) continue;
        out.push(relative(root, full));
      }
    };
    walk(root);
    return out;
  }

  it('every model-facing lookup is alias-aware, or is an allowlisted exception', () => {
    const srcRoot = join(__dirname, '..', '..');
    const offenders: string[] = [];

    for (const rel of sourceFiles(srcRoot)) {
      const text = readFileSync(join(srcRoot, rel), 'utf-8');
      text.split(/\r?\n/).forEach((line, i) => {
        // Lookups by `f.name` / spoken_name are a DIFFERENT contract (a
        // human-facing label, not a wire id) and are deliberately out of scope.
        if (!LOOKUP_RE.test(line)) return;
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
    const all = sourceFiles(srcRoot)
      .map((rel) => readFileSync(join(srcRoot, rel), 'utf-8'))
      .join('\n');
    for (const allowed of Object.keys(ALLOWED)) {
      expect(all, `stale ALLOWED entry: ${allowed}`).toContain(allowed);
    }
  });
});

/**
 * THE SECOND SHAPE: section.fields MEMBERSHIP (bd polyglot-pdf-db1en).
 *
 * A section's `fields` array holds field IDS, and an entry there can carry a
 * different bracket form from the `field.id` it names. Asking "does this
 * section declare this field" with an exact `includes` therefore silently
 * answers NO for a field that plainly belongs to it.
 *
 * This is a membership test, not a `.find`, so the lookup scan above cannot see
 * it -- which is exactly how extractSectionFields survived the una9 sweep that
 * widened its five siblings. Guarded here on its own terms.
 */
describe('sectionDeclaresField', () => {
  const section = { fields: ['name', 'race[]'] };

  it('matches an exact entry', () => {
    expect(sectionDeclaresField(section, 'name')).toBe(true);
    expect(sectionDeclaresField(section, 'race[]')).toBe(true);
  });

  it('matches across the bracket drift, in BOTH directions', () => {
    // section declares `race[]`, the field/caller says `race`
    expect(sectionDeclaresField(section, 'race')).toBe(true);
    // section declares `name`, the caller says `name[]`
    expect(sectionDeclaresField(section, 'name[]')).toBe(true);
  });

  it('does not match a field the section does not declare', () => {
    expect(sectionDeclaresField(section, 'other')).toBe(false);
    expect(sectionDeclaresField(section, 'other[]')).toBe(false);
  });

  it('is safe on absent input', () => {
    expect(sectionDeclaresField(null, 'name')).toBe(false);
    expect(sectionDeclaresField(undefined, 'name')).toBe(false);
    expect(sectionDeclaresField({}, 'name')).toBe(false);
    expect(sectionDeclaresField(section, '')).toBe(false);
  });
});

describe('the set of exact-only section.fields membership tests', () => {
  // Same tree-wide discipline as the lookup scan: an exact
  // `section.fields.includes(...)` answers "is this field in this section", and
  // every consumer of that question degrades SILENTLY on a wrong NO (a section
  // schema missing a field, a resume landing on the wrong section, a section
  // validating complete with an answer missing). Route them through
  // sectionDeclaresField.
  // `?.` is matched as well as `.` (bd polyglot-pdf-a6cl2). The first version
  // of this regex required a plain dot, so the ONE live optional-chain site --
  // `s.fields?.includes(fieldId)` in webFormConnection's other_section gate --
  // was invisible to the guard written to pin this exact set. That is the
  // recurring shape of these misses: a guard enumerates over a CONVENTION, and
  // the member that escapes is the one written slightly differently.
  const MEMBERSHIP_RE = /\.fields\s*\??\s*\.includes\(/;

  const ALLOWED: Record<string, string> = {
    // sectionDeclaresField's OWN implementation -- it IS the alias-aware
    // membership test, so routing it through itself would recurse.
    'section.fields.includes(fieldId) ||': 'the helper implementing the test',
    'section.fields.includes(baseId) ||': 'the helper implementing the test',
    'section.fields.includes(aliasId)': 'the helper implementing the test',
  };

  function sourceFiles(root: string): string[] {
    const out: string[] = [];
    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir)) {
        if (entry === 'node_modules' || entry === 'dist') continue;
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          walk(full);
          continue;
        }
        if (!/\.tsx?$/.test(entry) || /\.test\.tsx?$/.test(entry)) continue;
        out.push(relative(root, full));
      }
    };
    walk(root);
    return out;
  }

  it('every section.fields membership test is alias-aware, or allowlisted', () => {
    const srcRoot = join(__dirname, '..', '..');
    const offenders: string[] = [];

    for (const rel of sourceFiles(srcRoot)) {
      readFileSync(join(srcRoot, rel), 'utf-8')
        .split(/\r?\n/)
        .forEach((line, i) => {
          if (!MEMBERSHIP_RE.test(line)) return;
          const trimmed = line.trim();
          // Skip COMMENT lines. Prose describing this hazard (including the
          // helper's own docstring, which quotes the bad shape to explain it)
          // is not an occurrence of it, and flagging prose would make the only
          // way to document the rule be to stop documenting it.
          if (/^(\/\/|\*|\/\*)/.test(trimmed)) return;
          if (ALLOWED[trimmed]) return;
          offenders.push(`${rel}:${i + 1}  ${trimmed}`);
        });
    }

    expect(
      offenders,
      'Exact `section.fields.includes(...)` membership test. A section.fields ' +
        'entry can carry a different bracket form from the field.id it names ' +
        '(bd polyglot-pdf-db1en), so this silently answers NO for a field that ' +
        'does belong to the section. Use sectionDeclaresField, or allowlist the ' +
        'line above with the reason it is safe.'
    ).toEqual([]);
  });

  it('the allowlist itself is live -- every entry still exists in source', () => {
    const srcRoot = join(__dirname, '..', '..');
    const all = sourceFiles(srcRoot)
      .map((rel) => readFileSync(join(srcRoot, rel), 'utf-8'))
      .join('\n');
    for (const allowed of Object.keys(ALLOWED)) {
      expect(all, `stale ALLOWED entry: ${allowed}`).toContain(allowed);
    }
  });
});
