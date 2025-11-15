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
 * Generate manifest for a single part
 *
 * Extracts all fields from sections within the part and creates
 * a lightweight manifest with only field_id and spoken_name.
 *
 * @param part - The part to generate manifest for
 * @param schema - Full form schema
 * @returns Part manifest with minimal field info
 */
export function generatePartManifest(
  part: FormPart,
  schema: FormSchema
): PartManifest {
  const fields: FieldManifestEntry[] = [];

  // Get all sections for this part
  const partSections = schema.sections.filter(section =>
    part.section_ids.includes(section.id)
  );

  // Sort sections by order to maintain field sequence
  const sortedSections = [...partSections].sort((a, b) => a.order - b.order);

  // Extract fields from each section in order
  for (const section of sortedSections) {
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
  }

  return {
    part_id: part.id,
    part_label: part.label,
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
 * Creates a manifest for the current part plus manifests for all
 * previously completed parts (for cross-part field lookups).
 *
 * @param currentPartId - ID of the current part
 * @param schema - Full form schema
 * @param state - Current form state
 * @returns Complete handshake manifest
 */
export function buildHandshakeManifest(
  currentPartId: string,
  schema: FormSchema,
  state: SchemaFormState
): HandshakeManifest {
  // Find current part
  const currentPart = schema.parts.find(p => p.id === currentPartId);
  if (!currentPart) {
    throw new Error(`Part ${currentPartId} not found in schema`);
  }

  // Generate manifest for current part
  const current_part = generatePartManifest(currentPart, schema);

  // Generate manifests for all completed parts (for cross-part queries)
  const previous_parts: PartManifest[] = [];

  for (const partId of state.completedParts) {
    const part = schema.parts.find(p => p.id === partId);
    if (part) {
      previous_parts.push(generatePartManifest(part, schema));
    }
  }

  return {
    current_part,
    previous_parts,
    // Include parts metadata for section navigation
    parts: schema.parts.map(p => ({
      id: p.id,
      order: p.order,
      label: p.label
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
