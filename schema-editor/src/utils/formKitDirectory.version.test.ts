/**
 * Tests for versionInfoFromSchema (bd polyglot-pdf-s4dp.2): the catalogue-card
 * version summary. A schema with a confident version shows it plainly; a
 * low-confidence or "unknown" version is flagged for the human to verify.
 */
import { describe, it, expect } from 'vitest';
import { versionInfoFromSchema } from './formKitDirectory';
import type { FormSchema } from '../types/schema';

function schemaWith(meta: Partial<FormSchema['form_metadata']>): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'X', form_number: 'X', version: 'unknown', language: 'en', total_widgets: 0, total_fields: 0, ...meta },
    parts: [],
    sections: [],
    fields: [],
  } as unknown as FormSchema;
}

describe('versionInfoFromSchema', () => {
  it('prefers edition_date and marks high confidence as not-low', () => {
    const v = versionInfoFromSchema(schemaWith({ edition_date: '01/20/25', version: '01/20/25', version_confidence: 0.9 }));
    expect(v.label).toBe('01/20/25');
    expect(v.lowConfidence).toBe(false);
  });

  it('falls back to version when there is no edition_date', () => {
    const v = versionInfoFromSchema(schemaWith({ version: 'December 2024', version_confidence: 0.9 }));
    expect(v.label).toBe('December 2024');
    expect(v.lowConfidence).toBe(false);
  });

  it('flags a low version_confidence as low (verify hint)', () => {
    const v = versionInfoFromSchema(schemaWith({ version: '2025', version_confidence: 0.4 }));
    expect(v.label).toBe('2025');
    expect(v.lowConfidence).toBe(true);
  });

  it('treats an "unknown" version as low confidence regardless of score', () => {
    const v = versionInfoFromSchema(schemaWith({ version: 'unknown', version_confidence: 0 }));
    expect(v.label).toBe('unknown');
    expect(v.lowConfidence).toBe(true);
  });

  it('defaults to "unknown" when no version metadata is present at all', () => {
    const v = versionInfoFromSchema({ source: 'pdf', form_metadata: {}, parts: [], sections: [], fields: [] } as unknown as FormSchema);
    expect(v.label).toBe('unknown');
    expect(v.lowConfidence).toBe(true);
  });
});
