/**
 * Unit tests for the File System Access save helpers (bd polyglot-pdf-s1e2).
 *
 * These cover the pure logic: feature detection, user-abort classification, and
 * the write/read round-trip against a mock FileSystemFileHandle. The actual
 * showSaveFilePicker prompt is a browser UI we cannot drive in jsdom, so
 * pickSchemaFile's wiring is tested only for the unsupported-browser guard.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  isFileSystemAccessSupported,
  isUserAbort,
  pickSchemaFile,
  writeSchemaToHandle,
  readSchemaFromHandle,
  type FsFileHandle,
  type FsWritableStream,
} from './fileSystemAccess';
import type { FormSchema } from '../types/schema';

const SCHEMA: FormSchema = {
  form_metadata: { title: 'Test', form_number: 'T-1', version: '1' },
  fields: [{ id: 'f1', name: 'F1', type: 'text' }],
} as unknown as FormSchema;

/** A mock file handle backed by an in-memory string, recording writes. */
function makeMockHandle(initial = ''): FsFileHandle & {
  contents: string; closed: boolean;
} {
  const state = { contents: initial, closed: false };
  const writable: FsWritableStream = {
    write: vi.fn(async (data: string) => { state.contents = data; }),
    close: vi.fn(async () => { state.closed = true; }),
  };
  return {
    kind: 'file' as const,
    name: 'mock_schema.json',
    createWritable: vi.fn(async () => writable),
    getFile: vi.fn(async () =>
      ({ text: async () => state.contents } as unknown as File)),
    get contents() { return state.contents; },
    get closed() { return state.closed; },
  };
}

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).showSaveFilePicker;
  vi.restoreAllMocks();
});

describe('isFileSystemAccessSupported', () => {
  it('is false when showSaveFilePicker is absent', () => {
    expect(isFileSystemAccessSupported()).toBe(false);
  });

  it('is true when showSaveFilePicker is a function', () => {
    (window as unknown as Record<string, unknown>).showSaveFilePicker = () => {};
    expect(isFileSystemAccessSupported()).toBe(true);
  });
});

describe('isUserAbort', () => {
  it('detects the AbortError DOMException (picker cancelled)', () => {
    expect(isUserAbort(new DOMException('cancelled', 'AbortError'))).toBe(true);
  });

  it('is false for other errors', () => {
    expect(isUserAbort(new Error('disk full'))).toBe(false);
    expect(isUserAbort(new DOMException('x', 'NotAllowedError'))).toBe(false);
  });
});

describe('pickSchemaFile', () => {
  it('throws when the API is unsupported', async () => {
    await expect(pickSchemaFile('x.json')).rejects.toThrow(/not supported/i);
  });

  it('forwards the suggested name + json types to showSaveFilePicker', async () => {
    const handle = makeMockHandle();
    const picker = vi.fn(async () => handle);
    (window as unknown as Record<string, unknown>).showSaveFilePicker = picker;
    const got = await pickSchemaFile('i-90_edited.json');
    expect(got).toBe(handle);
    expect(picker).toHaveBeenCalledWith(expect.objectContaining({
      suggestedName: 'i-90_edited.json',
      types: expect.arrayContaining([
        expect.objectContaining({ accept: { 'application/json': ['.json'] } }),
      ]),
    }));
  });

  it('invokes showSaveFilePicker with window as the receiver (no Illegal invocation)', async () => {
    // Real native methods throw "Illegal invocation" when called off a detached
    // reference. Use a getter that records `this` to prove we call ON window.
    let receiver: unknown = null;
    const handle = makeMockHandle();
    const picker = vi.fn(async function (this: unknown) { receiver = this; return handle; });
    (window as unknown as Record<string, unknown>).showSaveFilePicker = picker;
    await pickSchemaFile('x.json');
    expect(receiver).toBe(window);
  });
});

describe('write/read round-trip', () => {
  it('writes pretty JSON to the handle and closes the stream', async () => {
    const handle = makeMockHandle();
    await writeSchemaToHandle(handle, SCHEMA);
    expect(handle.closed).toBe(true);
    // Pretty-printed (2-space indent) and parses back to the same object.
    expect(handle.contents).toContain('\n  ');
    expect(JSON.parse(handle.contents)).toEqual(SCHEMA);
  });

  it('closes the stream even if write throws', async () => {
    const writable: FsWritableStream = {
      write: vi.fn(async () => { throw new Error('quota'); }),
      close: vi.fn(async () => {}),
    };
    const handle: FsFileHandle = {
      kind: 'file',
      name: 'x.json',
      createWritable: async () => writable,
      getFile: async () => ({ text: async () => '' } as unknown as File),
    };
    await expect(writeSchemaToHandle(handle, SCHEMA)).rejects.toThrow('quota');
    expect(writable.close).toHaveBeenCalled();
  });

  it('reads a schema back from the handle', async () => {
    const handle = makeMockHandle(JSON.stringify(SCHEMA));
    const got = await readSchemaFromHandle(handle);
    expect(got).toEqual(SCHEMA);
  });

  it('round-trips: write then read yields the same schema', async () => {
    const handle = makeMockHandle();
    await writeSchemaToHandle(handle, SCHEMA);
    const got = await readSchemaFromHandle(handle);
    expect(got).toEqual(SCHEMA);
  });
});
