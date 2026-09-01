/**
 * Remote form-kit catalogue over the backend's editor/author-gated
 * /api/editor routes (bd polyglot-pdf-92qe.2).
 *
 * The hosted delivery mode's counterpart of formKitDirectory.ts: instead of a
 * local directory picked via the File System Access API, kits live in the
 * shared store behind the backend (GCS in production, a local form-kits/ dir in
 * dev), served by /api/editor/* (bd 92qe.1). A contractor opens ONE URL, signs
 * in as themselves, and works the same catalogue -> open -> edit -> save ->
 * mark-complete loop against the shared store.
 *
 * Auth: every call carries the signed-in person's Firebase ID token as
 * `Authorization: Bearer` (bd polyglot-pdf-yswp3). The token comes from
 * utils/editorAuth.ts and is fetched PER REQUEST, since it expires roughly
 * hourly and the SDK refreshes it transparently. A 401 raises AuthError (the
 * token was refused) and a 403 raises ForbiddenError (a real account with no
 * editor role -- see editor_auth.py); a 503 means the server has no editor
 * surface configured.
 *
 * The shared access code this replaced (X-Editor-Token) is gone: the server
 * stopped accepting it when per-user identity landed (bd polyglot-pdf-hn0jq).
 *
 * Delivery-mode gate: isHostedMode() reads VITE_DELIVERY_MODE at call time
 * (not module load) so tests can stub the env per case.
 */
import { editorIdToken } from './editorAuth';
import type { FormSchema } from '../types/schema';
import { stripEditorState } from './fieldGrouping';
import { migrateLegacyRequired } from './schemaMigrate';

export type EditorRole = 'editor' | 'author';

/** A kit as the editor list route reports it -- the remote mirror of
 * CatalogueEntry (formKitDirectory.ts) minus the directory handle. */
/**
 * A kit's RECORDED review progress, written into metadata.json at save/publish
 * by the backend's publish_readiness (sprint-18 C4, bd polyglot-pdf-g687).
 *
 * The catalogue renders this stored answer instead of re-deriving its own, so
 * a card and the open editor cannot disagree. Two fields make the stamp
 * honest rather than merely convenient:
 *
 *   verified   false when the counts were computed with NO usable lint report.
 *              The card must then show the verify hint, never a confident %.
 *   schemaSha1 the schema the stamp measured, for callers that HOLD the schema
 *              and can compare. The catalogue listing deliberately does not
 *              (not re-reading every kit is the point of the stamp), so it
 *              cannot detect an out-of-band edit -- see readStamp's own doc and
 *              bd polyglot-pdf-j8sr, which tracks re-stamping the routes that
 *              rewrite a schema without one.
 *
 * Absent entirely on a kit not saved since C4 shipped: also the verify hint.
 */
export interface ReadinessStamp {
  reviewed: number;
  toReview: number;
  total: number;
  errors: number;
  percent: number;
  ready: boolean;
  verified: boolean;
  schemaSha1: string;
  stampedAt?: string | null;
}

/** A kit's lifecycle status (bd polyglot-pdf-6dz0).
 *  draft       -- editable, hidden from the voice app.
 *  complete    -- published and served; write-locked.
 *  unpublished -- a SUPERSEDED revision: hidden like a draft but still
 *                 write-locked, because its schema is what earlier
 *                 confirmation records were confirmed against. It returns to
 *                 service only through the full publish gate, never via draft.
 */
// 'submitted' means an editor finished it and an author has not yet
// published it (bd polyglot-pdf-hqztg). Not deployable, and write-locked.
export type KitLifecycleStatus = 'draft' | 'submitted' | 'complete' | 'unpublished';

export interface RemoteKitEntry {
  id: string;
  label: string;
  description?: string | null;
  status: KitLifecycleStatus | 'unknown';
  hasSchema: boolean;
  hasPdf: boolean;
  schemaFile: string;
  pdfFile: string;
  readiness?: ReadinessStamp | null;
  /** Who holds this kit for editing, if anyone (bd polyglot-pdf-hqztg).
   * 'editor' | 'author' | null -- a ROLE, not a person. */
  heldBy?: string | null;
  /** Hidden from the default catalogue (bd polyglot-pdf-n5fwd).
   *
   * OPTIONAL, and absent means visible: a kit whose metadata predates this
   * feature carries no such key, and the server defaults it false. Nothing is
   * backfilled. Distinct from the per-kit revision ARCHIVE, which is the
   * frozen audit copy a confirmation record points at. */
  hidden?: boolean;
}

/** The sign-in was missing or refused (HTTP 401): sign in again. */
export class AuthError extends Error {
  constructor(message = 'Sign-in required') {
    super(message);
    this.name = 'AuthError';
  }
}

/**
 * A VALID account with no editor access (HTTP 403).
 *
 * Kept DISTINCT from AuthError because the remedy is completely different and
 * the two are easy to confuse: 401 means "sign in again" (a retry can fix it),
 * while 403 means "you are who you say you are, but you are not listed here"
 * -- no amount of retrying helps; an operator must grant access with
 * scripts/bootstrap_editor_user.py. Collapsing them would send a voice-app user
 * round a sign-in loop that can never succeed.
 */
export class ForbiddenError extends Error {
  /**
   * True only when the server said this account holds NO editor role at all --
   * the case that must evict to the refused screen.
   *
   * A 403 also arrives for "you ARE an editor, but this action is author-only"
   * (publishing, reopening a live kit, the author-tier routes). Those must
   * surface as a normal refusal: throwing a working editor out of the editor
   * for clicking an author button is a far worse bug than the one this class
   * was added to fix. The server marks the evicting one with a machine-readable
   * prefix (editor_auth.NO_EDITOR_ACCESS_PREFIX) rather than a message we
   * string-match, because prose is not a contract.
   */
  readonly noEditorAccess: boolean;

  constructor(message = 'This account does not have schema editor access',
              noEditorAccess = false) {
    super(message);
    this.name = 'ForbiddenError';
    this.noEditorAccess = noEditorAccess;
  }
}

/** The server's marker for "no editor role at all" -- mirrors
 * backend/services/editor_auth.py's NO_EDITOR_ACCESS_PREFIX. */
const NO_EDITOR_ACCESS_PREFIX = 'NO_EDITOR_ACCESS:';

/** Build a ForbiddenError from a 403's detail, classifying it and stripping
 * the wire marker.
 *
 * EXPORTED because the editor has a SECOND direct fetch site (localStamp.ts)
 * that cannot go through editorFetch. Sharing the classifier is what stops
 * the two paths disagreeing about which 403s evict -- duplicating the
 * `startsWith` there is how the split drifts. */
export function forbiddenFromDetail(detail: string): ForbiddenError {
  const evicting = detail.startsWith(NO_EDITOR_ACCESS_PREFIX);
  return new ForbiddenError(
    evicting ? detail.slice(NO_EDITOR_ACCESS_PREFIX.length).trim() : detail,
    evicting,
  );
}

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

/**
 * Every editor API call, carrying the signed-in person's identity.
 *
 * The ID token is fetched HERE, per request, rather than captured once at
 * sign-in: Firebase ID tokens expire in about an hour and the SDK refreshes
 * them from the persisted session, so asking each time is what keeps a long
 * editing session from 401ing halfway through a kit.
 */
async function editorFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await editorIdToken();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${apiBaseUrl()}${path}`, { ...init, headers });
  if (res.status === 401) throw new AuthError();
  // 403 is a REAL account without editor access -- a different remedy from 401,
  // so it gets its own error type rather than being folded into AuthError. The
  // server's detail is carried through because it names the actual reason.
  if (res.status === 403) {
    throw forbiddenFromDetail(await errorDetail(
      res, 'This account does not have schema editor access'));
  }
  return res;
}

/** Extract the backend's error detail for a human-readable failure message. */
export async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === 'string' && body.detail) return body.detail;
  } catch {
    // non-JSON error body -> fallback
  }
  return `${fallback} (HTTP ${res.status})`;
}

/** Confirm the signed-in person has editor access, and learn their role.
 * AuthError on a refused token, ForbiddenError on a real account with no editor
 * role; a thrown Error with the server detail on 503 (surface is off). */
export async function probeSession(): Promise<{ role: EditorRole }> {
  const res = await editorFetch('/api/editor/session');
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not check your access'));
  return (await res.json()) as { role: EditorRole };
}

/** Result of the same-folder handshake (bd polyglot-pdf-s2bf). */
export interface StoreHandshake {
  sameFolder: boolean;
  backendRoot?: string | null;
  // Exactly what the backend can return (editor_kit_routes.py's
  // store-handshake handler). NOT 'unwritable': that is minted
  // client-side in formKitDirectory.ts when the marker WRITE fails,
  // and it returns before this route is called -- it belongs to
  // FolderCheck, not to the wire type.
  reason?: 'mismatch' | 'stale' | 'not-a-local-store' | null;
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

/** One superseded revision of a kit (bd polyglot-pdf-qfyxr): the encoded
 * archive marker plus the archived snapshot's published_at (null when the
 * snapshot predates the stamp). */
export interface ArchivedRevision {
  marker: string;
  published_at: string | null;
}

/** A kit's superseded revisions, newest first (the backend sorts by the
 * archived snapshot's published_at; stampless revisions last). Empty for a
 * kit with no archive -- the normal state, not an error. */
export async function listArchivedRevisions(kitId: string): Promise<ArchivedRevision[]> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/archive`);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load archived versions'));
  const body = (await res.json()) as { revisions?: ArchivedRevision[] };
  return Array.isArray(body.revisions) ? body.revisions : [];
}

/** An archived revision's schema, READ-ONLY (there is deliberately no write
 * counterpart -- superseded bytes are what the audit trail names). Null when
 * the marker has no revision. */
export async function loadArchivedSchema(
  kitId: string, marker: string,
): Promise<FormSchema | null> {
  const res = await editorFetch(
    `/api/editor/kits/${encodeURIComponent(kitId)}/archive/${encodeURIComponent(marker)}/schema`,
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the archived version'));
  return (await res.json()) as FormSchema;
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
 * ruleset -- the same rules the mark-complete promotion gate enforces. Always
 * sends the schema the editor HOLDS, so the strip lints exactly what is on
 * screen before any save.
 *
 * `kitId` (sprint-18 C1, bd polyglot-pdf-o7y9) scopes the lint to the open
 * kit: the kit-scoped route loads the kit's persisted AcroForm dump exactly as
 * the publish gate does, so the two dump-gated rules (widget multiclaim /
 * unclaimed) are visible to the strip too -- without it a confidently clean
 * strip could still 409 at the gate. Omit for a schema with no kit identity
 * (nothing opened from the store); that falls back to the dump-less route.
 * AuthError on a rotated code (editorFetch throws it for the caller to
 * re-prompt). */
export async function lintSchema(
  schema: FormSchema, kitId?: string,
): Promise<LintReport> {
  const path = kitId
    ? `/api/editor/kits/${encodeURIComponent(kitId)}/lint`
    : '/api/editor/lint';
  const res = await editorFetch(path, {
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
  status: KitLifecycleStatus;
  retranslated: number;
  translationModel: string | null;
  /** The kit retired by a cross-kit supersede, when one was named. */
  supersededKitId: string | null;
}

/** Flip a kit's status. Promotion to complete is validated server-side (the
 * publish gate) -- a 422 carries the validation detail to show the human. A
 * complete flip ALSO runs the translation drift sweep server-side (bd
 * polyglot-pdf-783r): it can take tens of seconds (one pro-tier call per
 * language, with retry), and a 409 whose detail is the "N of M translations
 * complete" message means some language is still missing -- re-press to retry
 * only the gaps. */
/** Optional extras on a status change. An OPTIONS OBJECT rather than more
 * positional parameters: two same-typed optionals in a row (replacesKitId,
 * authorVersion) are trivially swappable at a call site, and swapping THESE two
 * would retire the wrong kit and record a kit id as a revision marker. */
export interface SetRemoteStatusOptions {
  /** Retire this other live kit for the same form as part of this publish. */
  replacesKitId?: string;
  /** Author-supplied revision marker, required to publish a kit that has no
   * government edition_date (bd polyglot-pdf-xzw5). The backend REFUSES to
   * change one that is already published. */
  authorVersion?: string;
}

export async function setRemoteStatus(
  kitId: string, status: KitLifecycleStatus, options: SetRemoteStatusOptions = {},
): Promise<KitStatusResult> {
  const { replacesKitId, authorVersion } = options;
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      status,
      ...(replacesKitId ? { replaces_kit_id: replacesKitId } : {}),
      ...(authorVersion ? { author_version: authorVersion } : {}),
    }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the status'));
  return (await res.json()) as KitStatusResult;
}

/** Who holds a kit for editing (bd polyglot-pdf-hqztg). */
export interface KitLockResult {
  ok: boolean;
  kitId: string;
  /** 'editor' | 'author' | null -- a ROLE, not a person: the editor API has
   * only two shared tokens (bd polyglot-pdf-ijntk lifts that). */
  heldBy: string | null;
  /** True when this call TOOK the lock from someone else, so the UI can say so
   * rather than silently winning. */
  preempted: boolean;
}

/** A live kit that MIGHT be an older revision of the one being published. */
export interface RetireCandidate {
  kitId: string;
  label: string;
  formNumber?: string | null;
  edition?: string | null;
  /** "edition_date" | "author_version" | "published" -- what `edition` IS, so
   * the UI can label it rather than showing a bare string. */
  editionKind?: string | null;
  /** "form_number" | "label" -- why this was suggested. A label match deserves
   * more suspicion than a declared form number. */
  matchedOn: string;
}

/**
 * Live kits that plausibly serve the same form as this one (bd
 * polyglot-pdf-bdedm).
 *
 * A SUGGESTION. Nothing is retired by asking: the author ticks one and it
 * rides the publish as `replaces_kit_id`. Author-only, like the publish it
 * feeds.
 */
export async function fetchRetireCandidates(kitId: string): Promise<RetireCandidate[]> {
  const res = await editorFetch(
    `/api/editor/kits/${encodeURIComponent(kitId)}/retire-candidates`);
  if (!res.ok) {
    throw new Error(await errorDetail(res, 'Could not check for older versions'));
  }
  const body = (await res.json()) as { candidates?: RetireCandidate[] };
  return body.candidates ?? [];
}

/** Take a kit for editing. An author can always take one back from an editor;
 * the reverse 409s. */
export async function takeKitLock(kitId: string): Promise<KitLockResult> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/lock`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not take the form'));
  return (await res.json()) as KitLockResult;
}

/** Release a kit. An author may release anyone's lock; an editor cannot evict
 * an author. */
export async function releaseKitLock(kitId: string): Promise<KitLockResult> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/lock`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not release the form'));
  return (await res.json()) as KitLockResult;
}

/** Permanently delete a kit and everything under it, archives included.
 *
 * AUTHOR ONLY, and the only destructive call in this module (bd
 * polyglot-pdf-6x1j). The server refuses with 409 both when confirmation
 * records name the kit AND when it cannot verify whether they do -- callers
 * should surface that detail verbatim rather than retrying, because a refusal
 * here is the guard working, not a transient failure.
 */
/** How firmly the server wants this deletion confirmed (bd polyglot-pdf-6zhaf).
 *
 *   'ack'        -- never published, but records exist or could not be checked
 *   'double-ack' -- ever live: the form may have been filled and agreed to
 *
 * A refusal is never final. The old design refused outright when the
 * confirmation check was positive OR unavailable, and because un-attributable
 * legacy records make it permanently unavailable, every kit became undeletable
 * forever. A safeguard makes a destructive act deliberate, not impossible. */
export type DeleteEscalation = 'ack' | 'double-ack';

/** A delete the server wants confirmed rather than refused outright. Carries
 * the server's own wording -- it names what is at risk for THIS kit, which a
 * generic client-side warning cannot. */
export class DeleteNeedsAcknowledgement extends Error {
  readonly escalation: DeleteEscalation;

  constructor(message: string, escalation: DeleteEscalation) {
    super(message);
    this.name = 'DeleteNeedsAcknowledgement';
    this.escalation = escalation;
  }
}

/** Server markers -- mirror editor_kit_routes.DELETE_NEEDS_*_PREFIX. Matched on
 * a PREFIX rather than message text: the copy will be reworded, and here the
 * wording decides whether the human is offered a way through at all. */
const DELETE_NEEDS_ACK_PREFIX = 'DELETE_NEEDS_ACK:';
const DELETE_NEEDS_DOUBLE_ACK_PREFIX = 'DELETE_NEEDS_DOUBLE_ACK:';

/** The acknowledgement each escalation clears -- mirrors editor_kit_routes'
 * ACK_UNDERSTOOD / ACK_UNDERSTOOD_PUBLISHED. DISTINCT values, not one boolean:
 * the weaker one must not satisfy an ever-live delete, or the second
 * confirmation is decoration the server never checks. */
const ACK_TOKEN: Record<DeleteEscalation, string> = {
  'ack': 'understood',
  'double-ack': 'understood-published',
};

/** Delete a kit. Pass acknowledged once the human has confirmed a warning the
 * server raised; without it a risky delete comes back as
 * DeleteNeedsAcknowledgement rather than succeeding. */
export async function deleteRemoteKit(
  kitId: string, opts: { acknowledged?: DeleteEscalation | null } = {},
): Promise<number> {
  // The token names WHICH warning was confirmed, so acknowledging the lighter
  // one cannot clear the heavier gate.
  const query = opts.acknowledged
    ? `?acknowledged=${encodeURIComponent(ACK_TOKEN[opts.acknowledged])}`
    : '';
  const res = await editorFetch(
    `/api/editor/kits/${encodeURIComponent(kitId)}${query}`,
    { method: 'DELETE' },
  );
  if (!res.ok) {
    const detail = await errorDetail(res, 'Could not delete the form');
    if (detail.startsWith(DELETE_NEEDS_DOUBLE_ACK_PREFIX)) {
      throw new DeleteNeedsAcknowledgement(
        detail.slice(DELETE_NEEDS_DOUBLE_ACK_PREFIX.length).trim(), 'double-ack');
    }
    if (detail.startsWith(DELETE_NEEDS_ACK_PREFIX)) {
      throw new DeleteNeedsAcknowledgement(
        detail.slice(DELETE_NEEDS_ACK_PREFIX.length).trim(), 'ack');
    }
    throw new Error(detail);
  }
  const body = (await res.json()) as { objectsRemoved?: number };
  return body.objectsRemoved ?? 0;
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

/** Hide a kit from the default catalogue, or bring it back (bd n5fwd).
 *
 * AUTHOR-ONLY server-side, so an editor calling this gets a 403 -- the UI
 * hides the control for them, but the server is what enforces it. */
export async function setRemoteHidden(kitId: string, hidden: boolean): Promise<void> {
  const res = await editorFetch(`/api/editor/kits/${encodeURIComponent(kitId)}/hidden`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hidden }),
  });
  if (!res.ok) {
    throw new Error(await errorDetail(
      res, hidden ? 'Could not hide the form' : 'Could not unhide the form'));
  }
}

// --- author tier (bd polyglot-pdf-92qe.3) ----------------------------------
// Onboarding + hosted extraction: multipart POSTs (no manual Content-Type --
// the browser sets the boundary). Both need the AUTHOR role; the server
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
  // so after the post-translate reload they render at their option rows in
  // the field editor (sprint-18 C1; the pane that used to list them is gone).
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
