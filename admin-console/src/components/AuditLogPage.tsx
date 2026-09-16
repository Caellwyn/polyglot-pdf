import React from 'react';
import { listAuditRows, type AuditRow } from '../utils/adminApi';
import { PageIntro } from './PageIntro';

interface AuditLogPageProps {
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
 * Audit log list page (bd polyglot-pdf-b6943): the first reader of GET
 * /admin/audit (admin_backend/routes/audit_routes.py), which the maintainer's
 * "who granted this" question is answered by.
 *
 * FILTERS mirror the route's own vocabulary exactly (action, actor_uid,
 * channel, state) -- see audit_routes.py's docstring for why those four and
 * no free-text search (Firestore cannot do it, and faking it client-side over
 * an unbounded collection is how this page becomes a bill).
 *
 * PAGINATION is cursor-based, one page at a time via "Load more": the route
 * returns `next_cursor` (null on the last page), and this page appends each
 * fetched page's rows rather than replacing them, so paging never loses what
 * an operator already scrolled past. Changing a filter resets the list and
 * refetches from the top -- an old page's rows under new filters would be a
 * different query's results silently mixed into this one.
 */
export const AuditLogPage: React.FC<AuditLogPageProps> = ({ onAuthExpired }) => {
  const [rows, setRows] = React.useState<AuditRow[]>([]);
  const [cursor, setCursor] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [action, setAction] = React.useState('');
  const [actorUid, setActorUid] = React.useState('');
  const [channel, setChannel] = React.useState('');
  const [state, setState] = React.useState('');

  const currentFilters = React.useCallback(() => ({
    action: action || undefined,
    actor_uid: actorUid || undefined,
    channel: channel || undefined,
    state: state || undefined,
  }), [action, actorUid, channel, state]);

  const loadFirstPage = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAuditRows(currentFilters());
      setRows(page.rows);
      setCursor(page.next_cursor);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the audit log');
    } finally {
      setLoading(false);
    }
  }, [currentFilters, onAuthExpired]);

  const loadNextPage = React.useCallback(async () => {
    if (!cursor) return;
    setLoading(true);
    setError(null);
    try {
      const page = await listAuditRows({ ...currentFilters(), cursor });
      setRows((prev) => [...prev, ...page.rows]);
      setCursor(page.next_cursor);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load more rows');
    } finally {
      setLoading(false);
    }
  }, [cursor, currentFilters, onAuthExpired]);

  // Initial load on mount only; filter changes are applied via the Apply
  // button (loadFirstPage), not on every keystroke -- an audit log filter is
  // a deliberate query, not a live-search box, and refetching per keystroke
  // would spam the admin service.
  React.useEffect(() => {
    void loadFirstPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div data-testid="audit-log-page">
      <h2 className="text-lg font-semibold text-gray-900">Audit log</h2>
      <PageIntro>
        Browse every mutating action taken through this console, who did it,
        and what changed.
      </PageIntro>

      <form
        onSubmit={(e) => { e.preventDefault(); void loadFirstPage(); }}
        className="mt-4 flex flex-wrap gap-2 items-end text-sm"
      >
        <div>
          <label className="block text-gray-500" htmlFor="audit-filter-action">Action</label>
          <input
            id="audit-filter-action"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-gray-500" htmlFor="audit-filter-actor">Actor UID</label>
          <input
            id="audit-filter-actor"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={actorUid}
            onChange={(e) => setActorUid(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-gray-500" htmlFor="audit-filter-channel">Channel</label>
          <input
            id="audit-filter-channel"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-gray-500" htmlFor="audit-filter-state">State</label>
          <input
            id="audit-filter-state"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={state}
            onChange={(e) => setState(e.target.value)}
          />
        </div>
        <button type="submit" className="btn btn-primary" disabled={loading}>
          Apply
        </button>
      </form>

      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}

      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-sm text-left" data-testid="audit-log-table">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500">
              <th className="py-1 pr-4">Time</th>
              <th className="py-1 pr-4">Action</th>
              <th className="py-1 pr-4">Actor</th>
              <th className="py-1 pr-4">Channel</th>
              <th className="py-1 pr-4">Target</th>
              <th className="py-1 pr-4">State</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.doc_id} className="border-b border-gray-100">
                <td className="py-1 pr-4 whitespace-nowrap">
                  {row.ts ? new Date(row.ts * 1000).toLocaleString() : ''}
                </td>
                <td className="py-1 pr-4">{row.action ?? ''}</td>
                <td className="py-1 pr-4">{row.actor_email ?? row.actor_uid ?? ''}</td>
                <td className="py-1 pr-4">{row.channel ?? ''}</td>
                <td className="py-1 pr-4 font-mono">{row.target ?? ''}</td>
                <td className="py-1 pr-4">{row.state ?? ''}</td>
              </tr>
            ))}
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={6} className="py-4 text-gray-500">No audit rows.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {cursor && (
        <button
          type="button"
          className="btn mt-4 border border-gray-300"
          onClick={() => void loadNextPage()}
          disabled={loading}
        >
          {loading ? 'Loading...' : 'Load more'}
        </button>
      )}
    </div>
  );
};
