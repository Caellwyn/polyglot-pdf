import React from 'react';
import {
  getFirm, getFirmUsage, listFirms, MONITORING_CHANNELS,
  type FirmUsagePage, type MonitoringChannel, type FirmRow, type FirmUsageRollup,
} from '../utils/adminApi';
import { PageIntro } from '../components/PageIntro';

interface UsagePageProps {
  onAuthExpired: (err: unknown) => boolean;
}

function currentMonth(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return String(now.getFullYear()) + '-' + month;
}

function breakdownRows(
  breakdown: Record<string, { sessions?: number; cost_usd?: number; links_minted?: number }> | null | undefined,
): Array<{ key: string; sessions: number; cost_usd: number; links_minted?: number }> {
  if (!breakdown) return [];
  return Object.keys(breakdown)
    .sort()
    .map((key) => ({
      key,
      sessions: breakdown[key]?.sessions ?? 0,
      cost_usd: breakdown[key]?.cost_usd ?? 0,
      links_minted: breakdown[key]?.links_minted,
    }));
}

function formatUsd(value: number): string {
  return value.toFixed(2);
}

/** True if a ledger entry's unix-seconds `ts` falls within the given
 * "YYYY-MM" month, in UTC -- matching usage_rollups.py's own `_month_key`
 * convention (UTC, not the browser's local timezone) so a ledger row and
 * its corresponding rollup doc always agree on which month they belong to. */
function tsInMonth(ts: number, month: string): boolean {
  const d = new Date(ts * 1000);
  const stamp = String(d.getUTCFullYear()) + '-' + String(d.getUTCMonth() + 1).padStart(2, '0');
  return stamp === month;
}

/** The complete set of usage.ts counter keys that a Firestore-side write
 * can populate (mirrors usage_routes.py's own _FIRM_USAGE_KEYS numeric/map
 * fields; kind/channel are metadata, not counters, and are excluded on
 * purpose -- a doc written with only kind/channel set does not exist in
 * this backend, but excluding them here keeps the predicate scoped to
 * "did any activity get recorded" rather than "did metadata get stamped").
 * Enumerated explicitly so a future counter added to the allowlist is a
 * visible one-line diff here, not a silent gap in the no-data check. */
const USAGE_COUNTER_KEYS = [
  'connections_ended', 'sessions_completed', 'cost_usd_total',
  'links_opened', 'links_completed', 'links_minted',
  'by_kit', 'by_employee', 'by_language',
] as const;

/** True only when EVERY counter above is null -- i.e. no rollup doc exists
 * for this firm-month at all. A single null counter (most commonly
 * sessions_completed, which is written only for completion_status ==
 * "completed" sessions) means a real doc exists with real activity in it,
 * even though that one field never got incremented. */
function hasNoUsageData(usage: FirmUsageRollup | null): boolean {
  if (!usage) return true;
  return USAGE_COUNTER_KEYS.every((key) => usage[key] === null);
}

/**
 * Usage page (bd polyglot-pdf-i6dlb, E3.11b), driving
 * admin_backend/routes/usage_routes.py's GET /admin/firms/{firm_id}/usage.
 *
 * FIRM PICKER OVER GET /admin/firms (bead B1, listFirms) -- unlike
 * UsersPage's free-text firm-id field, this page has the full firm list to
 * choose from, so it renders a real select populated on mount. MONTH
 * PICKER defaults to the current calendar month (YYYY-MM); CHANNEL
 * defaults to demo, matching every other channel-scoped page's default.
 *
 * A MONTH WITH NO ROLLUP DOC SAYS SO EXPLICITLY (bead requirement) --
 * usage_routes.py returns an all-null usage object rather than a 404 for a
 * quiet month, so this page treats EVERY allowlisted counter being null as
 * the "no data" signal and renders a dedicated empty-state message.
 * sessions_completed ALONE is not a safe proxy for "no rollup doc": a
 * firm-month where every connection was abandoned or reconnected (never
 * reached completion_status == "completed") writes connections_ended,
 * cost_usd_total, kind, channel and the breakdown maps while leaving
 * sessions_completed null -- backend/services/usage_rollups.py's
 * record_session_end only increments sessions_completed inside its
 * "if completed:" branch. The same shape happens for a links-only month:
 * _increment_firm_counter (record_link_opened / record_link_completed)
 * writes just links_opened/links_completed via merge=True, never touching
 * sessions_completed. Both are real activity, not "no data" -- checking
 * every counter, not one field, is what tells them apart from a genuinely
 * missing doc. A MINT-ONLY month (bd polyglot-pdf-he3lt) is the same shape
 * again: record_link_minted writes ONLY links_minted (and
 * by_employee.{uid}.links_minted) before a client has ever opened the
 * link, so links_minted joins the allowlist below for the identical
 * reason links_opened/links_completed already did.
 *
 * A MISSING DOC WITH LEDGER ACTIVITY THAT MONTH SAYS SO TOO (bd
 * polyglot-pdf-he3lt): a fresh mint's rollup write can itself still be
 * pending (best-effort, fire-and-forget from the route's point of view) in
 * the moment right after a staff member mints a link, so "no rollup doc
 * yet" and "genuinely nothing happened" are not quite the same signal
 * either. This page makes a SECOND read, of the firm's ledger (GET
 * /admin/firms/{firm_id}, already used by FirmDetailPage), and shows "no
 * sessions yet this month" instead of the bare "no data" whenever any
 * ledger row's timestamp falls in the selected month -- a mint always
 * writes a ledger entry (credit_ledger.append_entry, from
 * link_routes.py's _reserve_mint) even on the rare chance its rollup
 * write did not land, so this is a reliable proxy for "something really
 * did happen this month" that does not require a new backend route: it
 * reuses getFirm's existing `ledger` field. getFirm returns only the
 * newest page of ledger rows (default 50) -- checked ONLY for the
 * currently-viewed month, so this can only ever miss a month that already
 * has 50+ NEWER entries after it (an old, already-quiet-looking month on a
 * very active firm); the current/recent month this page defaults to is
 * never affected. Best-effort either way -- a miss degrades to the plain
 * "no data" message, never a wrong claim of activity.
 */
export const UsagePage: React.FC<UsagePageProps> = ({ onAuthExpired }) => {
  const [firms, setFirms] = React.useState<FirmRow[]>([]);
  const [firmsLoading, setFirmsLoading] = React.useState(true);
  const [firmsError, setFirmsError] = React.useState<string | null>(null);

  const [firmId, setFirmId] = React.useState('');
  const [month, setMonth] = React.useState(currentMonth());
  const [channel, setChannel] = React.useState<MonitoringChannel>('demo');

  const [page, setPage] = React.useState<FirmUsagePage | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // True when the usage doc came back empty BUT the firm's ledger shows
  // activity in the selected month -- a fresh mint whose rollup write has
  // not (yet, or ever, best-effort) landed, not a genuinely quiet month.
  // Checked ONLY when the primary usage read is empty (never on the happy
  // path), via a second, best-effort getFirm() call: a failure there must
  // not block or corrupt the primary "no data" reading, so it degrades
  // silently to the plain empty-state message rather than surfacing its
  // own error.
  const [hadLedgerActivity, setHadLedgerActivity] = React.useState(false);

  React.useEffect(() => {
    (async () => {
      setFirmsLoading(true);
      setFirmsError(null);
      try {
        const rows = await listFirms();
        setFirms(rows);
      } catch (err) {
        if (onAuthExpired(err)) return;
        setFirmsError(err instanceof Error ? err.message : 'Could not load the firm list');
      } finally {
        setFirmsLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLoad = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!firmId) return;
    setLoading(true);
    setError(null);
    setHadLedgerActivity(false);
    try {
      const result = await getFirmUsage(firmId, month, channel);
      setPage(result);
      if (hasNoUsageData(result.usage)) {
        // Best-effort second check: never let a failure here block the
        // page or overwrite the primary (successful) "no data" result.
        try {
          const detail = await getFirm(firmId);
          setHadLedgerActivity(detail.ledger.some((row) => tsInMonth(row.ts, month)));
        } catch {
          setHadLedgerActivity(false);
        }
      }
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the firm usage');
      setPage(null);
    } finally {
      setLoading(false);
    }
  }, [firmId, month, channel, onAuthExpired]);

  const usage = page?.usage ?? null;
  const hasData = usage !== null && !hasNoUsageData(usage);

  return (
    <div data-testid="usage-page" className="max-w-4xl">
      <h2 className="text-lg font-semibold text-gray-900">Usage</h2>
      <PageIntro>
        See a firm&apos;s session and link activity for a given month,
        broken down by kit, employee, and language.
      </PageIntro>

      {firmsError && <div className="mt-3 text-sm text-red-600">{firmsError}</div>}

      <form onSubmit={(e) => void handleLoad(e)} className="mt-4 flex flex-wrap items-end gap-2 text-sm">
        <div>
          <label className="block text-gray-700" htmlFor="usage-firm">Firm</label>
          <select
            id="usage-firm"
            required
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={firmId}
            disabled={firmsLoading}
            onChange={(e) => setFirmId(e.target.value)}
          >
            <option value="" disabled>Choose a firm...</option>
            {firms.map((firm) => (
              <option key={firm.firm_id} value={firm.firm_id}>
                {firm.name || firm.firm_id}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-gray-700" htmlFor="usage-month">Month</label>
          <input
            id="usage-month"
            type="month"
            required
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-gray-700" htmlFor="usage-channel">Channel</label>
          <select
            id="usage-channel"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={channel}
            onChange={(e) => setChannel(e.target.value as MonitoringChannel)}
          >
            {MONITORING_CHANNELS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <button type="submit" className="btn btn-primary" disabled={loading || !firmId}>
          {loading ? 'Loading...' : 'Load'}
        </button>
      </form>

      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}

      {page && !hasData && hadLedgerActivity && (
        <p className="mt-6 text-gray-500" data-testid="usage-no-sessions-yet">
          No sessions yet this month for {page.firm_id} in {page.month} ({page.channel}).
        </p>
      )}

      {page && !hasData && !hadLedgerActivity && (
        <p className="mt-6 text-gray-500" data-testid="usage-no-data">
          No usage recorded for {page.firm_id} in {page.month} ({page.channel}).
        </p>
      )}

      {page && hasData && usage && (
        <div className="mt-6 space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <Stat label="Sessions completed" value={usage.sessions_completed ?? 0} />
            <Stat label="Connections ended" value={usage.connections_ended ?? 0} />
            <Stat label="Links minted" value={usage.links_minted ?? 0} />
            <Stat label="Links opened" value={usage.links_opened ?? 0} />
            <Stat label="Links completed" value={usage.links_completed ?? 0} />
            <Stat label="Cost (USD)" value={formatUsd(usage.cost_usd_total ?? 0)} />
            <Stat label="Kind" value={usage.kind ?? '--'} />
          </div>

          <BreakdownTable title="By kit" rows={breakdownRows(usage.by_kit)} keyLabel="Kit" />
          <BreakdownTable
            title="By employee" rows={breakdownRows(usage.by_employee)} keyLabel="Employee"
            showLinksMinted
          />
          <BreakdownTable title="By language" rows={breakdownRows(usage.by_language)} keyLabel="Language" />
        </div>
      )}
    </div>
  );
};

const Stat: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="border border-gray-200 rounded p-3">
    <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
    <p className="mt-1 text-base font-medium text-gray-900">{value}</p>
  </div>
);

const BreakdownTable: React.FC<{
  title: string;
  keyLabel: string;
  rows: Array<{ key: string; sessions: number; cost_usd: number; links_minted?: number }>;
  /** by_employee only (bd polyglot-pdf-he3lt): render links_minted as a
   * fourth column. by_kit/by_language never carry this field (see
   * usage_rollups.record_link_minted's own docstring), so the column is
   * opt-in rather than derived from row contents -- an employee who has
   * only ever minted (never had a completed session) still gets a row with
   * sessions=0 and a real links_minted count, and the column must show for
   * that table even though every OTHER breakdown table never has one. */
  showLinksMinted?: boolean;
}> = ({ title, keyLabel, rows, showLinksMinted }) => (
  <div>
    <h3 className="text-sm font-medium text-gray-900">{title}</h3>
    <div className="mt-2 overflow-x-auto">
      <table className="min-w-full text-sm text-left">
        <thead>
          <tr className="border-b border-gray-200 text-gray-500">
            <th className="py-1 pr-4">{keyLabel}</th>
            <th className="py-1 pr-4">Sessions</th>
            <th className="py-1 pr-4">Cost (USD)</th>
            {showLinksMinted && <th className="py-1 pr-4">Links minted</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-gray-100">
              <td className="py-1 pr-4">{row.key}</td>
              <td className="py-1 pr-4">{row.sessions}</td>
              <td className="py-1 pr-4">{formatUsd(row.cost_usd)}</td>
              {showLinksMinted && <td className="py-1 pr-4">{row.links_minted ?? 0}</td>}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={showLinksMinted ? 4 : 3} className="py-2 text-gray-500">No breakdown data.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  </div>
);
