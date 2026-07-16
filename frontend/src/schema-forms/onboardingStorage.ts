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
  sessionStorage.removeItem(ONBOARDING_FORM_KEY);
  sessionStorage.removeItem(ONBOARDING_LANGUAGE_KEY);
}
