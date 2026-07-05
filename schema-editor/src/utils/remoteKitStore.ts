/**
 * Remote form-kit catalogue over the backend's token-gated /api/editor routes
 * (bd polyglot-pdf-92qe.2).
 *
 * The hosted delivery mode's counterpart of formKitDirectory.ts: instead of a
 * local directory picked via the File System Access API, kits live in the
 * shared store behind the backend (GCS in production, a local form-kits/ dir in
 * dev), served by /api/editor/* (bd 92qe.1). A contractor opens ONE URL, enters
 * an access code once, and works the same catalogue -> open -> edit -> save ->
 * mark-complete loop against the shared store.
 *
 * Auth: every call carries the access code as the X-Editor-Token header. The
 * code comes from localStorage (entered once in the UI) or a baked
 * VITE_EDITOR_TOKEN (the original single-contractor plan's shape -- still
 * honored). A 401 raises AuthError so the UI can clear the stored code and
 * re-prompt; a 503 means the server has no editor surface configured.
 *
 * Delivery-mode gate: isHostedMode() reads VITE_DELIVERY_MODE at call time
 * (not module load) so tests can stub the env per case.
 */
import type { FormSchema } from '../types/schema';
import { stripEditorState } from './fieldGrouping';

export type EditorRole = 'editor' | 'author';

/** A kit as the editor list route reports it -- the remote mirror of
 * CatalogueEntry (formKitDirectory.ts) minus the directory handle. */
export interface RemoteKitEntry {
  id: string;
  label: string;
  description?: string | null;
  status: 'draft' | 'complete' | 'unknown';
  hasSchema: boolean;
  hasPdf: boolean;
  schemaFile: string;
  pdfFile: string;
}

/** The access code was missing/wrong (HTTP 401): clear it and re-prompt. */
export class AuthError extends Error {
  constructor(message = 'Invalid or missing access code') {
    super(message);
    this.name = 'AuthError';
  }
}

const ACCESS_CODE_KEY = 'schema-editor.accessCode';

// In-memory fallback for the access code (Codex P1 r2, PR #280): when
// localStorage is unavailable (Safari private browsing, storage disabled),
// setAccessCode would otherwise swallow the typed code entirely -- the very
// next probeSession() reads getAccessCode(), gets nothing, and the editor is
// unopenable even with a valid code. Memory keeps the CURRENT session working;
// it just won't persist across reloads.
let memoryAccessCode: string | null = null;

/** True when this build runs against the remote store (VITE_DELIVERY_MODE=hosted). */
export function isHostedMode(): boolean {
  return import.meta.env.VITE_DELIVERY_MODE === 'hosted';
}

/** Backend base URL ('' = same origin). Hosted builds set VITE_API_BASE_URL to
 * the Cloud Run URL (the editor calls it directly -- no Hosting /api rewrite,
 * whose 60s cap would kill minutes-long extraction). */
export function apiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
}

/** The active access code: the human-entered one (localStorage, with an
 * in-memory fallback for storage-less browsers) wins, else a baked
 * VITE_EDITOR_TOKEN (single-contractor compat), else null (prompt). */
export function getAccessCode(): string | null {
  try {
    const stored = window.localStorage.getItem(ACCESS_CODE_KEY);
    if (stored) return stored;
  } catch {
    // storage unavailable -> fall through to the in-memory copy
  }
  if (memoryAccessCode) return memoryAccessCode;
  const baked = import.meta.env.VITE_EDITOR_TOKEN as string | undefined;
  return baked || null;
}

export function setAccessCode(code: string): void {
  memoryAccessCode = code; // always -- storage is best-effort persistence only
  try {
    window.localStorage.setItem(ACCESS_CODE_KEY, code);
  } catch {
    // storage unavailable -> the in-memory copy above carries the session.
  }
}

export function clearAccessCode(): void {
  memoryAccessCode = null;
  try {
    window.localStorage.removeItem(ACCESS_CODE_KEY);
  } catch {
    // nothing to clear
  }
}

async function editorFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const code = getAccessCode();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (code) headers['X-Editor-Token'] = code;
  const res = await fetch(`${apiBaseUrl()}${path}`, { ...init, headers });
  if (res.status === 401) throw new AuthError();
  return res;
}

/** Extract the backend's error detail for a human-readable failure message. */
async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === 'string' && body.detail) return body.detail;
  } catch {
    // non-JSON error body -> fallback
  }
  return `${fallback} (HTTP ${res.status})`;
}

/** Validate the access code and learn the caller's role. AuthError on a bad
 * code; a thrown Error with the server detail on 503 (surface is off). */
export async function probeSession(): Promise<{ role: EditorRole }> {
  const res = await editorFetch('/api/editor/session');
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not validate the access code'));
  return (await res.json()) as { role: EditorRole };
}

/** Every kit in the shared store, DRAFTS INCLUDED -- the contractor work list. */
export async function listRemoteKits(): Promise<RemoteKitEntry[]> {
  const res = await editorFetch('/api/editor/kits');
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the kit list'));
  const body = (await res.json()) as { kits?: RemoteKitEntry[] };
  return Array.isArray(body.kits) ? body.kits : [];
}

/** A kit's schema for editing (drafts included). Null when it has none yet. */
export async function loadRemoteSchema(kitId: string): Promise<FormSchema | null> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/schema`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the schema'));
  return (await res.json()) as FormSchema;
}

/** A kit's PDF as a blob object URL for the viewer (caller revokes it). Null
 * when the kit has no PDF. */
export async function loadRemotePdfBlobUrl(kitId: string): Promise<string | null> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/pdf`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the PDF'));
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

/** Save an edited schema back to the shared store (the hosted Cmd+S). Applies
 * the same stripEditorState the File System Access save path applies. */
export async function saveRemoteSchema(kitId: string, schema: FormSchema): Promise<void> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/schema`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(stripEditorState(schema)),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not save the schema'));
}

/** One lint finding as the backend's /api/editor/lint route reports it -- the
 * authoritative Python schema_lint output (bd h76m.11, P4.3). field_id is the
 * field the ValidationPanel focuses on click (null for a non-field-anchored
 * finding, e.g. a PDF widget-claim). */
export interface LintFinding {
  severity: 'ERROR' | 'WARNING';
  rule: string;
  path: string;
  message: string;
  field_id: string | null;
}

export interface LintReport {
  findings: LintFinding[];
  errorCount: number;
  warningCount: number;
}

/** Lint the CURRENT (possibly-unsaved) schema over the backend's single Python
 * ruleset -- the same rules the mark-complete promotion gate enforces. Sends
 * the schema the editor holds, not a kit id, so the panel lints exactly what is
 * on screen before any save. AuthError on a rotated code (editorFetch throws it
 * for the caller to re-prompt). */
export async function lintSchema(schema: FormSchema): Promise<LintReport> {
  const res = await editorFetch('/api/editor/lint', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(stripEditorState(schema)),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not lint the schema'));
  return (await res.json()) as LintReport;
}

/** Flip a kit's status. Promotion to complete is validated server-side (the
 * publish gate) -- a 422 carries the validation detail to show the human. */
export async function setRemoteStatus(
  kitId: string, status: 'draft' | 'complete',
): Promise<void> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the status'));
}

// --- author tier (bd polyglot-pdf-92qe.3) ----------------------------------
// Onboarding + hosted extraction: multipart POSTs (no manual Content-Type --
// the browser sets the boundary). Both need the AUTHOR access code; the server
// answers 403 for the editor tier.

/** Upload a blank form PDF -> a new draft kit in the shared store. */
export async function onboardRemoteKit(
  pdf: File, label?: string,
): Promise<RemoteKitEntry> {
  const form = new FormData();
  form.append('pdf', pdf, pdf.name);
  if (label) form.append('label', label);
  const res = await editorFetch('/api/editor/kits', { method: 'POST', body: form });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not upload the PDF'));
  return (await res.json()) as RemoteKitEntry;
}

export interface RemoteExtractionResult {
  ok: boolean;
  detail: string;
  schemaFile?: string;
  fieldCount?: number;
}

/** Run the server-side PDF -> draft-schema extraction for a kit. Minutes-long:
 * the caller shows elapsed progress. An optional official instructions PDF
 * enriches the per-field help text (parity with the local dev flow). */
export async function extractRemoteKit(
  kitId: string,
  opts: { force?: boolean; instructionsPdf?: File } = {},
): Promise<RemoteExtractionResult> {
  const form = new FormData();
  if (opts.force) form.append('force', 'true');
  if (opts.instructionsPdf) {
    form.append('instructions_pdf', opts.instructionsPdf, opts.instructionsPdf.name);
  }
  const res = await editorFetch(
    `/api/editor/kits/${encodeURIComponent(kitId)}/extract`,
    { method: 'POST', body: form },
  );
  if (!res.ok) throw new Error(await errorDetail(res, 'Extraction failed'));
  return (await res.json()) as RemoteExtractionResult;
}
