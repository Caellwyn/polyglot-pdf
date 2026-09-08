/**
 * SignInGate (bd polyglot-pdf-b6943): the admin console's per-user front
 * door. MIRRORS schema-editor/src/components/SignInGate.test.tsx's shape --
 * the behaviours worth pinning are the ones a careless refactor would
 * collapse:
 *   - loading (restoring a session) shows a spinner, not the form.
 *   - signed out shows the sign-in form.
 *   - signed in WITHOUT the app_admin claim (403) must NOT be treated as a
 *     sign-in failure. Retyping a password can never fix it.
 *   - signed in WITH the claim calls onReady with the server's whoami.
 *   - a 401 signs the person out first, so the retry starts clean.
 *   - a 503 must NOT sign the person out.
 *   - the gate never mints accounts (admin access is granted, not self-served).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SignInGate } from './SignInGate';
import { AuthError, ForbiddenError, probeWhoAmI } from '../utils/adminApi';
import {
  isAuthConfigured, sendReset, signInWithGoogle, signInWithPassword,
  signOutAdmin, watchAdminUser,
} from '../utils/adminAuth';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  // Keep the REAL error classes -- the gate branches on instanceof, so
  // mocking them would make every branch test vacuous.
  return { ...actual, probeWhoAmI: vi.fn() };
});

vi.mock('../utils/adminAuth', () => ({
  isAuthConfigured: vi.fn(() => true),
  watchAdminUser: vi.fn(),
  signInWithGoogle: vi.fn(),
  signInWithPassword: vi.fn(),
  sendReset: vi.fn(),
  signOutAdmin: vi.fn(async () => {}),
  currentAdminEmail: vi.fn(() => 'admin@example.com'),
  adminIdToken: vi.fn(async () => 'id-token'),
}));

let authListeners: Array<(u: unknown) => void> = [];
let currentUser: unknown = null;

function emitUser(user: unknown) {
  currentUser = user;
  authListeners.forEach((cb) => cb(user));
}

const SIGNED_IN = { uid: 'u1', email: 'admin@example.com' };

beforeEach(() => {
  vi.clearAllMocks();
  authListeners = [];
  currentUser = null;
  vi.mocked(isAuthConfigured).mockReturnValue(true);
  vi.mocked(signOutAdmin).mockResolvedValue(undefined);
  vi.mocked(watchAdminUser).mockImplementation((cb: (u: never) => void) => {
    const fn = cb as (u: unknown) => void;
    authListeners.push(fn);
    fn(currentUser);
    return () => { authListeners = authListeners.filter((l) => l !== fn); };
  });
  vi.mocked(probeWhoAmI).mockResolvedValue({ uid: 'u1', email: 'admin@example.com' });
});

describe('SignInGate', () => {
  // LOADING: a returning admin's session is still being restored/probed.
  it('shows a loading state while restoring an existing session', async () => {
    currentUser = SIGNED_IN;
    let resolveProbe: (v: { uid: string; email: string }) => void = () => {};
    vi.mocked(probeWhoAmI).mockReturnValue(
      new Promise((resolve) => { resolveProbe = resolve; }));
    render(<SignInGate onReady={vi.fn()} />);

    expect(await screen.findByText('Checking your access...')).toBeInTheDocument();
    // Resolve and let the effect settle so the pending state update lands
    // inside act() and does not leak an unhandled update warning into a
    // later test.
    resolveProbe({ uid: 'u1', email: 'admin@example.com' });
    await waitFor(() => expect(screen.queryByText('Checking your access...'))
      .not.toBeInTheDocument());
  });

  // SIGNED OUT: no Firebase session -- shows the sign-in form.
  it('shows the sign-in form when nobody is signed in', async () => {
    render(<SignInGate onReady={vi.fn()} />);

    await screen.findByTestId('signin-gate');
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(probeWhoAmI).not.toHaveBeenCalled();
  });

  // SIGNED IN WITH CLAIM: onReady fires with the server's whoami.
  it('signs in with email and reports the whoami the server returns', async () => {
    vi.mocked(probeWhoAmI).mockResolvedValue({ uid: 'u9', email: 'ops@example.com' });
    vi.mocked(signInWithPassword).mockImplementation(async () => emitUser(SIGNED_IN));
    const onReady = vi.fn();
    render(<SignInGate onReady={onReady} />);

    fireEvent.change(await screen.findByLabelText('Email'),
      { target: { value: 'ops@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() =>
      expect(onReady).toHaveBeenCalledWith({ uid: 'u9', email: 'ops@example.com' }));
    expect(signInWithPassword).toHaveBeenCalledWith('ops@example.com', 'pw');
  });

  it('signs in with Google', async () => {
    vi.mocked(signInWithGoogle).mockImplementation(async () => emitUser(SIGNED_IN));
    const onReady = vi.fn();
    render(<SignInGate onReady={onReady} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Sign in with Google' }));

    await waitFor(() =>
      expect(onReady).toHaveBeenCalledWith({ uid: 'u1', email: 'admin@example.com' }));
  });

  // SIGNED IN WITHOUT CLAIM: THE case this bead exists to get right. A valid
  // account authenticates perfectly and still has no app_admin claim: showing
  // the sign-in form again would loop them forever through a step that
  // already succeeded.
  it('a 403 explains that access must be granted, and does NOT re-prompt', async () => {
    vi.mocked(probeWhoAmI).mockRejectedValue(
      new ForbiddenError('This account does not have admin console access', true));
    const onReady = vi.fn();
    currentUser = SIGNED_IN;
    render(<SignInGate onReady={onReady} />);

    await screen.findByTestId('signin-refused');
    expect(screen.getByText(/does not have admin console access/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
    expect(onReady).not.toHaveBeenCalled();
    // NOT signed out automatically -- the person may legitimately want to
    // stay signed in while an operator grants them access.
    expect(signOutAdmin).not.toHaveBeenCalled();
  });

  it('the refused screen offers a way back to a different account', async () => {
    vi.mocked(probeWhoAmI).mockRejectedValue(new ForbiddenError('nope', true));
    currentUser = SIGNED_IN;
    render(<SignInGate onReady={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button',
      { name: 'Sign in with a different account' }));

    await waitFor(() => expect(signOutAdmin).toHaveBeenCalled());
  });

  it('a 401 signs the person out and shows the form again', async () => {
    vi.mocked(probeWhoAmI).mockRejectedValue(new AuthError());
    currentUser = SIGNED_IN;
    render(<SignInGate onReady={vi.fn()} />);

    await screen.findByLabelText('Password');
    await waitFor(() => expect(signOutAdmin).toHaveBeenCalled());
  });

  // A transient server fault must not evict a working admin: their
  // credential is fine, and signing everyone out over a 503 is worse than
  // the outage.
  it('a 503 shows the reason and does NOT sign the person out', async () => {
    vi.mocked(probeWhoAmI).mockRejectedValue(
      new Error('The admin service is unreachable'));
    currentUser = SIGNED_IN;
    render(<SignInGate onReady={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText(/unreachable/)).toBeInTheDocument());
    expect(signOutAdmin).not.toHaveBeenCalled();
  });

  it('sends a password reset email and returns to the sign-in form', async () => {
    vi.mocked(sendReset).mockResolvedValue(undefined);
    render(<SignInGate onReady={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Forgot password?' }));
    fireEvent.change(screen.getByLabelText('Email'),
      { target: { value: 'admin@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send reset email' }));

    await waitFor(() => expect(sendReset).toHaveBeenCalledWith('admin@example.com'));
    expect(await screen.findByText(/reset email sent/i)).toBeInTheDocument();
  });

  it('turns a Firebase error code into something a human can act on', async () => {
    vi.mocked(signInWithPassword).mockRejectedValue({ code: 'auth/invalid-credential' });
    render(<SignInGate onReady={vi.fn()} />);

    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'e@x.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'bad' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Incorrect email or password.')).toBeInTheDocument();
  });

  // The console is a SEPARATE Hosting site, so its domain must be on the
  // Firebase project's authorized list. Nothing at build time can catch this
  // (the config is present and valid) -- it only fires at a human's first
  // sign-in, so the message has to name the fix.
  it('names the fix when the site is not an authorized Firebase domain', async () => {
    vi.mocked(signInWithGoogle).mockRejectedValue({ code: 'auth/unauthorized-domain' });
    render(<SignInGate onReady={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Sign in with Google' }));

    expect(await screen.findByText(/authorized domains/)).toBeInTheDocument();
  });

  // Admin access is GRANTED (scripts/bootstrap_admin_user.py), never
  // self-served: an account created here could only ever hit the 403 above.
  it('offers no way to create an account', async () => {
    render(<SignInGate onReady={vi.fn()} />);
    await screen.findByLabelText('Password');
    expect(screen.queryByText(/create account/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sign up/i)).not.toBeInTheDocument();
  });

  // Handed a mid-session 403 by App, the gate must show the refused screen
  // WITHOUT probing again -- the probe would only 403 a second time, so the
  // person would watch a spinner just to reach the same answer.
  it('renders the refused screen from refusedReason without re-probing', async () => {
    currentUser = SIGNED_IN;
    render(<SignInGate onReady={vi.fn()} refusedReason="Access was revoked" />);

    await screen.findByTestId('signin-refused');
    expect(screen.getByText('Access was revoked')).toBeInTheDocument();
    expect(probeWhoAmI).not.toHaveBeenCalled();
  });

  it('says so when the build has no Firebase configuration', async () => {
    vi.mocked(isAuthConfigured).mockReturnValue(false);
    render(<SignInGate onReady={vi.fn()} />);

    await screen.findByTestId('signin-unconfigured');
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
    expect(probeWhoAmI).not.toHaveBeenCalled();
  });
});
