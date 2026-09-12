/**
 * AlertsPage (bd polyglot-pdf-i6dlb, E3.11b). Pins the exit criterion:
 * "list with kind / level / firm filters, an unacknowledged-only default,
 * and an Acknowledge button that calls the PATCH exactly once and re-reads
 * the list; a 409 on a second acknowledge shows as already acknowledged"
 * (mocked API, mutation-verified).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { AlertsPage } from './AlertsPage';
import { AuthError, listAlerts, acknowledgeAlert } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return { ...actual, listAlerts: vi.fn(), acknowledgeAlert: vi.fn() };
});

const noAuthExpired = () => false;

const UNACK_ALERT = {
  id: 'alert-1', firm_id: 'firm-a', kind: 'link_exhausted' as const, level: 'warning' as const,
  ts: 1_700_000_000, context: null, acknowledged_by: null, acknowledged_at: null,
  emailed_at: null, expire_at: null,
};

const ACK_ALERT = {
  ...UNACK_ALERT, id: 'alert-2', acknowledged_by: 'admin@example.com', acknowledged_at: 1_700_000_100,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listAlerts).mockResolvedValue({ alerts: [UNACK_ALERT] });
});

describe('AlertsPage', () => {
  it('defaults to unacknowledged-only on load', async () => {
    render(<AlertsPage onAuthExpired={noAuthExpired} />);
    await waitFor(() => expect(listAlerts).toHaveBeenCalledWith({
      acknowledged: false, firmId: undefined, kind: undefined,
    }));
    expect(screen.getByLabelText('Status')).toHaveValue('unacknowledged');
  });

  it('filter form re-queries with the chosen kind/firm/status filters', async () => {
    render(<AlertsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('link_exhausted');

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'all' } });
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'credit_low' } });
    fireEvent.change(screen.getByLabelText('Firm ID'), { target: { value: 'firm-b' } });
    fireEvent.click(screen.getByRole('button', { name: 'Filter' }));

    await waitFor(() => expect(listAlerts).toHaveBeenCalledWith({
      acknowledged: undefined, firmId: 'firm-b', kind: 'credit_low',
    }));
  });

  it('acknowledge calls the PATCH exactly once, then re-reads the list', async () => {
    vi.mocked(acknowledgeAlert).mockResolvedValue({
      id: 'alert-1', acknowledged_by: 'admin@example.com', acknowledged_at: 1_700_000_200,
      request_id: 'req-1',
    });
    render(<AlertsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('link_exhausted');

    vi.mocked(listAlerts).mockResolvedValueOnce({
      alerts: [{ ...UNACK_ALERT, acknowledged_by: 'admin@example.com', acknowledged_at: 1_700_000_200 }],
    });

    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }));

    await waitFor(() => expect(acknowledgeAlert).toHaveBeenCalledTimes(1));
    expect(acknowledgeAlert).toHaveBeenCalledWith('alert-1');
    // Initial load + the post-acknowledge re-read.
    await waitFor(() => expect(listAlerts).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByText(/Acknowledged by admin@example.com/)).toBeInTheDocument());
  });

  it('a 409 on a second acknowledge shows as already acknowledged, not a generic error', async () => {
    vi.mocked(acknowledgeAlert).mockRejectedValueOnce(
      new Error('alert alert-1 was already acknowledged by someone-else@example.com'),
    );
    render(<AlertsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('link_exhausted');

    const table = screen.getByTestId('alerts-table');
    const row = within(table).getByText('link_exhausted').closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: 'Acknowledge' }));

    expect(await screen.findByText(
      'alert alert-1 was already acknowledged by someone-else@example.com',
    )).toBeInTheDocument();
    // A failed acknowledge does not trigger a second re-read beyond the initial load.
    expect(listAlerts).toHaveBeenCalledTimes(1);
  });

  it('an already-acknowledged row disables the Acknowledge button', async () => {
    vi.mocked(listAlerts).mockResolvedValue({ alerts: [ACK_ALERT] });
    render(<AlertsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('link_exhausted');

    expect(screen.getByRole('button', { name: 'Acknowledge' })).toBeDisabled();
  });

  it('routes an AuthError on load to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(listAlerts).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<AlertsPage onAuthExpired={onAuthExpired} />);

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Sign-in required')).not.toBeInTheDocument();
  });
});
