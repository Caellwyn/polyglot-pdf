/**
 * Unit tests for the form-kit catalogue over a directory (bd polyglot-pdf-b0pe).
 * Uses an in-memory mock of the File System Access directory/file handles.
 */
import { describe, it, expect } from 'vitest';
import {
  listKits, loadKitSchema, onboardPdf, readKitEntry,
  deriveFormId, friendlyLabel,
} from './formKitDirectory';
import type { FsDirectoryHandle, FsFileHandle } from './fileSystemAccess';

// --- in-memory mock FS ----------------------------------------------------- //

type Node = MockDir | MockFile;

class MockFile implements FsFileHandle {
  readonly kind = 'file' as const;
  constructor(public name: string, public contents: string | ArrayBuffer = '') {}
  async createWritable() {
    return {
      write: async (d: string | ArrayBuffer) => { this.contents = d; },
      close: async () => {},
    };
  }
  async getFile(): Promise<File> {
    const text = typeof this.contents === 'string' ? this.contents : '';
    return { text: async () => text } as unknown as File;
  }
}

class MockDir implements FsDirectoryHandle {
  readonly kind = 'directory' as const;
  children = new Map<string, Node>();
  constructor(public name: string) {}
  async *entries(): AsyncIterableIterator<[string, Node]> {
    for (const [n, h] of this.children) yield [n, h];
  }
  async getDirectoryHandle(name: string, opts?: { create?: boolean }) {
    let d = this.children.get(name);
    if (!d) {
      if (!opts?.create) throw new DOMException('not found', 'NotFoundError');
      d = new MockDir(name);
      this.children.set(name, d);
    }
    if (d.kind !== 'directory') throw new DOMException('is file', 'TypeMismatchError');
    return d as FsDirectoryHandle;
  }
  async getFileHandle(name: string, opts?: { create?: boolean }) {
    let f = this.children.get(name);
    if (!f) {
      if (!opts?.create) throw new DOMException('not found', 'NotFoundError');
      f = new MockFile(name);
      this.children.set(name, f);
    }
    if (f.kind !== 'file') throw new DOMException('is dir', 'TypeMismatchError');
    return f as FsFileHandle;
  }
}

function kitDir(name: string, files: Record<string, string>): MockDir {
  const d = new MockDir(name);
  for (const [fn, content] of Object.entries(files)) {
    d.children.set(fn, new MockFile(fn, content));
  }
  return d;
}

function rootWith(kits: MockDir[]): MockDir {
  const root = new MockDir('form-kits');
  for (const k of kits) root.children.set(k.name, k);
  return root;
}

const SCHEMA = JSON.stringify({ form_metadata: { title: 'X' }, fields: [{ id: 'a' }] });

// --------------------------------------------------------------------------- //

describe('friendlyLabel / deriveFormId', () => {
  it('makes a friendly label from an id', () => {
    expect(friendlyLabel('i-90')).toBe('I 90');
    expect(friendlyLabel('n_400_form')).toBe('N 400 Form');
  });
  it('derives a url-safe id from a filename', () => {
    expect(deriveFormId('Form I-90 (1).pdf')).toBe('form-i-90-1');
    expect(deriveFormId('i589.PDF')).toBe('i589');
    expect(deriveFormId('!!!.pdf')).toBe('form');
  });
});

describe('readKitEntry', () => {
  it('reads status + label from metadata.json', async () => {
    const d = kitDir('i-90', {
      'schema.json': SCHEMA, 'form.pdf': 'PDF',
      'metadata.json': JSON.stringify({ label: 'I-90 Card', status: 'complete' }),
    });
    const e = await readKitEntry('i-90', d);
    expect(e).toMatchObject({
      id: 'i-90', label: 'I-90 Card', status: 'complete',
      hasSchema: true, hasPdf: true,
    });
  });

  it('treats a missing/blank status as unknown and falls back to a friendly label', async () => {
    const d = kitDir('n-400', { 'schema.json': SCHEMA });
    const e = await readKitEntry('n-400', d);
    expect(e.status).toBe('unknown');
    expect(e.label).toBe('N 400');
    expect(e.hasSchema).toBe(true);
    expect(e.hasPdf).toBe(false);
  });

  it('honors custom schema/pdf filenames from metadata', async () => {
    const d = kitDir('i-589', {
      'final.json': SCHEMA, 'i589.pdf': 'PDF',
      'metadata.json': JSON.stringify({ schema: 'final.json', pdf: 'i589.pdf', status: 'draft' }),
    });
    const e = await readKitEntry('i-589', d);
    expect(e.schemaFile).toBe('final.json');
    expect(e.pdfFile).toBe('i589.pdf');
    expect(e.hasSchema).toBe(true);
    expect(e.hasPdf).toBe(true);
    expect(e.status).toBe('draft');
  });
});

describe('listKits', () => {
  it('lists every subdirectory, sorted by label, ignoring stray files', async () => {
    const root = rootWith([
      kitDir('i-90', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'B' }) }),
      kitDir('a-form', { 'schema.json': SCHEMA, 'metadata.json': JSON.stringify({ label: 'A' }) }),
    ]);
    root.children.set('index.json', new MockFile('index.json', '{}')); // stray file
    const kits = await listKits(root);
    expect(kits.map(k => k.label)).toEqual(['A', 'B']); // sorted, file skipped
  });

  it('lists a PDF-only kit (no schema yet) so a freshly onboarded form appears', async () => {
    const root = rootWith([kitDir('new-form', {
      'form.pdf': 'PDF', 'metadata.json': JSON.stringify({ status: 'draft' }),
    })]);
    const kits = await listKits(root);
    expect(kits).toHaveLength(1);
    expect(kits[0].hasSchema).toBe(false);
    expect(kits[0].hasPdf).toBe(true);
    expect(kits[0].status).toBe('draft');
  });
});

describe('loadKitSchema', () => {
  it('loads the kit schema.json', async () => {
    const d = kitDir('i-90', { 'schema.json': SCHEMA });
    const e = await readKitEntry('i-90', d);
    const schema = await loadKitSchema(e);
    expect(schema?.fields?.[0]?.id).toBe('a');
  });
  it('returns null when no schema is present', async () => {
    const d = kitDir('pdf-only', { 'form.pdf': 'PDF' });
    const e = await readKitEntry('pdf-only', d);
    expect(await loadKitSchema(e)).toBeNull();
  });
});

describe('onboardPdf', () => {
  function pdfFile(name: string): File {
    return {
      name,
      arrayBuffer: async () => new TextEncoder().encode('PDFDATA').buffer,
    } as unknown as File;
  }

  it('creates a new kit dir with form.pdf + metadata.json status:draft', async () => {
    const root = rootWith([]);
    const { id, entry } = await onboardPdf(root, pdfFile('Form I-90.pdf'));
    expect(id).toBe('form-i-90');
    expect(entry.status).toBe('draft');
    expect(entry.hasPdf).toBe(true);
    expect(entry.hasSchema).toBe(false);

    // The new dir is real and contains both files.
    const dir = await root.getDirectoryHandle('form-i-90');
    const meta = await (await dir.getFileHandle('metadata.json')).getFile();
    expect(JSON.parse(await meta.text())).toMatchObject({ status: 'draft' });
    expect(await dir.getFileHandle('form.pdf')).toBeTruthy();
  });

  it('suffixes the id to avoid clobbering an existing kit', async () => {
    const root = rootWith([kitDir('form-i-90', { 'form.pdf': 'x' })]);
    const { id } = await onboardPdf(root, pdfFile('Form I-90.pdf'));
    expect(id).toBe('form-i-90-2');
    // both kits now exist
    expect(await root.getDirectoryHandle('form-i-90')).toBeTruthy();
    expect(await root.getDirectoryHandle('form-i-90-2')).toBeTruthy();
  });
});
