import React from 'react';
import type { AlertRow as AlertRowData } from '../utils/adminApi';

interface AlertRowProps {
  alert: AlertRowData;
  /** True while THIS row's acknowledge PATCH is in flight -- disables the
   * button and swaps its label, mirroring AlertsPage.tsx's original
   * per-row `busyId` gate (extracted here, not duplicated). */
  busy: boolean;
  /** A message from a failed acknowledge on THIS row (e.g. a 409's "already
   * acknowledged by X" text) -- rendered next to the button, never a
   * generic banner. `undefined`/`null` renders nothing. */
  rowError?: string | null;
  onAcknowledge: (alert: AlertRowData) => void;
  /** Render a Firm column (the operator-wide AlertsPage, which lists
   * alerts across every firm). Omit it on a page already scoped to one
   * firm (FirmDetailPage's alerts section) -- the firm is redundant there
   * and the bead's row shows only kind/level/time/status/actions. */
  showFirm?: boolean;
}

function formatTs(ts: number | null): string {
  if (ts === null) return '--';
  return new Date(ts * 1000).toISOString();
}

/**
 * ONE alert `<tr>` renderer (bd polyglot-pdf-362nk), extracted out of
 * AlertsPage.tsx (bd polyglot-pdf-i6dlb, E3.11b) so FirmDetailPage's new
 * alerts section can reuse the exact same kind/level/plain-text rendering
 * instead of a second copy of it (exit criterion 2: "AlertsPage and
 * FirmDetailPage share one row component"). Byte-for-byte the same markup
 * AlertsPage rendered inline before this bead -- callers own the
 * surrounding `<table>`/`<thead>`, this component owns only the `<tr>`.
 *
 * The Acknowledge button's disabled/busy/label logic is unchanged from the
 * original inline version: disabled when THIS row is mid-flight (`busy`)
 * or already acknowledged (`alert.acknowledged_by` truthy); callers are
 * responsible for calling the PATCH exactly once per click (the
 * `busy`/`onAcknowledge` split mirrors AlertsPage's own `busyId`/
 * `handleAcknowledge` pattern) and for not re-invoking `onAcknowledge`
 * while `busy` is already true.
 */
export const AlertRow: React.FC<AlertRowProps> = ({
  alert, busy, rowError, onAcknowledge, showFirm = false,
}) => {
  return (
    <tr className="border-b border-gray-100">
      <td className="py-1 pr-4">{alert.kind}</td>
      <td className="py-1 pr-4">
        <span
          className={
            'inline-block rounded px-2 py-0.5 text-xs font-medium ' +
            (alert.level === 'critical' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800')
          }
        >
          {alert.level}
        </span>
      </td>
      {showFirm && <td className="py-1 pr-4">{alert.firm_id ?? ''}</td>}
      <td className="py-1 pr-4">{formatTs(alert.ts)}</td>
      <td className="py-1 pr-4">
        {alert.acknowledged_by
          ? 'Acknowledged by ' + alert.acknowledged_by
          : 'Unacknowledged'}
      </td>
      <td className="py-1 pr-4">
        <button
          type="button"
          className="btn border border-gray-300"
          disabled={busy || Boolean(alert.acknowledged_by)}
          onClick={() => onAcknowledge(alert)}
        >
          {busy ? 'Acknowledging...' : 'Acknowledge'}
        </button>
        {rowError && (
          <p className="mt-1 text-xs text-red-600">{rowError}</p>
        )}
      </td>
    </tr>
  );
};
