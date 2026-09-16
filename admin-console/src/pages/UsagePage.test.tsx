/**
 * UsagePage (bd polyglot-pdf-i6dlb, E3.11b). Pins the exit criterion: "firm
 * picker + month picker, rendering the rollup doc's counters and the
 * by_kit / by_employee / by_language breakdowns as tables; a month with no
 * doc says so" (mocked API, mutation-verified).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { UsagePage } from './UsagePage';
import { AuthError, listFirms, getFirmUsage, getFirm } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return { ...actual, listFirms: vi.fn(), getFirmUsage: vi.fn(), getFirm: vi.fn() };
});

const noAuthExpired = () => false;

const FIRM_A = {
  firm_id: 'firm-a', name: 'Firm A', contact_email: 'a@example.com',
  kind: 'live' as const, status: 'active' as const, allowed_kits: [], balance_credits: 100,
  plan: { tier: 'starter' as const, monthly_credits: 35, rollover: false },
};

const NO_DATA_USAGE = {
  connections_ended: null, sessions_completed: null, cost_usd_total: null,
  links_opened: null, links_completed: null, links_minted: null,
  by_kit: null, by_employee: null,
  by_language: null, kind: null, channel: null,
};

const REAL_USAGE = {
  connections_ended: 5, sessions_completed: 4, cost_usd_total: 12.5,
  links_opened: 6, links_completed: 4, links_minted: 7,
  by_kit: { 'i-90': { sessions: 4, cost_usd: 12.5 } },
  by_employee: { emp1: { sessions: 4, cost_usd: 12.5, links_minted: 7 } },
  by_language: { 'zh-CN': { sessions: 2, cost_usd: 6.25 } },
  kind: 'live', channel: 'demo',
};

/** A bare FirmDetail with an empty ledger -- the "genuinely no activity"
 * default every test opts into unless it overrides `ledger` to pin the
 * links_minted-yet-no-rollup-doc empty-state case. */
function firmDetail(ledger: Array<{ ts: number }> = []) {
  return {
    firm_id: 'firm-a', name: 'Firm A', contact_email: 'a@example.com',
    kind: 'live' as const, status: 'active' as const, allowed_kits: [],
    balance_credits: 100,
    plan: { tier: 'starter' as const, monthly_credits: 35, rollover: false },
    ledger: ledger.map((row, i) => ({
      type: 'mint_debit', amount: -1, usd_amount: null, firm_kind: 'live' as const,
      channel: 'demo', balance_after: 99, actor: 'u1', actor_label: 'u1',
      reason: null, link_jti: 'jti' + i, kit_id: 'i-90', ...row,
    })),
    ledger_truncated: false,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listFirms).mockResolvedValue([FIRM_A]);
  // Default: no ledger activity at all, matching the plain "no data" case
  // most existing tests exercise. Tests pinning the "no sessions yet this
  // month" wording override this per-test.
  vi.mocked(getFirm).mockResolvedValue(firmDetail());
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

  it('a firm-month with real activity but zero completed sessions still renders the stats grid (not "no data")', async () => {
    // Every connection this month was abandoned/reconnected -- record_session_end
    // (backend/services/usage_rollups.py) only increments sessions_completed
    // inside its `if completed:` branch, so this is a real, non-null doc with
    // sessions_completed left null. Checking sessions_completed alone as the
    // "no data" signal would misreport this as an empty month, hiding the real
    // cost and connection counts (finding 1, bd polyglot-pdf-i6dlb review round).
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo',
      usage: {
        connections_ended: 5, sessions_completed: null, cost_usd_total: 12.5,
        links_opened: null, links_completed: null, links_minted: null,
        by_kit: null, by_employee: null,
        by_language: null, kind: 'live', channel: 'demo',
      },
    });
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    expect(screen.queryByTestId('usage-no-data')).not.toBeInTheDocument();
    await screen.findByText('Connections ended');
    expect(screen.getAllByText('5').length).toBeGreaterThan(0);
    expect(screen.getAllByText('12.50').length).toBeGreaterThan(0);
  });

  it('a firm-month with only link activity (no session data at all) still renders the stats grid', async () => {
    // _increment_firm_counter (record_link_opened / record_link_completed)
    // writes just links_opened/links_completed via merge=True, never touching
    // sessions_completed, connections_ended, or cost_usd_total.
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo',
      usage: {
        connections_ended: null, sessions_completed: null, cost_usd_total: null,
        links_opened: 3, links_completed: 1, links_minted: null,
        by_kit: null, by_employee: null,
        by_language: null, kind: null, channel: null,
      },
    });
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    expect(screen.queryByTestId('usage-no-data')).not.toBeInTheDocument();
    await screen.findByText('Links opened');
    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
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

  it('shows links_minted in the summary row and the by-employee table (bd polyglot-pdf-he3lt)', async () => {
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo', usage: REAL_USAGE,
    });
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    // "Links minted" appears TWICE by design: once as the summary Stat
    // label, once as the by-employee table's column header.
    expect(await screen.findAllByText('Links minted')).toHaveLength(2);
    // REAL_USAGE.links_minted=7 (summary) AND by_employee.emp1.links_minted=7
    // (breakdown table) -- both render the same digit, so at least two "7"s.
    expect(screen.getAllByText('7').length).toBeGreaterThanOrEqual(2);
    // by_kit/by_language never carry links_minted -- their tables must NOT
    // gain a fourth column just because the by-employee one did.
    const kitTable = screen.getByText('By kit').closest('div') as HTMLElement;
    expect(kitTable.querySelector('thead')?.textContent).not.toContain('Links minted');
  });

  it('a mint-only month (links_minted set, everything else null) renders the stats grid, not "no data" (bd polyglot-pdf-he3lt)', async () => {
    // record_link_minted writes ONLY links_minted (+ by_employee) before a
    // client ever opens the link -- the newest member of the same "real
    // activity with mostly-null counters" family links_opened/completed
    // already established.
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo',
      usage: {
        connections_ended: null, sessions_completed: null, cost_usd_total: null,
        links_opened: null, links_completed: null, links_minted: 2,
        by_kit: null, by_employee: { 'u-emp-a': { links_minted: 2 } },
        by_language: null, kind: null, channel: null,
      },
    });
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    expect(screen.queryByTestId('usage-no-data')).not.toBeInTheDocument();
    expect(screen.queryByTestId('usage-no-sessions-yet')).not.toBeInTheDocument();
    expect(await screen.findAllByText('Links minted')).toHaveLength(2);
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
  });

  it('a missing rollup doc WITH ledger activity that month says "no sessions yet" (bd polyglot-pdf-he3lt)', async () => {
    // The fresh-mint gap the bead calls out by name: the rollup write can
    // still be in flight (or, worst case, never landed) in the moments
    // right after a mint, but the mint's ledger entry always committed
    // first (same transaction as the debit) -- so ledger activity this
    // month is a reliable "something happened" signal even with no usage
    // doc yet.
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo', usage: NO_DATA_USAGE,
    });
    const septemberTs = Date.UTC(2026, 8, 10) / 1000; // 2026-09-10 UTC
    vi.mocked(getFirm).mockResolvedValue(firmDetail([{ ts: septemberTs }]));

    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    expect(await screen.findByTestId('usage-no-sessions-yet')).toHaveTextContent(
      'No sessions yet this month for firm-a in 2026-09 (demo)',
    );
    expect(screen.queryByTestId('usage-no-data')).not.toBeInTheDocument();
  });

  it('a missing rollup doc with ledger activity in a DIFFERENT month still says plain "no data" (bd polyglot-pdf-he3lt)', async () => {
    // Mutation: drop the tsInMonth() filter and treat ANY ledger row as
    // "activity this month" -- red (an August entry would wrongly produce
    // "no sessions yet" for a September query).
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo', usage: NO_DATA_USAGE,
    });
    const augustTs = Date.UTC(2026, 7, 10) / 1000; // 2026-08-10 UTC
    vi.mocked(getFirm).mockResolvedValue(firmDetail([{ ts: augustTs }]));

    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    expect(await screen.findByTestId('usage-no-data')).toHaveTextContent(
      'No usage recorded for firm-a in 2026-09 (demo)',
    );
    expect(screen.queryByTestId('usage-no-sessions-yet')).not.toBeInTheDocument();
  });

  it('a failed ledger check degrades to the plain "no data" message, not an error', async () => {
    // Best-effort: the secondary getFirm() call must never crash the page
    // or block the primary (already-successful) empty reading.
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo', usage: NO_DATA_USAGE,
    });
    vi.mocked(getFirm).mockRejectedValue(new Error('boom'));

    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    expect(await screen.findByTestId('usage-no-data')).toBeInTheDocument();
    expect(screen.queryByTestId('usage-no-sessions-yet')).not.toBeInTheDocument();
  });

  it('the ledger check runs ONLY when the usage doc is empty, never on the happy path', async () => {
    vi.mocked(getFirmUsage).mockResolvedValue({
      firm_id: 'firm-a', month: '2026-09', channel: 'demo', usage: REAL_USAGE,
    });
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    await loadUsage('2026-09');

    await screen.findByText('Sessions completed');
    expect(getFirm).not.toHaveBeenCalled();
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
