/**
 * SchemaFormDemo's "Start Fresh" button clears form state but PRESERVES
 * the client-link token (bd polyglot-pdf-ylokf).
 *
 * An earlier version of this bead's fix routed "Start Fresh" through
 * SchemaFormStateManager.clearAllClientState(), which also clears
 * vff_client_link_token. Opus cross-surface review caught the
 * consequence before it shipped: ClientLinkEntry's reload-recovery
 * branch (readTokenFromHash finds nothing once the URL fragment is
 * stripped) depends entirely on hasClientLinkToken() to reach the
 * "ready" phase -- clear the token and the very next reload (which this
 * button triggers) lands on "This link is not valid" instead of the
 * form the client was filling. A staff session never has a token set in
 * the first place, so leaving it untouched costs staff nothing.
 *
 * Renders past the onboarding modal (formId + language pre-seeded, per
 * loadOnboardingState's "returning user" branch) and past schemaLoading
 * (both the manifest fetch and the schema-JSON fetch are stubbed) so the
 * "Start Fresh" button actually mounts -- it only renders once
 * `!showOnboardingModal && schema`.
 *
 * Mocks SchemaForm (heavy: WS/audio/PDF), matching
 * SchemaFormDemo.formPin.test.tsx's own convention.
 *
 * Mutation: change handleClearSession back to
 * SchemaFormStateManager.clearAllClientState() -- red (the token is gone
 * after the click).
 *
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SchemaFormDemo } from "./SchemaFormDemo";
import { ONBOARDING_FORM_KEY, ONBOARDING_LANGUAGE_KEY } from "./onboardingStorage";
import { clearClientLinkToken, setClientLinkToken } from "../shared/sessionCredential";

vi.mock("./components/SchemaForm", () => ({
  SchemaForm: () => <div data-testid="schema-form" />,
}));
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({ user: null }),
}));

const MANIFEST = {
  forms: [
    {
      id: "firm-a-intake",
      label: "Firm A Intake",
      schema_file: "schema.json",
      schema_path: "/form-kits/firm-a-intake/schema.json",
      pdf_file: "form.pdf",
      pdf_path: "/form-kits/firm-a-intake/form.pdf",
    },
  ],
};

const MINIMAL_SCHEMA = {
  source: "web",
  form_metadata: { title: "Firm A Intake", version: "1.0", language: "en" },
  sections: [{ id: "section_1", label: "Section 1", order: 1, fields: [] }],
  fields: [],
};

const TOKEN_KEY = "vff_client_link_token";
const FORM_STATE_KEY = "schema_form_state";

beforeEach(() => {
  sessionStorage.setItem(ONBOARDING_FORM_KEY, "firm-a-intake");
  sessionStorage.setItem(ONBOARDING_LANGUAGE_KEY, "en");
  setClientLinkToken("a-real-client-link-token");
  sessionStorage.setItem(FORM_STATE_KEY, '{"schema":{},"fieldValues":{}}');

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.includes("/api/form-kits")) {
        return { ok: true, status: 200, json: async () => MANIFEST } as Response;
      }
      // Schema JSON fetch (resolveKitAssetUrl(form.schemaPath)).
      return { ok: true, status: 200, json: async () => MINIMAL_SCHEMA } as Response;
    }),
  );
  vi.stubGlobal("confirm", vi.fn(() => true));
  vi.stubGlobal("location", { ...window.location, reload: vi.fn() });
});

afterEach(() => {
  cleanup();
  clearClientLinkToken();
  sessionStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("SchemaFormDemo Start Fresh preserves the client-link token (bd ylokf)", () => {
  it("clicking Start Fresh clears form state but PRESERVES vff_client_link_token", async () => {
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe("a-real-client-link-token");

    render(<SchemaFormDemo />);

    const startFreshButton = await waitFor(
      () => screen.getByRole("button", { name: /start fresh/i }),
      { timeout: 3000 },
    );
    fireEvent.click(startFreshButton);

    expect(sessionStorage.getItem(TOKEN_KEY)).toBe("a-real-client-link-token");
    expect(sessionStorage.getItem(FORM_STATE_KEY)).toBeNull();
  });
});
