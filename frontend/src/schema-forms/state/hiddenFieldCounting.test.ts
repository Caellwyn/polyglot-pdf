/**
 * bd polyglot-pdf-52qm.7 -- the completion denominator must exclude fields the
 * user cannot act on.
 *
 * This WAS a characterization test pinning the defect (progress capped below
 * 100% because `schema.fields.length` counted statically hidden fields). The
 * denominator is now filtered, so the assertions are flipped to the FIXED
 * behavior and stand as the regression guard.
 *
 * What getProgress / getProgressCounts count (schemaFormState.ts):
 *   - NOT `hidden`
 *   - unconditional, OR `show_if` currently satisfied
 *   - `ignored` needs no filter: ignoring quarantines the field out of
 *     `schema.fields` entirely (schema-editor/src/utils/ignoreField.ts), so it
 *     never reaches any counting surface.
 *
 * VoiceOverlay.tsx's 3 live progress-counter sites (the field-count/section-
 * switch effects) were migrated onto getProgressCounts, and VoiceOverlayMobile
 * has none (its `fieldCount`/`requiredCount` render a static whole-form
 * inventory -- "N fields, M required" -- not a completion ratio, so raw
 * schema.fields.length is the CORRECT count there) -- bd polyglot-pdf-kbkd.
 * Still separately tracked: the backend renders its own unfiltered
 * "Progress: N/M" into the voice model's prompt (ai_context.py) -- a distinct
 * surface this bead did not touch. This file pins the shared state-manager
 * path only.
 *
 * THE SPECIMEN IS FROZEN, and is the last GIT-TRACKED W-7 rather than the
 * published one. Two reasons, both load-bearing:
 *   - no kit is tracked any more (bd polyglot-pdf-q3u5r), so a live import of
 *     form-kits/w7/schema.json fails the build in CI while resolving fine on a
 *     machine that pulled the kit;
 *   - the PUBLISHED W-7 has zero hidden fields. The maintainer removed the
 *     acceptance-agent block in the schema editor, and those 7 fields were the
 *     only statically hidden ones. This test asserts hidden.length > 0, so its
 *     premise died when the FORM was fixed -- it would have broken on the next
 *     kit refresh regardless of git.
 * Freezing keeps the RULE under test while the form moves on. Structure only:
 * labels and geometry are stripped, because counting never reads them.
 */
import { describe, expect, it } from "vitest";
import w7 from "./__fixtures__/w7_structure_frozen.json";
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

  it("counts a SKIPPED field as done, like isSectionValid does", () => {
    // A skipped field satisfies isSectionValid (a required field must stay
    // skippable -- defer to a translator, or genuinely no answer) and counts as
    // SETTLED for computeReadyWindows. If getProgress disagreed, a user who
    // legitimately skips could complete the section while the bar stuck below
    // 100% -- the same "never reads complete" complaint the hidden-field filter
    // fixed. Uses the fixpoint fill, then converts one entry to a skip.
    const filled = stateWithAllVisibleFieldsFilled() as unknown as {
      fieldValues: Record<string, { value: string; confirmed?: boolean; skipped?: boolean }>;
    };
    const firstId = Object.keys(filled.fieldValues)[0];
    expect(firstId).toBeDefined();
    // A skip stores no value (bd 4dxt: the skipped flag is separate, the value
    // stays empty) -- so this is exactly the shape that must still count.
    filled.fieldValues[firstId] = { value: "", skipped: true };

    const progress = SchemaFormStateManager.getProgress(
      filled as unknown as ProgressState
    );
    expect(progress).toBe(100);
  });

  it("does not count an empty array as filled", () => {
    // isSectionValid treats [] as empty; getProgress must agree or a
    // multi-select left untouched would read as answered.
    const first = (fields as unknown as FormField[]).find(
      f => !f.hidden && !f.show_if
    )!;
    const progress = SchemaFormStateManager.getProgress(
      stateFrom({ [first.id]: { value: [] as unknown as string, confirmed: true } })
    );
    expect(progress).toBe(0);
  });

  it("COUNTS a hidden field whose show_if is satisfied (it renders)", () => {
    // shouldShowField returns `!field.hidden` ONLY when there is no show_if.
    // With a SATISFIED show_if, a `hidden: true` field IS rendered by
    // FieldRenderer and IS required by isSectionValid -- so it must appear in
    // the progress ratio too. An extra `!f.hidden &&` in getProgress would drop
    // it from BOTH halves and resurrect the "never reads complete" bug for this
    // shape. No shipped kit has it today, hence a synthetic fixture.
    const trigger = { id: "trig", type: "text" };
    const revealed = {
      id: "revealed",
      type: "text",
      hidden: true,
      show_if: { field: "trig", operator: "is_not_empty" },
    };
    const tiny = {
      ...schema,
      fields: [trigger, revealed],
    } as unknown as FormSchema;

    // Trigger empty -> show_if unmet -> `revealed` is not visible; only `trig`
    // counts, and it is empty, so 0%.
    const before = {
      schema: tiny,
      fieldValues: {},
    } as unknown as ProgressState;
    expect(SchemaFormStateManager.getProgress(before)).toBe(0);

    // Trigger filled -> show_if satisfied -> `revealed` becomes answerable and
    // MUST enter the denominator. 1 of 2 done => 50%, NOT 100%.
    const after = {
      schema: tiny,
      fieldValues: { trig: { value: "x", confirmed: true } },
    } as unknown as ProgressState;
    expect(SchemaFormStateManager.getProgress(after)).toBe(50);
  });

  it("returns 0 rather than NaN when nothing is visible", () => {
    const empty = {
      schema: { ...schema, fields: [] },
      fieldValues: {},
    } as unknown as ProgressState;
    expect(SchemaFormStateManager.getProgress(empty)).toBe(0);
  });
});

describe("getProgressCounts (bd polyglot-pdf-kbkd)", () => {
  it("total matches the VISIBLE count, not schema.fields.length", () => {
    // Same premise as "measures against the VISIBLE count" above, but
    // asserting the raw counts a UI counter displays ("N of M"), not just the
    // derived percentage.
    const unconditionalVisible = fields.filter(f => !f.hidden && !f.show_if);
    const { total } = SchemaFormStateManager.getProgressCounts(
      stateFrom({})
    );
    expect(total).toBe(unconditionalVisible.length);
    expect(total).toBeLessThan(fields.length);
  });

  it("filled/total agree exactly with getProgress's own ratio", () => {
    // getProgress delegates to getProgressCounts internally; this pins that
    // the two can never drift apart (a caller reading one must be able to
    // trust the other means the same thing).
    const state = stateWithAllVisibleFieldsFilled();
    const { filled, total } = SchemaFormStateManager.getProgressCounts(state);
    expect(filled).toBe(total);
    expect(SchemaFormStateManager.getProgress(state)).toBe(100);
  });

  it("a SKIPPED field counts as filled in the numerator too", () => {
    const trigger: Field & Partial<FormField> = { id: "trig", type: "text" };
    const tiny = { ...schema, fields: [trigger] } as unknown as FormSchema;
    const state = {
      schema: tiny,
      fieldValues: { trig: { skipped: true } },
    } as unknown as ProgressState;
    expect(SchemaFormStateManager.getProgressCounts(state)).toEqual({
      filled: 1,
      total: 1,
    });
  });

  it("returns {filled: 0, total: 0} rather than NaN when nothing is visible", () => {
    const empty = {
      schema: { ...schema, fields: [] },
      fieldValues: {},
    } as unknown as ProgressState;
    expect(SchemaFormStateManager.getProgressCounts(empty)).toEqual({
      filled: 0,
      total: 0,
    });
  });
});

describe("VoiceOverlay wiring (bd polyglot-pdf-kbkd)", () => {
  it("VoiceOverlay.tsx's progress counters call getProgressCounts, not a raw schema.fields.length scan", async () => {
    // A mechanical source-text guard, not a rendered-component test: fully
    // rendering VoiceOverlay needs heavy VAD/connection-manager mocking (see
    // VoiceOverlay.disclaimer.test.tsx), which is disproportionate for pinning
    // "did this call site get migrated." Reads the real file so a future
    // revert of the fix (reintroducing a raw schema.fields.length denominator
    // or a raw fieldValues key scan) fails here.
    const fs = await import("node:fs");
    const path = await import("node:path");
    const filePath = path.resolve(__dirname, "../../demo/VoiceOverlay.tsx");
    const src = fs.readFileSync(filePath, "utf-8");

    // The fix: all 3 live counter sites call the shared helper.
    const callSites = (src.match(/getProgressCounts\(/g) || []).length;
    expect(callSites).toBeGreaterThanOrEqual(3);

    // The regression this guards against: a raw denominator/numerator scan
    // reintroduced at a progress-counter call site. Strip comment lines first
    // so this doesn't trip on prose ABOUT the old pattern (as in the
    // migration comments this fix itself left behind), then collapse all
    // whitespace so a cosmetic reformat (e.g. `schema . fields . length` or a
    // line break mid-expression) cannot silently defeat this regex the way
    // the un-collapsed version could.
    const codeLines = src
      .split("\n")
      .filter((line) => !line.trim().startsWith("//"))
      .join("\n")
      .replace(/\s+/g, "");
    expect(codeLines).not.toMatch(/schema\.fields\.length/);
    expect(codeLines).not.toMatch(/Object\.keys\([^)]*fieldValues[^)]*\)\.filter/);
  });
});
