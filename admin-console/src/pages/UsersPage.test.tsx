/**
 * UsersPage (bd polyglot-pdf-z4y91). Pins the exit criterion verbatim:
 * "create shows the reset link exactly once and never a password; disable
 * and role change call their routes once and re-read; the firm selector is
 * required for the app admin (mocked API, mutation-verified)".
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
  listUsers, createUser, setUserDisabled, setUserRole,
} from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return {
    ...actual,
    listUsers: vi.fn(),
    createUser: vi.fn(),
    setUserDisabled: vi.fn(),
    setUserRole: vi.fn(),
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

async function loadFirm(firmId = 'firm-a') {
  fireEvent.change(screen.getByLabelText('Firm ID'), { target: { value: firmId } });
  fireEvent.click(screen.getByRole('button', { name: 'Load' }));
  await waitFor(() => expect(listUsers).toHaveBeenCalledWith(firmId));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listUsers).mockResolvedValue(FIRM_A_PAGE);
});

describe('UsersPage', () => {
  it('does not load or show the create form / table until a firm ID is submitted', () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);

    expect(listUsers).not.toHaveBeenCalled();
    expect(screen.queryByTestId('users-table')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument();
  });

  it('the firm ID field is a required input -- the selector app admins cannot skip', () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);

    const firmInput = screen.getByLabelText('Firm ID') as HTMLInputElement;
    expect(firmInput).toBeRequired();
  });

  it('loading a firm lists its users, keyed by firm_id', async () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    await loadFirm('firm-a');

    expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
    expect(listUsers).toHaveBeenCalledTimes(1);
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

    fireEvent.change(screen.getByLabelText('Firm ID'), { target: { value: 'firm-a' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load' }));

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
