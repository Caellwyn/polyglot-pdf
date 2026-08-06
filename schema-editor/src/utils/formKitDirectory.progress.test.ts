/**
 * Unit tests for the D3 catalogue review-progress metric (bd polyglot-pdf-vl3o).
 * The per-form metric reuses reviewCounts -- the pinned count predicate
 * App.liveStats computes for the open kit (bd polyglot-pdf-q3rm) -- and the
 * aggregate summary counts complete / in-progress / awaiting-extraction kits.
 */
import { describe, it, expect } from 'vitest';
import { summarizeCatalogue, readKitProgress, type CatalogueEntry } from './formKitDirectory';
import { liveStats } from '../App';
import type { FormField, FormSchema } from '../types/schema';

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

// A field counted as REVIEWED by reviewCounts: human sign-off
// (_review.reviewed_correct, the bd g63j rule -- the progress figure reports
// how much a person has reviewed, not how much the machine failed to fault)
// with no structural error and, in this findings-less scan, no lint gate.
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
  it('does NOT compute a review percent -- that is the stamp\'s job (bd g687)', async () => {
    // Sprint-18 C4: the percentage comes from the kit's readiness stamp in
    // metadata.json, never from a client-side re-derivation here. This scan
    // survives only for schemaError + version. Computing a percentage "just in
    // case" would leave a live SECOND definition of the number the epic
    // centralized -- which is how the fallback creeps back (bd q3rm was that
    // exact fallback disagreeing with the open kit).
    const schema = {
      source: 'pdf', form_metadata: { form_number: 'T-1' }, parts: [], sections: [],
      fields: [
        completeField('f1'), completeField('f2'),
        incompleteField('f3'), incompleteField('f4'),
      ],
    };
    const prog = await readKitProgress(entryServingSchema('k', schema));
    // Null even though the schema is perfectly measurable -- the point.
    expect(prog.reviewPercent).toBeNull();
    expect(prog.schemaError).toBe(false);
    // The version line IS still derived (no stamp carries it).
    expect(prog.version).not.toBeNull();
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
    // Valid JSON but no `fields` array -> reviewCounts would throw. Must be
    // swallowed so it cannot reject the catalogue-wide Promise.all (fresh-eyes
    // finding: a single bad schema would otherwise wipe every progress bar), and
    // flagged schemaError so the UI distinguishes it from a pre-extraction kit
    // (Codex finding).
    const prog = await readKitProgress(entryServingSchema('k', { form_metadata: {} }));
    expect(prog.reviewPercent).toBeNull();
    expect(prog.schemaError).toBe(true);
  });

  it('flags schemaError for a non-array fields value (iterable but invalid)', async () => {
    // Codex finding: `fields: "abc"` is iterable, so the stats scan would NOT
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
    // reviewCounts would read props off the strings without throwing and
    // report a bogus %. Every entry must be an object.
    const prog = await readKitProgress(
      entryServingSchema('k', { form_metadata: { form_number: 'T' }, fields: ['abc', 1] }),
    );
    expect(prog.reviewPercent).toBeNull();
    expect(prog.schemaError).toBe(true);
  });

  it('flags schemaError for array-valued field entries (typeof [] === object)', async () => {
    // Codex round 4: `fields: [[]]` -- entries are arrays, which pass a bare
    // typeof==='object' check. reviewCounts reads props off them without
    // throwing -> bogus 0%. The guard must also reject arrays.
    const prog = await readKitProgress(
      entryServingSchema('k', { form_metadata: { form_number: 'T' }, fields: [[]] }),
    );
    expect(prog.reviewPercent).toBeNull();
    expect(prog.schemaError).toBe(true);
  });

  it('distinguishes an extracted-but-empty schema from a broken one', async () => {
    // Still the meaningful distinction after C4 (the percentage moved to the
    // stamp): an empty-but-valid schema is READABLE (schemaError false, so the
    // card shows the verify hint), while an unparseable one is not.
    const prog = await readKitProgress(
      entryServingSchema('k', { form_metadata: { form_number: 'T' }, sections: [], fields: [] }),
    );
    expect(prog.schemaError).toBe(false);
    expect(prog.reviewPercent).toBeNull();
  });
});

describe('the disk scan can no longer disagree with the open kit (bd polyglot-pdf-q3rm, carried to C4)', () => {
  it('the scan offers NO percentage for a kit the open editor measures at 100%', async () => {
    // q3rm's original divergence: checkFieldComplete ERRORs a text field with
    // no pdf_field_name, so the old scan showed 0% while the open kit showed
    // 100% -- the same card flipping between two numbers. q3rm fixed it by
    // making both sides run one predicate; C4 removes the second computation
    // ENTIRELY, which is stronger: the scan now yields null and the card reads
    // the backend's stamp instead, so there is no client-side number left to
    // disagree with.
    //
    // The "both sides agree" property itself did not go away -- it moved to
    // the shared cross-language fixture
    // (src/utils/__fixtures__/reviewPredicateParity.json), which pins the
    // predicate against the BACKEND's implementation, the pairing that
    // actually matters now.
    const schema = {
      source: 'pdf', form_metadata: { form_number: 'T-1' }, parts: [], sections: [],
      fields: [{
        id: 'unmapped', name: 'U', type: 'text', read_only: false,
        spoken_name: 'u', help: { instructions: 'Fill this in.' },
        _review: { status: 'reviewed_correct' },
      }],
    };
    const prog = await readKitProgress(entryServingSchema('k', schema));
    const live = liveStats(schema as unknown as FormSchema, []);
    // The open kit still measures it (the sign-off counts -- q3rm's direction).
    expect(live.percent).toBe(100);
    // ...and the scan declines to answer at all, rather than answering
    // differently. No second number exists to drift.
    expect(prog.reviewPercent).toBeNull();
  });
});
