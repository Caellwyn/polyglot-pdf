/**
 * PDF fields must never be rendered with a COERCING HTML input type.
 * bd polyglot-pdf-md20o.
 *
 * These are PDF AcroForm fields, not web-form fields. The kit schema's
 * help.format_hint is the authority on a value's shape, and the PDF layer
 * writes the stored string verbatim (pdf_fill_routes.py never rewrites a
 * value). A native input type silently coerces or truncates the value to the
 * browser's own convention, which then diverges from what the PDF and the
 * backend validator expect -- and the voice model reads the coerced value back
 * out and learns the wrong format from it.
 *
 * Live failure this pins (maintainer session, W-7, 2026-08-25): date_of_birth
 * stored "1980-10-26" on a field declaring MM/DD/YYYY, because
 * <input type="date"> can only hold yyyy-mm-dd per the HTML spec. An ISO
 * string in a comb-8 date box renders as a plausible-looking WRONG date -- the
 * same class documented at pdf_fill_routes.py:200-236, where '1990-03-14'
 * stripped to '19900314' and printed as month=19 on a filed ITIN application.
 */

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FieldRenderer } from "../FieldRenderer";
import type { FormField } from "../../types/schema";

// HTML input types that COERCE or constrain the value the browser will hold.
// A PDF-backed field must never use one of these: the kit's format_hint is the
// authority, not the browser's convention.
const COERCING_INPUT_TYPES = ["date", "month", "week", "time", "datetime-local", "number", "email", "tel", "url"];

// Every schema field type that renders a free-text value the PDF will receive.
// Enumerations (radio/select/checkbox) are excluded on purpose: they are
// genuine closed sets, not free-text coercion, so a native type is correct
// there.
const VALUE_BEARING_TYPES = ["text", "date", "number", "email", "tel", "textarea"];

function fieldOf(type: string, extra: Partial<FormField> = {}): FormField {
  return {
    id: `f_${type}`,
    name: `Field ${type}`,
    type,
    section_id: "sec1",
    ...extra,
  } as FormField;
}

function renderField(field: FormField) {
  return render(
    <FieldRenderer field={field} value="" onChange={vi.fn()} onBlur={vi.fn()} />
  );
}

describe("no coercing input types on PDF-backed fields", () => {
  it.each(VALUE_BEARING_TYPES)(
    "type=%s does not render a coercing HTML input type",
    (schemaType) => {
      const { container } = renderField(fieldOf(schemaType));
      const control = container.querySelector("input, textarea");
      expect(control, `no input rendered for schema type ${schemaType}`).toBeTruthy();

      // textarea has no `type`; that is fine -- it cannot coerce.
      const domType = control!.getAttribute("type");
      if (domType !== null) {
        expect(
          COERCING_INPUT_TYPES,
          `schema type "${schemaType}" rendered <input type="${domType}">, which coerces the ` +
            `value away from the kit's declared format`
        ).not.toContain(domType);
      }
    }
  );

  it("a date field renders a text input, not a native date picker", () => {
    const { container } = renderField(
      fieldOf("date", { help: { format_hint: "MM/DD/YYYY" } } as Partial<FormField>)
    );
    const input = container.querySelector("input")!;
    expect(input.getAttribute("type")).toBe("text");
  });

  it("a month_year date field also renders text, not <input type=month>", () => {
    // date_precision previously routed to type="month", which has the same
    // ISO-coercion problem (yyyy-MM).
    const { container } = renderField(
      fieldOf("date", { date_precision: "month_year" } as Partial<FormField>)
    );
    expect(container.querySelector("input")!.getAttribute("type")).toBe("text");
  });

  it("a date field shows its declared format as the placeholder", () => {
    // The hint is how the user learns the expected shape once the native
    // picker's implicit affordance is gone.
    const { container } = renderField(
      fieldOf("date", { help: { format_hint: "MM/DD/YYYY" } } as Partial<FormField>)
    );
    expect(container.querySelector("input")!.getAttribute("placeholder")).toBe("MM/DD/YYYY");
  });
});

describe("comb cell count is not applied as a text limit", () => {
  it("does not truncate a value whose declared format exceeds max_length", () => {
    // The exact W-7 shape: comb-8 widget, 10-char declared format. Wiring the
    // cell count to maxLength would clip "10/26/1980" to "10/26/19" -- a wrong
    // year on a filed form.
    const { container } = renderField(
      fieldOf("text", {
        max_length: 8,
        help: { format_hint: "MM/DD/YYYY" },
      } as Partial<FormField>)
    );
    const input = container.querySelector("input")!;
    const maxLength = input.getAttribute("maxLength");
    expect(
      maxLength === null || Number(maxLength) >= "MM/DD/YYYY".length,
      `maxLength=${maxLength} would truncate the field's own declared format`
    ).toBe(true);
  });

  it("still honors max_length when the declared format fits inside it", () => {
    // Guards the other direction: this is a real author-set cap and must
    // survive. Without this, "fixing" the truncation by dropping maxLength
    // entirely would pass the test above and silently remove every cap.
    const { container } = renderField(
      fieldOf("text", {
        max_length: 5,
        help: { format_hint: "ABCDE" },
      } as Partial<FormField>)
    );
    expect(container.querySelector("input")!.getAttribute("maxLength")).toBe("5");
  });

  it("still honors a nested validation.max_length with no format hint", () => {
    const { container } = renderField(
      fieldOf("text", { validation: { max_length: 12 } } as Partial<FormField>)
    );
    expect(container.querySelector("input")!.getAttribute("maxLength")).toBe("12");
  });
});

describe("max_length edge cases", () => {
  it("preserves a max_length of 0 instead of treating it as absent", () => {
    // 0 is falsy but MEANINGFUL. A `||` fallback here would silently swap a
    // real zero-width cap for an unrelated validation.max_length, or drop it.
    // No shipped kit sets 0 today -- this pins the branch before one does.
    const { container } = renderField(
      fieldOf("text", {
        max_length: 0,
        validation: { max_length: 25 },
      } as Partial<FormField>)
    );
    expect(container.querySelector("input")!.getAttribute("maxLength")).toBe("0");
  });

  it("falls back to validation.max_length when no top-level cap exists", () => {
    const { container } = renderField(
      fieldOf("text", { validation: { max_length: 7 } } as Partial<FormField>)
    );
    expect(container.querySelector("input")!.getAttribute("maxLength")).toBe("7");
  });

  it("keeps the cap when the declared format fits exactly", () => {
    // Boundary: format length === cap. Fits, so the cap must survive.
    const { container } = renderField(
      fieldOf("text", {
        max_length: 10,
        help: { format_hint: "MM/DD/YYYY" },
      } as Partial<FormField>)
    );
    expect(container.querySelector("input")!.getAttribute("maxLength")).toBe("10");
  });
});
