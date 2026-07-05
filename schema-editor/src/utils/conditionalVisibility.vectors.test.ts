// Shared conditional-semantics vector runner -- EDITOR PREVIEW side (bd
// polyglot-pdf-h76m.1, P0.1). Executes every vector in the repo-root
// shared/conditional-vectors.json against THIS package's shouldShowField and
// asserts the pinned expectation. The voice runtime has a sibling runner
// (frontend/src/schema-forms/utils/validation.vectors.test.ts) over the SAME
// file: a semantic change made in one evaluator but not the other (or not in the
// vector file) turns exactly one suite red. Vectors with a per-evaluator expect
// object pin the shapes where the two evaluators genuinely diverge today; this
// runner reads the `editor` leg.

import { describe, it, expect, vi } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { shouldShowField } from './conditionalVisibility';
import { normalizeToComposite } from './normalizeToComposite';
import type { FormField } from '../types/schema';
import rawSuite from '../../../shared/conditional-vectors.json';

interface Vector {
  name: string;
  field: Record<string, unknown>;
  fields?: Record<string, unknown>[];
  fieldValues: Record<string, unknown>;
  expect: boolean | { frontend: boolean; editor: boolean };
}

interface NormalizeCase {
  name: string;
  input?: unknown;
  expect: unknown;
}

const suite = rawSuite as unknown as {
  vectors: Vector[];
  normalize: NormalizeCase[];
};

// Repo root located by its marker file (import.meta.url is not a file: URL
// under vitest+jsdom, and process.cwd() is only usually the package root).
function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 6; i += 1) {
    if (existsSync(join(dir, 'shared', 'conditional-vectors.json'))) return dir;
    dir = dirname(dir);
  }
  throw new Error('repo root not found from ' + process.cwd());
}

describe('shared conditional vectors (editor shouldShowField)', () => {
  it('suite is non-empty', () => {
    expect(suite.vectors.length).toBeGreaterThan(0);
  });

  for (const vector of suite.vectors) {
    const expected =
      typeof vector.expect === 'boolean' ? vector.expect : vector.expect.editor;
    it(`${vector.name} -> ${expected}`, () => {
      const field = vector.field as unknown as FormField;
      const fields = [
        ...(vector.fields ?? []),
        vector.field,
      ] as unknown as FormField[];
      expect(shouldShowField(field, vector.fieldValues, fields)).toBe(expected);
    });
  }
});

// P3.0 (bd h76m.7): the shape-only coexistence contract, pinned by the same
// shared file. MALFORMED-* cases must fail OPEN (null) and warn.
describe('shared normalize vectors (editor normalizeToComposite)', () => {
  it('suite has normalize cases', () => {
    expect(suite.normalize.length).toBeGreaterThan(0);
  });

  it('the two island copies are byte-identical (duplicated VERBATIM by design)', () => {
    const root = repoRoot();
    const editorCopy = readFileSync(
      resolve(root, 'schema-editor/src/utils/normalizeToComposite.ts'),
      'utf-8',
    );
    const frontendCopy = readFileSync(
      resolve(root, 'frontend/src/schema-forms/utils/normalizeToComposite.ts'),
      'utf-8',
    );
    expect(editorCopy).toBe(frontendCopy);
  });

  for (const c of suite.normalize) {
    it(c.name, () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      try {
        expect(normalizeToComposite(c.input)).toEqual(c.expect);
        if (c.name.startsWith('MALFORMED')) {
          expect(warnSpy).toHaveBeenCalled();
        } else {
          expect(warnSpy).not.toHaveBeenCalled();
        }
      } finally {
        warnSpy.mockRestore();
      }
    });
  }
});

// P3.0 exit criterion 2: normalize is pure shape -- for every v0 vector,
// evaluating the normalized one-atom group's atom must equal evaluating the
// original legacy show_if through TODAY'S evaluator.
describe('property: evaluate(normalize(show_if)) == evaluate(show_if)', () => {
  for (const vector of suite.vectors) {
    if (!vector.field.show_if) continue;
    it(vector.name, () => {
      const field = vector.field as unknown as FormField;
      const fields = [
        ...(vector.fields ?? []),
        vector.field,
      ] as unknown as FormField[];
      const original = shouldShowField(field, vector.fieldValues, fields);

      const group = normalizeToComposite(vector.field.show_if);
      expect(group).not.toBeNull();
      expect(group!.all_of).toHaveLength(1);
      const rebuilt = {
        ...vector.field,
        show_if: group!.all_of![0],
      } as unknown as FormField;
      expect(shouldShowField(rebuilt, vector.fieldValues, fields)).toBe(original);
    });
  }
});
