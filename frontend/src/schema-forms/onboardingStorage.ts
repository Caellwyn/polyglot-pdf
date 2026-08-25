/**
 * Onboarding storage - the app-start form + language selection.
 *
 * These sessionStorage keys record the user's app-start choices (which form,
 * which spoken language). While they are present, SchemaFormDemo skips the
 * language-choice modal on load and restores the saved selection. Clearing them
 * forces the language-choice modal to show again on the next load -- this is how
 * "clear form" resets all the way back to language choice to start a new client.
 *
 * The keys and the clear helper live here (not inside SchemaFormDemo) so the
 * voice overlays' clear-form buttons can force the same full reset without
 * re-declaring the key strings.
 */

// Session storage keys for onboarding state.
import { hasClientLinkToken } from "../shared/sessionCredential";

export const ONBOARDING_FORM_KEY = "vff_selected_form_id";
export const ONBOARDING_LANGUAGE_KEY = "vff_selected_language";

export interface OnboardingState {
  formId: string | null;
  language: string | null;
}

export function loadOnboardingState(): OnboardingState {
  if (typeof window === "undefined") {
    return { formId: null, language: null };
  }
  return {
    formId: sessionStorage.getItem(ONBOARDING_FORM_KEY),
    language: sessionStorage.getItem(ONBOARDING_LANGUAGE_KEY),
  };
}

export function saveOnboardingState(state: Partial<OnboardingState>) {
  if (typeof window === "undefined") return;

  if (state.formId !== undefined) {
    if (state.formId) {
      sessionStorage.setItem(ONBOARDING_FORM_KEY, state.formId);
    } else {
      sessionStorage.removeItem(ONBOARDING_FORM_KEY);
    }
  }
  if (state.language !== undefined) {
    if (state.language) {
      sessionStorage.setItem(ONBOARDING_LANGUAGE_KEY, state.language);
    } else {
      sessionStorage.removeItem(ONBOARDING_LANGUAGE_KEY);
    }
  }
}

export function clearOnboardingState() {
  if (typeof window === "undefined") return;

  // A CLIENT-LINK SESSION KEEPS ITS FORM (bd polyglot-pdf-ugm6, Opus
  // cross-surface r10). "Clear form" exists so STAFF can start a new client
  // from scratch -- choosing a different form is the point. A client has no
  // such choice: their link names ONE form, and clearing the pin hands them
  // the firm's whole catalogue on the next render.
  //
  // That is not theoretical. The clear-form buttons reload the page, and
  // ClientLinkEntry's reload recovery deliberately does NOT re-POST /open
  // because "the form id is already pinned from the first open" -- so with
  // the pin gone it renders the picker, the client picks something else, and
  // the socket refuses them 1008 with no explanation. The r1 fix closed the
  // initial-load door; this was the mid-session one.
  //
  // The language IS cleared either way: re-choosing a language is a
  // legitimate thing for a client to want.
  const keepPinnedForm = hasClientLinkToken();
  if (!keepPinnedForm) {
    sessionStorage.removeItem(ONBOARDING_FORM_KEY);
  }
  sessionStorage.removeItem(ONBOARDING_LANGUAGE_KEY);
}
