/**
 * SchemaFormDemo actually HANDS the pin to the modal (bd polyglot-pdf-ugm6).
 *
 * Opus cross-surface r9 found this unpinned, making it the TENTH
 * one-layer-removed test in this bead -- and the most pointed one, because
 * clientLinkFormPin.test.tsx's own header says it exists to avoid exactly
 * this. It then renders LanguageSelectionModal DIRECTLY and hands it
 * `preselectedFormId="firm-a-intake"` by hand. That proves the modal honors
 * a pin it is given; nothing proved SchemaFormDemo gives it one. Replacing
 * the production expression with `undefined` left all 21 client-link tests
 * green while restoring the r1 defect in full: the client falls through to
 * "Select Form" and is offered the firm's whole catalogue.
 *
 * So this file mocks SchemaForm (heavy: WS/audio/PDF) but NOT the modal --
 * the wiring between them is the entire subject.
 *
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import { SchemaFormDemo } from "./SchemaFormDemo";
import {
  ONBOARDING_FORM_KEY,
  clearOnboardingState,
} from "./onboardingStorage";
import {
  clearClientLinkToken,
  setClientLinkToken,
} from "../shared/sessionCredential";

vi.mock("./components/SchemaForm", () => ({
  SchemaForm: () => <div data-testid="schema-form" />,
}));
// LanguageSelectionModal is deliberately NOT mocked.
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({ user: null }),   // a client: no account, ever
}));

const MANIFEST = {
  forms: [
    { id: "firm-a-intake", label: "Firm A Intake",
      schemaFile: "schema.json", schemaPath: "/form-kits/firm-a-intake/schema.json",
      pdfFile: "form.pdf", pdfPath: "/form-kits/firm-a-intake/form.pdf" },
    { id: "i-90", label: "I-90",
      schemaFile: "schema.json", schemaPath: "/form-kits/i-90/schema.json",
      pdfFile: "form.pdf", pdfPath: "/form-kits/i-90/form.pdf" },
    { id: "n-400", label: "N-400",
      schemaFile: "schema.json", schemaPath: "/form-kits/n-400/schema.json",
      pdfFile: "form.pdf", pdfPath: "/form-kits/n-400/form.pdf" },
  ],
};

afterEach(() => {
  cleanup();
  clearClientLinkToken();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

function stubManifest() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => MANIFEST,
    })) as unknown as typeof fetch,
  );
}

/** "English" renders twice per card (native + english name), so a bare
 *  getByText is ambiguous -- click the BUTTON. */
async function pickEnglish() {
  const button = await waitFor(() => {
    const match = screen
      .getAllByRole("button")
      .find((b) => b.textContent?.includes("English"));
    if (!match) throw new Error("no language button yet");
    return match;
  });
  fireEvent.click(button);
}

describe("SchemaFormDemo hands the client's pinned form to the modal", () => {
  it("offers NO form picker when a form is pinned", async () => {
    // The client-link shape: ClientLinkEntry pinned the form and left the
    // language unset (the language is the client's own choice).
    //
    // Mutation: preselectedFormId={undefined} in SchemaFormDemo -- red.
    sessionStorage.setItem(ONBOARDING_FORM_KEY, "firm-a-intake");
    stubManifest();

    render(<SchemaFormDemo />);

    // The client picks their language -- the one onboarding step that IS
    // theirs -- and must then go straight through, never to a form picker.
    await pickEnglish();

    await waitFor(() => {
      expect(screen.queryByText(/select form/i)).toBeNull();
      for (const other of ["I-90", "N-400"]) {
        expect(screen.queryByText(other)).toBeNull();
      }
    });
  });

  it("STILL offers the picker to a staff user with no pin", async () => {
    // The narrowing must not leak into the staff flow, where choosing a form
    // at app start is the normal path.
    stubManifest();

    render(<SchemaFormDemo />);

    await pickEnglish();

    // With NO pin, the staff flow must reach the form picker -- proving the
    // narrowing is driven by the pin and did not leak into the normal path.
    await waitFor(() => expect(screen.getByText(/select form/i)).toBeTruthy());
  });

  it("keeps the pin when a CLIENT clears the form mid-session", async () => {
    // THE MID-SESSION DOOR (Opus r10). "Clear form" reloads the page, and
    // ClientLinkEntry's reload recovery deliberately does NOT re-POST /open
    // because the form is "already pinned from the first open". So clearing
    // the pin hands the client the firm's whole catalogue on the next
    // render -- the r1 defect through a door the r1 fix never touched.
    //
    // Mutation: remove the hasClientLinkToken() guard in
    // clearOnboardingState -- red.
    setClientLinkToken("a-client-link");
    sessionStorage.setItem(ONBOARDING_FORM_KEY, "firm-a-intake");
    stubManifest();

    clearOnboardingState();          // exactly what the overlay button does

    render(<SchemaFormDemo />);
    await pickEnglish();

    await waitFor(() => {
      expect(screen.queryByText(/select form/i)).toBeNull();
      for (const other of ["I-90", "N-400"]) {
        expect(screen.queryByText(other)).toBeNull();
      }
    });
  });

  it("STILL clears the pin for STAFF, who need to pick a new form", async () => {
    // The whole point of "clear form" for staff: start a new client on a
    // DIFFERENT form. The client carve-out must not take that away.
    clearClientLinkToken();
    sessionStorage.setItem(ONBOARDING_FORM_KEY, "firm-a-intake");
    stubManifest();

    clearOnboardingState();

    render(<SchemaFormDemo />);
    await pickEnglish();

    await waitFor(() => expect(screen.getByText(/select form/i)).toBeTruthy());
  });
});
