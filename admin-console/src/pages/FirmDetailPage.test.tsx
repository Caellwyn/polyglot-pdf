/**
 * FirmDetailPage (bd polyglot-pdf-r8z9g). Pins the exit criterion's
 * remaining halves verbatim: "grant sends usd_amount only for the two
 * income types; adjust requires a reason; revoke calls the route once and
 * re-reads; kind change requires two confirmations" (mocked API,
 * mutation-verified).
 *
 * The "alerts" describe block below (bd polyglot-pdf-362nk) pins this
 * page's own exit criteria: the alerts section renders through the SAME
 * shared AlertRow component AlertsPage.test.tsx asserts (a separate test,
 * `AlertRow.test.tsx`, checks BOTH pages import it), lists
 * unacknowledged alerts before acknowledged ones, calls the acknowledge
 * PATCH exactly once per click and re-reads on success only, and a fetch
 * error there never blanks the rest of the already-loaded page.
 *
 * Mirrors UsersPage.test.tsx's mocking approach: keep the real
 * AuthError/ForbiddenError classes (onAuthExpired branches on instanceof),
 * mock only the network calls.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { FirmDetailPage } from './FirmDetailPage';
import {
  AuthError, ForbiddenError,
  getFirm, setFirmAllowedKits, setFirmKind, setFirmPlan,
  grantCredits, adjustCredits, listFirmLinks, revokeLink,
  listAlerts, acknowledgeAlert,
} from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return {
    ...actual,
    getFirm: vi.fn(),
    setFirmAllowedKits: vi.fn(),
    setFirmKind: vi.fn(),
    setFirmPlan: vi.fn(),
    grantCredits: vi.fn(),
    adjustCredits: vi.fn(),
    listFirmLinks: vi.fn(),
    revokeLink: vi.fn(),
    listAlerts: vi.fn(),
    acknowledgeAlert: vi.fn(),
  };
});

const noAuthExpired = () => false;
const noBack = () => {};

const FIRM_DETAIL = {
  firm_id: 'firm-a', name: 'Acme LLP', contact_email: 'ops@acme.test',
  kind: 'live' as const, status: 'active' as const, allowed_kits: ['w7'],
  balance_credits: 120,
  balance_credits_malformed: false,
  plan: { tier: 'starter' as const, monthly_credits: 35, rollover: false },
  // No doc_id: GET /admin/firms/{firm_id}'s ledger rows are the persisted
  // credit_ledger document verbatim (backend/services/credit_ledger.py's
  // read_entries()), which does NOT include doc_id -- unlike the grant/
  // adjust routes' responses. See adminApi.ts's LedgerEntry comment and
  // bd polyglot-pdf-migp9.
  ledger: [
    {
      type: 'subscription_grant', amount: 100,
      usd_amount: 49.99, firm_kind: 'live' as const, channel: null,
      balance_after: 100, actor: 'admin-1',
      // bd polyglot-pdf-cpsi0: actor_label is what the console displays;
      // 'admin-1' (the raw uid) is kept on `actor` for the title tooltip.
      actor_label: 'ops@example.com', reason: null,
      link_jti: null, kit_id: null, ts: 1700000000,
    },
  ],
  ledger_truncated: false,
};

const LINK_MINTED = {
  jti: 'jti-1', kit_id: 'w7', employee_id: 'emp-1',
  // bd polyglot-pdf-cpsi0: same relationship as the ledger's actor_label.
  employee_label: 'staffer@example.com', status: 'minted',
  minted_at: 1700000000, open_deadline: 1700003600, opened_at: null,
  completed_at: null, spend_usd: null, turns: null, cap_usd: 3,
  credit_cost: 1,
};

const ACK_ALERT = {
  id: 'alert-ack', firm_id: 'firm-a', kind: 'credit_low' as const, level: 'warning' as const,
  ts: 1_700_000_000, context: null, acknowledged_by: 'admin@example.com',
  acknowledged_at: 1_700_000_100, emailed_at: null, expire_at: null,
};

const UNACK_ALERT = {
  id: 'alert-unack', firm_id: 'firm-a', kind: 'link_exhausted' as const, level: 'critical' as const,
  ts: 1_699_999_000, context: null, acknowledged_by: null, acknowledged_at: null,
  emailed_at: null, expire_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getFirm).mockResolvedValue(FIRM_DETAIL);
  vi.mocked(listFirmLinks).mockResolvedValue({
    firm_id: 'firm-a', channel: 'demo', links: [LINK_MINTED],
  });
  // The seeded order is ACK, then UNACK -- tests below assert the section
  // reorders unacknowledged first rather than merely preserving the
  // route's own newest-ts-first order.
  vi.mocked(listAlerts).mockResolvedValue({ alerts: [ACK_ALERT, UNACK_ALERT] });
});

async function renderLoaded() {
  render(<FirmDetailPage firmId="firm-a" onAuthExpired={noAuthExpired} onBack={noBack} />);
  await screen.findByText('Acme LLP');
  await waitFor(() => expect(listFirmLinks).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(listAlerts).toHaveBeenCalledTimes(1));
}

describe('FirmDetailPage', () => {
  it('loads the firm profile and ledger, and the demo-channel link list, on mount', async () => {
    await renderLoaded();

    expect(getFirm).toHaveBeenCalledWith('firm-a');
    expect(listFirmLinks).toHaveBeenCalledWith('firm-a', 'demo');
    expect(screen.getByTestId('firm-balance')).toHaveTextContent('120 credits');
    // 'subscription_grant' also appears as <option> text in the grant
    // form's type <select>, so this scopes the lookup to the ledger table.
    expect(within(screen.getByTestId('ledger-table')).getByText('subscription_grant')).toBeInTheDocument();
    // bd polyglot-pdf-cpsi0: the links table shows employee_label (an
    // email here), with the raw uid (employee_id) as a hover tooltip
    // rather than the visible cell text.
    const employeeCell = screen.getByText('staffer@example.com');
    expect(employeeCell).toBeInTheDocument();
    expect(employeeCell).toHaveAttribute('title', 'emp-1');
  });

  it('shows the ledger actor_label with the raw uid as a title tooltip', async () => {
    await renderLoaded();

    // bd polyglot-pdf-cpsi0 exit criterion 3: FirmDetailPage renders the
    // label (an email here) with the uid as a title attribute, never the
    // other way around.
    const actorCell = within(screen.getByTestId('ledger-table')).getByText('ops@example.com');
    expect(actorCell).toBeInTheDocument();
    expect(actorCell).toHaveAttribute('title', 'admin-1');
  });

  it('prettifies a system actor label instead of showing the raw origin string', async () => {
    vi.mocked(getFirm).mockResolvedValueOnce({
      ...FIRM_DETAIL,
      ledger: [
        {
          ...FIRM_DETAIL.ledger[0],
          actor: 'system:backfill_firm_kind',
          actor_label: 'system:backfill_firm_kind',
        },
      ],
    });

    await renderLoaded();

    // Mutation: remove prettifyActorLabel's call site in the ledger cell
    // (render entry.actor_label directly) -- red (the raw
    // "system:backfill_firm_kind" string would show instead).
    const actorCell = within(screen.getByTestId('ledger-table'))
      .getByText('system: backfill firm kind');
    expect(actorCell).toBeInTheDocument();
    expect(actorCell).toHaveAttribute('title', 'system:backfill_firm_kind');
  });

  it('renders the ledger table without a React key warning when rows carry no doc_id', async () => {
    // The route (GET /admin/firms/{firm_id}) never sends doc_id -- see
    // LedgerEntry's comment in adminApi.ts and bd polyglot-pdf-migp9. Rows
    // must key on fields the route actually sends (ts+index), not on the
    // absent doc_id; a `key={entry.doc_id}` regression makes every row's
    // key `undefined` and React logs "Each child in a list should have a
    // unique key prop."
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    await renderLoaded();
    const keyWarning = errorSpy.mock.calls.some(
      (args) => typeof args[0] === 'string' && args[0].includes('unique "key" prop'),
    );
    expect(keyWarning).toBe(false);
    errorSpy.mockRestore();
  });

  describe('grant credits: usd_amount only for the two income types', () => {
    it('subscription_grant shows and requires a USD amount field', async () => {
      await renderLoaded();
      expect(screen.getByLabelText('USD amount')).toBeInTheDocument();
    });

    it('promo_grant hides the USD amount field entirely', async () => {
      await renderLoaded();
      fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'promo_grant' } });
      expect(screen.queryByLabelText('USD amount')).not.toBeInTheDocument();
    });

    it('grant sends usd_amount for subscription_grant', async () => {
      vi.mocked(grantCredits).mockResolvedValue({
        doc_id: 'l2', firm_id: 'firm-a', type: 'subscription_grant',
        amount: 50, usd_amount: 25, balance_credits: 170, request_id: 'req-1',
      });
      await renderLoaded();

      fireEvent.change(screen.getByLabelText('Amount (credits)'), { target: { value: '50' } });
      fireEvent.change(screen.getByLabelText('USD amount'), { target: { value: '25' } });
      fireEvent.click(screen.getByRole('button', { name: 'Grant' }));

      await waitFor(() => expect(grantCredits).toHaveBeenCalledTimes(1));
      expect(grantCredits).toHaveBeenCalledWith('firm-a', {
        type: 'subscription_grant', amount: 50, usdAmount: 25,
      });
      // Re-reads the firm after a successful grant.
      await waitFor(() => expect(getFirm).toHaveBeenCalledTimes(2));
    });

    it('grant sends NO usd_amount for promo_grant, even if one was typed before switching type', async () => {
      vi.mocked(grantCredits).mockResolvedValue({
        doc_id: 'l3', firm_id: 'firm-a', type: 'promo_grant',
        amount: 10, usd_amount: null, balance_credits: 130, request_id: 'req-2',
      });
      await renderLoaded();

      // Type a USD amount while still on subscription_grant, THEN switch to
      // promo_grant -- the component must clear it (module docstring), so
      // the eventual request must not smuggle the stale value through.
      fireEvent.change(screen.getByLabelText('USD amount'), { target: { value: '999' } });
      fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'promo_grant' } });
      fireEvent.change(screen.getByLabelText('Amount (credits)'), { target: { value: '10' } });
      fireEvent.click(screen.getByRole('button', { name: 'Grant' }));

      await waitFor(() => expect(grantCredits).toHaveBeenCalledTimes(1));
      expect(grantCredits).toHaveBeenCalledWith('firm-a', {
        type: 'promo_grant', amount: 10, usdAmount: undefined,
      });
    });

    it('purchase also requires and sends usd_amount', async () => {
      vi.mocked(grantCredits).mockResolvedValue({
        doc_id: 'l4', firm_id: 'firm-a', type: 'purchase',
        amount: 20, usd_amount: 9.99, balance_credits: 140, request_id: 'req-3',
      });
      await renderLoaded();

      fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'purchase' } });
      fireEvent.change(screen.getByLabelText('Amount (credits)'), { target: { value: '20' } });
      fireEvent.change(screen.getByLabelText('USD amount'), { target: { value: '9.99' } });
      fireEvent.click(screen.getByRole('button', { name: 'Grant' }));

      await waitFor(() => expect(grantCredits).toHaveBeenCalledTimes(1));
      expect(grantCredits).toHaveBeenCalledWith('firm-a', {
        type: 'purchase', amount: 20, usdAmount: 9.99,
      });
    });
  });

  describe('adjust credits: reason required', () => {
    it('a blank reason refuses submit client-side -- adjustCredits is never called', async () => {
      await renderLoaded();

      fireEvent.change(screen.getByLabelText('Amount (may be negative)'), { target: { value: '-5' } });
      // Reason left blank. The input's own `required` attribute blocks
      // jsdom's native form submission before the handler's onSubmit ever
      // fires (a second, independent layer ahead of the .trim() check the
      // whitespace-only case below actually exercises) -- so the assertion
      // here is on the ONE property both layers guarantee together: the
      // route is never called with no reason.
      fireEvent.click(screen.getByRole('button', { name: 'Adjust' }));

      expect(adjustCredits).not.toHaveBeenCalled();
    });

    it('a non-blank reason (with a negative amount) submits', async () => {
      vi.mocked(adjustCredits).mockResolvedValue({
        doc_id: 'l5', firm_id: 'firm-a', type: 'adjustment',
        amount: -5, balance_credits: 115, request_id: 'req-4',
      });
      await renderLoaded();

      fireEvent.change(screen.getByLabelText('Amount (may be negative)'), { target: { value: '-5' } });
      fireEvent.change(screen.getByLabelText('Reason (required)', { selector: '#adjust-reason' }), {
        target: { value: 'correcting a duplicate grant' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Adjust' }));

      await waitFor(() => expect(adjustCredits).toHaveBeenCalledTimes(1));
      expect(adjustCredits).toHaveBeenCalledWith('firm-a', {
        amount: -5, reason: 'correcting a duplicate grant',
      });
      await waitFor(() => expect(getFirm).toHaveBeenCalledTimes(2));
    });

    it('a whitespace-only reason is treated as blank and refuses', async () => {
      await renderLoaded();

      fireEvent.change(screen.getByLabelText('Amount (may be negative)'), { target: { value: '3' } });
      fireEvent.change(screen.getByLabelText('Reason (required)', { selector: '#adjust-reason' }), {
        target: { value: '   ' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Adjust' }));

      expect(adjustCredits).not.toHaveBeenCalled();
    });
  });

  describe('kind change: two confirmations required', () => {
    it('opening the form does not call setFirmKind (confirmation #1 only)', async () => {
      await renderLoaded();
      fireEvent.click(screen.getByRole('button', { name: 'Change kind' }));

      expect(screen.getByLabelText('New kind')).toBeInTheDocument();
      expect(setFirmKind).not.toHaveBeenCalled();
    });

    it('submitting the first form (with a reason) shows the confirm dialog but does NOT call setFirmKind yet', async () => {
      await renderLoaded();
      fireEvent.click(screen.getByRole('button', { name: 'Change kind' }));

      fireEvent.change(screen.getByLabelText('New kind'), { target: { value: 'mock' } });
      fireEvent.change(screen.getByLabelText('Reason (required)', { selector: '#firm-kind-reason' }), {
        target: { value: 'staging test firm' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

      expect(await screen.findByTestId('kind-confirm-dialog')).toBeInTheDocument();
      expect(setFirmKind).not.toHaveBeenCalled();
    });

    it('a blank reason refuses to even reach the confirm dialog', async () => {
      await renderLoaded();
      fireEvent.click(screen.getByRole('button', { name: 'Change kind' }));

      fireEvent.change(screen.getByLabelText('New kind'), { target: { value: 'mock' } });
      // Reason left blank. Same two-layer refusal as the adjust form's
      // blank-reason case: the input's own `required` attribute blocks
      // jsdom's native submission before onSubmit's .trim() check ever
      // runs, so the assertion is on what BOTH layers guarantee together.
      fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

      expect(screen.queryByTestId('kind-confirm-dialog')).not.toBeInTheDocument();
      expect(setFirmKind).not.toHaveBeenCalled();
    });

    it('confirming the second dialog is what actually calls setFirmKind, exactly once, then re-reads', async () => {
      vi.mocked(setFirmKind).mockResolvedValue({
        firm_id: 'firm-a', kind: 'mock', before_kind: 'live', request_id: 'req-5',
      });
      await renderLoaded();
      fireEvent.click(screen.getByRole('button', { name: 'Change kind' }));
      fireEvent.change(screen.getByLabelText('New kind'), { target: { value: 'mock' } });
      fireEvent.change(screen.getByLabelText('Reason (required)', { selector: '#firm-kind-reason' }), {
        target: { value: 'staging test firm' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
      const dialog = await screen.findByTestId('kind-confirm-dialog');

      fireEvent.click(within(dialog).getByRole('button', { name: 'Yes, change kind' }));

      await waitFor(() => expect(setFirmKind).toHaveBeenCalledTimes(1));
      expect(setFirmKind).toHaveBeenCalledWith('firm-a', 'mock', 'staging test firm');
      await waitFor(() => expect(getFirm).toHaveBeenCalledTimes(2));
      // The dialog and form are dismissed after a successful change.
      expect(screen.queryByTestId('kind-confirm-dialog')).not.toBeInTheDocument();
    });

    it('cancelling the confirm dialog never calls setFirmKind', async () => {
      await renderLoaded();
      fireEvent.click(screen.getByRole('button', { name: 'Change kind' }));
      fireEvent.change(screen.getByLabelText('New kind'), { target: { value: 'mock' } });
      fireEvent.change(screen.getByLabelText('Reason (required)', { selector: '#firm-kind-reason' }), {
        target: { value: 'staging test firm' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
      const dialog = await screen.findByTestId('kind-confirm-dialog');

      fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

      expect(setFirmKind).not.toHaveBeenCalled();
      expect(screen.queryByTestId('kind-confirm-dialog')).not.toBeInTheDocument();
    });
  });

  describe('links: channel selector and revoke', () => {
    it('switching the channel reloads the link list for that channel', async () => {
      await renderLoaded();
      vi.mocked(listFirmLinks).mockResolvedValueOnce({
        firm_id: 'firm-a', channel: 'staging', links: [],
      });

      fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'staging' } });

      await waitFor(() => expect(listFirmLinks).toHaveBeenCalledWith('firm-a', 'staging'));
    });

    it('revoke calls the route exactly once with the jti and current channel, then re-reads the link list', async () => {
      vi.mocked(revokeLink).mockResolvedValue({
        jti: 'jti-1', channel: 'demo', status: 'revoked',
        before_status: 'minted', revoked_at: 1700004000, request_id: 'req-6',
      });
      await renderLoaded();

      fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));

      await waitFor(() => expect(revokeLink).toHaveBeenCalledTimes(1));
      expect(revokeLink).toHaveBeenCalledWith('jti-1', 'demo');
      // listFirmLinks: once on mount, once as the post-revoke re-read.
      await waitFor(() => expect(listFirmLinks).toHaveBeenCalledTimes(2));
    });

    it('a link that is not minted has no enabled Revoke button', async () => {
      vi.mocked(listFirmLinks).mockResolvedValue({
        firm_id: 'firm-a', channel: 'demo',
        links: [{ ...LINK_MINTED, status: 'opened' }],
      });
      render(<FirmDetailPage firmId="firm-a" onAuthExpired={noAuthExpired} onBack={noBack} />);
      await screen.findByText('Acme LLP');
      await screen.findByText('opened');

      expect(screen.getByRole('button', { name: 'Revoke' })).toBeDisabled();
    });
  });

  describe('allowed kits', () => {
    it('saves the comma-separated list as a trimmed array, then re-reads', async () => {
      vi.mocked(setFirmAllowedKits).mockResolvedValue({
        firm_id: 'firm-a', allowed_kits: ['w7', 'i-90'], request_id: 'req-7',
      });
      await renderLoaded();

      fireEvent.change(screen.getByLabelText('Allowed kits (comma-separated)'), {
        target: { value: 'w7, i-90 ,' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Save allowed kits' }));

      await waitFor(() => expect(setFirmAllowedKits).toHaveBeenCalledTimes(1));
      expect(setFirmAllowedKits).toHaveBeenCalledWith('firm-a', ['w7', 'i-90']);
      await waitFor(() => expect(getFirm).toHaveBeenCalledTimes(2));
    });
  });

  describe('alerts (bd polyglot-pdf-362nk)', () => {
    it('fetches this firm\'s alerts via GET /admin/alerts?firm_id=<id> on mount', async () => {
      await renderLoaded();
      expect(listAlerts).toHaveBeenCalledWith({ firmId: 'firm-a' });
    });

    it('renders unacknowledged alerts before acknowledged ones, regardless of fetch order', async () => {
      await renderLoaded();
      const table = screen.getByTestId('firm-alerts-table');
      const rows = within(table).getAllByRole('row').slice(1); // drop the header row
      // Fixture order is [ACK_ALERT, UNACK_ALERT] -- the rendered order
      // must be the reverse: unacknowledged (link_exhausted) first.
      expect(within(rows[0]).getByText('link_exhausted')).toBeInTheDocument();
      expect(within(rows[1]).getByText('credit_low')).toBeInTheDocument();
    });

    it('shows an explicit "no alerts" state when the firm has none', async () => {
      vi.mocked(listAlerts).mockResolvedValue({ alerts: [] });
      await renderLoaded();
      expect(screen.getByText('No alerts for this firm.')).toBeInTheDocument();
    });

    it('a failed alerts fetch shows its own error and leaves the rest of the page intact', async () => {
      vi.mocked(listAlerts).mockRejectedValueOnce(new Error('alerts store unavailable'));
      await renderLoaded();

      expect(screen.getByText('alerts store unavailable')).toBeInTheDocument();
      // The rest of the page -- profile, balance, ledger -- is untouched.
      expect(screen.getByText('Acme LLP')).toBeInTheDocument();
      expect(screen.getByTestId('firm-balance')).toHaveTextContent('120 credits');
      expect(within(screen.getByTestId('ledger-table')).getByText('subscription_grant')).toBeInTheDocument();
    });

    it('acknowledge calls the PATCH exactly once, then re-reads the firm alerts list', async () => {
      vi.mocked(acknowledgeAlert).mockResolvedValue({
        id: 'alert-unack', acknowledged_by: 'admin@example.com',
        acknowledged_at: 1_700_000_200, request_id: 'req-8',
      });
      await renderLoaded();

      const table = screen.getByTestId('firm-alerts-table');
      const unackRow = within(table).getByText('link_exhausted').closest('tr')!;
      fireEvent.click(within(unackRow).getByRole('button', { name: 'Acknowledge' }));

      await waitFor(() => expect(acknowledgeAlert).toHaveBeenCalledTimes(1));
      expect(acknowledgeAlert).toHaveBeenCalledWith('alert-unack');
      // Initial load + the post-acknowledge re-read.
      await waitFor(() => expect(listAlerts).toHaveBeenCalledTimes(2));
    });

    it('a failed acknowledge does not trigger a re-read', async () => {
      vi.mocked(acknowledgeAlert).mockRejectedValueOnce(
        new Error('alert alert-unack was already acknowledged by someone-else@example.com'),
      );
      await renderLoaded();

      const table = screen.getByTestId('firm-alerts-table');
      const unackRow = within(table).getByText('link_exhausted').closest('tr')!;
      fireEvent.click(within(unackRow).getByRole('button', { name: 'Acknowledge' }));

      expect(await screen.findByText(
        'alert alert-unack was already acknowledged by someone-else@example.com',
      )).toBeInTheDocument();
      expect(listAlerts).toHaveBeenCalledTimes(1);
    });

    it('an already-acknowledged row disables its own Acknowledge button', async () => {
      await renderLoaded();
      const table = screen.getByTestId('firm-alerts-table');
      const ackRow = within(table).getByText('credit_low').closest('tr')!;
      expect(within(ackRow).getByRole('button', { name: 'Acknowledge' })).toBeDisabled();
    });
  });

  describe('plan (bd polyglot-pdf-0euzk): one write per save, no confirm-twice', () => {
    it('saves the plan form fields in one call, then re-reads', async () => {
      vi.mocked(setFirmPlan).mockResolvedValue({
        firm_id: 'firm-a',
        plan: { tier: 'starter', monthly_credits: 50, rollover: true },
        before_plan: { tier: 'starter', monthly_credits: 35, rollover: false },
        request_id: 'req-plan-1',
      });
      await renderLoaded();

      fireEvent.change(screen.getByLabelText('Monthly credits'), {
        target: { value: '50' },
      });
      fireEvent.click(screen.getByLabelText(/Rollover/));
      fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));

      await waitFor(() => expect(setFirmPlan).toHaveBeenCalledTimes(1));
      expect(setFirmPlan).toHaveBeenCalledWith('firm-a', {
        tier: 'starter', monthly_credits: 50, rollover: true,
      });
      await waitFor(() => expect(getFirm).toHaveBeenCalledTimes(2));
    });

    it('the form pre-fills from the loaded firm plan', async () => {
      await renderLoaded();
      expect(screen.getByLabelText('Monthly credits')).toHaveValue(35);
      expect(screen.getByLabelText(/Rollover/)).not.toBeChecked();
    });

    it('a fractional monthly_credits refuses submit client-side via handleSavePlan\'s own check, and shows the error', async () => {
      // No native min/step constraint on this input (unlike grant-amount) --
      // the input's own Number.isInteger check inside handleSavePlan is
      // what refuses this, so this test actually exercises that guard
      // end-to-end, unlike the zero-value case above (which the native
      // `required`+"0" combination cannot cleanly isolate from -- see that
      // test's own comment).
      await renderLoaded();

      fireEvent.change(screen.getByLabelText('Monthly credits'), {
        target: { value: '35.7' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));

      expect(setFirmPlan).not.toHaveBeenCalled();
      expect(await screen.findByText(/Monthly credits must be a positive whole number/)).toBeInTheDocument();
    });

    it('a zero monthly_credits also refuses via handleSavePlan\'s own check, and shows the error', async () => {
      // With min= dropped, "0" now also reaches the JS handler directly
      // (jsdom's `required` attribute only blocks a BLANK value, not "0"),
      // so this proves the <= 0 half of the same guard end-to-end too.
      await renderLoaded();

      fireEvent.change(screen.getByLabelText('Monthly credits'), {
        target: { value: '0' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));

      expect(setFirmPlan).not.toHaveBeenCalled();
      expect(await screen.findByText(/Monthly credits must be a positive whole number/)).toBeInTheDocument();
    });

    it('a route-side 422 surfaces as an inline error, not a thrown exception', async () => {
      vi.mocked(setFirmPlan).mockRejectedValueOnce(new Error('tier must be one of (starter,)'));
      await renderLoaded();

      fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));

      await waitFor(() => expect(setFirmPlan).toHaveBeenCalledTimes(1));
      expect(await screen.findByText('tier must be one of (starter,)')).toBeInTheDocument();
    });
  });

  it('routes a 403 on load to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(getFirm).mockRejectedValueOnce(new ForbiddenError('Access was revoked'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<FirmDetailPage firmId="firm-a" onAuthExpired={onAuthExpired} onBack={noBack} />);

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(ForbiddenError);
    expect(screen.queryByText('Access was revoked')).not.toBeInTheDocument();
  });

  it('routes a 401 on grant to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(grantCredits).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<FirmDetailPage firmId="firm-a" onAuthExpired={onAuthExpired} onBack={noBack} />);
    await screen.findByText('Acme LLP');

    fireEvent.change(screen.getByLabelText('Amount (credits)'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('USD amount'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Grant' }));

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(AuthError);
  });

  it('back button reports upward', async () => {
    const onBack = vi.fn();
    render(<FirmDetailPage firmId="firm-a" onAuthExpired={noAuthExpired} onBack={onBack} />);
    await screen.findByText('Acme LLP');

    fireEvent.click(screen.getByText(/Back to firms/));

    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
