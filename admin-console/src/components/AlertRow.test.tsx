/**
 * AlertRow (bd polyglot-pdf-362nk) -- the shared alert `<tr>` renderer
 * extracted out of AlertsPage.tsx so FirmDetailPage's alerts section can
 * reuse it. Two kinds of tests: the component's own render/interaction
 * behavior, and a SOURCE-LEVEL check (exit criterion 2's own wording --
 * "a test asserts both import it") that both AlertsPage.tsx and
 * FirmDetailPage.tsx actually import THIS module, not a parallel copy.
 */
import { describe, it, expect, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { AlertRow } from './AlertRow';
import type { AlertRow as AlertRowData } from '../utils/adminApi';

const __dirname = dirname(fileURLToPath(import.meta.url));

const UNACK_ALERT: AlertRowData = {
  id: 'alert-1', firm_id: 'firm-a', kind: 'link_exhausted', level: 'warning',
  ts: 1_700_000_000, context: null, acknowledged_by: null, acknowledged_at: null,
  emailed_at: null, expire_at: null,
};

const ACK_ALERT: AlertRowData = {
  ...UNACK_ALERT, id: 'alert-2', acknowledged_by: 'admin@example.com',
};

function renderRow(props: Partial<React.ComponentProps<typeof AlertRow>> = {}) {
  return render(
    <table>
      <tbody>
        <AlertRow
          alert={UNACK_ALERT}
          busy={false}
          onAcknowledge={() => {}}
          {...props}
        />
      </tbody>
    </table>,
  );
}

describe('AlertRow', () => {
  it('renders kind, level, formatted time, and Unacknowledged status', () => {
    renderRow();
    expect(screen.getByText('link_exhausted')).toBeInTheDocument();
    expect(screen.getByText('warning')).toBeInTheDocument();
    expect(screen.getByText('Unacknowledged')).toBeInTheDocument();
    expect(screen.getByText('2023-11-14T22:13:20.000Z')).toBeInTheDocument();
  });

  it('renders "Acknowledged by X" and disables the button for an acknowledged alert', () => {
    renderRow({ alert: ACK_ALERT });
    expect(screen.getByText('Acknowledged by admin@example.com')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Acknowledge' })).toBeDisabled();
  });

  it('disables the button and swaps its label while busy', () => {
    renderRow({ busy: true });
    const button = screen.getByRole('button', { name: 'Acknowledging...' });
    expect(button).toBeDisabled();
  });

  it('calls onAcknowledge with the alert exactly once per click', () => {
    const onAcknowledge = vi.fn();
    renderRow({ onAcknowledge });
    screen.getByRole('button', { name: 'Acknowledge' }).click();
    expect(onAcknowledge).toHaveBeenCalledTimes(1);
    expect(onAcknowledge).toHaveBeenCalledWith(UNACK_ALERT);
  });

  it('renders a row-level error message next to the button when given one', () => {
    renderRow({ rowError: 'alert alert-1 was already acknowledged by someone-else@example.com' });
    expect(screen.getByText(
      'alert alert-1 was already acknowledged by someone-else@example.com',
    )).toBeInTheDocument();
  });

  it('renders no Firm column by default', () => {
    renderRow();
    expect(screen.queryByText('firm-a')).not.toBeInTheDocument();
  });

  it('renders a Firm column when showFirm is set', () => {
    renderRow({ showFirm: true });
    expect(screen.getByText('firm-a')).toBeInTheDocument();
  });

  it('AlertsPage.tsx and FirmDetailPage.tsx both import THIS component (exit criterion 2)', () => {
    const alertsPageSrc = readFileSync(
      resolve(__dirname, '../pages/AlertsPage.tsx'), 'utf-8',
    );
    const firmDetailPageSrc = readFileSync(
      resolve(__dirname, '../pages/FirmDetailPage.tsx'), 'utf-8',
    );
    const importsAlertRow = /import\s*\{\s*AlertRow\s*\}\s*from\s*'\.\.\/components\/AlertRow'/;
    expect(alertsPageSrc).toMatch(importsAlertRow);
    expect(firmDetailPageSrc).toMatch(importsAlertRow);
  });
});
