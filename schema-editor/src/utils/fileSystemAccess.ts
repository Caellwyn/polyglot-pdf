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
import { stripEditorState } from './fieldGrouping';

// --- minimal local typings for the slice of the API we use ----------------- //

export interface FsWritableStream {
  write(data: string): Promise<void>;
  close(): Promise<void>;
}

export interface FsFileHandle {
  readonly kind: 'file';
  readonly name: string;
  createWritable(): Promise<FsWritableStream>;
  getFile(): Promise<File>;
}

// Directory handle slice (bd b0pe): enough to list a form-kits/ dir, read/create
// per-kit subdirs, and read/write files within them. The async-iterable
// `entries()` yields [name, handle] pairs like the real FileSystemDirectoryHandle.
export interface FsDirectoryHandle {
  readonly kind: 'directory';
  readonly name: string;
  entries(): AsyncIterableIterator<[string, FsFileHandle | FsDirectoryHandle]>;
  getDirectoryHandle(name: string, opts?: { create?: boolean }): Promise<FsDirectoryHandle>;
  getFileHandle(name: string, opts?: { create?: boolean }): Promise<FsFileHandle>;
  // Optional: used to clean up the same-folder handshake marker (bd
  // polyglot-pdf-s2bf). Marked optional because a stale marker is harmless
  // (the nonce is per-run, so an old one reads as "stale" not "match") and
  // older implementations may not expose it.
  removeEntry?(name: string, opts?: { recursive?: boolean }): Promise<void>;
}

interface SaveFilePickerOptions {
  suggestedName?: string;
  types?: Array<{ description?: string; accept: Record<string, string[]> }>;
}

interface DirectoryPickerOptions {
  mode?: 'read' | 'readwrite';
}

type WindowWithFsAccess = Window & {
  showSaveFilePicker?: (opts?: SaveFilePickerOptions) => Promise<FsFileHandle>;
  showDirectoryPicker?: (opts?: DirectoryPickerOptions) => Promise<FsDirectoryHandle>;
};

// --------------------------------------------------------------------------- //

/** True when the running browser exposes the File System Access save picker. */
export function isFileSystemAccessSupported(): boolean {
  return typeof window !== 'undefined' &&
    typeof (window as WindowWithFsAccess).showSaveFilePicker === 'function';
}

/** True when the browser exposes the directory picker (catalogue/onboarding). */
export function isDirectoryAccessSupported(): boolean {
  return typeof window !== 'undefined' &&
    typeof (window as WindowWithFsAccess).showDirectoryPicker === 'function';
}

/**
 * Prompt the human to pick a directory (the form-kits/ root) for read+write.
 * Throws AbortError if cancelled (treat as a no-op). Returns the dir handle.
 */
export async function pickDirectory(): Promise<FsDirectoryHandle> {
  const win = window as WindowWithFsAccess;
  if (!win.showDirectoryPicker) {
    throw new Error('Directory access is not supported in this browser');
  }
  // Call ON window (receiver binding -- same Illegal-invocation trap as the
  // save picker; bd s1e2).
  return win.showDirectoryPicker({ mode: 'readwrite' });
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
  const json = JSON.stringify(stripEditorState(schema), null, 2);
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
