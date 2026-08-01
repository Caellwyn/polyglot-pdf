/**
 * bd polyglot-pdf-52qm.7 -- the completion denominator must exclude statically
 * hidden fields.
 *
 * VoiceOverlay computes `const totalFields = schema.fields.length` (four sites),
 * with no hidden filter -- while navigation/visibility elsewhere correctly uses
 * `!f.hidden && shouldShowField(...)` (schemaFormState.ts). On the shipped W-7
 * that means the counter reads "N of 53" while only 46 fields can ever be
 * filled, so progress caps at 87% and the form never reads complete.
 *
 * This is a CHARACTERIZATION test: it pins the current arithmetic so the gap is
 * visible in CI. When the counter is fixed to exclude hidden fields, flip the
 * marked assertion to expect the visible count.
 */
import { describe, expect, it } from "vitest";
import w7 from "../../../../form-kits/w7/schema.json";

type Field = { id: string; hidden?: boolean; show_if?: unknown };

const fields = (w7 as { fields: Field[] }).fields;

describe("W-7 completion denominator", () => {
  it("has statically hidden fields that can never be filled", () => {
    const hidden = fields.filter(f => f.hidden);
    expect(hidden.length).toBeGreaterThan(0);
    // Statically hidden: no condition could ever reveal them.
    for (const f of hidden) {
      expect(f.show_if).toBeUndefined();
    }
  });

  it("GAP: schema.fields.length counts hidden fields the user cannot fill", () => {
    const total = fields.length; // what VoiceOverlay uses as the denominator
    const visible = fields.filter(f => !f.hidden).length; // what it should use
    const hidden = total - visible;

    // Relative, not magic numbers: W-7 is hand-edited by the maintainer, so a
    // hardcoded 53/46 would break on any unrelated field addition and read as a
    // regression rather than "the fixture moved".
    expect(hidden).toBeGreaterThan(0);
    expect(visible).toBeLessThan(total);

    // The consequence: progress can never reach 100% while hidden fields are
    // counted, because nothing can ever fill them.
    const ceiling = (visible / total) * 100;
    expect(ceiling).toBeLessThan(100);

    // WHEN FIXED: the denominator should equal `visible`, making the ceiling 100.
    expect(total).not.toBe(visible); // gap closed -- flip this test
  });
});
