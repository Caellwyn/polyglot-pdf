import type { FormSchema, FormConfig } from '../types/schema';
import { stripEditorState } from './fieldGrouping';
import { migrateLegacyRequired } from './schemaMigrate';

// Re-export so consumers (e.g. FormSelector) can import FormConfig from here.
export type { FormConfig };

/**
 * Available forms for editing
 */
export const AVAILABLE_FORMS: FormConfig[] = [
  {
    name: 'I-90 (Green Card Replacement) - Draft',
    pdfPath: '/schemas/i-90/i-90.pdf',
    schemaPath: '/schemas/i-90/i-90_draft_schema.json',
  },
  {
    name: 'I-90 (Green Card Replacement) - Gold Standard',
    pdfPath: '/schemas/i-90/i-90.pdf',
    schemaPath: '/schemas/i-90/i-90_schema.json',
  },
  {
    name: 'I-589 (Asylum Application)',
    pdfPath: '/schemas/i-589/i-589.pdf',
    schemaPath: '/schemas/i-589/final_schema_minimal.json',
  },
];

/**
 * Load schema from file path
 */
export async function loadSchema(schemaPath: string): Promise<FormSchema> {
  const response = await fetch(schemaPath);
  if (!response.ok) {
    throw new Error(`Failed to load schema: ${response.statusText}`);
  }
  // Self-heal legacy shapes on the way in (bd 0x10.4) so a stale kit does
  // not re-save its dead top-level `required` keys forever.
  return migrateLegacyRequired(await response.json());
}

/**
 * Save schema to file (downloads as JSON)
 */
export function saveSchema(schema: FormSchema, filename: string): void {
  const json = JSON.stringify(stripEditorState(schema), null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Load PDF document
 */
export async function loadPDF(pdfPath: string): Promise<string> {
  // For now, just return the path - PDF.js will handle loading
  return pdfPath;
}
