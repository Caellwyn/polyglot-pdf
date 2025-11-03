/**
 * SchemaFormDemo - Demo page for testing schema-driven form rendering
 *
 * Loads I-90 schema and renders it using SchemaForm component
 */

import { useState, useEffect } from "react";
import { SchemaForm } from "./components/SchemaForm";
import type { FormSchema } from "./types/schema";

export function SchemaFormDemo() {
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load I-90 schema from JSON file
  useEffect(() => {
    async function loadSchema() {
      try {
        setLoading(true);
        const response = await fetch(
          "/pdf_schema_extractor/test_schemas/test_pdfs/i-90/i-90_schema.json"
        );

        if (!response.ok) {
          throw new Error(`Failed to load schema: ${response.statusText}`);
        }

        const schemaData = await response.json();
        setSchema(schemaData);
        setError(null);
      } catch (err) {
        console.error("[SchemaFormDemo] Failed to load schema:", err);
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    }

    loadSchema();
  }, []);

  const handleSubmit = (fieldValues: Record<string, any>) => {
    console.log("[SchemaFormDemo] Form submitted with values:", fieldValues);
    alert("Form submitted! Check console for field values.");
  };

  const handleSectionChange = (sectionId: string) => {
    console.log("[SchemaFormDemo] Section changed to:", sectionId);
  };

  if (loading) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__loading">
          <p>Loading I-90 schema...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__error">
          <h2>Error Loading Schema</h2>
          <p>{error}</p>
          <p>
            Make sure the I-90 schema file exists at:
            <br />
            <code>/pdf_schema_extractor/test_schemas/test_pdfs/i-90/i-90_schema.json</code>
          </p>
        </div>
      </div>
    );
  }

  if (!schema) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__error">
          <h2>No Schema Loaded</h2>
          <p>Schema data is empty or invalid.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="schema-form-demo">
      <SchemaForm schema={schema} onSubmit={handleSubmit} onSectionChange={handleSectionChange} />
    </div>
  );
}
