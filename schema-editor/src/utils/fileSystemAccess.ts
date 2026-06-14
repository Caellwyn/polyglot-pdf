/**
 * One-step schema save via the File System Access API (bd polyglot-pdf-s1e2).
 *
 * The editor previously could only DOWNLOAD the edited schema, forcing the human
 * to then manually copy the file into place -- the quiet loop-killer for the
 * touch-up workflow. With the File System Access API the human picks a
 * destination ONCE (showSaveFilePicker), and every subsequent save writes
 * straight to that same file handle with no re-prompt. Reloading reads it back
 * from the same handle.
 *
 * Chrome/Edge only; Firefox/Safari lack the API. Callers fall back to the
 * download path (saveSchema in schemaLoader.ts) when isFileSystemAccessSupported
 * is false. Maintainer decision (2026-06-13): the Chrome-only + per-session
 * permission prompt tradeoff is acceptable for the local authoring workflow.
 *
 * The File System Access types are not in this project's TS lib.dom, so the
 * minimal slice we use is declared locally rather than pulling in a dependency.
 */
import type { FormSchema } from '../types/schema';

// --- minimal local typings for the slice of the API we use ----------------- //

export interface FsWritableStream {
  write(data: string): Promise<void>;
  close(): Promise<void>;
}

export interface FsFileHandle {
  readonly name: string;
  createWritable(): Promise<FsWritableStream>;
  getFile(): Promise<File>;
}

interface SaveFilePickerOptions {
  suggestedName?: string;
  types?: Array<{ description?: string; accept: Record<string, string[]> }>;
}

type WindowWithFsAccess = Window & {
  showSaveFilePicker?: (opts?: SaveFilePickerOptions) => Promise<FsFileHandle>;
};

// --------------------------------------------------------------------------- //

/** True when the running browser exposes the File System Access save picker. */
export function isFileSystemAccessSupported(): boolean {
  return typeof window !== 'undefined' &&
    typeof (window as WindowWithFsAccess).showSaveFilePicker === 'function';
}

const JSON_PICKER_TYPES = [{
  description: 'FormSchema JSON',
  accept: { 'application/json': ['.json'] },
}];

/**
 * Prompt the human for a destination file and return its handle.
 * Throws AbortError (DOMException) if the human cancels the picker -- callers
 * should treat that as a no-op, not an error to surface.
 */
export async function pickSchemaFile(suggestedName: string): Promise<FsFileHandle> {
  const win = window as WindowWithFsAccess;
  if (!win.showSaveFilePicker) {
    throw new Error('File System Access API is not supported in this browser');
  }
  // Call ON window (not via a detached reference): native browser methods bind
  // their receiver to window, so `const p = window.showSaveFilePicker; p(...)`
  // throws "Illegal invocation" in real Chrome (a vi.fn() mock would mask it).
  return win.showSaveFilePicker({ suggestedName, types: JSON_PICKER_TYPES });
}

/** True when an error is the human cancelling the file picker (not a failure). */
export function isUserAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError';
}

/** Write the schema to an already-chosen file handle (the one-step re-save). */
export async function writeSchemaToHandle(
  handle: FsFileHandle,
  schema: FormSchema,
): Promise<void> {
  const json = JSON.stringify(schema, null, 2);
  const writable = await handle.createWritable();
  try {
    await writable.write(json);
  } finally {
    await writable.close();
  }
}

/** Read a schema back from a file handle (verifies the saved-then-reload path). */
export async function readSchemaFromHandle(handle: FsFileHandle): Promise<FormSchema> {
  const file = await handle.getFile();
  const text = await file.text();
  return JSON.parse(text) as FormSchema;
}
