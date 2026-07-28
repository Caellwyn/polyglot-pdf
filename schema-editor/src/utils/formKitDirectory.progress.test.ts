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
// A field counted as COMPLETE by getCompletionStats. Since bd g63j that means
// human sign-off (_review.reviewed_correct) -- the progress figure reports how
// much a person has reviewed, not how much the machine failed to fault.
function completeField(id: string): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: id, read_only: false,
    spoken_name: id, help: { instructions: 'Fill this in.' },
    _review: { status: 'reviewed_correct' },
  } as FormField;
}
function incompleteField(id: string): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: id, read_only: false,
    // no spoken_name, no help -> needsReview
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

  it('counts a complete-status kit WITHOUT a schema as awaiting extraction', () => {
    // deploy-all.sh skips a kit with no resolved schema BEFORE the complete check,
    // so a complete-marked, schema-less kit is not actually deployable -- it must
    // count as awaiting extraction, not complete (Codex finding, deploy-flow
    // evidence overrides the earlier metadata-only reasoning).
    const entries: CatalogueEntry[] = [
      entry({ id: 'a', status: 'complete', hasSchema: false }),
    ];
    expect(summarizeCatalogue(entries)).toEqual({
      total: 1, complete: 0, inProgress: 0, noSchema: 1,
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

  it('returns null percent (no schemaError) for a kit with no schema', async () => {
    const prog = await readKitProgress(entry({ id: 'k', hasSchema: false }));
    expect(prog.reviewPercent).toBeNull();
    expect(prog.totalFields).toBe(0);
    expect(prog.schemaError).toBe(false); // pre-extraction, not broken
  });

  it('returns null percent when the schema cannot be parsed', async () => {
    const dirHandle = {
      getFileHandle: async () => ({
        getFile: async () => ({ text: async () => 'not json{' } as unknown as File),
      }),
    } as unknown as CatalogueEntry['dirHandle'];
    const prog = await readKitProgress(entry({ id: 'k', hasSchema: true, dirHandle }));
    expect(prog.reviewPercent).toBeNull();
    expect(prog.schemaError).toBe(true); // present but unparseable
  });

  it('flags schemaError (does not throw) for a structurally malformed schema', async () => {
    // Valid JSON but no `fields` array -> getCompletionStats would throw. Must be
    // swallowed so it cannot reject the catalogue-wide Promise.all (fresh-eyes
    // finding: a single bad schema would otherwise wipe every progress bar), and
    // flagged schemaError so the UI distinguishes it from a pre-extraction kit
    // (Codex finding).
    const prog = await readKitProgress(entryServingSchema('k', { form_metadata: {} }));
    expect(prog.reviewPercent).toBeNull();
    expect(prog.schemaError).toBe(true);
  });

  it('flags schemaError for a non-array fields value (iterable but invalid)', async () => {
    // Codex finding: `fields: "abc"` is iterable, so getCompletionStats would NOT
    // throw -- it would report a bogus % with schemaError=false. The Array.isArray
    // guard must catch this and surface it as a broken schema.
    const prog = await readKitProgress(
      entryServingSchema('k', { form_metadata: { form_number: 'T' }, fields: 'abc' }),
    );
    expect(prog.reviewPercent).toBeNull();
    expect(prog.schemaError).toBe(true);
  });

  it('flags schemaError for a fields array of non-objects', async () => {
    // Codex round 3: `fields: ["abc"]` is an array, so Array.isArray passes, but
    // getCompletionStats would read props off the strings without throwing and
    // report a bogus %. Every entry must be an object.
    const prog = await readKitProgress(
      entryServingSchema('k', { form_metadata: { form_number: 'T' }, fields: ['abc', 1] }),
    );
    expect(prog.reviewPercent).toBeNull();
    expect(prog.schemaError).toBe(true);
  });

  it('flags schemaError for array-valued field entries (typeof [] === object)', async () => {
    // Codex round 4: `fields: [[]]` -- entries are arrays, which pass a bare
    // typeof==='object' check. getCompletionStats reads props off them without
    // throwing -> bogus 0%. The guard must also reject arrays.
    const prog = await readKitProgress(
      entryServingSchema('k', { form_metadata: { form_number: 'T' }, fields: [[]] }),
    );
    expect(prog.reviewPercent).toBeNull();
    expect(prog.schemaError).toBe(true);
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
