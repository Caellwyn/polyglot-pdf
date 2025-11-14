/**
 * SchemaFormDemo - Demo page for testing schema-driven form rendering
 *
 * Loads I-90 schema and renders it using SchemaForm component
 */

import { useState, useEffect, type ChangeEvent } from "react";
import { SchemaForm } from "./components/SchemaForm";
import type { FormSchema } from "./types/schema";
import type { FormKitDescriptor, FormKitManifest } from "./types/formKit";

const SELECTED_FORM_STORAGE_KEY = "schema_form_selected_form_id";

function persistSelectedForm(formId: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (formId) {
    window.localStorage.setItem(SELECTED_FORM_STORAGE_KEY, formId);
  } else {
    window.localStorage.removeItem(SELECTED_FORM_STORAGE_KEY);
  }
}

export function SchemaFormDemo() {
  const [forms, setForms] = useState<FormKitDescriptor[]>([]);
  const [selectedFormId, setSelectedFormId] = useState<string | null>(null);
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [manifestLoading, setManifestLoading] = useState(true);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const selectedForm = forms.find((form) => form.id === selectedFormId) ?? null;

  useEffect(() => {
    async function loadManifest() {
      try {
        setManifestLoading(true);
        setManifestError(null);
        const response = await fetch("/form-kits/index.json");

        if (!response.ok) {
          throw new Error(`Failed to load manifest: ${response.statusText}`);
        }

        const manifest = (await response.json()) as FormKitManifest;
        setForms(manifest.forms);

        if (manifest.forms.length > 0) {
          const storedSelection =
            typeof window !== "undefined"
              ? window.localStorage.getItem(SELECTED_FORM_STORAGE_KEY)
              : null;

          const defaultSelection = storedSelection && manifest.forms.some((form) => form.id === storedSelection)
            ? storedSelection
            : manifest.forms[0].id;

          setSelectedFormId(defaultSelection);
          persistSelectedForm(defaultSelection);
        } else {
          setSelectedFormId(null);
          persistSelectedForm(null);
        }
      } catch (err) {
        console.error("[SchemaFormDemo] Failed to load form manifest:", err);
        setForms([]);
        setSelectedFormId(null);
        persistSelectedForm(null);
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

    let cancelled = false;

    async function loadSchema() {
      try {
        setSchemaLoading(true);
        setSchemaError(null);
        const response = await fetch(selectedForm.schemaPath);

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
            `[SchemaFormDemo] Failed to load schema for ${selectedForm.id}:`,
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
      sessionStorage.removeItem("schema_form_state");
      window.location.reload();
    }
  };

  if (manifestLoading) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__loading">
          <p>Loading available forms...</p>
        </div>
      </div>
    );
  }

  if (manifestError) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__error">
          <h2>Unable to load form list</h2>
          <p>{manifestError}</p>
          <p>
            Ensure <code>public/form-kits/index.json</code> exists. Run <code>npm run form-kits:prepare</code>
            from the frontend folder to regenerate it.
          </p>
        </div>
      </div>
    );
  }

  if (!forms.length) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__error">
          <h2>No forms available</h2>
          <p>Add a folder under <code>public/form-kits</code> with schema and PDF assets.</p>
        </div>
      </div>
    );
  }

  const handleFormChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const nextId = event.target.value || null;
    setSelectedFormId(nextId);
    persistSelectedForm(nextId);
  };

  return (
    <div className="schema-form-demo">
      <div
        style={{
          padding: "10px",
          background: "#f0f0f0",
          marginBottom: "20px",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        <label style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontWeight: 600 }}>Select a form kit</span>
          <select
            value={selectedFormId ?? ""}
            onChange={handleFormChange}
            style={{ padding: "8px", fontSize: "1rem" }}
          >
            {forms.map((form) => (
              <option key={form.id} value={form.id}>
                {form.label}
              </option>
            ))}
          </select>
        </label>
        {selectedForm?.description ? (
          <p style={{ margin: 0 }}>{selectedForm.description}</p>
        ) : null}
        <button onClick={handleClearSession} style={{ padding: "8px 16px", cursor: "pointer", alignSelf: "flex-start" }}>
          🗑️ Clear Form & Start Fresh
        </button>
      </div>

      {schemaLoading && (
        <div className="schema-form-demo__loading">
          <p>
            Loading schema for <strong>{selectedForm?.label ?? "form"}</strong>...
          </p>
        </div>
      )}

      {schemaError && !schemaLoading && (
        <div className="schema-form-demo__error">
          <h2>Error loading schema</h2>
          <p>{schemaError}</p>
          {selectedForm ? (
            <p>
              Verify schema + PDF exists in <code>public/form-kits/{selectedForm.id}</code>.
            </p>
          ) : null}
        </div>
      )}

      {schema && selectedForm && !schemaLoading ? (
        <SchemaForm
          schema={schema}
          kitId={selectedForm.id}
          pdfUrl={selectedForm.pdfPath}
          onSubmit={handleSubmit}
          onSectionChange={handleSectionChange}
        />
      ) : null}
    </div>
  );
}
