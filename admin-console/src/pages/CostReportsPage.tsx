import React from 'react';
import {
  getCostReport, getIncomeReport, COST_GROUP_BY, MONITORING_CHANNELS,
  MAX_REPORT_RANGE_MONTHS,
  type CostGroupBy, type CostReportRow, type IncomeReportRow, type MonitoringChannel,
} from '../utils/adminApi';

interface CostReportsPageProps {
  onAuthExpired: (err: unknown) => boolean;
}

type Tab = 'cost' | 'income';

function currentMonth(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return String(now.getFullYear()) + '-' + month;
}

/** Inclusive month-span in calendar months between two "YYYY-MM" strings
 * (mirrors report_routes.py's own _month_delta exactly: 2026-01 to
 * 2026-01 is 0, 2026-01 to 2026-12 is 11 -- i.e. 12 calendar months
 * inclusive). Returns null for a malformed value rather than throwing, so
 * an in-progress edit (an empty or partial month input) never crashes the
 * range check mid-keystroke. */
function monthDelta(from: string, to: string): number | null {
  const re = /^\d{4}-(0[1-9]|1[0-2])$/;
  if (!re.test(from) || !re.test(to)) return null;
  const [fy, fm] = from.split('-').map(Number);
  const [ty, tm] = to.split('-').map(Number);
  return (ty - fy) * 12 + (tm - fm);
}

/** THE SAME MESSAGE THE SERVER RETURNS (bead requirement: "refuse to
 * submit a range wider than 12 months client-side with the same message
 * the server returns") -- mirrors report_routes.py's _validated_range
 * refusal text verbatim (format, wording, and argument order), so an
 * operator sees an identical string whether the client catches it or the
 * 422 does. */
function rangeTooWideMessage(from: string, to: string): string {
  return 'the range from ' + from + ' to ' + to + ' spans more than '
    + MAX_REPORT_RANGE_MONTHS + ' months; narrow it and query again';
}

function formatUsd(value: number): string {
  return value.toFixed(2);
}

/**
 * Cost reports page (bd polyglot-pdf-i6dlb, E3.11b), driving
 * admin_backend/routes/report_routes.py's GET /admin/reports/cost and
 * GET /admin/reports/income over two tabs.
 *
 * BOTH TABS SHARE THE from/to MONTH RANGE STATE (one range for whichever
 * report is being viewed) -- group_by and channel apply to the cost tab
 * only (income has neither: report_routes.py's own income route refuses a
 * channel filter outright, and has no group_by concept at all).
 *
 * THE 12-MONTH CEILING IS ENFORCED CLIENT-SIDE FIRST (bead requirement:
 * "refuse to submit a range wider than 12 months client-side with the same
 * message the server returns") -- monthDelta/rangeTooWideMessage above
 * mirror report_routes.py's _validated_range exactly, so a range that
 * would 422 never reaches the network at all; the server's own 422 text
 * (surfaced via errorDetail) still governs any range shape this client
 * check does not anticipate (e.g. `to` before `from`, which this page also
 * checks client-side with the server's own wording).
 *
 * THE DELAYED LABEL IS DRIVEN BY THE RESPONSE'S OWN `delayed` FLAG (bead
 * requirement), never hard-coded to always show -- see adminApi.ts's
 * CostReportPage/IncomeReportPage docstrings for why this client reads the
 * flag rather than assuming BigQuery sink lag always applies.
 */
export const CostReportsPage: React.FC<CostReportsPageProps> = ({ onAuthExpired }) => {
  const [tab, setTab] = React.useState<Tab>('cost');
  const [from, setFrom] = React.useState(currentMonth());
  const [to, setTo] = React.useState(currentMonth());
  const [groupBy, setGroupBy] = React.useState<CostGroupBy>('firm');
  const [channel, setChannel] = React.useState<MonitoringChannel | ''>('');

  const [rangeError, setRangeError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [costRows, setCostRows] = React.useState<CostReportRow[] | null>(null);
  const [costDelayed, setCostDelayed] = React.useState(false);
  const [costNote, setCostNote] = React.useState('');

  const [incomeRows, setIncomeRows] = React.useState<IncomeReportRow[] | null>(null);
  const [incomeDelayed, setIncomeDelayed] = React.useState(false);
  const [incomeNote, setIncomeNote] = React.useState('');

  const validateRange = React.useCallback((): string | null => {
    const delta = monthDelta(from, to);
    if (delta === null) return null; // malformed input -- let the native month input's own validity handle it
    if (delta < 0) {
      return 'to (' + to + ') must not be before from (' + from + ')';
    }
    if (delta > MAX_REPORT_RANGE_MONTHS - 1) {
      return rangeTooWideMessage(from, to);
    }
    return null;
  }, [from, to]);

  const handleSubmit = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const rangeErr = validateRange();
    setRangeError(rangeErr);
    if (rangeErr) return;

    setLoading(true);
    setError(null);
    try {
      if (tab === 'cost') {
        const page = await getCostReport(groupBy, from, to, channel ? { channel } : {});
        setCostRows(page.rows);
        setCostDelayed(page.delayed);
        setCostNote(page.note);
      } else {
        const page = await getIncomeReport(from, to);
        setIncomeRows(page.rows);
        setIncomeDelayed(page.delayed);
        setIncomeNote(page.note);
      }
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the report');
    } finally {
      setLoading(false);
    }
  }, [tab, from, to, groupBy, channel, validateRange, onAuthExpired]);

  const handleTabChange = React.useCallback((next: Tab) => {
    setTab(next);
    setError(null);
    setRangeError(null);
  }, []);

  const groupColumnLabel = groupBy === 'firm' ? 'Firm' : groupBy === 'kit' ? 'Kit' : 'Employee';
  const groupColumnKey = groupBy === 'firm' ? 'firm_id' : groupBy === 'kit' ? 'kit_id' : 'employee_id';

  return (
    <div data-testid="cost-reports-page" className="max-w-5xl">
      <h2 className="text-lg font-semibold text-gray-900">Cost &amp; income reports</h2>

      <nav className="mt-4 flex gap-4 text-sm border-b border-gray-200">
        <button
          type="button"
          className={
            'py-2 border-b-2 ' +
            (tab === 'cost' ? 'border-primary-600 text-primary-700 font-medium' : 'border-transparent text-gray-500')
          }
          onClick={() => handleTabChange('cost')}
        >
          Cost
        </button>
        <button
          type="button"
          className={
            'py-2 border-b-2 ' +
            (tab === 'income' ? 'border-primary-600 text-primary-700 font-medium' : 'border-transparent text-gray-500')
          }
          onClick={() => handleTabChange('income')}
        >
          Income
        </button>
      </nav>

      <form onSubmit={(e) => void handleSubmit(e)} className="mt-4 flex flex-wrap items-end gap-2 text-sm">
        <div>
          <label className="block text-gray-700" htmlFor="cost-from">From</label>
          <input
            id="cost-from"
            type="month"
            required
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-gray-700" htmlFor="cost-to">To</label>
          <input
            id="cost-to"
            type="month"
            required
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
        {tab === 'cost' && (
          <>
            <div>
              <label className="block text-gray-700" htmlFor="cost-group-by">Group by</label>
              <select
                id="cost-group-by"
                className="mt-1 border border-gray-300 rounded px-2 py-1"
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value as CostGroupBy)}
              >
                {COST_GROUP_BY.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-gray-700" htmlFor="cost-channel">Channel</label>
              <select
                id="cost-channel"
                className="mt-1 border border-gray-300 rounded px-2 py-1"
                value={channel}
                onChange={(e) => setChannel(e.target.value as MonitoringChannel | '')}
              >
                <option value="">All channels</option>
                {MONITORING_CHANNELS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </>
        )}
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? 'Loading...' : 'Run report'}
        </button>
      </form>

      {rangeError && (
        <div className="mt-3 text-sm text-red-600" data-testid="range-error">{rangeError}</div>
      )}
      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}

      {tab === 'cost' && costRows && (
        <div className="mt-6">
          {costDelayed && (
            <p className="mb-2 text-xs text-amber-700" data-testid="cost-delayed-note">
              {costNote}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm text-left" data-testid="cost-table">
              <thead>
                <tr className="border-b border-gray-200 text-gray-500">
                  <th className="py-1 pr-4">Month</th>
                  <th className="py-1 pr-4">{groupColumnLabel}</th>
                  <th className="py-1 pr-4">Channel</th>
                  <th className="py-1 pr-4">Usage kind</th>
                  <th className="py-1 pr-4">Calls</th>
                  <th className="py-1 pr-4">Cost (USD)</th>
                </tr>
              </thead>
              <tbody>
                {costRows.map((row, i) => (
                  <tr key={i} className="border-b border-gray-100">
                    <td className="py-1 pr-4">{row.month}</td>
                    <td className="py-1 pr-4">{String(row[groupColumnKey] ?? '')}</td>
                    <td className="py-1 pr-4">{row.channel ?? 'all'}</td>
                    <td className="py-1 pr-4">{row.usage_kind ?? ''}</td>
                    <td className="py-1 pr-4">{row.call_count}</td>
                    <td className="py-1 pr-4">{formatUsd(row.cost_usd)}</td>
                  </tr>
                ))}
                {costRows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-4 text-gray-500">No cost data for this range.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'income' && incomeRows && (
        <div className="mt-6">
          {incomeDelayed && (
            <p className="mb-2 text-xs text-amber-700" data-testid="income-delayed-note">
              {incomeNote}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm text-left" data-testid="income-table">
              <thead>
                <tr className="border-b border-gray-200 text-gray-500">
                  <th className="py-1 pr-4">Month</th>
                  <th className="py-1 pr-4">Entry type</th>
                  <th className="py-1 pr-4">Count</th>
                  <th className="py-1 pr-4">USD amount</th>
                </tr>
              </thead>
              <tbody>
                {incomeRows.map((row, i) => (
                  <tr key={i} className="border-b border-gray-100">
                    <td className="py-1 pr-4">{row.month}</td>
                    <td className="py-1 pr-4">{row.entry_type}</td>
                    <td className="py-1 pr-4">{row.entry_count}</td>
                    <td className="py-1 pr-4">{formatUsd(row.usd_amount)}</td>
                  </tr>
                ))}
                {incomeRows.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-4 text-gray-500">No income data for this range.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
