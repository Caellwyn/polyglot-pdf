/**
 * Firm-console link history (bd polyglot-pdf-x22hm, Epic 2 Track C bead C5).
 *
 * WHO SEES WHAT, AND A KNOWN GAP THIS PAGE CANNOT CLOSE ON ITS OWN. The
 * admin service's GET /admin/firms/{firm_id}/links (bd polyglot-pdf-jmiys,
 * Surface contract 22 -- admin_backend/routes/link_routes.py) sits behind
 * require_app_admin_or_owning_manager, which has exactly TWO actor kinds --
 * app admin, or a firm MANAGER. An EMPLOYEE-role account is refused with a
 * flat 403 before the route's own employee_id filtering ever runs; there is
 * no third, narrower gate today that would let an employee reach even their
 * OWN links. Filed as bd polyglot-pdf-scaig (P1, admin_backend surfaces --
 * NOT this bead's) once discovered while building this page; fixing the
 * server gate is out of scope here (x22hm's surfaces are frontend-only) and
 * would be scope creep into B4's surfaces. THIS PAGE is still built exactly
 * to the bead's contract -- the bead's own exit criterion 1 is a frontend
 * behavioral claim (what the page SENDS and hides), pinned here against a
 * mocked API regardless of the server-side gap -- so that the moment
 * polyglot-pdf-scaig closes, this page works with no frontend change.
 * Until then, an employee visiting this page sees the ForbiddenError
 * message the 403 already carries.
 *
 * An employee's fetch call always OMITS employee_id (never sent, matching
 * the bead's own wording: "the page passes no employee_id for employees"),
 * and the revoke button and the employee/status filter controls are hidden
 * entirely for a non-manager (UX only -- the same "the admin service
 * enforces" caveat bd polyglot-pdf-krbol's manager-only visibility will
 * carry once C4's EmployeesPage.tsx lands; that page does not exist on this
 * branch). Nothing about this split is itself a security boundary on THIS
 * page; the boundary is (and must be) the admin service's own gate -- see
 * polyglot-pdf-scaig for where that boundary is still missing for the
 * employee actor.
 *
 * ROLE COMES FROM THE VERIFIED TOKEN'S CUSTOM CLAIMS
 * (`user.getIdTokenResult()`'s `claims.firm_role` / `claims.firm_id`,
 * mirroring backend/services/firms.py's manager_firm_id -- the SAME two
 * claims that decide it server-side), read via getIdTokenResult() rather
 * than trusted from anywhere in page state, because a route param or a
 * piece of local state a user could edit would be exactly the kind of
 * client-asserted identity the backend never lets decide anything (bd
 * polyglot-pdf-gob8l's mint route reads firm_id/employee_id from the
 * VERIFIED token for the identical reason). A token result IS cached by the
 * SDK and can go briefly stale after a claims change server-side, but that
 * risk is bounded to a UI affordance appearing or disappearing a token
 * refresh late -- never to which rows the ADMIN SERVICE actually returns,
 * which re-verifies the bearer token on every request.
 *
 * THE RESPONSE IS ALREADY ALLOWLISTED SERVER-SIDE (B4's `_public_link_view`
 * -- jti, kit_id, employee_id, status, minted_at, open_deadline, opened_at,
 * completed_at, spend_usd, turns, cap_usd, credit_cost). This page renders
 * ONLY those columns and touches no other key on a row, so a row is never
 * spread onto the DOM (**row would leak the moment the server ever widens
 * its own allowlist by mistake -- the same by-hand-fields discipline B4's
 * own docstring requires of the backend, kept on this side of the wire too).
 * There is no field VALUE anywhere in a link record (the credit ledger and
 * the mint record hold ids, timestamps, and dollars-and-cents spend, never
 * an applicant's answers) -- "never any field value" in the bead's own
 * words is automatically true of what the backend can even return, not an
 * extra filter this page has to apply.
 *
 * REVOKE IS MANAGER-ONLY, IS ONE CALL, AND RE-READS. POST
 * /admin/links/{jti}/revoke?channel= (same admin service, same
 * adminFetch client) fires once per click (disabled while in flight so a
 * double-click cannot fire it twice), and on success re-fetches the list
 * from the server rather than patching the clicked row's status in local
 * state -- the server is the only place that knows whether the write
 * actually landed (a 409 means it did NOT, because the link was no longer
 * `minted`), and re-reading is the same "one call, re-read" shape the
 * bead's own exit criterion 1 names.
 */
import { useCallback, useEffect, useState } from 'react';

// Same stylesheet MintLinkPage.tsx uses -- imported here too (not
// centrally) for the same reason MintLinkPage's own comment gives: a page
// mounted elsewhere must not silently pull this CSS in.
import './styles/console.css';
import { useAuth } from '../contexts/AuthContext';
import { adminFetch, errorDetail } from './adminApi';
import { AuthError, ForbiddenError } from './adminApi';

/** The allowlisted row shape B4's `_public_link_view` returns -- every key
 * that route can send, and the only keys this page ever reads off a row.
 * Every field is nullable: `_public_link_view` seeds the whole allowlist to
 * None before filling in what it has, so an unopened link's opened_at/
 * completed_at/spend_usd/turns are genuinely absent, not a decoding bug. */
interface LinkRow {
  jti: string | null;
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

/** Only a `minted` link may be revoked (B4's `_do_revoke_link`: any other
 * status is refused with a 409 naming the current status). Restated here so
 * the button can hide itself for a row the server would refuse anyway,
 * rather than showing an action that always fails. */
const REVOCABLE_STATUS = 'minted';

interface AuthUserLike {
  uid?: string;
  getIdToken: () => Promise<string>;
  getIdTokenResult?: () => Promise<{ claims: Record<string, unknown> }>;
}

export interface LinkHistoryPageProps {
  /** Test override only. In the app the user comes from useAuth(). */
  user?: AuthUserLike | null;
  /** Injected in tests. */
  fetchImpl?: typeof fetch;
}

type Phase = 'loading' | 'ready' | 'error';

function fmtTime(epochSeconds: number | null): string {
  if (epochSeconds === null || epochSeconds === undefined) return '--';
  try {
    return new Date(epochSeconds * 1000).toLocaleString();
  } catch {
    return '--';
  }
}

function fmtUsd(amount: number | null): string {
  if (amount === null || amount === undefined) return '--';
  return `$${amount.toFixed(2)}`;
}

export function LinkHistoryPage({ user: userOverride, fetchImpl }: LinkHistoryPageProps) {
  // From CONTEXT, not a prop -- same reasoning as MintLinkPage.tsx: the
  // route element passes no props, so a `user` prop here would send every
  // request unauthenticated in production while tests (which inject it)
  // stayed green.
  const { user: authUser } = useAuth();
  const user = (userOverride ?? authUser) as AuthUserLike | null | undefined;
  const doFetch = fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));

  const [phase, setPhase] = useState<Phase>('loading');
  const [message, setMessage] = useState('');
  const [rows, setRows] = useState<LinkRow[]>([]);
  const [firmId, setFirmId] = useState<string | null>(null);
  const [isManager, setIsManager] = useState(false);

  // Manager-only filter inputs. Never rendered, and never sent, for an
  // employee -- see the module docstring's "who sees what".
  const [statusFilter, setStatusFilter] = useState('');
  const [employeeFilter, setEmployeeFilter] = useState('');

  const [revokingJti, setRevokingJti] = useState<string | null>(null);

  // The verified token's OWN claims -- firm_id and firm_role, read via
  // getIdTokenResult() the same way backend/services/firms.py's
  // manager_firm_id reads them server-side. Resolved once per user, not
  // trusted from any editable page state.
  //
  // Every path out of this effect that leaves firmId null (no claim, or the
  // catch below) ALSO flips `phase` to 'error' with a message -- otherwise
  // the page is stuck on the initial 'loading' phase forever, because
  // nothing downstream (buildPath/load/the fetch effect) ever runs to move
  // it off that phase when there is no firmId to fetch with. A signed-in
  // account with no firm claim (a dev/app-admin account, or a claims
  // propagation race right after a role change) is reachable here via the
  // generic ProtectedRoute, so this is not a hypothetical.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!user) return;
      try {
        const result = user.getIdTokenResult
          ? await user.getIdTokenResult()
          : { claims: {} as Record<string, unknown> };
        if (cancelled) return;
        const claims = result.claims || {};
        const claimedFirmId = typeof claims.firm_id === 'string' ? claims.firm_id : null;
        setFirmId(claimedFirmId);
        setIsManager(claims.firm_role === 'manager');
        if (!claimedFirmId) {
          setPhase('error');
          setMessage('Your account is not linked to a firm. Contact your firm administrator.');
        }
      } catch {
        if (!cancelled) {
          setFirmId(null);
          setIsManager(false);
          setPhase('error');
          setMessage('Could not verify your account. Please sign in again.');
        }
      }
    })();
    return () => { cancelled = true; };
  }, [user]);

  // The query this fetch sends. An employee's request NEVER carries
  // employee_id -- it is simply omitted, matching the bead's own wording
  // ("the page passes no employee_id for employees") -- rather than sending
  // the employee's own uid as a filter, which would depend on the admin
  // service someday deriving the SAME narrowing this page already applies
  // client-side (it does not today; see the module docstring).
  const buildPath = useCallback((): string | null => {
    if (!firmId) return null;
    const params = new URLSearchParams();
    if (isManager) {
      if (statusFilter) params.set('status', statusFilter);
      if (employeeFilter) params.set('employee_id', employeeFilter);
    }
    const qs = params.toString();
    return `/admin/firms/${encodeURIComponent(firmId)}/links${qs ? `?${qs}` : ''}`;
  }, [firmId, isManager, statusFilter, employeeFilter]);

  const load = useCallback(async () => {
    const path = buildPath();
    if (!path) return;
    setPhase('loading');
    setMessage('');
    try {
      const response = await adminFetch(path, user, {}, doFetch);
      if (!response.ok) {
        setPhase('error');
        setMessage(await errorDetail(response, 'Could not load link history.'));
        return;
      }
      const data = await response.json();
      const links = Array.isArray(data?.links) ? (data.links as LinkRow[]) : [];
      setRows(links);
      setPhase('ready');
    } catch (err) {
      setPhase('error');
      if (err instanceof AuthError) {
        setMessage('Please sign in again.');
      } else if (err instanceof ForbiddenError) {
        setMessage(err.message);
      } else {
        setMessage('Could not reach the server.');
      }
    }
  }, [buildPath, user, doFetch]);

  useEffect(() => {
    if (!firmId) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firmId, isManager]);

  const revoke = useCallback(async (jti: string) => {
    if (!isManager || revokingJti) return;
    setRevokingJti(jti);
    try {
      const response = await adminFetch(
        `/admin/links/${encodeURIComponent(jti)}/revoke`,
        user,
        { method: 'POST' },
        doFetch,
      );
      if (!response.ok) {
        setMessage(await errorDetail(response, 'Could not revoke this link.'));
        setPhase('error');
        setRevokingJti(null);
        return;
      }
      // ONE call, then RE-READ (exit criterion 1) -- the server, not local
      // state, decides what the table shows after a revoke.
      await load();
    } catch (err) {
      // adminFetch THROWS AuthError/ForbiddenError on a 401/403 rather than
      // returning them, so the !response.ok branch above never sees those
      // two -- this catch is their only handler. Mirrors load()'s own
      // handling a few lines up: an expired session or a permission refusal
      // must not read as "the server is unreachable" (x22hm review finding
      // 5), which would tell a manager to retry when they actually need to
      // sign in again.
      if (err instanceof AuthError) {
        setMessage('Please sign in again.');
      } else if (err instanceof ForbiddenError) {
        setMessage(err.message);
      } else {
        setMessage('Could not reach the server.');
      }
      setPhase('error');
    } finally {
      setRevokingJti(null);
    }
  }, [isManager, revokingJti, user, doFetch, load]);

  return (
    <div className="mint-page">
      <h1>Link history</h1>
      <p>
        {isManager
          ? 'Every link your firm has sent.'
          : 'Links you have sent.'}
      </p>

      {isManager && (
        <div className="link-history-filters">
          <label htmlFor="lh-status">Status</label>
          <select
            id="lh-status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All</option>
            <option value="minted">Minted</option>
            <option value="opened">Opened</option>
            <option value="completed">Completed</option>
            <option value="refunded">Refunded</option>
            <option value="revoked">Revoked</option>
            <option value="budget_exhausted">Budget exhausted</option>
          </select>

          <label htmlFor="lh-employee">Employee</label>
          <input
            id="lh-employee"
            type="text"
            value={employeeFilter}
            onChange={(e) => setEmployeeFilter(e.target.value)}
            placeholder="Employee uid"
          />

          <button type="button" onClick={() => void load()}>
            Filter
          </button>
        </div>
      )}

      {phase === 'loading' && <p>Loading...</p>}
      {phase === 'error' && <p role="alert">{message}</p>}

      {phase === 'ready' && (
        <table className="link-history-table">
          <thead>
            <tr>
              <th>Form</th>
              <th>Status</th>
              <th>Minted</th>
              <th>Opened</th>
              <th>Completed</th>
              <th>Spend</th>
              {isManager && <th>Revoke</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.jti ?? Math.random()}>
                <td>{row.kit_id ?? '--'}</td>
                <td>{row.status ?? '--'}</td>
                <td>{fmtTime(row.minted_at)}</td>
                <td>{fmtTime(row.opened_at)}</td>
                <td>{fmtTime(row.completed_at)}</td>
                <td>{fmtUsd(row.spend_usd)}</td>
                {isManager && (
                  <td>
                    {row.status === REVOCABLE_STATUS && row.jti && (
                      <button
                        type="button"
                        onClick={() => void revoke(row.jti as string)}
                        disabled={revokingJti === row.jti}
                      >
                        {revokingJti === row.jti ? 'Revoking...' : 'Revoke'}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={isManager ? 7 : 6}>No links yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
