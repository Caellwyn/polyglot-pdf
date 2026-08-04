/**
 * bd polyglot-pdf-52qm.7 -- the completion denominator must exclude fields the
 * user cannot act on.
 *
 * This WAS a characterization test pinning the defect (progress capped below
 * 100% because `schema.fields.length` counted statically hidden fields). The
 * denominator is now filtered, so the assertions are flipped to the FIXED
 * behavior and stand as the regression guard.
 *
 * What getProgress counts (schemaFormState.ts):
 *   - NOT `hidden`
 *   - unconditional, OR `show_if` currently satisfied
 *   - `ignored` needs no filter: ignoring quarantines the field out of
 *     `schema.fields` entirely (schema-editor/src/utils/ignoreField.ts), so it
 *     never reaches any counting surface.
 *
 * Still-unfixed sites (verified 2026-08-03), tracked separately: VoiceOverlay.tsx
 * (4 sites) and VoiceOverlayMobile.tsx (1) inline `schema.fields.length` in React
 * state, and the backend renders its own unfiltered "Progress: N/M" into the
 * voice model's prompt (ai_context.py). This file pins the shared
 * state-manager path only.
 */
import { describe, expect, it } from "vitest";
import w7 from "../../../../form-kits/w7/schema.json";
import { SchemaFormStateManager } from "./schemaFormState";
import { shouldShowField } from "../utils/validation";
import type { FormField, FormSchema } from "../types/schema";

type Field = { id: string; hidden?: boolean; show_if?: unknown };

const schema = w7 as unknown as FormSchema;
const fields = (w7 as { fields: Field[] }).fields;

type ProgressState = Parameters<typeof SchemaFormStateManager.getProgress>[0];

function stateFrom(
  fieldValues: Record<string, { value: string; confirmed: boolean }>
): ProgressState {
  return { schema, fieldValues } as unknown as ProgressState;
}

/**
 * Mark every field the user can actually act on as filled, to FIXPOINT.
 *
 * Filling is not a single pass: an answer can satisfy a `show_if` and reveal a
 * new field (on the W-7, filling `name_of_delegate` reveals
 * `delegate_relationship` via `is_not_empty`). A one-pass fill therefore leaves
 * a genuinely-visible field empty and progress legitimately below 100%. Iterate
 * until the visible set stops growing -- which is exactly what a user does.
 *
 * Uses the REAL shouldShowField rather than a static `!f.show_if`
 * approximation, so the fixture cannot drift away from the code's own notion of
 * visibility.
 */
function stateWithAllVisibleFieldsFilled(): ProgressState {
  const fieldValues: Record<string, { value: string; confirmed: boolean }> = {};
  for (let pass = 0; pass < 10; pass++) {
    let added = 0;
    for (const f of fields as unknown as FormField[]) {
      if (f.hidden || fieldValues[f.id]) continue;
      if (!shouldShowField(f, fieldValues, fields as unknown as FormField[])) continue;
      fieldValues[f.id] = { value: "x", confirmed: true };
      added++;
    }
    if (added === 0) break;
  }
  return stateFrom(fieldValues);
}

describe("W-7 completion denominator", () => {
  it("has statically hidden fields that can never be filled", () => {
    const hidden = fields.filter(f => f.hidden);
    // Guards the premise: if the W-7 ever stops shipping hidden fields, the
    // tests below prove nothing, so fail loudly rather than pass vacuously.
    expect(hidden.length).toBeGreaterThan(0);
    // Statically hidden: no condition could ever reveal them.
    for (const f of hidden) {
      expect(f.show_if).toBeUndefined();
    }
  });

  it("reaches 100% when every visible field is filled", () => {
    // Anchored to the REAL function, not a re-implementation of its arithmetic.
    const progress = SchemaFormStateManager.getProgress(
      stateWithAllVisibleFieldsFilled()
    );
    expect(progress).toBe(100);
  });

  it("measures against the VISIBLE count, not the raw total", () => {
    const total = fields.length;
    // "Visible" on an EMPTY form is narrower than "not hidden": the W-7 also
    // carries conditional fields whose show_if is unmet until an answer reveals
    // them, and those are correctly excluded too. Derive the baseline from the
    // function itself rather than re-implementing shouldShowField here.
    const unconditionalVisible = fields.filter(f => !f.hidden && !f.show_if);
    expect(unconditionalVisible.length).toBeGreaterThan(0);
    // Premise guard: the kit really does have both exclusion classes.
    expect(total - unconditionalVisible.length).toBeGreaterThan(0);

    // Fill exactly half of the unconditionally-visible fields. Filling only
    // these keeps every show_if unmet, so the visible set stays fixed at
    // unconditionalVisible.length for the whole assertion. A 100%-only test
    // would still pass with a wrong denominator; this partial fill is what
    // actually pins which number we divide by.
    const half = Math.floor(unconditionalVisible.length / 2);
    const fieldValues: Record<string, { value: string; confirmed: boolean }> = {};
    for (const f of unconditionalVisible.slice(0, half)) {
      fieldValues[f.id] = { value: "x", confirmed: true };
    }

    const progress = SchemaFormStateManager.getProgress(stateFrom(fieldValues));
    expect(Math.round(progress)).toBe(
      Math.round((half / unconditionalVisible.length) * 100)
    );
    // ...and specifically NOT the old raw-total denominator.
    expect(Math.round(progress)).not.toBe(Math.round((half / total) * 100));
  });

  it("excludes conditional fields whose show_if is unmet", () => {
    // The W-7's conditional fields cannot be filled until an answer reveals
    // them, so counting them would cap progress below 100% exactly as the
    // hidden fields did.
    const conditional = fields.filter(f => !f.hidden && f.show_if);
    expect(conditional.length).toBeGreaterThan(0);

    // Fill ONE unconditional field and confirm the denominator counts only the
    // currently-visible set -- if unmet conditionals were counted, the
    // denominator would be the far larger non-hidden total and progress would
    // be a much smaller number.
    const firstUnconditional = (fields as unknown as FormField[]).find(
      f => !f.hidden && !f.show_if
    )!;
    const fieldValues = {
      [firstUnconditional.id]: { value: "x", confirmed: true },
    };
    const visibleNow = (fields as unknown as FormField[]).filter(
      f => !f.hidden && shouldShowField(f, fieldValues, fields as unknown as FormField[])
    ).length;
    const nonHidden = fields.filter(f => !f.hidden).length;
    // Premise: the two counts genuinely differ, or this proves nothing.
    expect(visibleNow).toBeLessThan(nonHidden);

    const progress = SchemaFormStateManager.getProgress(stateFrom(fieldValues));
    expect(Math.round(progress)).toBe(Math.round((1 / visibleNow) * 100));
    expect(Math.round(progress)).not.toBe(Math.round((1 / nonHidden) * 100));
  });

  it("ignores a stale value left on a hidden field", () => {
    // The numerator was independently wrong: it walked `fieldValues` keys, so a
    // value stranded on a field that is hidden (or whose show_if flipped off)
    // kept counting -- and could push progress ABOVE 100%.
    const fieldValues: Record<string, { value: string; confirmed: boolean }> = {};
    for (const f of fields) {
      if (!f.hidden) fieldValues[f.id] = { value: "x", confirmed: true };
    }
    for (const f of fields) {
      if (f.hidden) fieldValues[f.id] = { value: "stale", confirmed: true };
    }

    const progress = SchemaFormStateManager.getProgress(stateFrom(fieldValues));
    expect(progress).toBe(100);
  });

  it("returns 0 rather than NaN when nothing is visible", () => {
    const empty = {
      schema: { ...schema, fields: [] },
      fieldValues: {},
    } as unknown as ProgressState;
    expect(SchemaFormStateManager.getProgress(empty)).toBe(0);
  });
});
