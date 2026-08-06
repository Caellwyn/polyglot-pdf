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
import { readStampFromMetadata } from './readinessStamp';
import type { ReadinessStamp } from './remoteKitStore';
import { migrateLegacyRequired } from './schemaMigrate';

export type KitStatus = 'draft' | 'complete' | 'unknown';

export interface KitMetadata {
  label?: string;
  description?: string;
  status?: KitStatus;
  schema?: string; // custom schema filename (defaults to schema.json)
  pdf?: string;    // custom pdf filename (defaults to form.pdf)
  // The readiness stamp the BACKEND writes at save/publish (sprint-18 C4, bd
  // polyglot-pdf-g687). Stored snake_case exactly as metadata.json carries it;
  // readStampFromMetadata converts it to the camelCase wire shape the cards
  // share with hosted mode. Local mode reads the same file the backend wrote,
  // so both catalogues render one definition of progress.
  readiness?: Record<string, unknown>;
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
  // The kit's recorded review progress (sprint-18 C4). Absent/null when the
  // kit has never been stamped or its stamp is malformed -- the card then
  // shows the verify hint, never a percentage. OPTIONAL rather than required
  // so a caller constructing an entry cannot be forced to invent a stamp;
  // readStamp treats undefined and null identically.
  readiness?: ReadinessStamp | null;
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
    readiness: readStampFromMetadata(meta?.readiness),
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

/** Read a kit's schema.json (the draft to edit). Null if absent/unparseable.
 * Legacy shapes self-heal on load (bd 0x10.4). */
export async function loadKitSchema(
  entry: CatalogueEntry,
): Promise<FormSchema | null> {
  const handle = await tryGetFile(entry.dirHandle, entry.schemaFile);
  if (!handle) return null;
  const schema = await readJsonFile<FormSchema>(handle);
  return schema ? migrateLegacyRequired(schema) : schema;
}

/**
 * Set a kit's metadata.json `status` (draft|complete), preserving every other
 * metadata field (label, schema, pdf, ...). This is the editor-side promote/
 * demote the deploy gate keys on: only status:complete kits reach GCS / the voice
 * app (deploy-all.sh kit_is_complete). Returns the kit's refreshed CatalogueEntry.
 * bd polyglot-pdf-nr8u (D2).
 */
export async function setKitStatus(
  entry: CatalogueEntry, status: KitStatus,
): Promise<CatalogueEntry> {
  const dir = entry.dirHandle;
  // Read-merge-write so we never clobber label/schema/pdf or unknown fields.
  const metaHandle = await tryGetFile(dir, METADATA_FILE);
  const existing = metaHandle ? await readJsonFile<KitMetadata>(metaHandle) : null;
  const next: KitMetadata = { ...(existing || {}), status };
  await writeFile(dir, METADATA_FILE, JSON.stringify(next, null, 2) + '\n');
  return readKitEntry(entry.id, dir);
}

/** Rename a kit's DISPLAY label (bd 15ic) -- the local-mode mirror of the
 * hosted /label route: a read-merge-write of metadata.json's `label`. The kit's
 * identity (directory name / id) never changes, so nothing downstream breaks. */
export async function setKitLabel(
  entry: CatalogueEntry, label: string,
): Promise<CatalogueEntry> {
  const trimmed = label.trim();
  if (!trimmed) throw new Error('Label must not be empty');
  if (trimmed.length > 200) throw new Error('Label too long (max 200 characters)');
  // Mirror the hosted route's _safe_label ban (load-bearing, not cosmetic):
  // deploy-all.sh extracts this label from metadata.json with grep/sed and
  // splices it into index.json by string concatenation -- a double quote,
  // backslash, or control character would ship an INVALID manifest the voice
  // app cannot parse (bd 15ic, Opus review).
  // eslint-disable-next-line no-control-regex
  if (/["\\]|[\x00-\x1f]/.test(trimmed)) {
    throw new Error('Label may not contain double quotes, backslashes, or control characters');
  }
  const dir = entry.dirHandle;
  const metaHandle = await tryGetFile(dir, METADATA_FILE);
  const existing = metaHandle ? await readJsonFile<KitMetadata>(metaHandle) : null;
  const next: KitMetadata = { ...(existing || {}), label: trimmed };
  await writeFile(dir, METADATA_FILE, JSON.stringify(next, null, 2) + '\n');
  return readKitEntry(entry.id, dir);
}

// --- Kit readability + version scan (was: the review-progress metric) ------- //
//
// This scan NO LONGER computes review progress. Since sprint-18 C4 (bd
// polyglot-pdf-g687) a kit's percentage comes from its readiness STAMP in
// metadata.json, written by the backend's publish_readiness -- the same
// definition the open editor's strip mirrors. What survives here is what no
// stamp carries: whether the schema is READABLE (schemaError) and its VERSION
// line.
//
// Do NOT reintroduce a percentage here. A client-side re-derivation living
// beside the stamp is a second definition of one number, and the two drifting
// apart is precisely the bug this area has already shipped twice (bd
// polyglot-pdf-q3rm: the same kit showed one number open and another after a
// refresh). readKitProgress returns reviewPercent: null deliberately.

/** A catalogue entry plus its readability/version scan. `reviewPercent` is
 * always null since C4 -- the field remains so the shape stays stable for the
 * card's other consumers; the percentage lives on the kit's stamp. */
/**
 * Displayable version summary for a kit's catalogue card (bd polyglot-pdf-s4dp.2).
 * `label` is the human-facing version string (edition_date or version, e.g.
 * "01/20/25" or "December 2024"); "unknown" when no version was recovered.
 * `lowConfidence` is true when version_confidence indicates a generic fallback,
 * so the card can append a "verify" hint.
 */
export interface KitVersionInfo {
  label: string;
  lowConfidence: boolean;
}

export interface KitProgress {
  entry: CatalogueEntry;
  /** % of fields complete (0-100), or null when there is no measurable schema. */
  reviewPercent: number | null;
  completeFields: number;
  totalFields: number;
  /**
   * True when the kit HAS a schema file but it could not be read/measured
   * (unparseable JSON or structurally malformed). Distinguishes "present but
   * broken" (show an error) from "no schema yet" (show nothing) -- both have
   * reviewPercent null.
   */
  schemaError: boolean;
  /** Version summary for the card, or null when the kit has no readable schema. */
  version: KitVersionInfo | null;
}

// A version_confidence at/below this is treated as a generic fallback (the card
// shows a "verify" hint). The extractor emits 0.4 for a bare-year/loose-OMB
// fallback and 0.9 for a specific Edition/Rev match (bd s4dp.2).
const LOW_CONFIDENCE_MAX = 0.5;

/** Build a card version summary from a schema's form_metadata (bd s4dp.2). */
export function versionInfoFromSchema(schema: FormSchema): KitVersionInfo {
  const meta = (schema.form_metadata ?? {}) as FormSchema['form_metadata'];
  const label = meta?.edition_date || meta?.version || 'unknown';
  const conf = meta?.version_confidence;
  // Low-confidence when the score is explicitly low, OR the version is unknown.
  const lowConfidence =
    label === 'unknown' || (typeof conf === 'number' && conf <= LOW_CONFIDENCE_MAX);
  return { label, lowConfidence };
}

/**
 * Read one kit's schema for its VERSION line and readability, NOT its review
 * percentage (that comes from the kit's readiness stamp since sprint-18 C4 --
 * see the body). A kit with no schema (PDF-only, pre-extraction) or an
 * unparseable schema yields schemaError so the UI can distinguish the two.
 */
export async function readKitProgress(
  entry: CatalogueEntry,
): Promise<KitProgress> {
  if (!entry.hasSchema) {
    return { entry, reviewPercent: null, completeFields: 0, totalFields: 0, schemaError: false, version: null };
  }
  const schema = await loadKitSchema(entry);
  if (!schema) {
    // Has a schema file but it is absent/unparseable -> a present-but-broken
    // schema, not a pre-extraction kit.
    return { entry, reviewPercent: null, completeFields: 0, totalFields: 0, schemaError: true, version: null };
  }
  // Validate the shape BEFORE measuring: a schema can parse as JSON yet be
  // structurally wrong in ways that don't throw -- e.g. `fields: "abc"` is
  // iterable, and `fields: ["abc"]` is an array whose entries reviewCounts
  // reads properties off without throwing -- either would silently report a bogus
  // % with schemaError=false. Require an actual array of objects (an empty [] is a
  // valid 0% schema). Anything else is a broken extraction, surfaced as schemaError.
  const fieldsOk =
    Array.isArray(schema.fields) &&
    schema.fields.every(f => f !== null && typeof f === 'object' && !Array.isArray(f));
  if (!fieldsOk) {
    return { entry, reviewPercent: null, completeFields: 0, totalFields: 0, schemaError: true, version: null };
  }
  try {
    // reviewPercent is deliberately NULL: since sprint-18 C4 the percentage
    // comes from the kit's readiness STAMP (metadata.json), never from a
    // client-side re-derivation here -- that fallback is what let a card and
    // the open editor disagree (bd polyglot-pdf-q3rm). Computing it "just in
    // case" would leave a live second definition of the very number this bead
    // centralized, which is exactly how the fallback creeps back (its
    // RemoteCatalogue twin nulls the field for the same reason; Opus
    // fresh-eyes round 2 caught this side still computing it).
    //
    // This function survives for schemaError + version, which no stamp carries.
    // Belt-and-suspenders try/catch retained: a malformed schema must surface
    // as schemaError, never as an unhandled rejection that would reject the
    // catalogue-wide Promise.all and wipe every card.
    return {
      entry,
      reviewPercent: null,
      completeFields: 0,
      totalFields: 0,
      schemaError: false,
      version: versionInfoFromSchema(schema),
    };
  } catch {
    return { entry, reviewPercent: null, completeFields: 0, totalFields: 0, schemaError: true, version: null };
  }
}

/** An at-a-glance overview an aggregate dashboard header shows. */
export interface CatalogueSummary {
  total: number;          // every kit in the folder
  complete: number;       // has a schema AND metadata status === 'complete'
  inProgress: number;     // has a schema but not marked complete (drafts/unknown)
  noSchema: number;       // no schema -- awaiting extraction (deploy would skip it)
}

/**
 * Aggregate counts across the catalogue. A schema-less kit is "awaiting
 * extraction" (the deploy skips it before the complete check, so it can't be
 * complete); a schema-bearing kit is "complete" iff its metadata status is
 * complete, else "in progress".
 */
export function summarizeCatalogue(entries: CatalogueEntry[]): CatalogueSummary {
  let complete = 0;
  let inProgress = 0;
  let noSchema = 0;
  for (const e of entries) {
    // hasSchema is checked FIRST: deploy-all.sh skips a kit with no resolved
    // schema file BEFORE it evaluates kit_is_complete, so a complete-marked kit
    // without a schema is NOT actually deployable -- counting it as complete
    // would overstate deployable forms and hide the missing extraction. Such a
    // kit belongs in "awaiting extraction".
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

// --- same-folder handshake (bd polyglot-pdf-s2bf) --------------------------- //

/**
 * The marker the browser drops in the picked folder for the BACKEND to read.
 * Must stay byte-identical to _HANDSHAKE_FILE in backend/routes/editor_kit_routes.py
 * (pinned by a test -- see markerNames.contract.test.ts).
 */
const HANDSHAKE_FILE = '.editor-store-check.json';

/**
 * The marker for the EXTRACTOR channel (bd polyglot-pdf-ball). Must stay
 * byte-identical to HANDSHAKE_FILE in vite-plugins/extractEndpoint.ts.
 *
 * A SEPARATE name from the backend's, deliberately (bd polyglot-pdf-bagn). Both
 * channels run verifySameFolder against the same picked folder and are not
 * serialized against each other -- the App-level backend check is already in
 * flight from the folder pick when an extraction check starts. Sharing one
 * filename meant either channel's cleanup deleted the other's in-flight marker,
 * so the host read an ABSENT marker and refused a folder that genuinely agrees.
 * Distinct names make that interference structurally impossible instead of
 * merely unlikely, and keep both readers a simple fixed-path read.
 */
const EXTRACTOR_HANDSHAKE_FILE = '.editor-extract-check.json';

/** What the handshake concluded, and why. */
export type FolderCheck =
  | { ok: true }
  | { ok: false; reason: 'unwritable' | 'mismatch'; backendRoot?: string | null };

/**
 * Prove the editor and the backend are reading/writing the SAME folder.
 *
 * The editor reads and writes the directory the human picked; the backend
 * resolves the same kit id against its own FORM_KITS_LOCAL_ROOT. When those
 * differ, every server-side action (repair, regenerate divisions, regenerate
 * guidance) rewrites the OTHER copy while the editor re-reads the picked one --
 * destructive, and completely invisible to the human.
 *
 * A path comparison is impossible (the browser cannot read a filesystem path
 * out of a directory handle, by design), so this proves agreement by shared
 * observation: write a fresh nonce here, ask the backend to read it back from
 * its own root, and require a match.
 *
 * A write failure is its OWN answer -- a read-only source folder cannot be the
 * write target either way, and the caller shows the "make a copy" dialog for it.
 * The marker is deleted afterwards; a leftover is harmless because the nonce is
 * per-check, so a stale file reads as a mismatch rather than a false match.
 */
export async function verifySameFolder(
  dir: FsDirectoryHandle,
  askBackend: (nonce: string) => Promise<{
    sameFolder: boolean; backendRoot?: string | null;
  }>,
): Promise<FolderCheck> {
  return runHandshake(dir, HANDSHAKE_FILE, askBackend);
}

/**
 * The same proof for the EXTRACTOR channel (bd polyglot-pdf-ball), against the
 * Vite dev host's FORM_KITS_ROOT rather than the backend's FORM_KITS_LOCAL_ROOT.
 *
 * Identical logic, DIFFERENT marker file -- see EXTRACTOR_HANDSHAKE_FILE for why
 * the two channels must not share one (bd polyglot-pdf-bagn).
 */
export async function verifySameFolderForExtractor(
  dir: FsDirectoryHandle,
  askHost: (nonce: string) => Promise<{
    sameFolder: boolean; backendRoot?: string | null;
  }>,
): Promise<FolderCheck> {
  return runHandshake(dir, EXTRACTOR_HANDSHAKE_FILE, askHost);
}

/** Shared implementation: write a fresh nonce, ask, always clean up. */
async function runHandshake(
  dir: FsDirectoryHandle,
  markerFile: string,
  ask: (nonce: string) => Promise<{
    sameFolder: boolean; backendRoot?: string | null;
  }>,
): Promise<FolderCheck> {
  const nonce = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  try {
    await writeFile(dir, markerFile, JSON.stringify({ nonce }));
  } catch {
    return { ok: false, reason: 'unwritable' };
  }
  try {
    const res = await ask(nonce);
    return res.sameFolder
      ? { ok: true }
      : { ok: false, reason: 'mismatch', backendRoot: res.backendRoot };
  } finally {
    try {
      await dir.removeEntry?.(markerFile);
    } catch {
      // Best-effort: a leftover marker cannot cause a FALSE match (the next
      // check mints a new nonce), so failing to delete is not worth surfacing.
    }
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

/**
 * Write an optional instructions PDF into an existing kit dir (bd s4dp.3) and
 * return the filename written. The extractor reads it from the kit dir by name
 * (the browser's directory handle is opaque to the host, exactly as the form PDF
 * flows). We use a FIXED name ("instructions.pdf") so a re-run overwrites rather
 * than accumulating; the safe-filename guard on the endpoint accepts it.
 */
export async function writeInstructionsPdf(
  kitDir: FsDirectoryHandle, file: File,
): Promise<string> {
  const name = 'instructions.pdf';
  const bytes = await file.arrayBuffer();
  await writeFile(kitDir, name, bytes);
  return name;
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
