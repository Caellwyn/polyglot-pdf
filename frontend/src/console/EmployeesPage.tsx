/**
 * Firm-console employee management (bd polyglot-pdf-krbol, Epic 2 Track C
 * bead C4) -- a MANAGER'S OWN version of admin-console's UsersPage.tsx (bd
 * polyglot-pdf-z4y91), mounted in the MAIN APP instead of the admin console.
 *
 * THE FIRM NEVER COMES FROM THIS PAGE. admin-console's UsersPage always
 * shows a firm-ID field because every caller there is an app admin (the
 * console's sign-in gate checks the strict require_app_admin, never the
 * composite gate). This page is the OPPOSITE case: it is reached by a firm
 * manager's own staff sign-in, so admin_backend/services/admin_auth.py's
 * resolve_target_firm takes the firm from the manager's VERIFIED token and
 * refuses (403) any request that names one at all -- "the same value" is
 * not the test, "did you try to choose" is (see admin_auth.py's docstring).
 * So every request this page sends omits firm_id entirely: no `firm_id`
 * query param on the list call, no `firm_id` key in the create/disable/
 * role-change bodies. Sending `firm_id: undefined` is not enough on its own
 * -- JSON.stringify drops an `undefined` value, which is what actually keeps
 * the key off the wire; a stray `null` would still trip the gate's `is not
 * None` check the same way a real value would.
 *
 * MANAGER-ONLY, BUT ONLY AS UX. The route this page is mounted at sits
 * behind ProtectedRoute (any signed-in staffer reaches it), and this
 * component additionally hides its OWN content unless the signed-in
 * account's ID-token claims carry `firm_role: "manager"` -- read via
 * Firebase's getIdTokenResult(), the one place a claim is visible
 * client-side. That is UX ONLY: an employee who forces this page open would
 * still hit the SAME admin-service gate every mutation below already goes
 * through (require_app_admin_or_owning_manager), which is where the real
 * enforcement lives. Hiding the page just avoids showing an employee a
 * dead-end form that would 403 on submit.
 *
 * Builds its own typed calls on adminApi.ts's generic adminFetch/errorDetail
 * (bd polyglot-pdf-z4ljj, C0) -- that module's own doc comment names this
 * page as one of the two callers it exists for (the other is C5, link
 * history). Deliberately NOT importing admin-console/src/utils/adminApi.ts:
 * admin-console/ and frontend/ do not import from each other (same
 * constraint documented on admin-console/src/utils/adminAuth.ts).
 */
import { useCallback, useEffect, useState } from 'react';

import './styles/console.css';
import { useAuth } from '../contexts/AuthContext';
import { adminFetch, errorDetail } from './adminApi';

/** Mirrors admin_backend/services/user_admin.py's FIRM_ROLES -- the console
 * sends these strings on create and on a role change. */
export const FIRM_ROLES = ['manager', 'employee'] as const;
export type FirmRole = (typeof FIRM_ROLES)[number];

/** One row from GET /admin/users' `users` array (admin_backend/services/
 * user_admin.py's `_user_row`, an explicit key allowlist, not a claims
 * dump). */
export interface EmployeeRow {
  uid: string;
  email: string | null;
  display_name: string | null;
  disabled: boolean;
  firm_id: string | null;
  firm_role: string | null;
}

interface UsersPageResponse {
  firm_id: string;
  users: EmployeeRow[];
  truncated: boolean;
}

interface CreateUserResult {
  uid: string;
  email: string;
  firm_id: string;
  firm_role: string;
  reset_link: string | null;
  request_id: string;
}

/** The minimal shape this page needs from a signed-in Firebase user --
 * matches MintLinkPage's own minimal prop shape, plus getIdTokenResult for
 * the manager-only UX check and `uid` for the self-action guard below (a
 * manager's own row appears in their firm's staff list -- see the
 * self-action guard comment on the table body). */
export interface EmployeesPageUser {
  uid: string;
  getIdToken: () => Promise<string>;
  getIdTokenResult: (forceRefresh?: boolean) => Promise<{ claims: Record<string, unknown> }>;
}

export interface EmployeesPageProps {
  /** Test override only. In the app the user comes from useAuth(). */
  user?: EmployeesPageUser | null;
  /** Injected in tests. */
  fetchImpl?: typeof fetch;
}

type LoadPhase = 'loading' | 'ready' | 'error';

/** GET the manager's own firm's staff pool. firm_id is OMITTED -- see the
 * module docstring for why a query param here, even a matching one, would
 * be refused. */
async function listEmployees(
  user: EmployeesPageUser | null | undefined,
  fetchImpl?: typeof fetch,
): Promise<UsersPageResponse> {
  const res = await adminFetch('/admin/users', user, {}, fetchImpl);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not load the staff list'));
  return (await res.json()) as UsersPageResponse;
}

interface CreateEmployeeRequest {
  email: string;
  firmRole: FirmRole;
  displayName?: string;
}

/** POST a new staff account. NO firm_id key on the body -- see the module
 * docstring. */
async function createEmployee(
  req: CreateEmployeeRequest,
  user: EmployeesPageUser | null | undefined,
  fetchImpl?: typeof fetch,
): Promise<CreateUserResult> {
  const res = await adminFetch('/admin/users', user, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: req.email,
      firm_role: req.firmRole,
      display_name: req.displayName || undefined,
      // firm_id intentionally absent: undefined keys are dropped by
      // JSON.stringify, which is what keeps this request manager-shaped.
    }),
  }, fetchImpl);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not create the account'));
  return (await res.json()) as CreateUserResult;
}

/** PATCH disable/re-enable. NO firm_id key on the body. */
async function setEmployeeDisabled(
  uid: string,
  disabled: boolean,
  user: EmployeesPageUser | null | undefined,
  fetchImpl?: typeof fetch,
): Promise<void> {
  const res = await adminFetch(`/admin/users/${encodeURIComponent(uid)}/disable`, user, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ disabled }),
  }, fetchImpl);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the account'));
}

/** PATCH role change. NO firm_id key on the body. */
async function setEmployeeRole(
  uid: string,
  firmRole: FirmRole,
  user: EmployeesPageUser | null | undefined,
  fetchImpl?: typeof fetch,
): Promise<void> {
  const res = await adminFetch(`/admin/users/${encodeURIComponent(uid)}/role`, user, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ firm_role: firmRole }),
  }, fetchImpl);
  if (!res.ok) throw new Error(await errorDetail(res, 'Could not update the account'));
}

/** True when the signed-in account's ID-token claims carry firm_role ===
 * "manager". UX gate only -- see the module docstring. A user with no
 * getIdTokenResult (should not happen for a real Firebase User, but keeps
 * this defensive for the test double / a mid-refresh edge) is treated as
 * NOT a manager, the fail-closed default for a UX hide. */
async function isManager(user: EmployeesPageUser | null | undefined): Promise<boolean> {
  if (!user) return false;
  try {
    const result = await user.getIdTokenResult();
    return result.claims['firm_role'] === 'manager';
  } catch {
    return false;
  }
}

export function EmployeesPage({ user: userOverride, fetchImpl }: EmployeesPageProps) {
  // From context, not a prop, mirroring MintLinkPage: mounted inside
  // ProtectedRoute with no props passed by the route element, so a real
  // render always has a user, and only tests supply the override.
  const { user: authUser } = useAuth();
  const user = (userOverride ?? authUser) as EmployeesPageUser | null | undefined;

  const [managerGate, setManagerGate] = useState<'checking' | 'manager' | 'not-manager'>('checking');
  const [phase, setPhase] = useState<LoadPhase>('loading');
  const [employees, setEmployees] = useState<EmployeeRow[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [listError, setListError] = useState('');
  const [busyUid, setBusyUid] = useState<string | null>(null);
  const [rowError, setRowError] = useState('');

  const [newEmail, setNewEmail] = useState('');
  const [newDisplayName, setNewDisplayName] = useState('');
  const [newRole, setNewRole] = useState<FirmRole>('employee');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  // The reset link from the MOST RECENT create only -- cleared on the next
  // create attempt, mirroring admin-console's UsersPage: this is the one
  // credential-bearing value this page ever holds.
  const [resetLink, setResetLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setPhase('loading');
    setListError('');
    try {
      const page = await listEmployees(user, fetchImpl);
      setEmployees(page.users);
      setTruncated(page.truncated);
      setPhase('ready');
    } catch (err) {
      setListError(err instanceof Error ? err.message : 'Could not load the staff list');
      setPhase('error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, fetchImpl]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const manager = await isManager(user);
      if (cancelled) return;
      setManagerGate(manager ? 'manager' : 'not-manager');
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  useEffect(() => {
    if (managerGate !== 'manager') return;
    void load();
  }, [managerGate, load]);

  const handleCreate = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError('');
    setResetLink(null);
    setCopied(false);
    try {
      const result = await createEmployee(
        { email: newEmail.trim(), firmRole: newRole, displayName: newDisplayName.trim() || undefined },
        user,
        fetchImpl,
      );
      setResetLink(result.reset_link);
      setNewEmail('');
      setNewDisplayName('');
      setNewRole('employee');
      await load();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Could not create the account');
    } finally {
      setCreating(false);
    }
  }, [newEmail, newDisplayName, newRole, user, fetchImpl, load]);

  const handleCopyResetLink = useCallback(() => {
    if (!resetLink) return;
    navigator.clipboard?.writeText(resetLink).then(() => {
      setCopied(true);
    }).catch(() => {
      // The link stays visible for a manual copy; a refused clipboard write
      // is not a page-breaking failure.
    });
  }, [resetLink]);

  const handleToggleDisabled = useCallback(async (row: EmployeeRow) => {
    // Defense in depth: the Disable button is already disabled for the
    // signed-in manager's own row (see the table body), but a caller
    // reaching this handler directly should not be able to route around
    // that -- see the self-action guard comment in the table body.
    if (user && row.uid === user.uid) return;
    setBusyUid(row.uid);
    setRowError('');
    try {
      await setEmployeeDisabled(row.uid, !row.disabled, user, fetchImpl);
      await load();
    } catch (err) {
      setRowError(err instanceof Error ? err.message : 'Could not update the account');
    } finally {
      setBusyUid(null);
    }
  }, [user, fetchImpl, load]);

  const handleRoleChange = useCallback(async (row: EmployeeRow, role: FirmRole) => {
    if (role === row.firm_role) return;
    // Defense in depth: see handleToggleDisabled above.
    if (user && row.uid === user.uid) return;
    setBusyUid(row.uid);
    setRowError('');
    try {
      await setEmployeeRole(row.uid, role, user, fetchImpl);
      await load();
    } catch (err) {
      setRowError(err instanceof Error ? err.message : 'Could not update the account');
    } finally {
      setBusyUid(null);
    }
  }, [user, fetchImpl, load]);

  // UX-ONLY gate (see module docstring): an employee (or a claim still
  // mid-refresh) sees nothing here rather than a form that would 403 on
  // submit. Rendering NOTHING while checking avoids a flash of the form
  // for an employee whose claim check has not resolved yet.
  if (managerGate !== 'manager') {
    return null;
  }

  return (
    <div className="employees-page">
      <h1>Your team</h1>
      <p>
        Manage your firm's staff accounts. New accounts sign in with the
        password-reset link shown below -- no email is sent.
      </p>

      <form onSubmit={(e) => void handleCreate(e)} className="employees-create-form">
        <div>
          <label htmlFor="employees-new-email">Email</label>
          <input
            id="employees-new-email"
            type="email"
            required
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="employees-new-display-name">Name</label>
          <input
            id="employees-new-display-name"
            value={newDisplayName}
            onChange={(e) => setNewDisplayName(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="employees-new-role">Role</label>
          <select
            id="employees-new-role"
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as FirmRole)}
          >
            {FIRM_ROLES.map((role) => (
              <option key={role} value={role}>{role}</option>
            ))}
          </select>
        </div>
        <button type="submit" disabled={creating}>
          {creating ? 'Creating...' : 'Create account'}
        </button>
      </form>

      {createError && <p role="alert">{createError}</p>}

      {resetLink && (
        <div className="employees-reset-link">
          <p>
            Account created. Share this password-reset link with them --
            no email was sent.
          </p>
          <input readOnly value={resetLink} aria-label="Password reset link" />
          <button type="button" onClick={handleCopyResetLink}>
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      )}

      {rowError && <p role="alert">{rowError}</p>}

      {phase === 'loading' && <p>Loading...</p>}
      {phase === 'error' && <p role="alert">{listError}</p>}

      {phase === 'ready' && (
        <>
          <table className="employees-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Name</th>
                <th>Role</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((row) => {
                // Self-action guard: list_firm_users filters on the same
                // firm_id claim the signed-in manager carries, so the
                // manager's OWN row is in this list. Neither backend route
                // (user_routes.py / user_admin.py) refuses actor.uid ===
                // uid, so a role change or Disable click on this row would
                // otherwise succeed and lock the manager out -- of the
                // console (self-demotion drops the firm_role claim a
                // subsequent /admin/users* call needs) or of the whole app
                // (self-disable). Render this row's role as static text and
                // the Disable button as disabled rather than omitted, so the
                // row does not silently lose its "who am I" affordance.
                const isSelf = !!user && row.uid === user.uid;
                return (
                  <tr key={row.uid}>
                    <td>{row.email ?? ''}{isSelf ? ' (you)' : ''}</td>
                    <td>{row.display_name ?? ''}</td>
                    <td>
                      {isSelf ? (
                        <span>{row.firm_role ?? ''}</span>
                      ) : (
                        <select
                          aria-label={`Role for ${row.email ?? row.uid}`}
                          value={row.firm_role ?? ''}
                          disabled={busyUid === row.uid}
                          onChange={(e) => void handleRoleChange(row, e.target.value as FirmRole)}
                        >
                          {FIRM_ROLES.map((role) => (
                            <option key={role} value={role}>{role}</option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td>{row.disabled ? 'Disabled' : 'Active'}</td>
                    <td>
                      <button
                        type="button"
                        disabled={isSelf || busyUid === row.uid}
                        title={isSelf ? 'You cannot disable your own account' : undefined}
                        onClick={() => void handleToggleDisabled(row)}
                      >
                        {row.disabled ? 'Enable' : 'Disable'}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {employees.length === 0 && (
                <tr>
                  <td colSpan={5}>No staff accounts yet.</td>
                </tr>
              )}
            </tbody>
          </table>
          {truncated && (
            <p className="employees-truncated-note">
              The staff pool walk was truncated; not every account may be shown.
            </p>
          )}
        </>
      )}
    </div>
  );
}
