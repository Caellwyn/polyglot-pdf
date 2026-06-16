/**
 * Unit tests for the D3 catalogue review-progress metric (bd polyglot-pdf-vl3o).
 * The per-form metric reuses getCompletionStats (% of fields complete); the
 * aggregate summary counts complete / in-progress / awaiting-extraction kits.
 */
import { describe, it, expect } from 'vitest';
import { summarizeCatalogue, readKitProgress, type CatalogueEntry } from './formKitDirectory';
import type { FormField } from '../types/schema';

// A minimal CatalogueEntry; dirHandle is only touched when hasSchema is true and
// readKitProgress loads it, so the progress tests below supply a stub handle.
function entry(partial: Partial<CatalogueEntry> & { id: string }): CatalogueEntry {
  return {
    label: partial.id,
    status: 'unknown',
    hasSchema: true,
    hasPdf: true,
    schemaFile: 'schema.json',
    pdfFile: 'form.pdf',
    dirHandle: {} as CatalogueEntry['dirHandle'],
    ...partial,
  };
}

// A schema fixture whose fields are a mix of complete and incomplete. A field is
// "complete" per checkFieldComplete when it has id/type/pdf_field_name, a
// spoken_name, and non-placeholder help.instructions.
function completeField(id: string): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: id, read_only: false,
    required: false, spoken_name: id, help: { instructions: 'Fill this in.' },
  } as FormField;
}
function incompleteField(id: string): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: id, read_only: false,
    required: false, // no spoken_name, no help -> needsReview
  } as FormField;
}

// Stub a CatalogueEntry whose dirHandle serves a given schema JSON for the one
// schema file, mirroring the FsDirectoryHandle surface readKitProgress uses.
function entryServingSchema(id: string, schemaObj: unknown, hasSchema = true): CatalogueEntry {
  const json = JSON.stringify(schemaObj);
  const dirHandle = {
    getFileHandle: async (name: string) => {
      if (name !== 'schema.json') throw new DOMException('x', 'NotFoundError');
      return { getFile: async () => ({ text: async () => json } as unknown as File) };
    },
  } as unknown as CatalogueEntry['dirHandle'];
  return entry({ id, hasSchema, dirHandle });
}

describe('summarizeCatalogue', () => {
  it('counts complete / in-progress / awaiting-extraction', () => {
    const entries: CatalogueEntry[] = [
      entry({ id: 'a', status: 'complete', hasSchema: true }),
      entry({ id: 'b', status: 'draft', hasSchema: true }),
      entry({ id: 'c', status: 'unknown', hasSchema: true }),  // schema but not complete -> in progress
      entry({ id: 'd', status: 'draft', hasSchema: false }),   // no schema -> awaiting extraction
    ];
    expect(summarizeCatalogue(entries)).toEqual({
      total: 4, complete: 1, inProgress: 2, noSchema: 1,
    });
  });

  it('is all-zero-ish for an empty catalogue', () => {
    expect(summarizeCatalogue([])).toEqual({ total: 0, complete: 0, inProgress: 0, noSchema: 0 });
  });

  it('counts a complete-status kit as complete even if its schema is missing', () => {
    // The deploy gate reads metadata status; a kit marked complete must not show
    // as "awaiting extraction" just because its schema file is momentarily absent
    // (fresh-eyes finding).
    const entries: CatalogueEntry[] = [
      entry({ id: 'a', status: 'complete', hasSchema: false }),
    ];
    expect(summarizeCatalogue(entries)).toEqual({
      total: 1, complete: 1, inProgress: 0, noSchema: 0,
    });
  });
});

describe('readKitProgress', () => {
  it('computes review percent from field completion (2 of 4 complete -> 50%)', async () => {
    const schema = {
      source: 'pdf', form_metadata: { form_number: 'T-1' }, parts: [], sections: [],
      fields: [
        completeField('f1'), completeField('f2'),
        incompleteField('f3'), incompleteField('f4'),
      ],
    };
    const prog = await readKitProgress(entryServingSchema('k', schema));
    expect(prog.reviewPercent).toBe(50);
    expect(prog.completeFields).toBe(2);
    expect(prog.totalFields).toBe(4);
  });

  it('returns null percent for a kit with no schema', async () => {
    const prog = await readKitProgress(entry({ id: 'k', hasSchema: false }));
    expect(prog.reviewPercent).toBeNull();
    expect(prog.totalFields).toBe(0);
  });

  it('returns null percent when the schema cannot be parsed', async () => {
    const dirHandle = {
      getFileHandle: async () => ({
        getFile: async () => ({ text: async () => 'not json{' } as unknown as File),
      }),
    } as unknown as CatalogueEntry['dirHandle'];
    const prog = await readKitProgress(entry({ id: 'k', hasSchema: true, dirHandle }));
    expect(prog.reviewPercent).toBeNull();
  });

  it('returns null percent (does not throw) for a structurally malformed schema', async () => {
    // Valid JSON but no `fields` array -> getCompletionStats would throw. Must be
    // swallowed so it cannot reject the catalogue-wide Promise.all (fresh-eyes
    // finding: a single bad schema would otherwise wipe every progress bar).
    const prog = await readKitProgress(entryServingSchema('k', { form_metadata: {} }));
    expect(prog.reviewPercent).toBeNull();
  });

  it('reports 0% (not null) for a valid schema with zero fields', async () => {
    // An extracted-but-empty schema is distinct from a pre-extraction kit: it has
    // a measurable (0%) progress, so the bar renders rather than being hidden.
    const prog = await readKitProgress(
      entryServingSchema('k', { form_metadata: { form_number: 'T' }, sections: [], fields: [] }),
    );
    expect(prog.reviewPercent).toBe(0);
    expect(prog.totalFields).toBe(0);
  });
});
