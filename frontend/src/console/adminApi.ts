/**
 * Client for the admin service's FIRM-SCOPED routes (bd polyglot-pdf-z4ljj,
 * Epic 2 Track C bead C0).
 *
 * A small, generic authenticated-fetch helper -- NOT a route-by-route client
 * like admin-console/src/utils/adminApi.ts (which is app-admin scoped and
 * ships every route it consumes). This one exists for C4 (employees) and C5
 * (link history) to build their OWN typed calls on: it owns the two things
 * every firm-scoped call needs and would otherwise duplicate --
 *
 *   1. The signed-in STAFF Firebase ID token as `Authorization: Bearer`,
 *      fetched PER REQUEST via resolveStaffToken (never cached client-side --
 *      an ID token expires in about an hour and the SDK refreshes it
 *      transparently, so caching one here would reintroduce a stale-
 *      credential 401 mid-session). resolveStaffToken, NOT
 *      resolveSessionToken: firm-console actions are staff-only, and the
 *      form-filling resolver's client-link-wins precedence would send the
 *      wrong credential the moment a staffer has tried one of their own
 *      links in the same tab (bd polyglot-pdf-so88g -- the exact bug
 *      MintLinkPage.tsx already works around this way).
 *   2. The `channel` query param every firm-scoped admin route requires
 *      (sprint_22_admin-console_plan.md "Architecture"): the admin service
 *      is ONE Cloud Run service backing BOTH channels' Firestore data and
 *      has no channel identity of its own, so the CALLER must say which
 *      channel's data it means. This build's own channel is
 *      config.ts's getAppChannel() -- resolved at DEPLOY time, not
 *      guessable at runtime.
 *
 * MIRRORS admin-console/src/utils/adminApi.ts's auth-error shape (AuthError /
 * ForbiddenError / errorDetail) against the SAME admin service, so a 401/403
 * means the same thing to a caller of either client. Deliberately duplicated
 * rather than imported -- admin-console/ and frontend/ do not import from
 * each other (same maintainer constraint documented on
 * admin-console/src/utils/adminAuth.ts: no new cross-surface dependencies to
 * unravel later).
 */
import { getAdminApiBaseUrl, getAppChannel } from '../shared/config';
import { resolveStaffToken } from '../shared/sessionCredential';

/** The sign-in was missing or refused (HTTP 401): sign in again. */
export class AuthError extends Error {
  constructor(message = 'Sign-in required') {
    super(message);
    this.name = 'AuthError';
  }
}

/** A signed-in account with no access to this firm-scoped route (HTTP 403). */
export class ForbiddenError extends Error {
  constructor(message = 'You do not have access to this') {
    super(message);
    this.name = 'ForbiddenError';
  }
}

/** The admin service's base URL, resolved at build time (see config.ts's
 * getAdminApiBaseUrl doc comment for the full resolution chain). */
export function adminApiBaseUrl(): string {
  return getAdminApiBaseUrl();
}

/** This build's own channel -- appended as `?channel=` to every firm-scoped
 * call below. See config.ts's getAppChannel doc comment for why this cannot
 * be derived at runtime and must come from a deploy-time env var. */
export function adminChannel(): string {
  return getAppChannel();
}

/** Append `channel=<this build's channel>` to a path's query string, keeping
 * any params the caller already put there. Exported so C4/C5 can build a
 * path with their OWN filters (e.g. `?employee_id=`) and still get the
 * channel param attached the same way every other call does. */
export function withChannel(path: string): string {
  const [base, query = ''] = path.split('?', 2);
  const params = new URLSearchParams(query);
  params.set('channel', adminChannel());
  return `${base}?${params.toString()}`;
}

/**
 * Every firm-scoped admin API call, carrying the signed-in staffer's
 * identity and this build's channel. `path` is channel-qualified
 * automatically via withChannel() -- callers pass the route's own path
 * (with any of their own query params already on it) and never add
 * `channel` themselves, so there is exactly one place that can get it wrong.
 */
export async function adminFetch(
  path: string,
  user: { getIdToken: () => Promise<string> } | null | undefined,
  init: RequestInit = {},
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  const token = await resolveStaffToken(user);
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetchImpl(`${adminApiBaseUrl()}${withChannel(path)}`, { ...init, headers });
  if (res.status === 401) throw new AuthError();
  if (res.status === 403) {
    throw new ForbiddenError(await errorDetail(res, 'You do not have access to this'));
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
