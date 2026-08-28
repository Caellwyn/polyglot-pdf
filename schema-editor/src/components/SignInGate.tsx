import React from 'react';
import {
  isAuthConfigured, sendReset, signInWithGoogle, signInWithPassword,
  signOutEditor, watchEditorUser,
} from '../utils/editorAuth';
import { AuthError, ForbiddenError, probeSession, type EditorRole } from '../utils/remoteKitStore';

interface SignInGateProps {
  /** Called once a signed-in person is confirmed to HAVE editor access;
   * carries the role the server reports (editor vs author). */
  onReady: (role: EditorRole) => void;
  /** Set when a call FAILED with 403 mid-session (an operator revoked this
   * person's editor role while their ID token was still valid). Shows the
   * refused screen immediately rather than re-probing, since the probe would
   * only 403 again. */
  refusedReason?: string | null;
}

type Mode = 'signin' | 'reset';

/**
 * The hosted editor's front gate (bd polyglot-pdf-yswp3): sign in AS YOURSELF.
 *
 * Replaces AccessCodeGate, which asked for a shared access code. The server
 * stopped accepting that code when per-user identity landed
 * (bd polyglot-pdf-hn0jq), so the old gate could no longer let anyone in at all.
 *
 * TWO GATES, and keeping them distinct is the whole UX problem here:
 *   1. AUTHENTICATION -- Firebase proves who you are.
 *   2. AUTHORIZATION  -- the server checks this surface's own role claim,
 *      stamped by scripts/bootstrap_editor_user.py.
 * Passing (1) and failing (2) is the NORMAL state for a voice-app account, and
 * for an editor whose account exists but has not been granted a role yet. That
 * case must not read as "wrong password": the person's credentials were fine
 * and retyping them will never help. It needs an operator to grant access, so
 * the message says so and offers a way back out (sign out and try another
 * account).
 *
 * DELIBERATELY NO "create account" (unlike the voice app's Login.tsx, whose
 * shape this otherwise mirrors): editor access is granted, never self-served.
 * A new account would only ever hit the 403 above.
 *
 * Duplicates the voice app's sign-in SHAPE without importing it -- see
 * utils/editorAuth.ts for why that duplication is deliberate.
 */
export const SignInGate: React.FC<SignInGateProps> = ({ onReady, refusedReason }) => {
  const [mode, setMode] = React.useState<Mode>('signin');
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [info, setInfo] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  // A signed-in account that the SERVER refused (no editor role). Held
  // separately from `error` because it needs its own escape hatch rather than
  // a retry -- retyping a correct password cannot fix it.
  const [refused, setRefused] = React.useState<string | null>(refusedReason ?? null);
  // True while we still have a Firebase session to restore + probe. Starts true
  // so a returning editor sees "Checking your access..." rather than a flash of
  // the sign-in form they are about to be sent through.
  const [restoring, setRestoring] = React.useState(!refusedReason);

  const configured = React.useMemo(isAuthConfigured, []);

  /** Ask the server whether this signed-in person actually has editor access. */
  const probe = React.useCallback(async () => {
    try {
      const session = await probeSession();
      onReady(session.role);
    } catch (err) {
      if (err instanceof ForbiddenError) {
        // Authenticated, NOT authorized -- the account is real but carries no
        // editor role claim. The actionable thing is to ask an operator, so
        // say that instead of a generic failure.
        setRefused(err.message);
      } else if (err instanceof AuthError) {
        // The token itself was refused. Sign out so the next attempt starts
        // from a clean session rather than retrying the same bad credential.
        await signOutEditor().catch(() => { /* already signed out */ });
        setError('Your sign-in was not accepted. Please sign in again.');
      } else {
        // A 503 (editor surface off server-side) or a network blip. Do NOT
        // sign the person out for this -- their credentials are fine and a
        // transient server problem must not log every editor out.
        setError(err instanceof Error ? err.message : 'Could not check your access');
      }
    }
  }, [onReady]);

  // Restore an existing Firebase session on mount, then probe it. This is what
  // makes a returning editor go straight to the catalogue.
  React.useEffect(() => {
    if (!configured) {
      setRestoring(false);
      return;
    }
    // Already known-refused (403 mid-session): re-probing would just 403 again,
    // and the person would watch a spinner to reach the same screen.
    if (refusedReason) {
      setRestoring(false);
      return;
    }
    let cancelled = false;
    const unsub = watchEditorUser((user) => {
      if (cancelled) return;
      if (!user) {
        setRestoring(false);
        return;
      }
      void probe().finally(() => { if (!cancelled) setRestoring(false); });
    });
    return () => { cancelled = true; unsub(); };
  }, [configured, probe, refusedReason]);

  const handleGoogle = React.useCallback(async () => {
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      await signInWithGoogle();
      // The onAuthStateChanged watcher above fires and runs the probe.
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const handleSubmit = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      if (mode === 'reset') {
        await sendReset(email);
        setInfo('Password reset email sent. Check your inbox.');
        setMode('signin');
      } else {
        await signInWithPassword(email, password);
        // The watcher fires and runs the probe.
      }
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }, [email, password, mode]);

  const handleSignOut = React.useCallback(async () => {
    setRefused(null);
    setError(null);
    setPassword('');
    await signOutEditor().catch(() => { /* nothing to sign out of */ });
  }, []);

  if (!configured) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-50">
        <div
          className="w-full max-w-sm bg-white border border-gray-200 rounded-lg shadow-sm p-6"
          data-testid="signin-unconfigured"
        >
          <h1 className="text-xl font-bold text-gray-900">PDF Schema Editor</h1>
          <p className="mt-2 text-sm text-red-600">
            This editor build has no Firebase configuration, so it cannot sign
            anyone in. It needs rebuilding with the VITE_FIREBASE_* values set.
          </p>
        </div>
      </div>
    );
  }

  if (restoring) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-500">Checking your access...</p>
      </div>
    );
  }

  if (refused) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-50">
        <div
          className="w-full max-w-sm bg-white border border-gray-200 rounded-lg shadow-sm p-6"
          data-testid="signin-refused"
        >
          <h1 className="text-xl font-bold text-gray-900">Not an editor account</h1>
          <p className="mt-2 text-sm text-gray-600">{refused}</p>
          <p className="mt-2 text-sm text-gray-600">
            You signed in successfully, but this account has not been granted
            access to the schema editor. Ask whoever administers the editor to
            grant it, then reload this page.
          </p>
          <button
            type="button"
            className="btn btn-primary mt-4 w-full"
            onClick={() => void handleSignOut()}
          >
            Sign in with a different account
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex items-center justify-center bg-gray-50">
      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="w-full max-w-sm bg-white border border-gray-200 rounded-lg shadow-sm p-6"
        data-testid="signin-gate"
      >
        <h1 className="text-xl font-bold text-gray-900">PDF Schema Editor</h1>
        <p className="mt-1 text-sm text-gray-600">
          {mode === 'reset'
            ? 'Enter your email and we will send you a reset link.'
            : 'Sign in with your own account to open the form workspace.'}
        </p>

        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
        {info && <div className="mt-3 text-sm text-green-700">{info}</div>}

        <label className="block mt-4 text-sm text-gray-700" htmlFor="editor-email">
          Email
        </label>
        <input
          id="editor-email"
          type="email"
          autoFocus
          required
          autoComplete="email"
          className="mt-1 w-full border border-gray-300 rounded px-3 py-2 text-sm"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy}
        />

        {mode !== 'reset' && (
          <>
            <label className="block mt-3 text-sm text-gray-700" htmlFor="editor-password">
              Password
            </label>
            <input
              id="editor-password"
              type="password"
              required
              autoComplete="current-password"
              className="mt-1 w-full border border-gray-300 rounded px-3 py-2 text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
            />
          </>
        )}

        <button type="submit" className="btn btn-primary mt-4 w-full" disabled={busy}>
          {busy ? 'Working...' : mode === 'reset' ? 'Send reset email' : 'Sign in'}
        </button>

        <div className="mt-4 flex items-center gap-2 text-xs text-gray-400">
          <span className="flex-1 border-t border-gray-200" />
          or
          <span className="flex-1 border-t border-gray-200" />
        </div>

        <button
          type="button"
          className="btn mt-4 w-full border border-gray-300"
          onClick={() => void handleGoogle()}
          disabled={busy}
        >
          Sign in with Google
        </button>

        <div className="mt-4 text-sm">
          {mode === 'signin' ? (
            <button
              type="button"
              className="text-blue-600 hover:underline"
              onClick={() => { setMode('reset'); setError(null); }}
            >
              Forgot password?
            </button>
          ) : (
            <button
              type="button"
              className="text-blue-600 hover:underline"
              onClick={() => { setMode('signin'); setError(null); setInfo(null); }}
            >
              Back to sign in
            </button>
          )}
        </div>
      </form>
    </div>
  );
};

/** Firebase error codes -> something a human can act on.
 *
 * Mirrors the voice app's friendlyError (frontend/src/components/auth/Login.tsx)
 * minus the sign-up cases, which cannot arise here: this gate has no account
 * creation. */
function friendlyError(err: unknown): string {
  const code = (err as { code?: string } | null)?.code ?? '';
  if (code === 'auth/invalid-credential' || code === 'auth/wrong-password'
      || code === 'auth/user-not-found') {
    return 'Incorrect email or password.';
  }
  if (code === 'auth/invalid-email') return 'Please enter a valid email address.';
  if (code === 'auth/too-many-requests') {
    return 'Too many attempts. Please try again later.';
  }
  if (code === 'auth/popup-closed-by-user' || code === 'auth/cancelled-popup-request') {
    return 'The Google sign-in window closed before finishing.';
  }
  if (code === 'auth/popup-blocked') {
    return 'Your browser blocked the Google sign-in window. Allow popups and try again.';
  }
  // The editor is a SEPARATE Hosting site from the voice app, so its domain
  // must be listed under Firebase Auth > Settings > Authorized domains.
  // Without this case an operator sees a raw SDK string naming neither the
  // cause nor the fix -- and the build-time config check cannot catch it,
  // since the config is present and valid.
  if (code === 'auth/unauthorized-domain') {
    return 'Sign-in is not enabled for this web address yet. Whoever '
      + 'administers the editor needs to add this site to the Firebase '
      + 'project\'s authorized domains.';
  }
  return (err as { message?: string } | null)?.message
    ?? 'Something went wrong. Please try again.';
}
