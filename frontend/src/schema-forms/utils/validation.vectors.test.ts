// Shared conditional-semantics vector runner -- FRONTEND RUNTIME side (bd
// polyglot-pdf-h76m.1, P0.1). Executes every vector in the repo-root
// shared/conditional-vectors.json against THIS package's shouldShowField and
// asserts the pinned expectation. The editor preview has a sibling runner
// (schema-editor/src/utils/conditionalVisibility.vectors.test.ts) over the SAME
// file: a semantic change made in one evaluator but not the other (or not in the
// vector file) turns exactly one suite red. Vectors with a per-evaluator expect
// object pin the shapes where the two evaluators genuinely diverge today; this
// runner reads the `frontend` leg.

import { describe, it, expect } from "vitest";
import { shouldShowField } from "./validation";
import type { FormField } from "../types/schema";
import rawSuite from "../../../../shared/conditional-vectors.json";

interface Vector {
  name: string;
  field: Record<string, unknown>;
  fields?: Record<string, unknown>[];
  fieldValues: Record<string, unknown>;
  expect: boolean | { frontend: boolean; editor: boolean };
}

const suite = rawSuite as unknown as { vectors: Vector[] };

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
