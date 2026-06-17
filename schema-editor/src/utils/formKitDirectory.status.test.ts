/**
 * Unit tests for setKitStatus (bd polyglot-pdf-nr8u, D2): the editor-side
 * promote/demote of a kit's metadata.json status. Must read-merge-write so it
 * never clobbers other metadata fields (label/schema/pdf/unknown keys), and the
 * resulting CatalogueEntry must reflect the new status.
 */
import { describe, it, expect } from 'vitest';
import { setKitStatus, type CatalogueEntry } from './formKitDirectory';

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
