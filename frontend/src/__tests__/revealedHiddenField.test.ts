/**
 * bd polyglot-pdf-ubam -- a `hidden: true` field whose `show_if` is SATISFIED is
 * ANSWERABLE, and every surface must agree on that.
 *
 * WHY THIS SHAPE IS REAL: `shouldShowField` returns `!field.hidden` ONLY when a
 * field has no `show_if`. With a satisfied `show_if` it returns the condition's
 * result -- so `hidden: true` + satisfied condition RENDERS (FieldRenderer calls
 * shouldShowField alone) and is REQUIRED (isSectionValid). Seven call sites had
 * independently re-derived visibility as `field.hidden || !shouldShowField(...)`,
 * which silently excluded exactly this shape and produced two user-visible bugs:
 *
 *   (a) FALSE COMPLETION -- isFormComplete skipped the field, so the form read
 *       complete with a visibly empty required field on screen. Since 2026-08-03
 *       that also SPENDS MONEY: completion fires the default-ON end-of-form pro
 *       validator (~$0.0093/call) against an incomplete snapshot.
 *   (b) UNREACHABLE BY VOICE -- computeNextField never offered it, switch_field
 *       refused it with reason:'hidden', handleFieldUpdate called it
 *       unavailable, and suggestNavigationCandidates omitted it. A required
 *       question the user could not answer the intended way.
 *
 * No shipped kit uses hidden+show_if together, so this was DORMANT -- hence the
 * synthetic fixture. It goes live the moment a kit author adds a
 * conditionally-revealed field that is also statically hidden, and nothing warns
 * them.
 *
 * These tests assert the surfaces AGREE, rather than pinning each separately:
 * the failure mode was divergence, so agreement is the property worth pinning.
 */
import { describe, expect, it } from "vitest";
import { computeNextField, getFormProgress, isFormComplete } from "../navigation";
import { SchemaFormStateManager } from "../schema-forms/state/schemaFormState";
import { shouldShowField } from "../schema-forms/utils/validation";
import type { FormField, FormSchema } from "../schema-forms/types/schema";

/** trigger (plain) + revealed (hidden:true, shown once trigger is non-empty). */
const TRIGGER: any = {
  id: "trigger",
  name: "Trigger",
  spoken_name: "trigger",
  type: "text",
  section_id: "s1",
};
const REVEALED: any = {
  id: "revealed",
  name: "Revealed",
  spoken_name: "revealed",
  type: "text",
  section_id: "s1",
  hidden: true,
  validation: { required: true },
  show_if: { field: "trigger", operator: "is_not_empty" },
};

const schema = {
  form_metadata: { form_number: "TEST" },
  sections: [{ id: "s1", title: "S1", field_ids: ["trigger", "revealed"] }],
  fields: [TRIGGER, REVEALED],
} as unknown as FormSchema;

function stateWith(fieldValues: Record<string, any>) {
  return { schema, fieldValues, validationErrors: {} } as any;
}

/** trigger answered+confirmed; `revealed` is now shown but still empty. */
const REVEALED_BUT_EMPTY = stateWith({
  trigger: { value: "yes", confirmed: true },
});

describe("a hidden field whose show_if is satisfied (bd ubam)", () => {
  it("premise: the fixture really does render once the condition is met", () => {
    // If this fails the whole file is vacuous -- shouldShowField is the
    // predicate every assertion below depends on.
    expect(shouldShowField(REVEALED as FormField, {}, schema.fields)).toBe(false);
    expect(
      shouldShowField(
        REVEALED as FormField,
        { trigger: { value: "yes" } },
        schema.fields
      )
    ).toBe(true);
  });

  it("does NOT report the form complete while it is unconfirmed", () => {
    // The false-completion bug: this returned true, firing the paid validator
    // on a form with a visibly empty required field.
    expect(isFormComplete(REVEALED_BUT_EMPTY)).toBe(false);
  });

  it("is offered as the next field to fill (reachable by voice)", () => {
    // The reachability bug: computeNextField skipped it forever.
    expect(computeNextField(REVEALED_BUT_EMPTY)?.id).toBe("revealed");
  });

  it("appears in the navigable suggestions", () => {
    const suggestions = SchemaFormStateManager.suggestNavigationCandidates(
      REVEALED_BUT_EMPTY,
      "revealed"
    );
    expect(suggestions.map(s => s.field_id)).toContain("revealed");
  });

  it("counts in BOTH progress functions, which agree with each other", () => {
    // Divergence was the bug, so pin agreement. 1 of 2 visible fields done.
    expect(SchemaFormStateManager.getProgress(REVEALED_BUT_EMPTY)).toBe(50);
    expect(getFormProgress(REVEALED_BUT_EMPTY).percentage).toBe(50);
  });

  it("progress and completion agree once it IS confirmed", () => {
    const done = stateWith({
      trigger: { value: "yes", confirmed: true },
      revealed: { value: "answered", confirmed: true },
    });
    expect(SchemaFormStateManager.getProgress(done)).toBe(100);
    expect(getFormProgress(done).percentage).toBe(100);
    expect(isFormComplete(done)).toBe(true);
    expect(computeNextField(done)).toBeNull();
  });

  it("honours a navigation PIN on it (the jump is not dropped as stale)", () => {
    // resolveLivePin had the same extra `!pinned.hidden` term, so a pin on this
    // shape was treated as STALE and silently dropped -- stranding the very
    // jump the user asked for on a field the form is showing.
    //
    // The pin must be ISOLATED to be observable: pinning `revealed` while it is
    // also the natural next field proves nothing (the PRIORITY-2 scan returns it
    // either way -- a genuinely vacuous assertion). So give the scan a DIFFERENT
    // answer: add a second visible empty field EARLIER in schema order, which
    // computeNextField would return if the pin were dropped.
    const early: any = {
      id: "early",
      name: "Early",
      spoken_name: "early",
      type: "text",
      section_id: "s1",
    };
    const pinSchema = {
      form_metadata: { form_number: "TEST" },
      sections: [{ id: "s1", title: "S1", field_ids: ["early", "trigger", "revealed"] }],
      fields: [early, TRIGGER, REVEALED],
    } as unknown as FormSchema;

    const pinned = {
      schema: pinSchema,
      fieldValues: { trigger: { value: "yes", confirmed: true } },
      validationErrors: {},
      pinnedFieldId: "revealed",
    } as any;

    // Sanity: without the pin, the scan really would return `early`.
    expect(computeNextField({ ...pinned, pinnedFieldId: undefined })?.id).toBe("early");
    // With the pin, the pinned field wins -- only true if the pin resolved LIVE.
    expect(computeNextField(pinned)?.id).toBe("revealed");
  });

  it("stays excluded while its condition is UNMET", () => {
    // The other half: an unrevealed field must not be counted or offered, or
    // the bar could never reach 100 and voice would ask an unshown question.
    const unmet = stateWith({});
    expect(computeNextField(unmet)?.id).toBe("trigger");
    // Only `trigger` is visible, and it is empty.
    expect(SchemaFormStateManager.getProgress(unmet)).toBe(0);
    expect(getFormProgress(unmet).total).toBe(1);
  });
});
