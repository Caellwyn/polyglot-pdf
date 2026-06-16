/**
 * Form-kit catalogue over a chosen form-kits/ directory (bd polyglot-pdf-b0pe).
 *
 * The editor's front door: instead of a hardcoded AVAILABLE_FORMS list, the human
 * picks their local form-kits/ directory once (File System Access directory API)
 * and the editor lists every kit it finds -- each form-kits/<id>/ with a
 * schema.json. Dropping an AcroForm PDF creates a new form-kits/<id>/ (form.pdf +
 * metadata.json status:draft), git-trackable so a dead laptop never loses work.
 *
 * "Complete" is a metadata.json status; the deploy (deploy-all.sh) gates on it so
 * only complete kits reach the voice app. This module never deploys -- it only
 * reads/writes the local directory.
 */
import type { FormSchema } from '../types/schema';
import type { FsDirectoryHandle, FsFileHandle } from './fileSystemAccess';
import { getCompletionStats } from './validation';

export type KitStatus = 'draft' | 'complete' | 'unknown';

export interface KitMetadata {
  label?: string;
  description?: string;
  status?: KitStatus;
  schema?: string; // custom schema filename (defaults to schema.json)
  pdf?: string;    // custom pdf filename (defaults to form.pdf)
}

export interface CatalogueEntry {
  id: string;                 // the <id> folder name
  label: string;              // metadata.label or a friendly fallback
  status: KitStatus;          // draft | complete | unknown (no/blank status)
  hasSchema: boolean;         // a schema.json (or custom) is present
  hasPdf: boolean;            // a form.pdf (or custom) is present
  schemaFile: string;         // resolved schema filename
  pdfFile: string;            // resolved pdf filename
  dirHandle: FsDirectoryHandle;
}

const SCHEMA_DEFAULT = 'schema.json';
const PDF_DEFAULT = 'form.pdf';
const METADATA_FILE = 'metadata.json';

/** Friendly label from an id when metadata has none (i-90 -> "I 90"). */
export function friendlyLabel(id: string): string {
  return id.replace(/[-_]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** URL-safe form id from a dropped filename ("Form I-90 (1).pdf" -> "form-i-90-1"). */
export function deriveFormId(filename: string): string {
  const base = filename.replace(/\.pdf$/i, '');
  const slug = base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'form';
}

async function readJsonFile<T>(handle: FsFileHandle): Promise<T | null> {
  try {
    const file = await handle.getFile();
    return JSON.parse(await file.text()) as T;
  } catch {
    return null;
  }
}

async function tryGetFile(
  dir: FsDirectoryHandle, name: string,
): Promise<FsFileHandle | null> {
  try {
    return await dir.getFileHandle(name);
  } catch {
    return null;
  }
}

/** Read a single kit subdirectory into a catalogue entry. */
export async function readKitEntry(
  id: string, dir: FsDirectoryHandle,
): Promise<CatalogueEntry> {
  let meta: KitMetadata | null = null;
  const metaHandle = await tryGetFile(dir, METADATA_FILE);
  if (metaHandle) meta = await readJsonFile<KitMetadata>(metaHandle);

  const schemaFile = meta?.schema || SCHEMA_DEFAULT;
  const pdfFile = meta?.pdf || PDF_DEFAULT;
  const hasSchema = (await tryGetFile(dir, schemaFile)) !== null;
  const hasPdf = (await tryGetFile(dir, pdfFile)) !== null;

  const status: KitStatus =
    meta?.status === 'complete' ? 'complete'
      : meta?.status === 'draft' ? 'draft'
        : 'unknown';

  return {
    id,
    label: meta?.label || friendlyLabel(id),
    status,
    hasSchema,
    hasPdf,
    schemaFile,
    pdfFile,
    dirHandle: dir,
  };
}

/**
 * List every form kit under the chosen directory. A kit is any immediate
 * subdirectory; entries without a schema are still listed (so a freshly
 * onboarded PDF-only kit appears, ready for extraction) with hasSchema=false.
 */
export async function listKits(
  root: FsDirectoryHandle,
): Promise<CatalogueEntry[]> {
  const entries: CatalogueEntry[] = [];
  for await (const [name, handle] of root.entries()) {
    if (handle.kind !== 'directory') continue;
    entries.push(await readKitEntry(name, handle as FsDirectoryHandle));
  }
  entries.sort((a, b) => a.label.localeCompare(b.label));
  return entries;
}

/** Read a kit's schema.json (the draft to edit). Null if absent/unparseable. */
export async function loadKitSchema(
  entry: CatalogueEntry,
): Promise<FormSchema | null> {
  const handle = await tryGetFile(entry.dirHandle, entry.schemaFile);
  if (!handle) return null;
  return readJsonFile<FormSchema>(handle);
}

// --- Review-progress metric (bd polyglot-pdf-vl3o, D3) ---------------------- //
//
// "Review progress" for a form is the SAME field-completion signal the editor
// already shows per field and the ValidationPanel already aggregates: a field is
// `complete` when checkFieldComplete() passes (has id/type/pdf_field_name, a
// spoken_name, and non-placeholder help). Per-form progress is the percentage of
// fields that are complete -- i.e. getCompletionStats(schema).percentage. We reuse
// that single definition rather than inventing a second one so the catalogue %
// and the in-editor % can never disagree.

/** A catalogue entry plus its computed review progress (null if no schema). */
export interface KitProgress {
  entry: CatalogueEntry;
  /** % of fields complete (0-100), or null when the kit has no loadable schema. */
  reviewPercent: number | null;
  completeFields: number;
  totalFields: number;
}

/**
 * Compute one kit's review progress by loading its schema and reusing
 * getCompletionStats. A kit with no schema (PDF-only, pre-extraction) or an
 * unparseable schema yields reviewPercent=null so the UI can show "no schema".
 */
export async function readKitProgress(
  entry: CatalogueEntry,
): Promise<KitProgress> {
  if (!entry.hasSchema) {
    return { entry, reviewPercent: null, completeFields: 0, totalFields: 0 };
  }
  const schema = await loadKitSchema(entry);
  if (!schema) {
    return { entry, reviewPercent: null, completeFields: 0, totalFields: 0 };
  }
  const stats = getCompletionStats(schema);
  return {
    entry,
    reviewPercent: stats.percentage,
    completeFields: stats.complete,
    totalFields: stats.total,
  };
}

/** An at-a-glance overview an aggregate dashboard header shows. */
export interface CatalogueSummary {
  total: number;          // every kit in the folder
  complete: number;       // metadata status === 'complete'
  inProgress: number;     // has a schema but not marked complete (drafts/unknown)
  noSchema: number;       // PDF-only, awaiting extraction
}

/**
 * Aggregate counts across the catalogue. A kit is "complete" by its metadata
 * status (the same flag the deploy gate uses); a schema-bearing non-complete kit
 * is "in progress"; a schema-less kit is awaiting extraction.
 */
export function summarizeCatalogue(entries: CatalogueEntry[]): CatalogueSummary {
  let complete = 0;
  let inProgress = 0;
  let noSchema = 0;
  for (const e of entries) {
    if (!e.hasSchema) noSchema++;
    else if (e.status === 'complete') complete++;
    else inProgress++;
  }
  return { total: entries.length, complete, inProgress, noSchema };
}

async function writeFile(
  dir: FsDirectoryHandle, name: string, data: string | ArrayBuffer,
): Promise<void> {
  const handle = await dir.getFileHandle(name, { create: true });
  const writable = await handle.createWritable();
  try {
    // The writable accepts string or BufferSource; FsWritableStream.write is
    // typed for string, so widen here for the PDF bytes path.
    await (writable.write as (d: string | ArrayBuffer) => Promise<void>)(data);
  } finally {
    await writable.close();
  }
}

export interface OnboardResult {
  id: string;
  entry: CatalogueEntry;
}

/**
 * Create a new form-kits/<id>/ from a dropped AcroForm PDF: writes form.pdf +
 * metadata.json (status:draft). Resolves a unique id if the derived one exists.
 * Does NOT extract a schema -- that is the B1 auto-pass, run separately; the new
 * kit appears in the catalogue with hasSchema=false until then.
 */
export async function onboardPdf(
  root: FsDirectoryHandle, file: File,
): Promise<OnboardResult> {
  const base = deriveFormId(file.name);
  // Avoid clobbering an existing kit folder: suffix -2, -3, ... if taken.
  let id = base;
  for (let n = 2; ; n++) {
    const existing = await tryGetDir(root, id);
    if (!existing) break;
    id = `${base}-${n}`;
  }

  const kitDir = await root.getDirectoryHandle(id, { create: true });
  const bytes = await file.arrayBuffer();
  await writeFile(kitDir, PDF_DEFAULT, bytes);
  const metadata: KitMetadata = {
    label: friendlyLabel(id),
    status: 'draft',
  };
  await writeFile(kitDir, METADATA_FILE, JSON.stringify(metadata, null, 2) + '\n');

  return { id, entry: await readKitEntry(id, kitDir) };
}

async function tryGetDir(
  root: FsDirectoryHandle, name: string,
): Promise<FsDirectoryHandle | null> {
  try {
    return await root.getDirectoryHandle(name);
  } catch {
    return null;
  }
}
