import React from 'react';
import {
  getFirmUsage, listFirms, MONITORING_CHANNELS,
  type FirmUsagePage, type MonitoringChannel, type FirmRow,
} from '../utils/adminApi';

interface UsagePageProps {
  onAuthExpired: (err: unknown) => boolean;
}

function currentMonth(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return String(now.getFullYear()) + '-' + month;
}

function breakdownRows(
  breakdown: Record<string, { sessions?: number; cost_usd?: number }> | null | undefined,
): Array<{ key: string; sessions: number; cost_usd: number }> {
  if (!breakdown) return [];
  return Object.keys(breakdown)
    .sort()
    .map((key) => ({
      key,
      sessions: breakdown[key]?.sessions ?? 0,
      cost_usd: breakdown[key]?.cost_usd ?? 0,
    }));
}

function formatUsd(value: number): string {
  return value.toFixed(2);
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
 * quiet month, so this page treats sessions_completed === null as the
 * "no data" signal and renders a dedicated empty-state message.
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
    try {
      const result = await getFirmUsage(firmId, month, channel);
      setPage(result);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the firm usage');
      setPage(null);
    } finally {
      setLoading(false);
    }
  }, [firmId, month, channel, onAuthExpired]);

  const usage = page?.usage ?? null;
  const hasData = usage !== null && usage.sessions_completed !== null;

  return (
    <div data-testid="usage-page" className="max-w-4xl">
      <h2 className="text-lg font-semibold text-gray-900">Usage</h2>

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

      {page && !hasData && (
        <p className="mt-6 text-gray-500" data-testid="usage-no-data">
          No usage recorded for {page.firm_id} in {page.month} ({page.channel}).
        </p>
      )}

      {page && hasData && usage && (
        <div className="mt-6 space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <Stat label="Sessions completed" value={usage.sessions_completed ?? 0} />
            <Stat label="Connections ended" value={usage.connections_ended ?? 0} />
            <Stat label="Links opened" value={usage.links_opened ?? 0} />
            <Stat label="Links completed" value={usage.links_completed ?? 0} />
            <Stat label="Cost (USD)" value={formatUsd(usage.cost_usd_total ?? 0)} />
            <Stat label="Kind" value={usage.kind ?? '--'} />
          </div>

          <BreakdownTable title="By kit" rows={breakdownRows(usage.by_kit)} keyLabel="Kit" />
          <BreakdownTable title="By employee" rows={breakdownRows(usage.by_employee)} keyLabel="Employee" />
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
  rows: Array<{ key: string; sessions: number; cost_usd: number }>;
}> = ({ title, keyLabel, rows }) => (
  <div>
    <h3 className="text-sm font-medium text-gray-900">{title}</h3>
    <div className="mt-2 overflow-x-auto">
      <table className="min-w-full text-sm text-left">
        <thead>
          <tr className="border-b border-gray-200 text-gray-500">
            <th className="py-1 pr-4">{keyLabel}</th>
            <th className="py-1 pr-4">Sessions</th>
            <th className="py-1 pr-4">Cost (USD)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-gray-100">
              <td className="py-1 pr-4">{row.key}</td>
              <td className="py-1 pr-4">{row.sessions}</td>
              <td className="py-1 pr-4">{formatUsd(row.cost_usd)}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={3} className="py-2 text-gray-500">No breakdown data.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  </div>
);
