/**
 * Unit tests for setKitStatus (bd polyglot-pdf-nr8u, D2): the editor-side
 * promote/demote of a kit's metadata.json status. Must read-merge-write so it
 * never clobbers other metadata fields (label/schema/pdf/unknown keys), and the
 * resulting CatalogueEntry must reflect the new status.
 */
import { describe, it, expect } from 'vitest';
import { setKitLabel, setKitStatus, type CatalogueEntry } from './formKitDirectory';

// A mock directory handle backing a single metadata.json. Captures the last
// written content so the test can assert the merged result, mirroring the
// FsDirectoryHandle surface setKitStatus uses (getFileHandle/getFile/
// createWritable).
function mockKitDir(initialMeta: string | null) {
  const state = { meta: initialMeta };
  const metaFile = {
    getFile: async () => ({ text: async () => state.meta ?? '' } as unknown as File),
    createWritable: async () => ({
      write: async (d: string | ArrayBuffer) => { state.meta = typeof d === 'string' ? d : ''; },
      close: async () => {},
    }),
  };
  const dirHandle = {
    getFileHandle: async (name: string, opts?: { create?: boolean }) => {
      if (name !== 'metadata.json') throw new DOMException('x', 'NotFoundError');
      if (state.meta === null && !opts?.create) throw new DOMException('x', 'NotFoundError');
      return metaFile;
    },
  } as unknown as CatalogueEntry['dirHandle'];
  return { dirHandle, read: () => state.meta };
}

function entry(id: string, dirHandle: CatalogueEntry['dirHandle']): CatalogueEntry {
  return {
    id, label: id, status: 'draft', hasSchema: true, hasPdf: true,
    schemaFile: 'schema.json', pdfFile: 'form.pdf', dirHandle,
  };
}

describe('setKitStatus', () => {
  it('REFUSES to write over a SUBMITTED kit', async () => {
    // `submitted` joined the write-locked set (bd polyglot-pdf-hqztg) and this
    // guard was left behind -- so local mode, which bypasses the server when
    // the backend is unreachable, would promote a kit awaiting author review
    // with no gate and no role check (Opus fresh-eyes round 6).
    const mock = mockKitDir(JSON.stringify({ label: 'W-7', status: 'submitted' }));

    await expect(setKitStatus(entry('w7', mock.dirHandle), 'complete'))
      .rejects.toThrow(/submitted/);

    expect(JSON.parse(mock.read()!).status).toBe('submitted');
  });

  it('refuses EVERY write-locked status, not just the one it was written for', async () => {
    // The guard originally named a single status. Enumerate the set instead:
    // adding a value to _WRITE_LOCKED_STATUSES without revisiting every reader
    // is how this bead lost the invariant twice.
    for (const locked of ['submitted', 'unpublished'] as const) {
      const mock = mockKitDir(JSON.stringify({ label: 'W-7', status: locked }));
      await expect(setKitStatus(entry('w7', mock.dirHandle), 'complete'))
        .rejects.toThrow();
      expect(JSON.parse(mock.read()!).status).toBe(locked);
    }
  });

  it('still allows revert-to-draft on a COMPLETE kit', async () => {
    // The guard must refuse local PROMOTION, not every write. Deriving it from
    // the shared write-locked set broke exactly this, and only this test
    // caught it -- "may its bytes change?" and "may a local write promote it?"
    // are different questions (Opus fresh-eyes round 7 fallout).
    const mock = mockKitDir(JSON.stringify({ label: 'N-400', status: 'complete' }));
    const updated = await setKitStatus(entry('n-400', mock.dirHandle), 'draft');
    expect(updated.status).toBe('draft');
  });

  it('still allows a DRAFT to be promoted locally', async () => {
    // The guard must not make local mode useless -- a draft is exactly what it
    // is for.
    const mock = mockKitDir(JSON.stringify({ label: 'W-7', status: 'draft' }));
    const updated = await setKitStatus(entry('w7', mock.dirHandle), 'complete');
    expect(updated.status).toBe('complete');
  });

  it('REFUSES to write over an unpublished (retired) kit', async () => {
    // The write-lock lives at this primitive, not only in the component that
    // calls it: a component guard protects one path, and once the render hides
    // the control it cannot be pinned through the UI at all (a mutation
    // disabling the component guard left all 56 catalogue tests green -- Opus
    // fresh-eyes). A retired revision's metadata is what its confirmation
    // records were confirmed against; it returns to service only through the
    // backend's publish gate.
    const mock = mockKitDir(JSON.stringify({ label: 'Old', status: 'unpublished' }));

    await expect(setKitStatus(entry('old', mock.dirHandle), 'complete'))
      .rejects.toThrow(/unpublished/);

    // Nothing was written -- the file still holds the retired status.
    expect(JSON.parse(mock.read()!).status).toBe('unpublished');
  });

  it('refuses a retired kit for EVERY target status, not just complete', async () => {
    for (const target of ['draft', 'complete', 'unpublished'] as const) {
      const mock = mockKitDir(JSON.stringify({ label: 'Old', status: 'unpublished' }));
      await expect(setKitStatus(entry('old', mock.dirHandle), target))
        .rejects.toThrow(/unpublished/);
      expect(JSON.parse(mock.read()!).status).toBe('unpublished');
    }
  });

  it('promotes draft -> complete, preserving other metadata fields', async () => {
    const mock = mockKitDir(JSON.stringify({ label: 'I-90', schema: 'custom.json', status: 'draft' }));
    const updated = await setKitStatus(entry('i-90', mock.dirHandle), 'complete');

    expect(updated.status).toBe('complete');
    const written = JSON.parse(mock.read()!);
    expect(written.status).toBe('complete');
    expect(written.label).toBe('I-90');       // preserved
    expect(written.schema).toBe('custom.json'); // preserved
  });

  it('reverts complete -> draft', async () => {
    const mock = mockKitDir(JSON.stringify({ label: 'N-400', status: 'complete' }));
    const updated = await setKitStatus(entry('n-400', mock.dirHandle), 'draft');

    expect(updated.status).toBe('draft');
    expect(JSON.parse(mock.read()!).status).toBe('draft');
  });

  it('preserves unknown metadata keys (read-merge-write, not overwrite)', async () => {
    const mock = mockKitDir(JSON.stringify({ status: 'draft', notes: 'keep me', pdf: 'f.pdf' }));
    await setKitStatus(entry('k', mock.dirHandle), 'complete');

    const written = JSON.parse(mock.read()!);
    expect(written.notes).toBe('keep me');
    expect(written.pdf).toBe('f.pdf');
    expect(written.status).toBe('complete');
  });

  it('writes a fresh metadata.json when none exists', async () => {
    const mock = mockKitDir(null); // no metadata.json yet
    const updated = await setKitStatus(entry('k', mock.dirHandle), 'complete');

    expect(updated.status).toBe('complete');
    expect(JSON.parse(mock.read()!).status).toBe('complete');
  });
});

describe('setKitLabel (bd 15ic)', () => {
  it('renames the display label, preserving other metadata fields', async () => {
    const mock = mockKitDir(JSON.stringify({ label: 'Form 2', status: 'draft', notes: 'keep' }));
    const updated = await setKitLabel(entry('form-2', mock.dirHandle), '  IRS W-9  ');

    expect(updated.id).toBe('form-2');           // identity untouched
    const written = JSON.parse(mock.read()!);
    expect(written.label).toBe('IRS W-9');       // trimmed
    expect(written.status).toBe('draft');        // preserved
    expect(written.notes).toBe('keep');          // preserved
  });

  it('rejects manifest-poison characters without writing (bd 15ic Opus review)', async () => {
    // deploy-all.sh splices this label into index.json by string concatenation;
    // a quote/backslash/control char would ship an invalid manifest. Mirror of
    // the hosted route's _safe_label ban.
    const mock = mockKitDir(JSON.stringify({ label: 'Form 2', status: 'draft' }));
    for (const bad of ['My "Special" Form', 'Path\\Back', 'Tab\there', 'x'.repeat(201)]) {
      await expect(setKitLabel(entry('form-2', mock.dirHandle), bad))
        .rejects.toThrow(/quotes|control|too long/i);
    }
    expect(JSON.parse(mock.read()!).label).toBe('Form 2');  // unchanged
  });

  it('allows legitimate punctuation and unicode', async () => {
    const mock = mockKitDir(JSON.stringify({ label: 'Form 2', status: 'draft' }));
    await setKitLabel(entry('form-2', mock.dirHandle), "O'Brien's Form (2024), Rev-2");
    expect(JSON.parse(mock.read()!).label).toBe("O'Brien's Form (2024), Rev-2");
  });

  it('rejects a blank label without writing', async () => {
    const mock = mockKitDir(JSON.stringify({ label: 'Form 2', status: 'draft' }));
    await expect(setKitLabel(entry('form-2', mock.dirHandle), '   '))
      .rejects.toThrow('must not be empty');
    expect(JSON.parse(mock.read()!).label).toBe('Form 2');  // unchanged
  });
});
