// Shared conditional-semantics vector runner -- FRONTEND RUNTIME side (bd
// polyglot-pdf-h76m.1, P0.1). Executes every vector in the repo-root
// shared/conditional-vectors.json against THIS package's shouldShowField and
// asserts the pinned expectation. The editor preview has a sibling runner
// (schema-editor/src/utils/conditionalVisibility.vectors.test.ts) over the SAME
// file: a semantic change made in one evaluator but not the other (or not in the
// vector file) turns exactly one suite red. Vectors with a per-evaluator expect
// object pin the shapes where the two evaluators genuinely diverge today; this
// runner reads the `frontend` leg.

import { describe, it, expect, vi } from "vitest";
import { isFieldRequired, shouldShowField } from "./validation";
import { normalizeToComposite } from "./normalizeToComposite";
import type { FormField } from "../types/schema";
import rawSuite from "../../../../shared/conditional-vectors.json";

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
  vectorsV2: Vector[];
  require: Vector[];
  normalize: NormalizeCase[];
};

describe("shared conditional vectors (frontend shouldShowField)", () => {
  it("suite is non-empty", () => {
    expect(suite.vectors.length).toBeGreaterThan(0);
  });

  for (const vector of suite.vectors) {
    const expected =
      typeof vector.expect === "boolean" ? vector.expect : vector.expect.frontend;
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

// P3.1 (bd h76m.8): composite + membership semantics, pinned by the same
// shared file once both evaluators were rewired through normalizeToComposite.
describe("shared v2 vectors (frontend shouldShowField, composite + membership)", () => {
  it("suite has v2 cases", () => {
    expect(suite.vectorsV2.length).toBeGreaterThan(0);
  });

  for (const vector of suite.vectorsV2) {
    const expected =
      typeof vector.expect === "boolean" ? vector.expect : vector.expect.frontend;
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

// P3.1 (bd h76m.8): require_if evaluation (isFieldRequired) over the same
// shared file.
describe("shared require vectors (frontend isFieldRequired)", () => {
  it("suite has require cases", () => {
    expect(suite.require.length).toBeGreaterThan(0);
  });

  for (const vector of suite.require) {
    const expected =
      typeof vector.expect === "boolean" ? vector.expect : vector.expect.frontend;
    it(`${vector.name} -> ${expected}`, () => {
      const field = vector.field as unknown as FormField;
      const fields = [
        ...(vector.fields ?? []),
        vector.field,
      ] as unknown as FormField[];
      expect(isFieldRequired(field, vector.fieldValues, fields)).toBe(expected);
    });
  }
});

// P3.0 (bd h76m.7): the shape-only coexistence contract, pinned by the same
// shared file. MALFORMED-* cases must fail OPEN (null) and warn.
describe("shared normalize vectors (frontend normalizeToComposite)", () => {
  it("suite has normalize cases", () => {
    expect(suite.normalize.length).toBeGreaterThan(0);
  });

  for (const c of suite.normalize) {
    it(c.name, () => {
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      try {
        expect(normalizeToComposite(c.input)).toEqual(c.expect);
        if (c.name.startsWith("MALFORMED")) {
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
describe("property: evaluate(normalize(show_if)) == evaluate(show_if)", () => {
  // Domain: LEGACY-shaped show_if only (every v0 vector today). A future
  // vector with a composite show_if belongs to the P3.1 v2 suite, not this
  // one-atom rebuild -- the shape guard keeps such an addition from turning
  // this property into a confusing .all_of[0] crash (fresh-eyes nit).
  const legacyVectors = suite.vectors.filter(
    (v) =>
      v.field.show_if &&
      typeof (v.field.show_if as Record<string, unknown>).field === "string",
  );

  it("covers every condition-bearing v0 vector", () => {
    expect(legacyVectors.length).toBeGreaterThan(0);
    expect(legacyVectors.length).toBe(
      suite.vectors.filter((v) => v.field.show_if).length,
    );
  });

  for (const vector of legacyVectors) {
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
