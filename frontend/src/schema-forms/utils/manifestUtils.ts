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
 * Part manifest structure
 */
export interface PartManifest {
  part_id: string;
  part_label: string;
  fields: FieldManifestEntry[];
}

/**
 * Complete handshake manifest
 */
export interface HandshakeManifest {
  current_part: PartManifest;
  previous_parts: PartManifest[];
}

/**
 * Generate manifest for a single section
 *
 * Extracts all fields from a section and creates
 * a lightweight manifest with only field_id and spoken_name.
 *
 * @param section - The section to generate manifest for
 * @param schema - Full form schema
 * @returns Part manifest with minimal field info
 */
export function generatePartManifest(
  section: FormSection,
  schema: FormSchema
): PartManifest {
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
    part_id: section.id,
    part_label: section.label,
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
    throw new Error(`Part ${currentSectionId} not found in schema`);
  }

  // Generate manifest for current section
  const current_part = generatePartManifest(currentSection, schema);

  // Generate manifests for all completed sections (for cross-section queries)
  const previous_parts: PartManifest[] = [];

  for (const sectionId of state.completedSections) {
    const section = schema.sections.find(s => s.id === sectionId);
    if (section) {
      previous_parts.push(generatePartManifest(section, schema));
    }
  }

  return {
    current_part,
    previous_parts,
    // Include sections metadata for section navigation
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
 * "CURRENT PART: Part 1
 *  Fields: firstName|first name | lastName|last name | ..."
 *
 * @param manifest - Handshake manifest
 * @returns Formatted text representation
 */
export function formatManifestForContext(manifest: HandshakeManifest): string {
  const lines: string[] = [];

  // Current part header
  lines.push(`CURRENT PART: ${manifest.current_part.part_label}`);

  // Current part fields (pipe-separated)
  const currentFields = manifest.current_part.fields
    .map(f => `${f.field_id}|${f.spoken_name}`)
    .join(' | ');

  lines.push(`Fields: ${currentFields}`);

  // Previous parts (if any)
  if (manifest.previous_parts.length > 0) {
    lines.push('');
    lines.push('PREVIOUS PARTS (lookup only):');

    for (const part of manifest.previous_parts) {
      const partFields = part.fields
        .map(f => `${f.field_id}|${f.spoken_name}`)
        .join(' | ');

      lines.push(`${part.part_label}: ${partFields}`);
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
