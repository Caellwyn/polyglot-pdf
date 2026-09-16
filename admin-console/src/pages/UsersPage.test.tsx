/**
 * UsersPage (bd polyglot-pdf-z4y91; renamed to "Staff accounts", given a
 * purpose intro, and the firm ID field turned into a firm-list select by
 * bd polyglot-pdf-dp1zq). Pins the exit criteria verbatim: "create shows
 * the reset link exactly once and never a password; disable and role
 * change call their routes once and re-read; the firm selector is required
 * for the app admin (mocked API, mutation-verified)" (z4y91) and "the tab
 * reads 'Staff accounts', the page carries the intro and role explanation,
 * and the firm selector is a select fed by GET /admin/firms with a text
 * fallback (tests, mutation-verified)" (dp1zq).
 *
 * Mirrors ConfigEditorPage.test.tsx's mocking approach: keep the real
 * AuthError/ForbiddenError classes (onAuthExpired branches on instanceof),
 * mock only the network calls.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { UsersPage } from './UsersPage';
import {
  AuthError, ForbiddenError,
  listUsers, createUser, setUserDisabled, setUserRole, listFirms,
} from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return {
    ...actual,
    listUsers: vi.fn(),
    createUser: vi.fn(),
    setUserDisabled: vi.fn(),
    setUserRole: vi.fn(),
    listFirms: vi.fn(),
  };
});

const noAuthExpired = () => false;

const EMPLOYEE_ROW = {
  uid: 'u1',
  email: 'alice@example.com',
  display_name: 'Alice',
  disabled: false,
  firm_id: 'firm-a',
  firm_role: 'employee',
};

const MANAGER_ROW = {
  uid: 'u2',
  email: 'bob@example.com',
  display_name: 'Bob',
  disabled: true,
  firm_id: 'firm-a',
  firm_role: 'manager',
};

const FIRM_A_PAGE = { firm_id: 'firm-a', users: [EMPLOYEE_ROW, MANAGER_ROW], truncated: false };

const FIRM_A = {
  firm_id: 'firm-a', name: 'Acme LLP', contact_email: 'ops@acme.test',
  kind: 'live' as const, status: 'active' as const, allowed_kits: [],
  balance_credits: 100,
  plan: { tier: 'starter' as const, monthly_credits: 35, rollover: false },
};
const FIRM_B = {
  firm_id: 'firm-b', name: null, contact_email: 'ops@beta.test',
  kind: 'mock' as const, status: 'active' as const, allowed_kits: [],
  balance_credits: 0,
  plan: { tier: 'starter' as const, monthly_credits: 35, rollover: false },
};

/** Selects a firm from the <select> populated by listFirms -- the default
 * path once GET /admin/firms is up (bd polyglot-pdf-dp1zq). Waits for the
 * select to appear first, since listFirms resolves asynchronously on
 * mount. */
async function loadFirm(firmId = 'firm-a') {
  const select = await screen.findByLabelText('Firm');
  fireEvent.change(select, { target: { value: firmId } });
  await waitFor(() => expect(listUsers).toHaveBeenCalledWith(firmId));
}

/** Loads a firm through the free-text fallback field -- only reachable
 * when listFirms has failed (see the "firm list fails to load" describe
 * block below). */
async function loadFirmViaTextFallback(firmId = 'firm-a') {
  const input = await screen.findByLabelText('Firm ID');
  fireEvent.change(input, { target: { value: firmId } });
  fireEvent.click(screen.getByRole('button', { name: 'Load' }));
  await waitFor(() => expect(listUsers).toHaveBeenCalledWith(firmId));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listUsers).mockResolvedValue(FIRM_A_PAGE);
  vi.mocked(listFirms).mockResolvedValue([FIRM_A, FIRM_B]);
});

describe('UsersPage', () => {
  it('renamed to "Staff accounts" (bd polyglot-pdf-dp1zq)', async () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await screen.findByLabelText('Firm'); // let the listFirms effect settle

    expect(screen.getByRole('heading', { name: 'Staff accounts' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Users' })).not.toBeInTheDocument();
  });

  it('carries a one-sentence intro naming what the page does and the manager/employee split', async () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await screen.findByLabelText('Firm'); // let the listFirms effect settle

    const intro = screen.getByTestId('page-intro');
    // Names the concrete actions (bead description, verbatim list): create
    // by email + firm + role, the one-time reset link (no email sent),
    // disable/re-enable, role change, and listing staff.
    expect(intro).toHaveTextContent(/create an account/i);
    expect(intro).toHaveTextContent(/password-reset link/i);
    expect(intro).toHaveTextContent(/no email is sent/i);
    expect(intro).toHaveTextContent(/disable or/i);
    // Names what a manager vs an employee may do.
    expect(intro).toHaveTextContent(/manager can mint links/i);
    expect(intro).toHaveTextContent(/employee can mint links/i);
  });

  it('does not load or show the create form / table until a firm is chosen', async () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await screen.findByLabelText('Firm'); // let the listFirms effect settle

    expect(listUsers).not.toHaveBeenCalled();
    expect(screen.queryByTestId('users-table')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument();
  });

  it('populates the firm select from GET /admin/firms, showing name and kind', async () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);

    const select = await screen.findByLabelText('Firm') as HTMLSelectElement;
    await waitFor(() => expect(listFirms).toHaveBeenCalledTimes(1));
    const optionLabels = Array.from(select.options).map((o) => o.textContent);
    expect(optionLabels).toEqual(
      expect.arrayContaining([
        expect.stringContaining('Acme LLP (firm-a)'),
        expect.stringContaining('firm-b'),
      ]),
    );
    // firm-a shows its kind badge; firm-b (no name) falls back to the bare id.
    expect(optionLabels.some((l) => l?.includes('[live]'))).toBe(true);
    expect(optionLabels.some((l) => l?.includes('[mock]'))).toBe(true);
    // No free-text fallback rendered while the select is up.
    expect(screen.queryByLabelText('Firm ID')).not.toBeInTheDocument();
  });

  it('choosing a firm from the select lists its users, keyed by firm_id', async () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await loadFirm('firm-a');

    expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
    expect(listUsers).toHaveBeenCalledTimes(1);
  });

  describe('when the firm list fails to load', () => {
    beforeEach(() => {
      vi.mocked(listFirms).mockRejectedValueOnce(new Error('admin service unreachable'));
    });

    it('falls back to the free-text firm ID field, which is required', async () => {
      render(<UsersPage onAuthExpired={noAuthExpired} />);

      const firmInput = await screen.findByLabelText('Firm ID') as HTMLInputElement;
      expect(firmInput).toBeRequired();
      // The select never renders while the fallback is showing.
      expect(screen.queryByLabelText('Firm')).not.toBeInTheDocument();
    });

    it('loading a firm through the text fallback still lists its users', async () => {
      render(<UsersPage onAuthExpired={noAuthExpired} />);
      await loadFirmViaTextFallback('firm-a');

      expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
      expect(listUsers).toHaveBeenCalledTimes(1);
    });

    it('routes a 403 from listFirms to onAuthExpired instead of falling back', async () => {
      vi.mocked(listFirms).mockReset();
      vi.mocked(listFirms).mockRejectedValueOnce(new ForbiddenError('Access was revoked'));
      const onAuthExpired = vi.fn((_err: unknown) => true);
      render(<UsersPage onAuthExpired={onAuthExpired} />);

      await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
      const [[passedErr]] = onAuthExpired.mock.calls;
      expect(passedErr).toBeInstanceOf(ForbiddenError);
      // Neither the select nor the text fallback claims a firm list --
      // a revoked session bounces to the sign-in gate, it does not degrade.
      expect(screen.queryByLabelText('Firm')).not.toBeInTheDocument();
    });
  });

  it('create shows the reset link exactly once and never a password', async () => {
    vi.mocked(createUser).mockResolvedValue({
      uid: 'u3',
      email: 'carol@example.com',
      firm_id: 'firm-a',
      firm_role: 'employee',
      reset_link: 'https://example.com/reset?oobCode=abc123',
      request_id: 'req-1',
    });
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await loadFirm('firm-a');

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'carol@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => expect(createUser).toHaveBeenCalledTimes(1));
    expect(createUser).toHaveBeenCalledWith({
      email: 'carol@example.com',
      firmRole: 'employee',
      firmId: 'firm-a',
      displayName: undefined,
    });

    // The reset link appears exactly once on the page.
    const occurrences = await screen.findAllByText('https://example.com/reset?oobCode=abc123');
    expect(occurrences).toHaveLength(1);

    // No password ever renders. The page's own copy legitimately says
    // "password-reset link" (that phrase is expected), so the guard is NOT
    // "the word password never appears" -- it is "there is no password
    // FIELD or VALUE": no input/label asking for or showing a password, and
    // the create call the component made never carried one (createUser's
    // wire request has no password key at all -- see CreateUserRequest in
    // adminApi.ts, which is the actual guarantee this test protects; a
    // future accidental `password` field on that request would fail this
    // assertion even though nothing in the DOM changed).
    expect(screen.queryByLabelText(/^password$/i)).not.toBeInTheDocument();
    expect(vi.mocked(createUser).mock.calls[0][0]).not.toHaveProperty('password');
  });

  it('a create with no reset_link (best-effort link generation failed) shows no link block and no crash', async () => {
    vi.mocked(createUser).mockResolvedValue({
      uid: 'u4', email: 'dana@example.com', firm_id: 'firm-a',
      firm_role: 'employee', reset_link: null, request_id: 'req-2',
    });
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await loadFirm('firm-a');

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'dana@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => expect(createUser).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/Share this password-reset link/)).not.toBeInTheDocument();
  });

  it('disable calls the disable route exactly once with the resolved firm, then re-reads the list', async () => {
    vi.mocked(setUserDisabled).mockResolvedValue({
      uid: 'u1', disabled: true, firm_id: 'firm-a', request_id: 'req-3',
    });
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await loadFirm('firm-a');
    await screen.findByText('alice@example.com');

    // After the mutation, the re-read shows Alice as disabled.
    vi.mocked(listUsers).mockResolvedValueOnce({
      firm_id: 'firm-a',
      users: [{ ...EMPLOYEE_ROW, disabled: true }, MANAGER_ROW],
      truncated: false,
    });

    const row = screen.getByText('alice@example.com').closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: 'Disable' }));

    await waitFor(() => expect(setUserDisabled).toHaveBeenCalledTimes(1));
    expect(setUserDisabled).toHaveBeenCalledWith('u1', 'firm-a', true);

    // listUsers called again (initial load + post-mutation re-read).
    await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(within(row).getByText('Disabled')).toBeInTheDocument());
  });

  it('enable (toggling a disabled account) sends disabled: false exactly once', async () => {
    vi.mocked(setUserDisabled).mockResolvedValue({
      uid: 'u2', disabled: false, firm_id: 'firm-a', request_id: 'req-4',
    });
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await loadFirm('firm-a');
    await screen.findByText('bob@example.com');

    const row = screen.getByText('bob@example.com').closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: 'Enable' }));

    await waitFor(() => expect(setUserDisabled).toHaveBeenCalledTimes(1));
    expect(setUserDisabled).toHaveBeenCalledWith('u2', 'firm-a', false);
  });

  it('role change calls the role route exactly once with the resolved firm, then re-reads the list', async () => {
    vi.mocked(setUserRole).mockResolvedValue({
      uid: 'u1', firm_id: 'firm-a', firm_role: 'manager',
      before_role: 'employee', request_id: 'req-5',
    });
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await loadFirm('firm-a');
    await screen.findByText('alice@example.com');

    vi.mocked(listUsers).mockResolvedValueOnce({
      firm_id: 'firm-a',
      users: [{ ...EMPLOYEE_ROW, firm_role: 'manager' }, MANAGER_ROW],
      truncated: false,
    });

    const row = screen.getByText('alice@example.com').closest('tr')!;
    fireEvent.change(within(row).getByLabelText('Role for alice@example.com'), {
      target: { value: 'manager' },
    });

    await waitFor(() => expect(setUserRole).toHaveBeenCalledTimes(1));
    expect(setUserRole).toHaveBeenCalledWith('u1', 'firm-a', 'manager');
    await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(2));
  });

  it('selecting the role a user already holds is a no-op -- no call at all', async () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await loadFirm('firm-a');
    await screen.findByText('alice@example.com');

    const row = screen.getByText('alice@example.com').closest('tr')!;
    fireEvent.change(within(row).getByLabelText('Role for alice@example.com'), {
      target: { value: 'employee' },
    });

    expect(setUserRole).not.toHaveBeenCalled();
  });

  it('routes a 403 on load to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(listUsers).mockRejectedValueOnce(new ForbiddenError('Access was revoked'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<UsersPage onAuthExpired={onAuthExpired} />);

    const select = await screen.findByLabelText('Firm');
    fireEvent.change(select, { target: { value: 'firm-a' } });

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(ForbiddenError);
    expect(screen.queryByText('Access was revoked')).not.toBeInTheDocument();
  });

  it('routes a 401 on create to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(createUser).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<UsersPage onAuthExpired={onAuthExpired} />);
    await loadFirm('firm-a');

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'carol@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(AuthError);
    expect(screen.queryByText(/Could not create/)).not.toBeInTheDocument();
  });

  it('shows the server error and does not re-read on a failed disable', async () => {
    vi.mocked(setUserDisabled).mockRejectedValueOnce(new Error('firm is on a mock kind hold'));
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await loadFirm('firm-a');
    await screen.findByText('alice@example.com');

    const row = screen.getByText('alice@example.com').closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: 'Disable' }));

    expect(await screen.findByText('firm is on a mock kind hold')).toBeInTheDocument();
    // Only the initial load read the list -- a failed mutation must not
    // trigger the success re-read.
    expect(listUsers).toHaveBeenCalledTimes(1);
  });
});
