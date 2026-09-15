/**
 * FirmsPage (bd polyglot-pdf-r8z9g). Pins the exit criterion's first half
 * verbatim: "create refuses without kind client-side" (mocked API,
 * mutation-verified).
 *
 * Mirrors UsersPage.test.tsx's mocking approach: keep the real
 * AuthError/ForbiddenError classes (onAuthExpired branches on instanceof),
 * mock only the network calls.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { FirmsPage } from './FirmsPage';
import { AuthError, ForbiddenError, listFirms, createFirm } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return {
    ...actual,
    listFirms: vi.fn(),
    createFirm: vi.fn(),
  };
});

const noAuthExpired = () => false;
const noOpenFirm = () => {};

const FIRM_A = {
  firm_id: 'firm-a', name: 'Acme LLP', contact_email: 'ops@acme.test',
  kind: 'live' as const, status: 'active' as const, allowed_kits: [],
  balance_credits: 120,
  plan: { tier: 'starter' as const, monthly_credits: 35, rollover: false },
};
const FIRM_B = {
  firm_id: 'firm-b', name: 'Beta Legal', contact_email: 'ops@beta.test',
  kind: 'mock' as const, status: 'active' as const, allowed_kits: ['w7'],
  balance_credits: 0,
  plan: { tier: 'starter' as const, monthly_credits: 35, rollover: false },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listFirms).mockResolvedValue([FIRM_A, FIRM_B]);
});

async function fillRequiredFields(overrides: { skipKind?: boolean } = {}) {
  fireEvent.change(screen.getByLabelText('Firm ID'), { target: { value: 'firm-c' } });
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Gamma Law' } });
  fireEvent.change(screen.getByLabelText('Contact email'), { target: { value: 'ops@gamma.test' } });
  if (!overrides.skipKind) {
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'mock' } });
  }
}

describe('FirmsPage', () => {
  it('loads the firm list on mount, unfiltered', async () => {
    render(<FirmsPage onAuthExpired={noAuthExpired} onOpenFirm={noOpenFirm} />);

    await waitFor(() => expect(listFirms).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Acme LLP')).toBeInTheDocument();
    expect(screen.getByText('Beta Legal')).toBeInTheDocument();
  });

  it('renders each firm kind and balance', async () => {
    render(<FirmsPage onAuthExpired={noAuthExpired} onOpenFirm={noOpenFirm} />);
    const table = await screen.findByTestId('firms-table');

    // 'live'/'mock' also appear as <option> text in the create form's kind
    // <select>, so this scopes the lookup to the firms table itself rather
    // than the whole document.
    expect(within(table).getByText('live')).toBeInTheDocument();
    expect(within(table).getByText('mock')).toBeInTheDocument();
    expect(within(table).getByText('120')).toBeInTheDocument();
  });

  it('the create button is disabled until a kind is chosen', async () => {
    render(<FirmsPage onAuthExpired={noAuthExpired} onOpenFirm={noOpenFirm} />);
    await screen.findByText('Acme LLP');

    await fillRequiredFields({ skipKind: true });
    expect(screen.getByRole('button', { name: 'Create firm' })).toBeDisabled();
  });

  it('choosing a kind enables create, and submits it', async () => {
    vi.mocked(createFirm).mockResolvedValue({
      firm_id: 'firm-c', created: true, request_id: 'req-1',
    });
    render(<FirmsPage onAuthExpired={noAuthExpired} onOpenFirm={noOpenFirm} />);
    await screen.findByText('Acme LLP');

    await fillRequiredFields();
    expect(screen.getByRole('button', { name: 'Create firm' })).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Create firm' }));

    await waitFor(() => expect(createFirm).toHaveBeenCalledTimes(1));
    expect(createFirm).toHaveBeenCalledWith({
      firmId: 'firm-c', name: 'Gamma Law', contactEmail: 'ops@gamma.test',
      kind: 'mock',
    });
    // re-reads after a successful create
    await waitFor(() => expect(listFirms).toHaveBeenCalledTimes(2));
  });

  it('create is NEVER called with no kind chosen -- the disabled button cannot be bypassed by a bare click', async () => {
    render(<FirmsPage onAuthExpired={noAuthExpired} onOpenFirm={noOpenFirm} />);
    await screen.findByText('Acme LLP');

    await fillRequiredFields({ skipKind: true });
    // A disabled button ignores click events in jsdom/RTL, mirroring what
    // a real browser does -- this assertion is the mutation-verified guard
    // (see the "test the tests" note below): if the disabled={...} check
    // were ever removed from the button, this click would go through and
    // createFirm would be called with kind: ''.
    fireEvent.click(screen.getByRole('button', { name: 'Create firm' }));

    expect(createFirm).not.toHaveBeenCalled();
  });

  it('routes a 403 on load to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(listFirms).mockRejectedValueOnce(new ForbiddenError('Access was revoked'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<FirmsPage onAuthExpired={onAuthExpired} onOpenFirm={noOpenFirm} />);

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(ForbiddenError);
    expect(screen.queryByText('Access was revoked')).not.toBeInTheDocument();
  });

  it('routes a 401 on create to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(createFirm).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<FirmsPage onAuthExpired={onAuthExpired} onOpenFirm={noOpenFirm} />);
    await screen.findByText('Acme LLP');

    await fillRequiredFields();
    fireEvent.click(screen.getByRole('button', { name: 'Create firm' }));

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(AuthError);
  });

  it('shows the server error on a failed create and does not re-read', async () => {
    vi.mocked(createFirm).mockRejectedValueOnce(new Error('firm_id already exists'));
    render(<FirmsPage onAuthExpired={noAuthExpired} onOpenFirm={noOpenFirm} />);
    await screen.findByText('Acme LLP');

    await fillRequiredFields();
    fireEvent.click(screen.getByRole('button', { name: 'Create firm' }));

    expect(await screen.findByText('firm_id already exists')).toBeInTheDocument();
    expect(listFirms).toHaveBeenCalledTimes(1);
  });

  it('clicking a firm name reports its firm_id upward', async () => {
    const onOpenFirm = vi.fn();
    render(<FirmsPage onAuthExpired={noAuthExpired} onOpenFirm={onOpenFirm} />);
    await screen.findByText('Acme LLP');

    fireEvent.click(screen.getByText('Acme LLP'));

    expect(onOpenFirm).toHaveBeenCalledWith('firm-a');
  });
});
