import React from 'react';
import {
  listUsers, createUser, setUserDisabled, setUserRole,
  FIRM_ROLES, type AdminUserRow, type FirmRole,
} from '../utils/adminApi';

interface UsersPageProps {
  /** Called first on every catch. Returns true when `err` was an
   * AuthError/ForbiddenError that App has already routed back to the
   * sign-in gate -- in that case this page must NOT also set its own
   * generic error banner (the gate is about to replace this page entirely).
   * Returns false for anything else, so this page's normal error handling
   * still applies. See App.tsx's handleAuthExpired docstring for why this
   * is the console's single mid-session-eviction predicate. */
  onAuthExpired: (err: unknown) => boolean;
}

/**
 * Staff-account management page (bd polyglot-pdf-z4y91), driving
 * admin_backend/routes/user_routes.py's four routes: list a firm's staff,
 * create one (returning a password-reset link), disable/re-enable, and
 * change role.
 *
 * THE FIRM SELECTOR IS REQUIRED, always, on this page. The console today
 * only supports the app-admin sign-in path -- GET /admin/whoami gates on the
 * strict `require_app_admin`, not the composite
 * `require_app_admin_or_owning_manager` the user routes accept -- so every
 * caller of this page is an app admin, and admin_auth.resolve_target_firm
 * refuses (422) an app admin who omits firm_id. A firm-manager mode with no
 * selector (the manager's firm comes from their token) is a later bead's
 * concern once the console itself supports signing in as one; this page
 * does not attempt to guess which actor kind is signed in.
 *
 * NO PASSWORD EVER RENDERS. create_staff_user (admin_backend/services/
 * user_admin.py) never returns one -- the account's real password is an
 * unguessable random value nobody, including this console, ever learns.
 * The only credential surfaced here is the password-RESET LINK, shown
 * exactly once right after a successful create, with a copy button; it is
 * cleared the moment the operator starts a new create or switches firms, so
 * it never lingers as stale state pointing at the wrong account.
 *
 * MUTATE THEN RE-READ. Disable and role-change both call their route once
 * and then reload the list from the server (mirrors ConfigEditorPage's
 * round-trip pattern) so the screen always reflects what the server
 * actually stored, not merely an optimistic local patch.
 */
export const UsersPage: React.FC<UsersPageProps> = ({ onAuthExpired }) => {
  const [firmId, setFirmId] = React.useState('');
  const [firmIdInput, setFirmIdInput] = React.useState('');
  const [users, setUsers] = React.useState<AdminUserRow[]>([]);
  const [truncated, setTruncated] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [busyUid, setBusyUid] = React.useState<string | null>(null);

  // Create-account form state, kept separate from the list state above.
  const [newEmail, setNewEmail] = React.useState('');
  const [newDisplayName, setNewDisplayName] = React.useState('');
  const [newRole, setNewRole] = React.useState<FirmRole>('employee');
  const [creating, setCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);
  // The reset link from the MOST RECENT create only -- see the module
  // docstring for why this is the one credential-bearing value this page
  // ever holds, and why it does not survive a firm switch or a new attempt.
  const [resetLink, setResetLink] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  const loadUsers = React.useCallback(async (targetFirmId: string) => {
    if (!targetFirmId) return;
    setLoading(true);
    setError(null);
    try {
      const page = await listUsers(targetFirmId);
      setUsers(page.users);
      setTruncated(page.truncated);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the user list');
    } finally {
      setLoading(false);
    }
  }, [onAuthExpired]);

  const handleLoadFirm = React.useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = firmIdInput.trim();
    setFirmId(trimmed);
    setResetLink(null);
    setCopied(false);
    setCreateError(null);
    void loadUsers(trimmed);
  }, [firmIdInput, loadUsers]);

  const handleCreate = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!firmId) return;
    setCreating(true);
    setCreateError(null);
    setResetLink(null);
    setCopied(false);
    try {
      const result = await createUser({
        email: newEmail.trim(),
        firmRole: newRole,
        firmId,
        displayName: newDisplayName.trim() || undefined,
      });
      setResetLink(result.reset_link);
      setNewEmail('');
      setNewDisplayName('');
      setNewRole('employee');
      await loadUsers(firmId);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setCreateError(err instanceof Error ? err.message : 'Could not create the account');
    } finally {
      setCreating(false);
    }
  }, [firmId, newEmail, newDisplayName, newRole, loadUsers, onAuthExpired]);

  const handleCopyResetLink = React.useCallback(() => {
    if (!resetLink) return;
    void navigator.clipboard?.writeText(resetLink).then(() => {
      setCopied(true);
    }).catch(() => {
      // Clipboard access can be refused by the browser (no permission, no
      // secure context in some test/dev setups); the link is still visible
      // in the page for a manual copy, so this failure is silent rather
      // than another error banner on top of a working feature.
    });
  }, [resetLink]);

  const handleToggleDisabled = React.useCallback(async (row: AdminUserRow) => {
    setBusyUid(row.uid);
    setError(null);
    try {
      await setUserDisabled(row.uid, firmId, !row.disabled);
      await loadUsers(firmId);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not update the account');
    } finally {
      setBusyUid(null);
    }
  }, [firmId, loadUsers, onAuthExpired]);

  const handleRoleChange = React.useCallback(async (row: AdminUserRow, role: FirmRole) => {
    if (role === row.firm_role) return;
    setBusyUid(row.uid);
    setError(null);
    try {
      await setUserRole(row.uid, firmId, role);
      await loadUsers(firmId);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not update the account');
    } finally {
      setBusyUid(null);
    }
  }, [firmId, loadUsers, onAuthExpired]);

  return (
    <div data-testid="users-page" className="max-w-3xl">
      <h2 className="text-lg font-semibold text-gray-900">Users</h2>

      <form onSubmit={handleLoadFirm} className="mt-4 flex items-end gap-2 text-sm">
        <div>
          <label className="block text-gray-700" htmlFor="users-firm-id">
            Firm ID
          </label>
          <input
            id="users-firm-id"
            required
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={firmIdInput}
            onChange={(e) => setFirmIdInput(e.target.value)}
          />
        </div>
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? 'Loading...' : 'Load'}
        </button>
      </form>

      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}

      {firmId && (
        <>
          <form
            onSubmit={(e) => void handleCreate(e)}
            className="mt-6 border border-gray-200 rounded p-4 flex flex-wrap items-end gap-2 text-sm"
          >
            <div>
              <label className="block text-gray-700" htmlFor="users-new-email">
                Email
              </label>
              <input
                id="users-new-email"
                type="email"
                required
                className="mt-1 border border-gray-300 rounded px-2 py-1"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-gray-700" htmlFor="users-new-display-name">
                Display name
              </label>
              <input
                id="users-new-display-name"
                className="mt-1 border border-gray-300 rounded px-2 py-1"
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-gray-700" htmlFor="users-new-role">
                Role
              </label>
              <select
                id="users-new-role"
                className="mt-1 border border-gray-300 rounded px-2 py-1"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as FirmRole)}
              >
                {FIRM_ROLES.map((role) => (
                  <option key={role} value={role}>{role}</option>
                ))}
              </select>
            </div>
            <button type="submit" className="btn btn-primary" disabled={creating}>
              {creating ? 'Creating...' : 'Create account'}
            </button>
          </form>

          {createError && <div className="mt-2 text-sm text-red-600">{createError}</div>}

          {resetLink && (
            <div className="mt-3 border border-green-200 bg-green-50 rounded p-3 text-sm">
              <p className="text-green-800">
                Account created. Share this password-reset link with the new user
                -- no email was sent.
              </p>
              <div className="mt-2 flex items-center gap-2">
                <code className="flex-1 break-all text-xs bg-white border border-gray-200 rounded px-2 py-1">
                  {resetLink}
                </code>
                <button
                  type="button"
                  className="btn border border-gray-300"
                  onClick={handleCopyResetLink}
                >
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
            </div>
          )}

          <div className="mt-6 overflow-x-auto">
            <table className="min-w-full text-sm text-left" data-testid="users-table">
              <thead>
                <tr className="border-b border-gray-200 text-gray-500">
                  <th className="py-1 pr-4">Email</th>
                  <th className="py-1 pr-4">Name</th>
                  <th className="py-1 pr-4">Role</th>
                  <th className="py-1 pr-4">Status</th>
                  <th className="py-1 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((row) => (
                  <tr key={row.uid} className="border-b border-gray-100">
                    <td className="py-1 pr-4">{row.email ?? ''}</td>
                    <td className="py-1 pr-4">{row.display_name ?? ''}</td>
                    <td className="py-1 pr-4">
                      <select
                        aria-label={`Role for ${row.email ?? row.uid}`}
                        className="border border-gray-300 rounded px-1 py-0.5"
                        value={row.firm_role ?? ''}
                        disabled={busyUid === row.uid}
                        onChange={(e) => void handleRoleChange(row, e.target.value as FirmRole)}
                      >
                        {FIRM_ROLES.map((role) => (
                          <option key={role} value={role}>{role}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-1 pr-4">{row.disabled ? 'Disabled' : 'Active'}</td>
                    <td className="py-1 pr-4">
                      <button
                        type="button"
                        className="btn border border-gray-300"
                        disabled={busyUid === row.uid}
                        onClick={() => void handleToggleDisabled(row)}
                      >
                        {row.disabled ? 'Enable' : 'Disable'}
                      </button>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && !loading && (
                  <tr>
                    <td colSpan={5} className="py-4 text-gray-500">No users for this firm.</td>
                  </tr>
                )}
              </tbody>
            </table>
            {truncated && (
              <p className="mt-2 text-xs text-amber-700">
                The staff pool walk was truncated; not every account may be shown.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
};
