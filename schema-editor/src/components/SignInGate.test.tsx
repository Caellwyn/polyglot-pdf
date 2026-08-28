/**
 * SignInGate (bd polyglot-pdf-yswp3): the editor's per-user front door.
 *
 * The behaviours worth pinning are the ones that were WRONG under the shared
 * access code, or that a careless refactor would collapse:
 *   - 403 (signed in, no editor role) must NOT be treated as a sign-in failure.
 *     Retyping a password can never fix it, so re-prompting is a dead end.
 *   - 401 signs the person out first, so the retry starts clean.
 *   - A 503 must NOT sign a working editor out.
 *   - The gate never mints accounts (editor access is granted, not self-served).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SignInGate } from './SignInGate';
import { AuthError, ForbiddenError, probeSession } from '../utils/remoteKitStore';
import {
  isAuthConfigured, sendReset, signInWithGoogle, signInWithPassword,
  signOutEditor, watchEditorUser,
} from '../utils/editorAuth';

vi.mock('../utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/remoteKitStore')>();
  // Keep the REAL error classes -- the gate branches on instanceof, so mocking
  // them would make every branch test vacuous.
  return { ...actual, probeSession: vi.fn() };
});

vi.mock('../utils/editorAuth', () => ({
  isAuthConfigured: vi.fn(() => true),
  watchEditorUser: vi.fn(),
  signInWithGoogle: vi.fn(),
  signInWithPassword: vi.fn(),
  sendReset: vi.fn(),
  signOutEditor: vi.fn(async () => {}),
  currentEditorEmail: vi.fn(() => 'editor@example.com'),
  editorIdToken: vi.fn(async () => 'id-token'),
}));

let authListeners: Array<(u: unknown) => void> = [];
let currentUser: unknown = null;

function emitUser(user: unknown) {
  currentUser = user;
  authListeners.forEach((cb) => cb(user));
}

const SIGNED_IN = { uid: 'u1', email: 'editor@example.com' };

beforeEach(() => {
  vi.clearAllMocks();
  authListeners = [];
  currentUser = null;
  vi.mocked(isAuthConfigured).mockReturnValue(true);
  vi.mocked(signOutEditor).mockResolvedValue(undefined);
  vi.mocked(watchEditorUser).mockImplementation((cb: (u: never) => void) => {
    const fn = cb as (u: unknown) => void;
    authListeners.push(fn);
    fn(currentUser);
    return () => { authListeners = authListeners.filter((l) => l !== fn); };
  });
  vi.mocked(probeSession).mockResolvedValue({ role: 'editor' });
});

describe('SignInGate', () => {
  it('signs in with email and reports the role the server returns', async () => {
    vi.mocked(probeSession).mockResolvedValue({ role: 'author' });
    vi.mocked(signInWithPassword).mockImplementation(async () => emitUser(SIGNED_IN));
    const onReady = vi.fn();
    render(<SignInGate onReady={onReady} />);

    fireEvent.change(await screen.findByLabelText('Email'),
      { target: { value: 'editor@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(onReady).toHaveBeenCalledWith('author'));
    expect(signInWithPassword).toHaveBeenCalledWith('editor@example.com', 'pw');
  });

  it('signs in with Google', async () => {
    vi.mocked(signInWithGoogle).mockImplementation(async () => emitUser(SIGNED_IN));
    const onReady = vi.fn();
    render(<SignInGate onReady={onReady} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Sign in with Google' }));

    await waitFor(() => expect(onReady).toHaveBeenCalledWith('editor'));
  });

  // THE case this bead exists to get right. A voice-app account authenticates
  // perfectly and still has no editor access: showing the sign-in form again
  // would loop them forever through a step that already succeeded.
  it('a 403 explains that access must be granted, and does NOT re-prompt', async () => {
    vi.mocked(probeSession).mockRejectedValue(
      new ForbiddenError('This account does not have schema editor access'));
    const onReady = vi.fn();
    currentUser = SIGNED_IN;
    render(<SignInGate onReady={onReady} />);

    await screen.findByTestId('signin-refused');
    expect(screen.getByText(/does not have schema editor access/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
    expect(onReady).not.toHaveBeenCalled();
    // NOT signed out automatically -- the person may legitimately want to stay
    // signed in while an operator grants them access.
    expect(signOutEditor).not.toHaveBeenCalled();
  });

  it('the refused screen offers a way back to a different account', async () => {
    vi.mocked(probeSession).mockRejectedValue(new ForbiddenError('nope'));
    currentUser = SIGNED_IN;
    render(<SignInGate onReady={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button',
      { name: 'Sign in with a different account' }));

    await waitFor(() => expect(signOutEditor).toHaveBeenCalled());
  });

  it('a 401 signs the person out and shows the form again', async () => {
    vi.mocked(probeSession).mockRejectedValue(new AuthError());
    currentUser = SIGNED_IN;
    render(<SignInGate onReady={vi.fn()} />);

    await screen.findByLabelText('Password');
    await waitFor(() => expect(signOutEditor).toHaveBeenCalled());
  });

  // A transient server fault must not evict a working editor: their credential
  // is fine, and signing everyone out over a 503 is worse than the outage.
  it('a 503 shows the reason and does NOT sign the person out', async () => {
    vi.mocked(probeSession).mockRejectedValue(
      new Error('The editor surface is not configured on this server'));
    currentUser = SIGNED_IN;
    render(<SignInGate onReady={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText(/not configured/)).toBeInTheDocument());
    expect(signOutEditor).not.toHaveBeenCalled();
  });

  it('sends a password reset email and returns to the sign-in form', async () => {
    vi.mocked(sendReset).mockResolvedValue(undefined);
    render(<SignInGate onReady={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Forgot password?' }));
    fireEvent.change(screen.getByLabelText('Email'),
      { target: { value: 'editor@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send reset email' }));

    await waitFor(() => expect(sendReset).toHaveBeenCalledWith('editor@example.com'));
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

  // Editor access is GRANTED (scripts/bootstrap_editor_user.py), never
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
    expect(probeSession).not.toHaveBeenCalled();
  });

  it('says so when the build has no Firebase configuration', async () => {
    vi.mocked(isAuthConfigured).mockReturnValue(false);
    render(<SignInGate onReady={vi.fn()} />);

    await screen.findByTestId('signin-unconfigured');
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
    expect(probeSession).not.toHaveBeenCalled();
  });
});
