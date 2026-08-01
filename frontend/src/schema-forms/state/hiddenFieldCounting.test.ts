/**
 * bd polyglot-pdf-52qm.7 -- the completion denominator must exclude statically
 * hidden fields.
 *
 * Every progress/count surface divides by `schema.fields.length` with no hidden
 * filter, while visibility elsewhere correctly uses `!f.hidden &&
 * shouldShowField(...)` (schemaFormState.ts). On the shipped W-7 that means 53
 * counted vs 46 fillable, so progress can never reach 100% and the form never
 * reads complete.
 *
 * Known sites (verified 2026-08-01):
 *   - SchemaFormStateManager.getProgress (schemaFormState.ts) -- exercised below
 *     via the REAL function, so a fix there flips this test.
 *   - VoiceOverlay.tsx (4 sites) and VoiceOverlayMobile.tsx (1 site) inline the
 *     same expression in React state; pinned by the schema-level assertion.
 *
 * This is a CHARACTERIZATION test: it asserts the CURRENT (defective) behavior
 * so the gap is visible in CI. When the denominator is fixed, the marked
 * assertions fail and should be flipped to expect full completion.
 */
import { describe, expect, it } from "vitest";
import w7 from "../../../../form-kits/w7/schema.json";
import { SchemaFormStateManager } from "./schemaFormState";
import type { FormSchema } from "../types/schema";

type Field = { id: string; hidden?: boolean; show_if?: unknown };

const schema = w7 as unknown as FormSchema;
const fields = (w7 as { fields: Field[] }).fields;

/** Mark every field the user can actually see as filled. */
function stateWithAllVisibleFieldsFilled() {
  const fieldValues: Record<string, { value: string; confirmed: boolean }> = {};
  for (const f of fields) {
    if (!f.hidden) fieldValues[f.id] = { value: "x", confirmed: true };
  }
  return { schema, fieldValues } as unknown as Parameters<
    typeof SchemaFormStateManager.getProgress
  >[0];
}

describe("W-7 completion denominator", () => {
  it("has statically hidden fields that can never be filled", () => {
    const hidden = fields.filter(f => f.hidden);
    expect(hidden.length).toBeGreaterThan(0);
    // Statically hidden: no condition could ever reveal them.
    for (const f of hidden) {
      expect(f.show_if).toBeUndefined();
    }
  });

  it("GAP: getProgress cannot reach 100% even with every visible field filled", () => {
    // Anchored to the REAL function, not a re-implementation of its arithmetic:
    // if getProgress starts filtering hidden fields, this assertion fails and
    // the test must be flipped -- which is the whole point of pinning it here.
    const progress = SchemaFormStateManager.getProgress(
      stateWithAllVisibleFieldsFilled()
    );

    expect(progress).toBeLessThan(100); // gap closed -- flip to toBe(100)
    expect(progress).toBeGreaterThan(0); // sanity: the fill actually registered
  });

  it("GAP: the shortfall equals exactly the hidden-field count", () => {
    const total = fields.length;
    const visible = fields.filter(f => !f.hidden).length;

    // Relative, not magic numbers: W-7 is hand-edited by the maintainer, so a
    // hardcoded 53/46 would break on any unrelated field addition and read as a
    // regression rather than "the fixture moved".
    expect(total - visible).toBeGreaterThan(0);

    const progress = SchemaFormStateManager.getProgress(
      stateWithAllVisibleFieldsFilled()
    );
    // The ceiling is precisely visible/total -- i.e. the hidden fields are the
    // entire cause, with no second contributing bug hiding behind this one.
    expect(Math.round(progress)).toBe(Math.round((visible / total) * 100));
  });
});
