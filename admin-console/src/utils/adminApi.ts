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
