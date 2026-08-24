/**
 * A client link PINS the form -- verified against the REAL onboarding modal
 * (bd polyglot-pdf-ugm6).
 *
 * WHY THIS FILE EXISTS SEPARATELY FROM ClientLinkEntry.test.tsx: that suite
 * mocks SchemaFormDemo away, so its test named "PINS the form so the client
 * never sees a form picker" only proves sessionStorage was WRITTEN. It could
 * never see that the app then ignored the pin and showed the picker anyway,
 * which is exactly what shipped (Opus cross-surface r1).
 *
 * The restore effect in SchemaFormDemo skips the modal only when BOTH formId
 * and language are set. A client link deliberately sets only the form -- the
 * language is the client's own choice -- so the client DOES reach the modal,
 * and the modal must ask for language only and then proceed with the pinned
 * form. Without the preselectedFormId prop it fell through to "Select Form"
 * and offered the whole catalogue.
 *
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { LanguageSelectionModal } from "./components/LanguageSelectionModal";

/** Click the language BUTTON. "English" renders twice inside each card (a
 *  native name and an english name), so a bare getByText is ambiguous. */
function pickLanguage(name = "English") {
  const buttons = screen.getAllByRole("button");
  const match = buttons.find((b) => b.textContent?.includes(name));
  if (!match) throw new Error("no language button for " + name);
  return match;
}

const FORMS = [
  { id: "firm-a-intake", label: "Firm A Intake" },
  { id: "i-90", label: "I-90" },
  { id: "n-400", label: "N-400" },
];

describe("client link form pinning", () => {
  afterEach(() => cleanup());

  it("asks ONLY for language and proceeds with the pinned form", () => {
    // The client-link shape: a form is pinned, no language yet.
    const onSelection = vi.fn();
    render(
      <LanguageSelectionModal
        forms={FORMS}
        onSelection={onSelection}
        preselectedFormId="firm-a-intake"
      />,
    );

    fireEvent.click(pickLanguage());

    // Straight through with the PINNED form -- no second step.
    expect(onSelection).toHaveBeenCalledWith("firm-a-intake", "English");
  });

  it("never offers a form picker when a form is pinned", () => {
    // The actual exit-criterion failure: a client seeing (and being able to
    // choose from) the firm's other forms -- for a PUBLIC kit, the entire
    // public catalogue.
    //
    // Mutation: drop preselectedFormId -- red (the picker appears).
    render(
      <LanguageSelectionModal
        forms={FORMS}
        onSelection={vi.fn()}
        preselectedFormId="firm-a-intake"
      />,
    );

    fireEvent.click(pickLanguage());

    expect(screen.queryByText(/select form/i)).toBeNull();
    for (const other of ["I-90", "N-400"]) {
      expect(screen.queryByText(other)).toBeNull();
    }
  });

  it("STILL shows the picker for a staff user with no pin", () => {
    // The narrowing must not leak into the staff path: a signed-in user
    // choosing a form at app start is the normal flow and must keep working.
    render(<LanguageSelectionModal forms={FORMS} onSelection={vi.fn()} />);

    fireEvent.click(pickLanguage());

    expect(screen.getByText(/select form/i)).toBeTruthy();
  });
});
