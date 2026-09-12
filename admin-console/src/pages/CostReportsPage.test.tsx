/**
 * CostReportsPage (bd polyglot-pdf-i6dlb, E3.11b). Pins the exit criterion:
 * "month range + group-by over GET /admin/reports/cost, plus an Income tab
 * over GET /admin/reports/income; both carry a visible delayed label
 * driven by the response's delayed flag, and refuse to submit a range
 * wider than 12 months client-side with the same message the server
 * returns" (mocked API, mutation-verified).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CostReportsPage } from './CostReportsPage';
import { AuthError, getCostReport, getIncomeReport } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return { ...actual, getCostReport: vi.fn(), getIncomeReport: vi.fn() };
});

const noAuthExpired = () => false;

const COST_ROW = {
  month: '2026-09', firm_id: 'firm-a', channel: 'demo', usage_kind: 'live_voice',
  call_count: 10, cost_usd: 5.5,
};

const INCOME_ROW = {
  month: '2026-09', entry_type: 'purchase', channel: null, entry_count: 2, usd_amount: 100,
};

function setRange(from: string, to: string) {
  fireEvent.change(screen.getByLabelText('From'), { target: { value: from } });
  fireEvent.change(screen.getByLabelText('To'), { target: { value: to } });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CostReportsPage', () => {
  it('runs the cost report with the chosen range, group_by, and channel', async () => {
    vi.mocked(getCostReport).mockResolvedValue({
      group_by: 'firm', from: '2026-01', to: '2026-09', channel: 'demo',
      rows: [COST_ROW], delayed: false, note: '',
    });
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    setRange('2026-01', '2026-09');
    fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'demo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    await waitFor(() => expect(getCostReport).toHaveBeenCalledTimes(1));
    expect(getCostReport).toHaveBeenCalledWith('firm', '2026-01', '2026-09', { channel: 'demo' });
  });

  it('refuses client-side a range wider than 12 months, with the server-matching message', async () => {
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    setRange('2026-01', '2027-02'); // 13 calendar months inclusive
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    expect(await screen.findByTestId('range-error')).toHaveTextContent(
      'the range from 2026-01 to 2027-02 spans more than 12 months; narrow it and query again',
    );
    expect(getCostReport).not.toHaveBeenCalled();
  });

  it('a range of exactly 12 months is allowed (the ceiling is inclusive)', async () => {
    vi.mocked(getCostReport).mockResolvedValue({
      group_by: 'firm', from: '2026-01', to: '2026-12', channel: null,
      rows: [], delayed: false, note: '',
    });
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    setRange('2026-01', '2026-12');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    await waitFor(() => expect(getCostReport).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('range-error')).not.toBeInTheDocument();
  });

  it('refuses client-side when to precedes from', async () => {
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    setRange('2026-06', '2026-01');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    expect(await screen.findByTestId('range-error')).toHaveTextContent(
      'to (2026-01) must not be before from (2026-06)',
    );
    expect(getCostReport).not.toHaveBeenCalled();
  });

  it('shows the delayed label only when the response says delayed: true', async () => {
    vi.mocked(getCostReport).mockResolvedValue({
      group_by: 'firm', from: '2026-09', to: '2026-09', channel: null,
      rows: [COST_ROW], delayed: true, note: 'Cost figures come from a delayed sink.',
    });
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    setRange('2026-09', '2026-09');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    expect(await screen.findByTestId('cost-delayed-note')).toHaveTextContent(
      'Cost figures come from a delayed sink.',
    );
  });

  it('does not show the delayed label when the response says delayed: false', async () => {
    vi.mocked(getCostReport).mockResolvedValue({
      group_by: 'firm', from: '2026-09', to: '2026-09', channel: null,
      rows: [COST_ROW], delayed: false, note: '',
    });
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    setRange('2026-09', '2026-09');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    await screen.findByTestId('cost-table');
    expect(screen.queryByTestId('cost-delayed-note')).not.toBeInTheDocument();
  });

  it('renders "--" for a null cost_usd instead of throwing (BigQuery SUM over all-NULL inputs)', async () => {
    // sql/telemetry_views.sql's cost views have no COALESCE around
    // SUM(SAFE_CAST(...)), so a group whose cost-bearing events all lack
    // cost_estimate_usd comes back with cost_usd: null while the row still
    // exists (COUNT(*) does not depend on that column). formatUsd calling
    // .toFixed() unconditionally used to throw here, and with no error
    // boundary in admin-console/src that unmounted the entire app, not just
    // this row (finding 2, bd polyglot-pdf-i6dlb review round).
    vi.mocked(getCostReport).mockResolvedValue({
      group_by: 'firm', from: '2026-09', to: '2026-09', channel: null,
      rows: [{ ...COST_ROW, cost_usd: null }], delayed: false, note: '',
    });
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    setRange('2026-09', '2026-09');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    await screen.findByTestId('cost-table');
    expect(screen.getByText('--')).toBeInTheDocument();
  });
});

describe('CostReportsPage income tab', () => {
  async function switchToIncome() {
    fireEvent.click(screen.getByRole('button', { name: 'Income' }));
  }

  it('runs the income report with the chosen range, no channel filter', async () => {
    vi.mocked(getIncomeReport).mockResolvedValue({
      from: '2026-01', to: '2026-09', rows: [INCOME_ROW], delayed: false, note: '',
    });
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    await switchToIncome();
    setRange('2026-01', '2026-09');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    await waitFor(() => expect(getIncomeReport).toHaveBeenCalledTimes(1));
    expect(getIncomeReport).toHaveBeenCalledWith('2026-01', '2026-09');
    expect(getCostReport).not.toHaveBeenCalled();
  });

  it('renders "--" for a null usd_amount instead of throwing (BigQuery SUM over all-NULL inputs)', async () => {
    // Same NULL-propagation shape as CostReportRow.cost_usd: income_month's
    // SUM(SAFE_CAST(jsonPayload.usd_amount AS FLOAT64)) has no COALESCE
    // either, so a group whose entries all fail the cast returns
    // usd_amount: null while the row still exists.
    vi.mocked(getIncomeReport).mockResolvedValue({
      from: '2026-09', to: '2026-09',
      rows: [{ ...INCOME_ROW, usd_amount: null }], delayed: false, note: '',
    });
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    await switchToIncome();
    setRange('2026-09', '2026-09');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    await screen.findByTestId('income-table');
    expect(screen.getByText('--')).toBeInTheDocument();
  });

  it('the income tab has no channel selector at all', async () => {
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    await switchToIncome();
    expect(screen.queryByLabelText('Channel')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Group by')).not.toBeInTheDocument();
  });

  it('income also refuses a range over 12 months client-side with the server-matching message', async () => {
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    await switchToIncome();
    setRange('2026-01', '2027-02');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    expect(await screen.findByTestId('range-error')).toHaveTextContent(
      'the range from 2026-01 to 2027-02 spans more than 12 months; narrow it and query again',
    );
    expect(getIncomeReport).not.toHaveBeenCalled();
  });

  it('shows the delayed label for income when the response says delayed: true', async () => {
    vi.mocked(getIncomeReport).mockResolvedValue({
      from: '2026-09', to: '2026-09', rows: [INCOME_ROW], delayed: true,
      note: 'Income figures come from a delayed sink.',
    });
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    await switchToIncome();
    setRange('2026-09', '2026-09');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    expect(await screen.findByTestId('income-delayed-note')).toHaveTextContent(
      'Income figures come from a delayed sink.',
    );
  });

  it('routes an AuthError to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(getIncomeReport).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<CostReportsPage onAuthExpired={onAuthExpired} />);
    await switchToIncome();
    setRange('2026-09', '2026-09');
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Sign-in required')).not.toBeInTheDocument();
  });
});
