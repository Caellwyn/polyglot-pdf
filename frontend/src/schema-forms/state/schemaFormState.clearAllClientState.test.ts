/**
 * SchemaFormStateManager.clearAllClientState() (bd polyglot-pdf-8v8i7).
 *
 * The single Clear-form path reused by all three automatic browser-PII
 * clearing triggers (form complete, idle timeout, logout): it must leave
 * sessionStorage holding none of `schema_form_state`, the onboarding
 * form/language keys (for a STAFF session), or `vff_client_link_token`.
 *
 * Order matters: `clearOnboardingState()` reads `hasClientLinkToken()` to
 * decide whether to keep the pinned form for an in-progress CLIENT session
 * (see onboardingStorage.ts), so the composed clear must call it BEFORE
 * clearing the link token -- clearing the token first would make every
 * session look like a staff session and wipe a client's form pin too.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { SchemaFormStateManager } from "./schemaFormState";
import { saveOnboardingState, ONBOARDING_FORM_KEY, ONBOARDING_LANGUAGE_KEY } from "../onboardingStorage";
import {
  setClientLinkToken,
  clearClientLinkToken,
  clearInMemoryOnly,
} from "../../shared/sessionCredential";

describe("SchemaFormStateManager.clearAllClientState (bd polyglot-pdf-8v8i7)", () => {
  let store: Record<string, string>;

  beforeEach(() => {
    store = {};
    global.sessionStorage = {
      getItem: vi.fn((key: string) => store[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key];
      }),
      clear: vi.fn(() => {
        store = {};
      }),
      length: 0,
      key: vi.fn(() => null),
    } as any;
  });

  afterEach(() => {
    clearInMemoryOnly();
    clearClientLinkToken();
  });

  it("clears schema_form_state, the onboarding keys, and the client-link token for a STAFF session", () => {
    store["schema_form_state"] = JSON.stringify({ fieldValues: { f1: { value: "x" } } });
    saveOnboardingState({ formId: "i-90", language: "English" });
    // No client-link token set: this is a staff session.

    SchemaFormStateManager.clearAllClientState();

    expect(store["schema_form_state"]).toBeUndefined();
    expect(store[ONBOARDING_FORM_KEY]).toBeUndefined();
    expect(store[ONBOARDING_LANGUAGE_KEY]).toBeUndefined();
    expect(store["vff_client_link_token"]).toBeUndefined();
  });

  it("clears schema_form_state and the client-link token, but KEEPS the pinned form, for a CLIENT-LINK session", () => {
    store["schema_form_state"] = JSON.stringify({ fieldValues: { f1: { value: "x" } } });
    saveOnboardingState({ formId: "i-90", language: "English" });
    setClientLinkToken("payload.signature");

    SchemaFormStateManager.clearAllClientState();

    expect(store["schema_form_state"]).toBeUndefined();
    // The form pin survives for a client session (onboardingStorage.ts's
    // documented behavior) -- only the language and the token are cleared.
    expect(store[ONBOARDING_FORM_KEY]).toBe("i-90");
    expect(store[ONBOARDING_LANGUAGE_KEY]).toBeUndefined();
    expect(store["vff_client_link_token"]).toBeUndefined();
  });

  it("is a no-op-safe call with nothing stored (no throw)", () => {
    expect(() => SchemaFormStateManager.clearAllClientState()).not.toThrow();
  });
});
