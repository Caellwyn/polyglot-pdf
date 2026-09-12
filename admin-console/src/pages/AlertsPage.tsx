import React from 'react';
import {
  listAlerts, acknowledgeAlert, ALERT_KINDS,
  type AlertRow, type AlertKind,
} from '../utils/adminApi';

interface AlertsPageProps {
  onAuthExpired: (err: unknown) => boolean;
}

function formatTs(ts: number | null): string {
  if (ts === null) return '--';
  return new Date(ts * 1000).toISOString();
}

/**
 * Alerts page (bd polyglot-pdf-i6dlb, E3.11b), driving
 * admin_backend/routes/alert_routes.py's GET /admin/alerts and
 * PATCH /admin/alerts/{id}/acknowledge.
 *
 * UNACKNOWLEDGED-ONLY IS THE DEFAULT VIEW (bead requirement) -- an operator
 * opening this page wants "what still needs attention" first; the
 * acknowledged filter is a tri-state select (unacknowledged / acknowledged
 * / all) rather than a checkbox, since "all" is a real fourth query shape
 * (acknowledged=undefined, no filter at all) the route itself supports.
 *
 * ACKNOWLEDGE CALLS THE PATCH EXACTLY ONCE PER CLICK, THEN RE-READS (bead
 * requirement, mirroring UsersPage's own mutate-then-reload pattern):
 * `busyId` disables the button for the row mid-flight so a double-click
 * cannot fire two PATCHes, and the re-read uses the SAME filters currently
 * selected so an acknowledged row disappears from the default
 * unacknowledged-only view exactly as an operator would expect.
 *
 * A 409 (ALREADY ACKNOWLEDGED) IS SHOWN AS SUCH, NOT A GENERIC ERROR (bead
 * requirement: "a 409 on a second acknowledge shows as already
 * acknowledged") -- alert_routes.py's own 409 detail names who
 * acknowledged it first ("alert X was already acknowledged by Y"), and
 * this page surfaces that exact server text next to the row, rather than a
 * generic failure banner. A FAILED acknowledge (409 or otherwise) does NOT
 * re-read the list -- mirrors UsersPage's own "a failed mutation must not
 * trigger the success re-read" rule, since re-reading on every failure
 * would make "acknowledge exactly once, re-read on success" ambiguous
 * with a caller who wants to confirm the call count a failure produced. An
 * operator who hits a stale-list 409 can re-run the Filter button to see
 * the current state.
 */
export const AlertsPage: React.FC<AlertsPageProps> = ({ onAuthExpired }) => {
  const [acknowledgedFilter, setAcknowledgedFilter] = React.useState<'unacknowledged' | 'acknowledged' | 'all'>('unacknowledged');
  const [kindFilter, setKindFilter] = React.useState<AlertKind | ''>('');
  const [firmIdFilter, setFirmIdFilter] = React.useState('');

  const [alerts, setAlerts] = React.useState<AlertRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [rowError, setRowError] = React.useState<{ id: string; message: string } | null>(null);

  const loadAlerts = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const acknowledged = acknowledgedFilter === 'all' ? undefined : acknowledgedFilter === 'acknowledged';
      const page = await listAlerts({
        acknowledged,
        firmId: firmIdFilter.trim() || undefined,
        kind: kindFilter || undefined,
      });
      setAlerts(page.alerts);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the alerts list');
    } finally {
      setLoading(false);
    }
  }, [acknowledgedFilter, firmIdFilter, kindFilter, onAuthExpired]);

  React.useEffect(() => {
    void loadAlerts();
    // Deliberately mount-only (empty deps): loadAlerts closes over the
    // current filter state, but re-firing this effect whenever any filter
    // changes would auto-submit on every select/keystroke change, making
    // the explicit Filter button below redundant. Filter changes apply
    // only when the operator submits the form (handleFilterSubmit) --
    // mirrors FirmsPage's own load-on-mount-only pattern.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFilterSubmit = React.useCallback((e: React.FormEvent) => {
    e.preventDefault();
    void loadAlerts();
  }, [loadAlerts]);

  const handleAcknowledge = React.useCallback(async (row: AlertRow) => {
    setBusyId(row.id);
    setRowError(null);
    try {
      await acknowledgeAlert(row.id);
      await loadAlerts();
    } catch (err) {
      if (onAuthExpired(err)) return;
      setRowError({
        id: row.id,
        message: err instanceof Error ? err.message : 'Could not acknowledge the alert',
      });
    } finally {
      setBusyId(null);
    }
  }, [loadAlerts, onAuthExpired]);

  return (
    <div data-testid="alerts-page" className="max-w-5xl">
      <h2 className="text-lg font-semibold text-gray-900">Alerts</h2>

      <form onSubmit={handleFilterSubmit} className="mt-4 flex flex-wrap items-end gap-2 text-sm">
        <div>
          <label className="block text-gray-700" htmlFor="alerts-acknowledged">Status</label>
          <select
            id="alerts-acknowledged"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={acknowledgedFilter}
            onChange={(e) => setAcknowledgedFilter(e.target.value as typeof acknowledgedFilter)}
          >
            <option value="unacknowledged">Unacknowledged</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="all">All</option>
          </select>
        </div>
        <div>
          <label className="block text-gray-700" htmlFor="alerts-kind">Kind</label>
          <select
            id="alerts-kind"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value as AlertKind | '')}
          >
            <option value="">All kinds</option>
            {ALERT_KINDS.map((kind) => (
              <option key={kind} value={kind}>{kind}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-gray-700" htmlFor="alerts-firm">Firm ID</label>
          <input
            id="alerts-firm"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={firmIdFilter}
            onChange={(e) => setFirmIdFilter(e.target.value)}
          />
        </div>
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? 'Loading...' : 'Filter'}
        </button>
      </form>

      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}

      <div className="mt-6 overflow-x-auto">
        <table className="min-w-full text-sm text-left" data-testid="alerts-table">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500">
              <th className="py-1 pr-4">Kind</th>
              <th className="py-1 pr-4">Level</th>
              <th className="py-1 pr-4">Firm</th>
              <th className="py-1 pr-4">Time</th>
              <th className="py-1 pr-4">Status</th>
              <th className="py-1 pr-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((row) => (
              <tr key={row.id} className="border-b border-gray-100">
                <td className="py-1 pr-4">{row.kind}</td>
                <td className="py-1 pr-4">
                  <span
                    className={
                      'inline-block rounded px-2 py-0.5 text-xs font-medium ' +
                      (row.level === 'critical' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800')
                    }
                  >
                    {row.level}
                  </span>
                </td>
                <td className="py-1 pr-4">{row.firm_id ?? ''}</td>
                <td className="py-1 pr-4">{formatTs(row.ts)}</td>
                <td className="py-1 pr-4">
                  {row.acknowledged_by
                    ? 'Acknowledged by ' + row.acknowledged_by
                    : 'Unacknowledged'}
                </td>
                <td className="py-1 pr-4">
                  <button
                    type="button"
                    className="btn border border-gray-300"
                    disabled={busyId === row.id || Boolean(row.acknowledged_by)}
                    onClick={() => void handleAcknowledge(row)}
                  >
                    {busyId === row.id ? 'Acknowledging...' : 'Acknowledge'}
                  </button>
                  {rowError && rowError.id === row.id && (
                    <p className="mt-1 text-xs text-red-600">{rowError.message}</p>
                  )}
                </td>
              </tr>
            ))}
            {alerts.length === 0 && !loading && (
              <tr>
                <td colSpan={6} className="py-4 text-gray-500">No alerts match this filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
