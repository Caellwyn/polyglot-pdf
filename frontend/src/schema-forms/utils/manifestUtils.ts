/**
 * Manifest Generation Utilities - Phase 3.2: Token Reduction
 *
 * Generates lightweight field manifests for JIT (Just-In-Time) schema loading.
 * Manifests contain only field_id and spoken_name pairs, dramatically reducing
 * token count in initial Gemini handshake.
 *
 * @version 1.0.0
 * @date 2025-11-10
 */

import type { FormSchema, FormPart, FormSection, FormField } from '../types/schema';
import type { SchemaFormState } from '../state/schemaFormState';

/**
 * Manifest entry for a single field (minimal representation)
 */
export interface FieldManifestEntry {
  field_id: string;
  spoken_name: string;
}

/**
 * Section manifest structure
 */
export interface SectionManifest {
  section_id: string;
  section_label: string;
  fields: FieldManifestEntry[];
}

/**
 * Complete handshake manifest
 */
export interface HandshakeManifest {
  current_section: SectionManifest;
  previous_sections: SectionManifest[];
  // Section navigation list consumed by the backend (websocket_routes.py reads
  // manifest.parts). The `parts` key is the backend wire-format contract; its
  // values are section data (bd polyglot-pdf-zun).
  parts: Array<{ id: string; order: number; label: string }>;
}

/**
 * Generate manifest for a single section
 *
 * Extracts all fields from a section and creates
 * a lightweight manifest with only field_id and spoken_name.
 *
 * @param section - The section to generate manifest for
 * @param schema - Full form schema
 * @returns Section manifest with minimal field info
 */
export function generateSectionManifest(
  section: FormSection,
  schema: FormSchema
): SectionManifest {
  const fields: FieldManifestEntry[] = [];

  // Extract fields from the section
  for (const fieldId of section.fields) {
    // Find the field definition in schema
    const field = schema.fields.find(f => f.id === fieldId);

    if (field) {
      fields.push({
        field_id: field.id,
        spoken_name: field.spoken_name || field.name || field.id
      });
    }
  }

  return {
    section_id: section.id,
    section_label: section.label,
    fields
  };
}

/**
 * Check if field schema should be included in response
 *
 * Returns true if Gemini hasn't received this field's schema yet.
 * Used by tools to decide whether to include schema in response.
 *
 * @param fieldId - Field ID to check
 * @param state - Current form state
 * @returns True if schema should be included, false if already sent
 */
export function shouldIncludeSchema(
  fieldId: string,
  state: SchemaFormState
): boolean {
  return !state.loadedFieldIds.has(fieldId);
}

/**
 * Build complete manifest for handshake
 *
 * Creates a manifest for the current section plus manifests for all
 * previously completed sections (for cross-section field lookups).
 *
 * @param currentSectionId - ID of the current section
 * @param schema - Full form schema
 * @param state - Current form state
 * @returns Complete handshake manifest
 */
export function buildHandshakeManifest(
  currentSectionId: string,
  schema: FormSchema,
  state: SchemaFormState
): HandshakeManifest {
  // Find current section
  const currentSection = schema.sections.find(s => s.id === currentSectionId);
  if (!currentSection) {
    throw new Error(`Section ${currentSectionId} not found in schema`);
  }

  // Generate manifest for current section
  const current_section = generateSectionManifest(currentSection, schema);

  // Generate manifests for all completed sections (for cross-section queries)
  const previous_sections: SectionManifest[] = [];

  for (const sectionId of state.completedSections) {
    const section = schema.sections.find(s => s.id === sectionId);
    if (section) {
      previous_sections.push(generateSectionManifest(section, schema));
    }
  }

  return {
    current_section,
    previous_sections,
    // Section navigation list. NOTE: the `parts` key name is the backend
    // wire-format contract (websocket_routes.py reads manifest.parts); the
    // VALUES are section data. Renaming this key requires a coordinated
    // backend change -- out of scope for the frontend-internal rename (bd
    // polyglot-pdf-zun).
    parts: schema.sections.map(s => ({
      id: s.id,
      order: s.order,
      label: s.label
    }))
  };
}

/**
 * Format manifest as pipe-separated text for Gemini context
 *
 * Converts manifest to lightweight text format:
 * "CURRENT SECTION: Section 1
 *  Fields: firstName|first name | lastName|last name | ..."
 *
 * @param manifest - Handshake manifest
 * @returns Formatted text representation
 */
export function formatManifestForContext(manifest: HandshakeManifest): string {
  const lines: string[] = [];

  // Current section header
  lines.push(`CURRENT SECTION: ${manifest.current_section.section_label}`);

  // Current section fields (pipe-separated)
  const currentFields = manifest.current_section.fields
    .map(f => `${f.field_id}|${f.spoken_name}`)
    .join(' | ');

  lines.push(`Fields: ${currentFields}`);

  // Previous sections (if any)
  if (manifest.previous_sections.length > 0) {
    lines.push('');
    lines.push('PREVIOUS SECTIONS (lookup only):');

    for (const section of manifest.previous_sections) {
      const sectionFields = section.fields
        .map(f => `${f.field_id}|${f.spoken_name}`)
        .join(' | ');

      lines.push(`${section.section_label}: ${sectionFields}`);
    }
  }

  return lines.join('\n');
}

/**
 * Estimate token count for manifest
 *
 * Rough estimation: ~1.3 tokens per word, 1 word per field entry.
 * Used for monitoring token reduction effectiveness.
 *
 * @param manifest - Handshake manifest
 * @returns Estimated token count
 */
export function estimateManifestTokens(manifest: HandshakeManifest): number {
  const text = formatManifestForContext(manifest);
  const words = text.split(/\s+/).length;
  return Math.ceil(words * 1.3); // Rough token estimate
}

/**
 * Get field schema by ID from full schema
 *
 * Helper function to extract a single field's complete schema.
 * Used when sending field schema in tool responses.
 *
 * @param fieldId - Field ID to look up
 * @param schema - Full form schema
 * @returns Field object or undefined if not found
 */
export function getFieldSchema(
  fieldId: string,
  schema: FormSchema
): FormField | undefined {
  return schema.fields.find(f => f.id === fieldId);
}
