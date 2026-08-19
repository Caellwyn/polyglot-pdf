/**
 * SchemaFormDemo - Production form filling page
 *
 * Onboarding flow:
 * 1. User selects form + language in initial modal (shown at this level)
 * 2. Schema loads for selected form
 * 3. Disclaimer modal appears (handled by VoiceOverlay, read in selected language)
 * 4. Form filling begins
 *
 * Form selection is locked after onboarding to prevent mid-session switches.
 */

import { useState, useEffect } from "react";
import { SchemaForm } from "./components/SchemaForm";
import type { FormSchema } from "./types/schema";
import type { FormKitDescriptor, FormKitManifest } from "./types/formKit";
import { getBackendHttpUrl, resolveKitAssetUrl } from "./utils/pdfFiller";
import { LanguageSelectionModal } from "./components/LanguageSelectionModal";
import { useAuth } from "../contexts/AuthContext";
import {
  loadOnboardingState,
  saveOnboardingState,
  clearOnboardingState,
} from "./onboardingStorage";

export function SchemaFormDemo() {
  // Rendered inside ProtectedRoute, so `user` is present (real or the local
  // test-harness mock). Its ID token rides Authorization headers to the
  // auth-gated /api/form-kits* routes (bd polyglot-pdf-z2is).
  const { user } = useAuth();

  // Onboarding state - form + language must be selected before proceeding
  const [selectedFormId, setSelectedFormId] = useState<string | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState<string | null>(null);
  const [showOnboardingModal, setShowOnboardingModal] = useState(true);

  // Form manifest & schema
  const [forms, setForms] = useState<FormKitDescriptor[]>([]);
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [manifestLoading, setManifestLoading] = useState(true);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const selectedForm = forms.find((form) => form.id === selectedFormId) ?? null;

  // Load onboarding state from session on mount
  useEffect(() => {
    const saved = loadOnboardingState();
    if (saved.formId && saved.language) {
      // Returning user - restore selections and skip modal
      setSelectedFormId(saved.formId);
      setSelectedLanguage(saved.language);
      setShowOnboardingModal(false);
    }
  }, []);

  // Load manifest from backend (for schema paths)
  useEffect(() => {
    async function loadManifest() {
      try {
        setManifestLoading(true);
        setManifestError(null);

        // Try backend API first, fall back to static file for local dev
        let manifest: FormKitManifest;
        let authRejected = false;
        try {
          const backendUrl = getBackendHttpUrl();
          let token: string | undefined;
          try {
            token = user ? await user.getIdToken() : undefined;
          } catch {
            // A failed token REFRESH (revoked session, clock skew) is an auth
            // failure, not "backend unavailable" -- surface it like a 401
            // instead of masking it behind the stale static bundle
            // (round-3 fresh-eyes on bd z2is).
            authRejected = true;
            throw new Error(
              "Could not refresh your sign-in (please sign in again)"
            );
          }
          const response = await fetch(`${backendUrl}/api/form-kits`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          });
          if (response.status === 401 || response.status === 403) {
            // An auth rejection must SURFACE, never silently degrade to the
            // static bundle -- that would mask a broken token path in prod
            // behind stale bundled kits (bd polyglot-pdf-z2is).
            authRejected = true;
            throw new Error("Not authorized to load form kits (sign in again?)");
          }
          if (response.ok) {
            const data = await response.json();
            // Backend returns { forms: [...] }, convert to manifest format.
            // Use the backend's schema_path/pdf_path when present (they carry the
            // kit's REAL filenames -- a kit may declare a custom schema filename,
            // bd polyglot-pdf-snpi); only fall back to the conventional
            // `/<id>/schema.json` when an older backend omits them.
            manifest = {
              generatedAt: new Date().toISOString(),
              forms: data.forms.map((f: any) => {
                const schemaPath: string = f.schema_path || `/form-kits/${f.id}/schema.json`;
                const pdfPath: string = f.pdf_path || `/form-kits/${f.id}/form.pdf`;
                // Prefer the backend's EXPLICIT filenames (bd polyglot-pdf-vccy):
                // a PRIVATE kit's paths are the backend routes .../schema and
                // .../pdf, so URL-splitting would yield the literal route word
                // and 404 the fill. The split remains only as the fallback for
                // an older backend that omits the fields.
                return {
                  id: f.id,
                  label: f.label,
                  description: f.description,
                  schemaFile: f.schema_file || schemaPath.split("/").pop() || "schema.json",
                  schemaPath,
                  pdfFile: f.pdf_file || pdfPath.split("/").pop() || "form.pdf",
                  pdfPath,
                };
              }),
            };
          } else {
            throw new Error("Backend unavailable");
          }
        } catch (err) {
          if (authRejected) {
            throw err; // bubble to the outer catch -> manifestError state
          }
          // Fall back to static manifest for local development
          console.log("[SchemaFormDemo] Backend unavailable, using static manifest");
          const response = await fetch("/form-kits/index.json");
          if (!response.ok) {
            throw new Error(`Failed to load manifest: ${response.statusText}`);
          }
          manifest = await response.json();
        }

        setForms(manifest.forms);
      } catch (err) {
        console.error("[SchemaFormDemo] Failed to load form manifest:", err);
        setForms([]);
        setManifestError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setManifestLoading(false);
      }
    }

    loadManifest();
  }, []);

  useEffect(() => {
    if (!selectedForm) {
      setSchema(null);
      return;
    }

    // Capture the narrowed (non-null) form so the async closure below keeps the
    // narrowing -- TS does not carry the `if (!selectedForm) return` guard across
    // the function boundary into loadSchema().
    const form = selectedForm;
    let cancelled = false;

    async function loadSchema() {
      try {
        setSchemaLoading(true);
        setSchemaError(null);
        // schemaPath is usually a static Hosting path (header ignored), but a
        // PRIVATE kit's manifest carries the auth-gated backend route
        // /api/form-kits/{id}/schema (bd polyglot-pdf-vccy) -- attach the
        // token either way, and resolve /api/ paths against the backend base
        // (a relative /api/ fetch works on Hosting via the rewrite but not
        // against the Vite dev server).
        const token = user ? await user.getIdToken() : undefined;
        const response = await fetch(resolveKitAssetUrl(form.schemaPath), {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });

        if (!response.ok) {
          throw new Error(`Failed to load schema: ${response.statusText}`);
        }

        const schemaData = (await response.json()) as FormSchema;
        if (!cancelled) {
          setSchema(schemaData);
        }
      } catch (err) {
        if (!cancelled) {
          console.error(
            `[SchemaFormDemo] Failed to load schema for ${form.id}:`,
            err
          );
          setSchema(null);
          setSchemaError(err instanceof Error ? err.message : "Unknown error");
        }
      } finally {
        if (!cancelled) {
          setSchemaLoading(false);
        }
      }
    }

    loadSchema();

    return () => {
      cancelled = true;
    };
  }, [selectedForm]);

  const handleSubmit = (fieldValues: Record<string, any>) => {
    console.log("[SchemaFormDemo] Form submitted with values:", fieldValues);
    alert("Form submitted! Check console for field values.");
  };

  const handleSectionChange = (sectionId: string) => {
    // Section change handler (currently unused)
  };

  const handleClearSession = () => {
    if (confirm("Clear all form data and start fresh?")) {
      // Clear form data
      sessionStorage.removeItem("schema_form_state");
      // Clear onboarding state (forces form/language re-selection)
      clearOnboardingState();
      window.location.reload();
    }
  };

  // Handler for form+language selection from modal
  const handleOnboardingSelection = (formId: string, language: string) => {
    console.log("[SchemaFormDemo] Onboarding selection:", formId, language);
    saveOnboardingState({ formId, language });
    setSelectedFormId(formId);
    setSelectedLanguage(language);
    setShowOnboardingModal(false);
  };

  // Show loading while manifest loads
  if (manifestLoading) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__loading">
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  // Show error if manifest failed
  if (manifestError) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__error">
          <h2>Unable to load forms</h2>
          <p>{manifestError}</p>
        </div>
      </div>
    );
  }

  // Show error if no forms available
  if (!forms.length) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__error">
          <h2>No forms available</h2>
          <p>Please contact support.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="schema-form-demo">
      {/* Onboarding modal - form + language selection */}
      {showOnboardingModal && (
        <LanguageSelectionModal
          forms={forms}
          onSelection={handleOnboardingSelection}
        />
      )}

      {/* Minimal header - only shows clear button, no form selector (form is locked after onboarding) */}
      {!showOnboardingModal && schema && (
        <div
          style={{
            padding: "10px",
            background: "#f0f0f0",
            marginBottom: "20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ fontWeight: 600 }}>
            {selectedForm?.label ?? "Form"}
          </span>
          <button
            onClick={handleClearSession}
            style={{ padding: "8px 16px", cursor: "pointer" }}
          >
            🗑️ Start Fresh
          </button>
        </div>
      )}

      {schemaLoading && !showOnboardingModal && (
        <div className="schema-form-demo__loading">
          <p>
            Loading <strong>{selectedForm?.label ?? "form"}</strong>...
          </p>
        </div>
      )}

      {schemaError && !schemaLoading && !showOnboardingModal && (
        <div className="schema-form-demo__error">
          <h2>Error loading form</h2>
          <p>{schemaError}</p>
        </div>
      )}

      {schema && selectedForm && !schemaLoading && !showOnboardingModal ? (
        <SchemaForm
          schema={schema}
          kitId={selectedForm.id}
          pdfUrl={selectedForm.pdfPath}
          pdfFile={selectedForm.pdfFile}
          onSubmit={handleSubmit}
          onSectionChange={handleSectionChange}
          initialLanguage={selectedLanguage ?? undefined}
        />
      ) : null}
    </div>
  );
}
