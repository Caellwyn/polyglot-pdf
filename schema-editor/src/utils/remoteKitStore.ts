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
import { migrateLegacyRequired } from './schemaMigrate';

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

/**
 * True when a backend is reachable for SERVER-SIDE work (bd polyglot-pdf-cpiw).
 *
 * WHY THIS IS SEPARATE FROM isHostedMode(): the two answer different questions,
 * and conflating them is what made local mode a second-class surface.
 *   isHostedMode()  -- WHERE DO KITS LIVE? hosted = the shared store behind
 *                      /api/editor; local = a directory picked with the File
 *                      System Access API.
 *   hasBackend()    -- CAN WE CALL THE SERVER? for the authoritative Python
 *                      lint, the translation sweep, guidance regeneration.
 *
 * Local mode kept kits on disk AND assumed no server, so it fell back to a
 * lighter client-side lint (rule ids dropped -> the guidance staleness gate
 * silently never fired) and hid the regenerate affordances. But the local dev
 * stack DOES run the backend, so that assumption was simply wrong.
 *
 * Hosted always has one. Local has one whenever VITE_BACKEND_URL is set --
 * scripts/run-schema-editor.sh starts the backend and sets it, so the default
 * local-dev experience now matches hosted feature-for-feature. The only
 * sanctioned difference is the LLM provider (local: the free `claude` CLI;
 * hosted: metered Gemini), which is a BACKEND-side choice the editor never sees.
 */
export function hasBackend(): boolean {
  return isHostedMode() || Boolean(import.meta.env.VITE_BACKEND_URL);
}

/** Backend base URL ('' = same origin). Hosted builds set VITE_API_BASE_URL to
 * the Cloud Run URL (the editor calls it directly -- no Hosting /api rewrite,
 * whose 60s cap would kill minutes-long extraction).
 *
 * Local mode uses VITE_BACKEND_URL instead (set by run-schema-editor.sh, which
 * launches the backend alongside the editor). Kept as a SEPARATE variable from
 * VITE_API_BASE_URL so a local session can never accidentally inherit the
 * committed Cloud Run URL from .env.hosted and start writing to the shared
 * store -- bd polyglot-pdf-cpiw. */
export function apiBaseUrl(): string {
  // VITE_API_BASE_URL wins wherever it is set (it is THE hosted contract and
  // deploy-editor.sh injects it at build time). VITE_BACKEND_URL is the
  // local-dev addition, consulted only when the hosted one is absent -- so a
  // hosted build can never accidentally fall through to a localhost backend,
  // and a local session can never inherit the committed Cloud Run URL.
  const hosted = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
  if (hosted) return hosted;
  return (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? '';
}

/** The active access code: the human-entered one (localStorage, with an
 * in-memory fallback for storage-less browsers) wins, else a baked
 * VITE_EDITOR_TOKEN (single-contractor compat), else null (prompt). */
export function getAccessCode(): string | null {
  const baked = import.meta.env.VITE_EDITOR_TOKEN as string | undefined;
  // LOCAL dev inverts the precedence: run-schema-editor.sh mints a FRESH
  // per-run token and gives the same value to the backend and this bundle, so
  // the baked one is authoritative. A code left in localStorage by an earlier
  // run would otherwise shadow it and 401 every request -- which reads exactly
  // like the silent no-lint failure this change exists to remove
  // (bd polyglot-pdf-cpiw). Hosted keeps the human-entered code on top: there
  // the baked value is a build-time fallback, and one build serves both tiers.
  if (baked && !isHostedMode()) return baked;
  try {
    const stored = window.localStorage.getItem(ACCESS_CODE_KEY);
    if (stored) return stored;
  } catch {
    // storage unavailable -> fall through to the in-memory copy
  }
  if (memoryAccessCode) return memoryAccessCode;
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

/** Result of the same-folder handshake (bd polyglot-pdf-s2bf). */
export interface StoreHandshake {
  sameFolder: boolean;
  backendRoot?: string | null;
  reason?: 'mismatch' | 'stale' | 'unwritable' | 'not-a-local-store' | null;
}

/**
 * Ask the backend whether it can see a nonce the caller just wrote into the
 * folder the human picked -- i.e. whether both sides are looking at the SAME
 * directory.
 *
 * WHY (bd polyglot-pdf-s2bf): in local mode the editor reads and writes the
 * picked folder while the backend resolves the same kit id against its own
 * FORM_KITS_LOCAL_ROOT. When those differ, the server-side actions rewrite the
 * OTHER copy while the editor re-reads the picked one -- destructive and
 * invisible. The browser cannot read a path out of a directory handle, so
 * agreement is proved by shared observation rather than by comparing names.
 */
export async function verifyStoreFolder(nonce: string): Promise<StoreHandshake> {
  const res = await editorFetch('/api/editor/store-handshake', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nonce }),
  });
  if (!res.ok) {
    throw new Error(await errorDetail(res, 'Could not verify the form-kits folder'));
  }
  return (await res.json()) as StoreHandshake;
}

/** Every kit in the shared store, DRAFTS INCLUDED -- the contractor work list. */
export async function listRemoteKits(): Promise<RemoteKitEntry[]> {
  const res = await editorFetch('/api/editor/kits');
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the kit list'));
  const body = (await res.json()) as { kits?: RemoteKitEntry[] };
  return Array.isArray(body.kits) ? body.kits : [];
}

/** A kit's schema for editing (drafts included). Null when it has none yet.
 * Legacy shapes self-heal on load (bd 0x10.4). */
export async function loadRemoteSchema(kitId: string): Promise<FormSchema | null> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/schema`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the schema'));
  return migrateLegacyRequired((await res.json()) as FormSchema);
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

/** One-click Repair-all result (bd polyglot-pdf-zgln, P5.3b). The repaired
 * schema is stored server-side (over the same schema_repair the CLI runs), so
 * the caller must RELOAD the kit's schema after this resolves. */
export interface RepairReport {
  applied: number;
  dropped: number;
  aliasHits: number;
  repairs: Array<{ action: string; path: string; detail: string; error: boolean }>;
  errorCount: number;
  warningCount: number;
}

/** Run the server-side one-click Repair-all on a kit's STORED draft. Author
 * tier. A 422 (the draft references PDF widgets that do not exist -- repair
 * cannot invent mappings) surfaces its detail for the human to fix. AuthError on
 * a rotated code. */
export async function repairKit(kitId: string): Promise<RepairReport> {
  const res = await editorFetch(
    `/api/editor/kits/${encodeURIComponent(kitId)}/repair`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not repair the schema'));
  return (await res.json()) as RepairReport;
}

/** Regenerate-divisions result (bd polyglot-pdf-6cfu.3). The kit's parts/
 * sections were recomputed deterministically from its PDF server-side and
 * STORED, so the caller must RELOAD the kit's schema after this resolves. */
export interface DeriveDivisionsReport {
  strategy: string;
  parts: number;
  sections: number;
  toReviewSectionIds: string[];
  toReviewFieldIds: string[];
  notes: string[];
  errorCount: number;
  warningCount: number;
}

/** Re-run the deterministic division derivation on a kit's STORED draft (the
 * same pass extraction runs, bd 6cfu.2). Author tier. DESTRUCTIVE to manual
 * division edits -- the caller fronts this with a confirm dialog. A 422
 * (unreadable/0-page PDF) surfaces its detail for the human to fix. */
export async function regenerateDivisions(kitId: string): Promise<DeriveDivisionsReport> {
  const res = await editorFetch(
    `/api/editor/kits/${encodeURIComponent(kitId)}/derive-divisions`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not regenerate divisions'));
  return (await res.json()) as DeriveDivisionsReport;
}

/** Guidance-regeneration result (bd polyglot-pdf-cpiw). The kit's stored
 * schema was rewritten server-side, so the caller must RELOAD it. */
export interface RegenerateGuidanceReport {
  regenerated: string[];   // field ids whose guidance was rewritten
  skipped: string[];       // requested ids the model returned nothing for
  model: string;           // which model produced it
  booklet: string | null;  // the instructions PDF it was grounded in
  errorCount: number;
  warningCount: number;
}

/**
 * Re-author field guidance from the form's instruction booklet -- the COSTLY
 * half of the staleness gate (bd anim), which previously had no
 * implementation, leaving "re-author it" as hand-copying prose out of the IRS
 * booklet.
 *
 * `fieldIds` scopes the rewrite (the staleness banner already knows which
 * fields drifted, so this avoids re-billing the whole form); omit for every
 * field. Author tier, draft-only. Rewrites the STORED schema, so RELOAD after
 * this resolves. A successful rewrite re-stamps provenance, which is what
 * clears the staleness flag for those fields.
 */
export async function regenerateGuidance(
  kitId: string, fieldIds?: string[],
): Promise<RegenerateGuidanceReport> {
  const res = await editorFetch(
    `/api/editor/kits/${encodeURIComponent(kitId)}/regenerate-guidance`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fieldIds: fieldIds ?? [] }),
    },
  );
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not regenerate guidance'));
  return (await res.json()) as RegenerateGuidanceReport;
}

/** One PDF button widget the schema does not yet claim (bd polyglot-pdf-nivy,
 * P5.3c) -- a candidate the "Add from PDF widgets" picker offers. */
export interface UnclaimedWidget {
  name: string;              // widget PDF field name
  type?: string | null;      // checkbox | radio
  on_value?: string | null;  // the widget's on state (-> option.pdf_on_value)
  tooltip?: string | null;   // /TU tooltip, a suggested label
  page?: number | null;      // 0-indexed page
  // A kid of a SHARED-name group (one name, >1 kid): the option gets pdf_on_value
  // and the FIELD carries pdf_field_name=name. False -> a distinct-name widget:
  // the option carries pdf_field_name=name (bd nivy).
  shared_name?: boolean;
}

/** The kit's unclaimed PDF button widgets for the widget picker. Author tier;
 * empty when the kit has no persisted AcroForm dump (pre-v96b kits). */
export async function loadUnclaimedWidgets(kitId: string): Promise<UnclaimedWidget[]> {
  const res = await editorFetch(
    `/api/editor/kits/${encodeURIComponent(kitId)}/unclaimed-widgets`,
  );
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load PDF widgets'));
  const body = (await res.json()) as { widgets?: UnclaimedWidget[] };
  return Array.isArray(body.widgets) ? body.widgets : [];
}

/** The status route's success payload (bd polyglot-pdf-783r). On a successful
 * `complete`, the server ran the drift sweep first: `retranslated` counts the
 * translation entries it freshly baked (0 when nothing had drifted) and
 * `translationModel` is the model that ran (null when the sweep did no work or
 * the flip was to draft). A BLOCKED completion never returns this -- it is a
 * non-ok response whose detail carries the editor-facing "N of M" / contact
 * message, surfaced by errorDetail below. */
export interface KitStatusResult {
  ok: boolean;
  status: 'draft' | 'complete';
  retranslated: number;
  translationModel: string | null;
}

/** Flip a kit's status. Promotion to complete is validated server-side (the
 * publish gate) -- a 422 carries the validation detail to show the human. A
 * complete flip ALSO runs the translation drift sweep server-side (bd
 * polyglot-pdf-783r): it can take tens of seconds (one pro-tier call per
 * language, with retry), and a 409 whose detail is the "N of M translations
 * complete" message means some language is still missing -- re-press to retry
 * only the gaps. */
export async function setRemoteStatus(
  kitId: string, status: 'draft' | 'complete',
): Promise<KitStatusResult> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the status'));
  return (await res.json()) as KitStatusResult;
}

/** Rename a kit's DISPLAY label (bd 15ic) -- metadata-only; the kit's identity
 * (id / storage path) never changes, so nothing downstream breaks. */
export async function setRemoteLabel(kitId: string, label: string): Promise<void> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/label`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not rename the form'));
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
  // Store-with-issues (bd polyglot-pdf-v96b, P5.3a): a parseable draft is stored
  // even when lint-dirty; these carry the lint counts the catalogue surfaces so
  // the author knows to open + repair. storedWithIssues is true when the stored
  // draft has lint ERRORs or failed validation.
  errorCount?: number;
  warningCount?: number;
  storedWithIssues?: boolean;
}

/** Run the server-side PDF -> draft-schema extraction for a kit. Minutes-long:
 * the caller shows elapsed progress. An optional official instructions PDF
 * enriches the per-field help text (parity with the local dev flow). */
export async function extractRemoteKit(
  kitId: string,
  opts: {
    force?: boolean; instructionsPdf?: File; translateOptions?: boolean;
    enrichGuidance?: boolean;
  } = {},
): Promise<RemoteExtractionResult> {
  const form = new FormData();
  // ALWAYS append force (true or false) so the multipart body is never empty.
  // A bare Run-extraction click (no force, no instructions PDF) used to send a
  // zero-part body, which python-multipart rejects with a MultipartParseError
  // that starlette does not catch -- FastAPI then 400s with "There was an error
  // parsing the body" BEFORE the route runs (bd polyglot-pdf-1ysc). The backend
  // declares force: Form() = False and coerces the string, so this is safe.
  form.append('force', opts.force ? 'true' : 'false');
  // Bake option label_translations during extraction (bd 2h9j; backend default
  // true) -- uncheckable in the catalogue for cheap extraction-strategy runs.
  form.append('translate_options', opts.translateOptions === false ? 'false' : 'true');
  // Booklet-grounded guidance enrichment (bd wsao.6; backend default true) --
  // the larger LLM add-on, so cheap test runs can skip it too.
  form.append('enrich_guidance', opts.enrichGuidance === false ? 'false' : 'true');
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

/** Standalone option-label translation bake (bd polyglot-pdf-2h9j). The kit's
 * option label_translations are baked server-side IN PLACE (idempotent: only
 * missing languages are translated; force retranslates after label renames),
 * so the caller must RELOAD the kit's schema after this resolves. Author tier. */
export interface TranslateOptionsReport {
  changed: boolean;
  model: string;
  failedLanguages: string[];
  languages: Record<string, {
    labels: number; missing: number; translated: number;
    options_updated: number; failed: boolean;
  }>;
  // Verify/rectify gate flags from THIS bake (bd polyglot-pdf-9djc), LintFinding-
  // shaped (severity always WARNING). The backend also persists them into the
  // stored schema's _bakeoff provenance, where the lint route re-emits them --
  // so after the post-translate reload the ValidationPanel shows the same rows.
  flags: LintFinding[];
  errorCount: number;
  warningCount: number;
}

export async function translateRemoteKitOptions(
  kitId: string, opts: { force?: boolean } = {},
): Promise<TranslateOptionsReport> {
  const qs = opts.force ? '?force=true' : '';
  const res = await editorFetch(
    `/api/editor/kits/${encodeURIComponent(kitId)}/translate-options${qs}`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not translate option labels'));
  return (await res.json()) as TranslateOptionsReport;
}
