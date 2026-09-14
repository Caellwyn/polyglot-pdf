/**
 * Client for the admin service's routes this console consumes (bd
 * polyglot-pdf-b6943, extended by polyglot-pdf-z4y91 for users,
 * polyglot-pdf-mzblw for kit commercials, and polyglot-pdf-r8z9g for
 * firms/credits/links): GET /admin/whoami, GET /admin/audit,
 * GET+PUT /admin/config/{channel}, the four staff-account routes, kit
 * commercial list/get/set, firm CRUD, credit grant/adjust, and link
 * listing/revoke.
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
 * return value, `{credit_cost, cap_usd, source, display}`, plus the
 * route-added `kit_id`. `source` is "kit" when a commercial doc exists for
 * this kit, "default" when it does not and the kit is riding the global
 * fallback (kit_commercials.DEFAULT_CREDIT_COST / link_budget's default
 * ceiling).
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
 * `display` (bd polyglot-pdf-zcbm1): the kit's stored console label map, or
 * `{}` when the kit has no commercial doc or no display value set --
 * resolve_commercial's own default, not something this client invents.
 * KitCommercialsPage.tsx reads this on Edit and echoes it back on Save so a
 * price edit can never silently wipe a label `scripts/seed_kit_commercials.py`
 * or a previous save set.
 *
 * NO `updated_by` HERE: kit_commercials.resolve_commercial's return value
 * does not carry it (only the raw Firestore doc does, which neither GET
 * route echoes) -- so a console page cannot show who last edited a kit's
 * pricing without a further wire change. Out of this bead's scope.
 */
export interface KitCommercial {
  kit_id: string;
  credit_cost: number;
  cap_usd: number;
  source: 'kit' | 'default';
  display: Record<string, string>;
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

// ---------------------------------------------------------------------------
// Firms, credits and links (bd polyglot-pdf-r8z9g, Epic 2 Track C bead C2),
// driving admin_backend/routes/firm_routes.py, credit_routes.py and
// link_routes.py.
// ---------------------------------------------------------------------------

/** The two firm kinds (backend/services/firms.py's FIRM_KIND_MOCK /
 * FIRM_KIND_LIVE) -- mirrored here as a wire contract, not re-derived,
 * since create/kind-change send these strings. */
export const FIRM_KINDS = ['mock', 'live'] as const;
export type FirmKind = (typeof FIRM_KINDS)[number];

/** The closed list of plan tiers (backend/services/plans.py::PLAN_TIERS,
 * bd polyglot-pdf-0euzk). Today: exactly one -- a second tier is a
 * maintainer-approved addition to that Python tuple, mirrored here. */
export const PLAN_TIERS = ["starter"] as const;
export type PlanTier = (typeof PLAN_TIERS)[number];

/** A firm's plan: tier, monthly credit allotment, and whether the
 * monthly top-up ADDS to the balance (rollover) or brings it UP TO the cap
 * (no rollover) -- backend/services/plans.py's doc shape, verbatim. */
export interface FirmPlan {
  tier: PlanTier;
  monthly_credits: number;
  rollover: boolean;
}

/** The maintainer's 2026-09-14 starting numbers
 * (backend/services/plans.py::DEFAULT_PLAN) -- what GET /admin/firms/
 * {firm_id} and GET /admin/firms both return for a firm with no plan of
 * its own yet (firm_routes.py's _public_firm_view fallback). */
export const DEFAULT_PLAN: FirmPlan = {
  tier: "starter", monthly_credits: 35, rollover: false,
};

/** The two firm statuses (backend/services/firms.py's FIRM_STATUS_ACTIVE /
 * FIRM_STATUS_SUSPENDED). */
export const FIRM_STATUSES = ['active', 'suspended'] as const;
export type FirmStatus = (typeof FIRM_STATUSES)[number];

/** One row from GET /admin/firms' `firms` array
 * (firm_routes.py's _public_firm_view -- an explicit key allowlist). */
export interface FirmRow {
  firm_id: string;
  name: string | null;
  contact_email: string | null;
  kind: FirmKind;
  status: FirmStatus | null;
  allowed_kits: string[];
  balance_credits: number;
  plan: FirmPlan;
}

/** GET /admin/firms' response shape. A read, so no audit row. */
export async function listFirms(): Promise<FirmRow[]> {
  const res = await adminFetch('/admin/firms');
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the firm list'));
  const body = (await res.json()) as { firms: FirmRow[] };
  return body.firms;
}

export interface CreateFirmRequest {
  firmId: string;
  name: string;
  contactEmail: string;
  kind: FirmKind;
  allowedKits?: string[];
  status?: FirmStatus;
}

/** POST /admin/firms' response shape. */
export interface CreateFirmResult {
  firm_id: string;
  created: boolean;
  request_id: string;
}

/** Create a firm. `kind` is REQUIRED by the route (422 if omitted) -- this
 * client's own CreateFirmRequest makes it a required field too, so a caller
 * cannot construct a request that would 422 server-side. */
export async function createFirm(req: CreateFirmRequest): Promise<CreateFirmResult> {
  const res = await adminFetch('/admin/firms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      firm_id: req.firmId,
      name: req.name,
      contact_email: req.contactEmail,
      kind: req.kind,
      allowed_kits: req.allowedKits ?? [],
      status: req.status ?? 'active',
    }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not create the firm'));
  return (await res.json()) as CreateFirmResult;
}

/** One row from GET /admin/firms/{firm_id}'s `ledger` array
 * (backend/services/credit_ledger.py's stored entry shape -- read_entries()
 * returns the persisted document verbatim and does NOT attach doc_id, unlike
 * the grant/adjust routes' GrantCreditsResult/AdjustCreditsResult or the
 * sibling audit_routes.py list route, so doc_id is optional here and MUST
 * NOT be relied on as a stable identity; see polyglot-pdf-migp9). */
export interface LedgerEntry {
  doc_id?: string;
  type: string;
  amount: number;
  usd_amount: number | null;
  firm_kind: FirmKind;
  channel: string | null;
  balance_after: number;
  actor: string;
  reason: string | null;
  link_jti: string | null;
  kit_id: string | null;
  ts: number;
}

/** GET /admin/firms/{firm_id}'s response shape: profile, balance, and a
 * page of ledger rows (newest first). */
export interface FirmDetail {
  firm_id: string;
  name: string | null;
  contact_email: string | null;
  kind: FirmKind;
  status: FirmStatus | null;
  allowed_kits: string[];
  balance_credits: number;
  plan: FirmPlan;
  ledger: LedgerEntry[];
  ledger_truncated: boolean;
}

/** One firm's profile, balance, and a page of ledger rows. `ledgerLimit`
 * mirrors the route's own `ledger_limit` query param (1-200, default 50). */
export async function getFirm(firmId: string, ledgerLimit?: number): Promise<FirmDetail> {
  const qs = ledgerLimit !== undefined ? `?ledger_limit=${ledgerLimit}` : '';
  const res = await adminFetch(`/admin/firms/${encodeURIComponent(firmId)}${qs}`);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the firm'));
  return (await res.json()) as FirmDetail;
}

/** PATCH /admin/firms/{firm_id}/status's response shape. */
export interface SetFirmStatusResult {
  firm_id: string;
  status: FirmStatus;
  before_status: FirmStatus | null;
  request_id: string;
}

/** Set a firm's status (active/suspended). */
export async function setFirmStatus(
  firmId: string, status: FirmStatus,
): Promise<SetFirmStatusResult> {
  const res = await adminFetch(`/admin/firms/${encodeURIComponent(firmId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the firm status'));
  return (await res.json()) as SetFirmStatusResult;
}

/** PATCH /admin/firms/{firm_id}/allowed_kits's response shape. */
export interface SetFirmAllowedKitsResult {
  firm_id: string;
  allowed_kits: string[];
  request_id: string;
}

/** Replace a firm's private-kit allowlist (full replace, not a merge). */
export async function setFirmAllowedKits(
  firmId: string, allowedKits: string[],
): Promise<SetFirmAllowedKitsResult> {
  const res = await adminFetch(`/admin/firms/${encodeURIComponent(firmId)}/allowed_kits`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ allowed_kits: allowedKits }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the allowed kits'));
  return (await res.json()) as SetFirmAllowedKitsResult;
}

/** PATCH /admin/firms/{firm_id}/kind's response shape. */
export interface SetFirmKindResult {
  firm_id: string;
  kind: FirmKind;
  before_kind: FirmKind | null;
  request_id: string;
}

/** Reclassify a firm mock<->live. `reason` is REQUIRED by the route (422 if
 * blank) -- the confirm-twice control is this console's OWN job
 * (firm_routes.py's SetKindRequest docstring: "a route cannot see how many
 * times a human clicked"), enforced in FirmDetailPage before this function
 * is ever called. */
export async function setFirmKind(
  firmId: string, kind: FirmKind, reason: string,
): Promise<SetFirmKindResult> {
  const res = await adminFetch(`/admin/firms/${encodeURIComponent(firmId)}/kind`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind, reason }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not change the firm kind'));
  return (await res.json()) as SetFirmKindResult;
}

/** PATCH /admin/firms/{firm_id}/plan's response shape. */
export interface SetFirmPlanResult {
  firm_id: string;
  plan: FirmPlan;
  before_plan: FirmPlan | null;
  request_id: string;
}

/** Set a firm's plan (tier, monthly_credits, rollover). No confirm-twice
 * here, unlike setFirmKind -- a plan change only affects a monthly top-up
 * amount, not minting eligibility, so one Save is enough (bd
 * polyglot-pdf-0euzk exit criterion 3: "one write per save"). The route's
 * own 422s (unknown tier, non-positive monthly_credits) are the source of
 * truth this function trusts for anything the caller's own form did not
 * already catch. */
export async function setFirmPlan(
  firmId: string, plan: FirmPlan,
): Promise<SetFirmPlanResult> {
  const res = await adminFetch(`/admin/firms/${encodeURIComponent(firmId)}/plan`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(plan),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the firm plan'));
  return (await res.json()) as SetFirmPlanResult;
}

/** The three grant-shaped ledger entry types (credit_routes.py's
 * GRANT_TYPES) -- adjustment is deliberately excluded, matching the route
 * split: grant() below can never send the signed operator escape hatch. */
export const GRANT_TYPES = ['subscription_grant', 'purchase', 'promo_grant'] as const;
export type GrantType = (typeof GRANT_TYPES)[number];

/** The two income types that carry a real dollar price
 * (credit_routes.py's _USD_REQUIRED_GRANT_TYPES) -- usd_amount is shown
 * ONLY for these two on the grant form (bead exit criterion 1). */
export const USD_REQUIRED_GRANT_TYPES: readonly GrantType[] = ['subscription_grant', 'purchase'];

export interface GrantCreditsRequest {
  type: GrantType;
  amount: number;
  usdAmount?: number;
  kitId?: string;
}

/** POST /admin/firms/{firm_id}/credits/grant's response shape
 * (backend/services/credit_ledger.py::append_entry's return, spread with
 * request_id). */
export interface GrantCreditsResult {
  doc_id: string;
  firm_id: string;
  type: GrantType;
  amount: number;
  usd_amount: number | null;
  balance_credits: number;
  request_id: string;
}

/** Grant credits to a firm. `usdAmount` is sent ONLY when the caller
 * supplies it -- the route itself REFUSES a usd_amount on promo_grant
 * (422), so this client does not default one in for that type. */
export async function grantCredits(
  firmId: string, req: GrantCreditsRequest,
): Promise<GrantCreditsResult> {
  const res = await adminFetch(`/admin/firms/${encodeURIComponent(firmId)}/credits/grant`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: req.type,
      amount: req.amount,
      usd_amount: req.usdAmount ?? undefined,
      kit_id: req.kitId || undefined,
    }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not grant credits'));
  return (await res.json()) as GrantCreditsResult;
}

export interface AdjustCreditsRequest {
  amount: number;
  reason: string;
}

/** POST /admin/firms/{firm_id}/credits/adjust's response shape. */
export interface AdjustCreditsResult {
  doc_id: string;
  firm_id: string;
  type: 'adjustment';
  amount: number;
  balance_credits: number;
  request_id: string;
}

/** The operator's signed adjustment. `reason` is REQUIRED by the route
 * (422 if blank); `amount` may be either sign. */
export async function adjustCredits(
  firmId: string, req: AdjustCreditsRequest,
): Promise<AdjustCreditsResult> {
  const res = await adminFetch(`/admin/firms/${encodeURIComponent(firmId)}/credits/adjust`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount: req.amount, reason: req.reason }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not adjust credits'));
  return (await res.json()) as AdjustCreditsResult;
}

/** The two channels the admin service knows about
 * (admin_backend/routes/link_routes.py's KNOWN_CHANNELS) -- link routes take
 * `channel` as a REQUIRED explicit query param (never derived), since a
 * link record lives in exactly one channel's collection. */
export const LINK_CHANNELS = ['demo', 'staging'] as const;
export type LinkChannel = (typeof LINK_CHANNELS)[number];

/** One row from GET /admin/firms/{firm_id}/links' `links` array
 * (link_routes.py's _ALLOWLISTED_KEYS join). */
export interface LinkRow {
  jti: string;
  kit_id: string | null;
  employee_id: string | null;
  status: string | null;
  minted_at: number | null;
  open_deadline: number | null;
  opened_at: number | null;
  completed_at: number | null;
  spend_usd: number | null;
  turns: number | null;
  cap_usd: number | null;
  credit_cost: number | null;
}

export interface ListFirmLinksFilters {
  status?: string;
  employeeId?: string;
}

/** GET /admin/firms/{firm_id}/links's response shape. */
export interface FirmLinksPage {
  firm_id: string;
  channel: LinkChannel;
  links: LinkRow[];
}

/** A firm's links, joined with their redemption detail. `channel` is
 * REQUIRED (mirrors the route's own 422-on-missing rule). */
export async function listFirmLinks(
  firmId: string, channel: LinkChannel, filters: ListFirmLinksFilters = {},
): Promise<FirmLinksPage> {
  const params = new URLSearchParams({ channel });
  if (filters.status) params.set('status', filters.status);
  if (filters.employeeId) params.set('employee_id', filters.employeeId);
  const res = await adminFetch(
    `/admin/firms/${encodeURIComponent(firmId)}/links?${params.toString()}`,
  );
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the firm links'));
  return (await res.json()) as FirmLinksPage;
}

/** POST /admin/links/{jti}/revoke's response shape. */
export interface RevokeLinkResult {
  jti: string;
  channel: LinkChannel;
  status: 'revoked';
  before_status: string;
  revoked_at: number;
  request_id: string;
}

/** Revoke a minted link. Only a `minted` link may be revoked (409
 * otherwise, naming the current status -- surfaced via errorDetail like
 * every other route's refusal). */
export async function revokeLink(
  jti: string, channel: LinkChannel,
): Promise<RevokeLinkResult> {
  const params = new URLSearchParams({ channel });
  const res = await adminFetch(`/admin/links/${encodeURIComponent(jti)}/revoke?${params.toString()}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not revoke the link'));
  return (await res.json()) as RevokeLinkResult;
}

// ---------------------------------------------------------------------------
// Monitoring (bd polyglot-pdf-i6dlb, E3.11b), driving admin_backend/routes/
// ops_routes.py, usage_routes.py, report_routes.py and alert_routes.py --
// health, per-firm usage rollups, BigQuery cost/income reports, and alerts.
// ---------------------------------------------------------------------------

/** The two channels every monitoring route below takes (ops_routes.py's /
 * usage_routes.py's / report_routes.py's own KNOWN_CHANNELS, restated here
 * as a wire contract like LINK_CHANNELS above). */
export const MONITORING_CHANNELS = ['demo', 'staging'] as const;
export type MonitoringChannel = (typeof MONITORING_CHANNELS)[number];

/** One channel's backend probe, from GET /admin/health's `backend` key
 * (ops_routes.py's `_fetch_backend_probe` / the `configured: false`
 * shortcut). `configured: false` means BACKEND_URLS_JSON has no entry for
 * this channel (nobody has wired it yet); `configured: true, reachable:
 * false` means the URL exists but the HTTP calls themselves failed --
 * these are DELIBERATELY DISTINCT states (module docstring), so a page
 * reading this must render them differently rather than collapsing both
 * into one generic "down" card. */
export interface BackendHealthProbe {
  configured: boolean;
  reachable: boolean;
  health: Record<string, unknown> | null;
  version: Record<string, unknown> | null;
}

/** The admin service's OWN version block on every /admin/health response --
 * a plain in-process read, never a second HTTP hop (module docstring). */
export interface AdminServiceVersion {
  version: string;
  git_sha: string;
  app_module: string;
}

/** GET /admin/health's response shape. */
export interface ChannelHealth {
  channel: MonitoringChannel;
  backend: BackendHealthProbe;
  admin_service: AdminServiceVersion;
}

/** One channel's health: the public backend's own /health + /version (or
 * an unconfigured/unreachable state, never a 500) plus the admin service's
 * own version. The channel query param is REQUIRED by the route. */
export async function getChannelHealth(channel: MonitoringChannel): Promise<ChannelHealth> {
  const res = await adminFetch('/admin/health?channel=' + encodeURIComponent(channel));
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load channel health'));
  return (await res.json()) as ChannelHealth;
}

/** One error group from GET /admin/errors' `groups` array
 * (error_stats.py's `_public_group_view` -- count, first/last seen, and
 * the group's TYPE and top FRAME only; no message body ever rides along,
 * per the P0 PII rule this route's own module docstring explains). */
export interface ErrorGroup {
  group_id: string | null;
  count: number;
  first_seen_time: string | null;
  last_seen_time: string | null;
  error_type: string | null;
  top_frame: {
    file_path: string | null;
    line_number: number | null;
    function_name: string | null;
  };
}

/** GET /admin/errors' response shape. */
export interface ChannelErrors {
  channel: MonitoringChannel;
  service: string;
  groups: ErrorGroup[];
}

/** One channel's Error Reporting group stats (a week's window,
 * error_stats.py's own `_fetch_group_stats`). The channel query param is
 * REQUIRED. */
export async function getChannelErrors(channel: MonitoringChannel): Promise<ChannelErrors> {
  const res = await adminFetch('/admin/errors?channel=' + encodeURIComponent(channel));
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load channel errors'));
  return (await res.json()) as ChannelErrors;
}

/** A firm-month usage rollup's allowlisted fields (usage_routes.py's
 * `_FIRM_USAGE_KEYS`) -- by_kit/by_employee/by_language are passed through
 * as stored maps, keyed by kit id / uid / language code respectively, each
 * value itself `{sessions, cost_usd}`-shaped (usage_rollups.py's own
 * increments), read here as loosely-typed records since this client does
 * not interpret them further. */
export interface FirmUsageRollup {
  connections_ended: number | null;
  sessions_completed: number | null;
  cost_usd_total: number | null;
  links_opened: number | null;
  links_completed: number | null;
  by_kit: Record<string, { sessions?: number; cost_usd?: number }> | null;
  by_employee: Record<string, { sessions?: number; cost_usd?: number }> | null;
  by_language: Record<string, { sessions?: number; cost_usd?: number }> | null;
  kind: string | null;
  channel: string | null;
}

/** GET /admin/firms/{firm_id}/usage's response shape. `usage` has every key
 * null for a month with no rollup doc yet -- usage_routes.py's own "a
 * missing doc is an empty reading, not a 404" rule -- so a page must treat
 * an all-null `usage` as "no data this month", not as an error. */
export interface FirmUsagePage {
  firm_id: string;
  month: string;
  channel: MonitoringChannel;
  usage: FirmUsageRollup;
}

/** This firm's usage rollup for one month. `month` and `channel` are BOTH
 * REQUIRED by the route (422 if missing/malformed). */
export async function getFirmUsage(
  firmId: string, month: string, channel: MonitoringChannel,
): Promise<FirmUsagePage> {
  const params = new URLSearchParams({ month, channel });
  const res = await adminFetch(
    '/admin/firms/' + encodeURIComponent(firmId) + '/usage?' + params.toString(),
  );
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the firm usage'));
  return (await res.json()) as FirmUsagePage;
}

/** The three `group_by` values the cost report accepts
 * (bigquery_reports.COST_VIEWS's own key set, mirrored here as a wire
 * contract). */
export const COST_GROUP_BY = ['firm', 'kit', 'employee'] as const;
export type CostGroupBy = (typeof COST_GROUP_BY)[number];

/** One row from GET /admin/reports/cost's `rows` array
 * (bigquery_reports.query_cost_report's SELECT list: month, the group
 * column -- firm_id/kit_id/employee_id depending on `group_by` -- channel,
 * usage_kind, call_count, cost_usd). The group column's NAME varies by
 * `group_by`, so this client reads it generically rather than typing three
 * near-identical row shapes; callers select it with the same `group_by`
 * value they requested.
 *
 * cost_usd IS NULLABLE. sql/telemetry_views.sql computes it as
 * SUM(SAFE_CAST(...cost_estimate_usd AS FLOAT64)) with no COALESCE --
 * BigQuery's SUM returns NULL (not 0) for a group whose inputs are all
 * NULL or fail the cast, which happens whenever a cost-bearing event lands
 * without a cost_estimate_usd in its metadata; the row still exists
 * because COUNT(*) does not depend on that column. CostReportsPage.tsx's
 * formatUsd renders this as "--", never assume it can call .toFixed()
 * directly. */
export interface CostReportRow {
  month: string;
  channel: string | null;
  usage_kind: string | null;
  call_count: number;
  cost_usd: number | null;
  firm_id?: string;
  kit_id?: string;
  employee_id?: string;
  [key: string]: unknown;
}

/** GET /admin/reports/cost's response shape. `delayed`/`note` are ALWAYS
 * present (BigQuery sink lag, report_routes.py's own DELAYED_NOTE) -- a
 * page must show this note whenever `delayed` is true, never assume it is
 * always true without reading the flag (report_routes.py's docstring
 * frames this as a bead requirement, not a hard-coded constant this client
 * should re-derive). */
export interface CostReportPage {
  group_by: CostGroupBy;
  from: string;
  to: string;
  channel: MonitoringChannel | null;
  rows: CostReportRow[];
  delayed: boolean;
  note: string;
}

export interface CostReportFilters {
  channel?: MonitoringChannel;
}

/** The inclusive month-span ceiling the server enforces
 * (report_routes.py's `_MAX_RANGE_MONTHS`), mirrored here as a wire
 * contract so this client's own client-side backstop (CostReportsPage.tsx)
 * refuses the SAME range the server would 422 on, without a round trip. */
export const MAX_REPORT_RANGE_MONTHS = 12;

/** Cost rows grouped by firm/kit/employee over [from, to] (both "YYYY-MM",
 * inclusive). `from`/`to`/`group_by` are all REQUIRED by the route; the
 * route itself 422s a range wider than 12 months (report_routes.py's
 * `_validated_range`) -- this client does not silently swallow that
 * refusal: see CostReportsPage.tsx for the client-side backstop that
 * mirrors it ahead of the network call, and errorDetail surfacing the
 * server's own 422 text for anything that check misses. */
export async function getCostReport(
  groupBy: CostGroupBy, from: string, to: string, filters: CostReportFilters = {},
): Promise<CostReportPage> {
  const params = new URLSearchParams({ group_by: groupBy, from, to });
  if (filters.channel) params.set('channel', filters.channel);
  const res = await adminFetch('/admin/reports/cost?' + params.toString());
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the cost report'));
  return (await res.json()) as CostReportPage;
}

/** One row from GET /admin/reports/income's `rows` array
 * (bigquery_reports.query_income_report's SELECT list). `channel` is
 * always null on every row (income_month's own view definition -- the
 * admin service that writes grants has no channel of its own), kept here
 * only because the wire row carries the column. */
export interface IncomeReportRow {
  month: string;
  entry_type: string;
  channel: null;
  entry_count: number;
  /** NULLABLE for the same reason CostReportRow.cost_usd is: income_month's
   * SUM(SAFE_CAST(jsonPayload.usd_amount AS FLOAT64)) has no COALESCE
   * either (sql/telemetry_views.sql), so an income-month group whose
   * entries all fail the cast returns NULL, not 0. */
  usd_amount: number | null;
}

/** GET /admin/reports/income's response shape. Same `delayed`/`note`
 * contract as the cost report. NO `channel` filter exists on this route
 * (income_month rows carry none -- report_routes.py's own
 * `_validated_income_channel` REFUSES one with a 422 rather than silently
 * returning zero rows), so this client's function accepts none either. */
export interface IncomeReportPage {
  from: string;
  to: string;
  rows: IncomeReportRow[];
  delayed: boolean;
  note: string;
}

/** Income rows (real firms only -- the view's own `firm_kind = 'live'`
 * filter) over [from, to] (both "YYYY-MM", inclusive). Both REQUIRED. */
export async function getIncomeReport(from: string, to: string): Promise<IncomeReportPage> {
  const params = new URLSearchParams({ from, to });
  const res = await adminFetch('/admin/reports/income?' + params.toString());
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the income report'));
  return (await res.json()) as IncomeReportPage;
}

/** The three alert `kind` values (backend/services/alerts.py's own
 * vocabulary, mirrored here as a wire contract). */
export const ALERT_KINDS = ['link_exhausted', 'credit_low', 'credit_exhausted'] as const;
export type AlertKind = (typeof ALERT_KINDS)[number];

/** The two alert `level` values (alerts.py's LEVEL_WARNING/LEVEL_CRITICAL). */
export const ALERT_LEVELS = ['warning', 'critical'] as const;
export type AlertLevel = (typeof ALERT_LEVELS)[number];

/** One row from GET /admin/alerts' `alerts` array (alert_routes.py's
 * `_public_alert_view`, built from alerts.ALERT_FIELDS plus the doc id --
 * an explicit key allowlist, never a raw doc spread). `acknowledged_by`/
 * `acknowledged_at` are both null until someone acknowledges it. */
export interface AlertRow {
  id: string;
  firm_id: string | null;
  kind: AlertKind;
  level: AlertLevel;
  ts: number | null;
  context: Record<string, unknown> | null;
  acknowledged_by: string | null;
  acknowledged_at: number | null;
  emailed_at: number | null;
  expire_at: unknown;
}

/** GET /admin/alerts' response shape. */
export interface AlertsPage {
  alerts: AlertRow[];
}

export interface ListAlertsFilters {
  acknowledged?: boolean;
  firmId?: string;
  kind?: AlertKind;
}

/** Alert docs, newest first, all THREE filters optional (`acknowledged`,
 * `firm_id`, `kind` -- alert_routes.py's own query params). */
export async function listAlerts(filters: ListAlertsFilters = {}): Promise<AlertsPage> {
  const params = new URLSearchParams();
  if (filters.acknowledged !== undefined) {
    params.set('acknowledged', String(filters.acknowledged));
  }
  if (filters.firmId) params.set('firm_id', filters.firmId);
  if (filters.kind) params.set('kind', filters.kind);
  const qs = params.toString();
  const res = await adminFetch('/admin/alerts' + (qs ? '?' + qs : ''));
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the alerts list'));
  return (await res.json()) as AlertsPage;
}

/** PATCH /admin/alerts/{id}/acknowledge's response shape. */
export interface AcknowledgeAlertResult {
  id: string;
  acknowledged_by: string;
  acknowledged_at: number;
  request_id: string;
}

/** Acknowledge one alert. A SECOND acknowledge on the same alert is a 409
 * (alert_routes.py's own transaction: "already acknowledged", naming who
 * got there first) -- surfaced via errorDetail like every other route's
 * refusal, so a caller sees the server's own message rather than a generic
 * one. This function makes exactly one PATCH call per invocation; callers
 * (AlertsPage.tsx) are responsible for not calling it twice per click. */
export async function acknowledgeAlert(alertId: string): Promise<AcknowledgeAlertResult> {
  const res = await adminFetch('/admin/alerts/' + encodeURIComponent(alertId) + '/acknowledge', {
    method: 'PATCH',
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not acknowledge the alert'));
  return (await res.json()) as AcknowledgeAlertResult;
}
