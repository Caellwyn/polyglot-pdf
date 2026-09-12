/**
 * UsagePage (bd polyglot-pdf-i6dlb, E3.11b). Pins the exit criterion: "firm
 * picker + month picker, rendering the rollup doc's counters and the
 * by_kit / by_employee / by_language breakdowns as tables; a month with no
 * doc says so" (mocked API, mutation-verified).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { UsagePage } from './UsagePage';
import { AuthError, listFirms, getFirmUsage } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return { ...actual, listFirms: vi.fn(), getFirmUsage: vi.fn() };
});

const noAuthExpired = () => false;

const FIRM_A = {
  firm_id: 'firm-a', name: 'Firm A', contact_email: 'a@example.com',
  kind: 'live' as const, status: 'active' as const, allowed_kits: [], balance_credits: 100,
};

const NO_DATA_USAGE = {
  connections_ended: null, sessions_completed: null, cost_usd_total: null,
  links_opened: null, links_completed: null, by_kit: null, by_employee: null,
  by_language: null, kind: null, channel: null,
};

const REAL_USAGE = {
  connections_ended: 5, sessions_completed: 4, cost_usd_total: 12.5,
  links_opened: 6, links_completed: 4,
  by_kit: { 'i-90': { sessions: 4, cost_usd: 12.5 } },
  by_employee: { emp1: { sessions: 4, cost_usd: 12.5 } },
  by_language: { 'zh-CN': { sessions: 2, cost_usd: 6.25 } },
  kind: 'live', channel: 'demo',
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listFirms).mockResolvedValue([FIRM_A]);
});

async function loadUsage(month = '2026-09') {
  await screen.findByText('Firm A');
  fireEvent.change(screen.getByLabelText('Firm'), { target: { value: 'firm-a' } });
  fireEvent.change(screen.getByLabelText('Month'), { target: { value: month } });
  fireEvent.click(screen.getByRole('button', { name: 'Load' }));
  await waitFor(() => expect(getFirmUsage).toHaveBeenCalled());
}

describe('UsagePage', () => {
  it('loads the firm list on mount', async () => {
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await waitFor(() => expect(listFirms).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Firm A')).toBeInTheDocument();
  });

  it('calls getFirmUsage with the chosen firm, month, and default channel', async () => {
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo', usage: REAL_USAGE,
    });
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    expect(getFirmUsage).toHaveBeenCalledWith('firm-a', '2026-09', 'demo');
    expect(getFirmUsage).toHaveBeenCalledTimes(1);
  });

  it('a month with no rollup doc (all-null usage) says so explicitly', async () => {
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo', usage: NO_DATA_USAGE,
    });
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    expect(await screen.findByTestId('usage-no-data')).toHaveTextContent(
      'No usage recorded for firm-a in 2026-09 (demo)',
    );
    // Never a table of zeros for a quiet month.
    expect(screen.queryByText('Sessions completed')).not.toBeInTheDocument();
  });

  it('renders the counters and the by_kit / by_employee / by_language breakdowns as tables', async () => {
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo', usage: REAL_USAGE,
    });
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    await screen.findByText('Sessions completed');
    expect(screen.getAllByText('4').length).toBeGreaterThan(0); // sessions_completed stat
    expect(screen.getAllByText('12.50').length).toBeGreaterThan(0); // formatted USD, two decimals
    expect(screen.getByText('i-90')).toBeInTheDocument(); // by_kit key
    expect(screen.getByText('emp1')).toBeInTheDocument(); // by_employee key
    expect(screen.getByText('zh-CN')).toBeInTheDocument(); // by_language key (hyphenated)
  });

  it('routes an AuthError on load to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(getFirmUsage).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<UsagePage onAuthExpired={onAuthExpired} />);
    await loadUsage('2026-09');

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Sign-in required')).not.toBeInTheDocument();
  });

  it('shows the server error message on a failed load', async () => {
    vi.mocked(getFirmUsage).mockRejectedValueOnce(new Error('month is required and must be YYYY-MM'));
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    expect(await screen.findByText('month is required and must be YYYY-MM')).toBeInTheDocument();
  });
});
