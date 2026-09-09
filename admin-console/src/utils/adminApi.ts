/**
 * Client for the admin service's routes this console consumes (bd
 * polyglot-pdf-b6943): GET /admin/whoami, GET /admin/audit, GET+PUT
 * /admin/config/{channel}.
 *
 * MIRRORS the auth/error handling in
 * schema-editor/src/utils/remoteKitStore.ts (editorFetch, AuthError,
 * ForbiddenError, errorDetail) against the admin service's OWN gate
 * (admin_backend/services/admin_auth.py's require_app_admin) instead of the
 * editor's. Same reasoning for keeping AuthError and ForbiddenError
 * distinct: a 401 means "sign in again" (retry can fix it); a 403 means
 * "you are who you say you are, but you hold no app_admin claim" -- no
 * amount of retrying helps, and an operator must run
 * scripts/bootstrap_admin_user.py.
 *
 * Every call carries the signed-in person's Firebase ID token as
 * `Authorization: Bearer`, fetched PER REQUEST via adminIdToken() (see that
 * module's docstring for why it is not cached here).
 */
import { adminIdToken } from './adminAuth';

/** The sign-in was missing or refused (HTTP 401): sign in again. */
export class AuthError extends Error {
  constructor(message = 'Sign-in required') {
    super(message);
    this.name = 'AuthError';
  }
}

/**
 * A VALID account with no admin access (HTTP 403).
 *
 * Kept DISTINCT from AuthError -- same reasoning as remoteKitStore's
 * ForbiddenError. `noAdminAccess` is true only for the ONE 403 that means
 * "this account holds no admin access at all" (the server marks it with
 * admin_auth.NO_ADMIN_ACCESS_PREFIX, a machine-readable prefix rather than
 * prose this client string-matches against a moving target), so the gate can
 * route it to the explicit not-authorized screen rather than an ordinary
 * in-app refusal.
 */
export class ForbiddenError extends Error {
  readonly noAdminAccess: boolean;

  constructor(message = 'This account does not have admin console access',
              noAdminAccess = false) {
    super(message);
    this.name = 'ForbiddenError';
    this.noAdminAccess = noAdminAccess;
  }
}

/** Mirrors admin_backend/services/admin_auth.py's NO_ADMIN_ACCESS_PREFIX. */
const NO_ADMIN_ACCESS_PREFIX = 'NO_ADMIN_ACCESS:';

/** Build a ForbiddenError from a 403's detail, classifying it and stripping
 * the wire marker. Mirrors remoteKitStore.forbiddenFromDetail. */
export function forbiddenFromDetail(detail: string): ForbiddenError {
  const evicting = detail.startsWith(NO_ADMIN_ACCESS_PREFIX);
  return new ForbiddenError(
    evicting ? detail.slice(NO_ADMIN_ACCESS_PREFIX.length).trim() : detail,
    evicting,
  );
}

/** The admin service's base URL. Set at build time by deploy-admin-console.sh
 * (mirroring deploy-editor.sh's live VITE_API_BASE_URL resolution) or by
 * .env.hosted's committed fallback; empty string in local dev falls through
 * to same-origin, which only works when a dev proxy is set up -- local
 * console development instead sets VITE_ADMIN_API_BASE_URL directly (see
 * README-equivalent guidance in the vite.config.ts server block). */
export function apiBaseUrl(): string {
  return (import.meta.env.VITE_ADMIN_API_BASE_URL as string | undefined) ?? '';
}

/** Every admin API call, carrying the signed-in person's identity. */
async function adminFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await adminIdToken();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${apiBaseUrl()}${path}`, { ...init, headers });
  if (res.status === 401) throw new AuthError();
  if (res.status === 403) {
    throw forbiddenFromDetail(await errorDetail(
      res, 'This account does not have admin console access'));
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

/** GET /admin/whoami's shape (admin_backend/routes/whoami.py). */
export interface WhoAmI {
  uid: string;
  email: string | null;
}

/** Confirm the signed-in person has admin access, and learn who the server
 * thinks they are. AuthError on a refused token, ForbiddenError on a real
 * account with no app_admin claim. */
export async function probeWhoAmI(): Promise<WhoAmI> {
  const res = await adminFetch('/admin/whoami');
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not check your access'));
  return (await res.json()) as WhoAmI;
}

/** One row from GET /admin/audit's `rows` array (admin_backend/services/
 * audit_log.py's stored shape, plus the doc_id the route adds). Left loose
 * (not enumerating every field) because the audit log's schema is owned by
 * audit_log.py, not this client -- the list page renders whatever it gets. */
export interface AuditRow {
  doc_id: string;
  ts?: number;
  action?: string;
  actor_uid?: string;
  actor_email?: string;
  target?: string;
  channel?: string;
  state?: string;
  before?: unknown;
  after?: unknown;
  request_id?: string;
  [key: string]: unknown;
}

/** GET /admin/audit's response shape. */
export interface AuditPage {
  rows: AuditRow[];
  next_cursor: string | null;
}

/** Optional equality filters GET /admin/audit accepts (admin_backend/routes/
 * audit_routes.py). */
export interface AuditFilters {
  action?: string;
  actor_uid?: string;
  channel?: string;
  state?: string;
  limit?: number;
  cursor?: string;
}

/** One page of audit rows, newest first. */
export async function listAuditRows(filters: AuditFilters = {}): Promise<AuditPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  const qs = params.toString();
  const res = await adminFetch(`/admin/audit${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the audit log'));
  return (await res.json()) as AuditPage;
}

/** GET /admin/config/{channel}'s response shape (admin_backend/routes/
 * config_routes.py). */
export interface ChannelConfig {
  channel: string;
  values: Record<string, unknown>;
  known_keys: string[];
  unknown_keys: string[];
}

/** The channel's stored runtime-config doc, raw (not coerced). */
export async function getChannelConfig(channel: string): Promise<ChannelConfig> {
  const res = await adminFetch(`/admin/config/${encodeURIComponent(channel)}`);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the channel config'));
  return (await res.json()) as ChannelConfig;
}

/** PUT /admin/config/{channel}'s response shape. */
export interface ConfigSetResult {
  channel: string;
  key: string;
  before: unknown;
  after: unknown;
  request_id: string;
}

/** Set ONE runtime-config key for ONE channel. The server audits this write
 * in the same Firestore transaction as the config change -- see
 * config_routes.py's docstring. */
export async function setChannelConfigKey(
  channel: string, key: string, value: unknown,
): Promise<ConfigSetResult> {
  const res = await adminFetch(`/admin/config/${encodeURIComponent(channel)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not save the config change'));
  return (await res.json()) as ConfigSetResult;
}

/** One row from GET /admin/users' `users` array (admin_backend/services/
 * user_admin.py's `_user_row` -- an explicit key allowlist, not a claims
 * dump). `firm_role`/`schema_editor_role`/`vff_dev` ride along READ-ONLY:
 * this console can only ever WRITE firm_id + firm_role (the allowlist lives
 * server-side in user_admin.WRITABLE_CLAIMS), so nothing here implies those
 * other fields are editable. */
export interface AdminUserRow {
  uid: string;
  email: string | null;
  display_name: string | null;
  disabled: boolean;
  firm_id: string | null;
  firm_role: string | null;
  schema_editor_role?: string | null;
  vff_dev?: boolean;
}

/** GET /admin/users' response shape. */
export interface UsersPage {
  firm_id: string;
  users: AdminUserRow[];
  truncated: boolean;
}

/** The valid `firm_role` values (admin_backend/services/user_admin.py's
 * FIRM_ROLES) -- mirrored here as a wire contract, not re-derived, since the
 * console sends these strings on create and on a role change. */
export const FIRM_ROLES = ['manager', 'employee'] as const;
export type FirmRole = (typeof FIRM_ROLES)[number];

/** The firm's staff pool. `firmId` is required by THIS client -- the console
 * currently only supports the app-admin sign-in path (whoami's gate is
 * strict require_app_admin, not the composite gate), and an app admin must
 * always name a firm (admin_auth.resolve_target_firm: omitting it is a 422,
 * never a guessed default). A firm-manager mode with no selector is a later
 * bead's concern once the console itself supports signing in as one. */
export async function listUsers(firmId: string): Promise<UsersPage> {
  const res = await adminFetch(`/admin/users?firm_id=${encodeURIComponent(firmId)}`);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the user list'));
  return (await res.json()) as UsersPage;
}

/** POST /admin/users' response shape. NO password field exists anywhere on
 * this type -- create_staff_user never returns one (an unguessable random
 * password that nobody, including this console, ever sees), so there is
 * nothing here for a careless render to leak. */
export interface CreateUserResult {
  uid: string;
  email: string;
  firm_id: string;
  firm_role: string;
  reset_link: string | null;
  request_id: string;
}

export interface CreateUserRequest {
  email: string;
  firmRole: FirmRole;
  firmId: string;
  displayName?: string;
}

/** Create a staff account. Returns the password-RESET LINK for the console
 * to display (with a copy button) -- no outbound email in this epic, and no
 * password is ever transmitted (see user_admin.create_staff_user's
 * docstring: the account's real password is an unguessable random value
 * nobody, including this console, ever learns). */
export async function createUser(req: CreateUserRequest): Promise<CreateUserResult> {
  const res = await adminFetch('/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: req.email,
      firm_role: req.firmRole,
      firm_id: req.firmId,
      display_name: req.displayName || undefined,
    }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not create the account'));
  return (await res.json()) as CreateUserResult;
}

/** PATCH /admin/users/{uid}/disable's response shape. */
export interface SetUserDisabledResult {
  uid: string;
  disabled: boolean;
  firm_id: string;
  request_id: string;
}

/** Disable or re-enable a staff account. `disabled` is explicit (never a
 * toggle) so a retried call is idempotent -- see user_routes.py's
 * DisableUserRequest docstring. */
export async function setUserDisabled(
  uid: string, firmId: string, disabled: boolean,
): Promise<SetUserDisabledResult> {
  const res = await adminFetch(`/admin/users/${encodeURIComponent(uid)}/disable`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ disabled, firm_id: firmId }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the account'));
  return (await res.json()) as SetUserDisabledResult;
}

/** PATCH /admin/users/{uid}/role's response shape. */
export interface SetUserRoleResult {
  uid: string;
  firm_id: string;
  firm_role: string;
  before_role: string | null;
  request_id: string;
}

/** Move a staff account between manager and employee. */
export async function setUserRole(
  uid: string, firmId: string, firmRole: FirmRole,
): Promise<SetUserRoleResult> {
  const res = await adminFetch(`/admin/users/${encodeURIComponent(uid)}/role`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ firm_role: firmRole, firm_id: firmId }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the account'));
  return (await res.json()) as SetUserRoleResult;
}

/** One kit's resolved commercial, from either GET /admin/kits' `kits` array
 * or GET /admin/kits/{kit_id}/commercial (admin_backend/routes/
 * kit_routes.py) -- both spread `kit_commercials.resolve_commercial`'s
 * return value, `{credit_cost, cap_usd, source}`, plus the route-added
 * `kit_id`. `source` is "kit" when a commercial doc exists for this kit,
 * "default" when it does not and the kit is riding the global fallback
 * (kit_commercials.DEFAULT_CREDIT_COST / link_budget's default ceiling).
 *
 * NOTE ON THE FIELD NAME: this is deliberately `cap_usd`, not
 * `burn_cap_usd` -- resolve_commercial's own vocabulary (bead A3), which
 * kit_routes.py's GET routes pass straight through unrenamed. The PUT
 * route's REQUEST body spells the same value `burn_cap_usd` (see
 * KitCommercialPutRequest below) because that is the stored doc's own key;
 * this client keeps both spellings distinct rather than picking one and
 * translating, mirroring the route module's own docstring on why the two
 * names coexist.
 *
 * NO `updated_by` HERE: kit_commercials.resolve_commercial's return value
 * does not carry it (only the raw Firestore doc does, which neither GET
 * route echoes) -- so this page cannot show who last edited a kit's
 * pricing without a wire change on the READ side, which is out of this
 * bead's scope (Surfaces lists only adminApi.ts + the page + the tab, not
 * kit_routes.py).
 */
export interface KitCommercial {
  kit_id: string;
  credit_cost: number;
  cap_usd: number;
  source: 'kit' | 'default';
}

/** GET /admin/kits' response shape. */
export interface KitsPage {
  kits: KitCommercial[];
}

/** Every kit in the form-kit store, each joined with its resolved
 * commercial doc or the global defaults -- the same list the mint path's
 * pricing can never disagree with (kit_routes.py's list_kits docstring). */
export async function listKits(): Promise<KitsPage> {
  const res = await adminFetch('/admin/kits');
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the kit list'));
  return (await res.json()) as KitsPage;
}

/** One kit's resolved commercial (GET /admin/kits/{kit_id}/commercial). */
export async function getKitCommercial(kitId: string): Promise<KitCommercial> {
  const res = await adminFetch(`/admin/kits/${encodeURIComponent(kitId)}/commercial`);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load this kit\'s pricing'));
  return (await res.json()) as KitCommercial;
}

/** PUT /admin/kits/{kit_id}/commercial's request body. All three fields are
 * REQUIRED on the wire (kit_routes.py's KitCommercialPutRequest docstring:
 * a PUT replaces the whole commercial doc, so a partial update that
 * silently kept a stale ceiling from a previous edit is exactly the failure
 * mode the per-kit ceiling rule exists to prevent) -- `display` defaults to
 * an empty object here rather than being left optional on this client, so
 * a caller can never accidentally send a partial body. */
export interface SetKitCommercialRequest {
  creditCost: number;
  burnCapUsd: number;
  display?: Record<string, string>;
}

/** PUT /admin/kits/{kit_id}/commercial's response shape. Echoes the just-
 * validated value under BOTH `burn_cap_usd` (this request's own field name)
 * and `cap_usd` (what the GET routes call the identical number) -- see
 * kit_routes.py's put_kit_commercial docstring for why both names ride
 * along on the same float rather than one being derived from the other. */
export interface SetKitCommercialResult {
  kit_id: string;
  credit_cost: number;
  burn_cap_usd: number;
  cap_usd: number;
  display: Record<string, string>;
  before: unknown;
  request_id: string;
}

/** Set a kit's commercial doc. The server validates BEFORE any write
 * (credit_cost a positive int, burn_cap_usd a positive finite float, both
 * refusing a stray bool/NaN/+-inf) and returns 422 on a bad value with no
 * write and no audit row -- this client does not pre-validate and swallow
 * that response, it surfaces the server's own detail message so the page's
 * field-level error always matches the rule the route actually enforces. */
export async function setKitCommercial(
  kitId: string, req: SetKitCommercialRequest,
): Promise<SetKitCommercialResult> {
  const res = await adminFetch(`/admin/kits/${encodeURIComponent(kitId)}/commercial`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      credit_cost: req.creditCost,
      burn_cap_usd: req.burnCapUsd,
      display: req.display ?? {},
    }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not save this kit\'s pricing'));
  return (await res.json()) as SetKitCommercialResult;
}
