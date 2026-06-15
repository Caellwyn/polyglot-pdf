// @vitest-environment jsdom
//
// Spec: the frontend auth surface -- AuthContext + ProtectedRoute
// (bd polyglot-pdf-uov.13, T3.2). There were no tests for this surface.
//
// The load-bearing, security-critical behavior is the email-signup ALLOWLIST
// GATE: signUpWithEmail must query the authorized_emails collection and REFUSE
// to create an account when the email is not on the list. A regression here
// would let anyone self-register, so it is spec'd first and hardest.
//
// Firebase is entirely mocked: ../firebase/config (which calls getAuth/
// getFirestore at import and would otherwise need real credentials) is replaced
// with sentinels, and the firebase/auth + firebase/firestore functions the
// context calls are vi.fn()s we assert on. ProtectedRoute is rendered with a
// mocked useAuth so its three gate states are exercised directly.
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// --- Firebase module mocks (declared before importing the units under test) ---
vi.mock('../firebase/config', () => ({
    auth: { __sentinel: 'auth' },
    db: { __sentinel: 'db' },
}));

const mockCreateUser = vi.fn();
const mockSignInEmail = vi.fn();
const mockSignInPopup = vi.fn();
const mockSignOut = vi.fn();
const mockResetEmail = vi.fn();
const mockOnAuthStateChanged = vi.fn();
const mockSetPersistence = vi.fn().mockResolvedValue(undefined);

vi.mock('firebase/auth', () => ({
    GoogleAuthProvider: class {},
    signInWithPopup: (...a: unknown[]) => mockSignInPopup(...a),
    signInWithEmailAndPassword: (...a: unknown[]) => mockSignInEmail(...a),
    createUserWithEmailAndPassword: (...a: unknown[]) => mockCreateUser(...a),
    signOut: (...a: unknown[]) => mockSignOut(...a),
    sendPasswordResetEmail: (...a: unknown[]) => mockResetEmail(...a),
    onAuthStateChanged: (...a: unknown[]) => mockOnAuthStateChanged(...a),
    setPersistence: (...a: unknown[]) => mockSetPersistence(...a),
    browserLocalPersistence: { __sentinel: 'persistence' },
}));

const mockGetDocs = vi.fn();
const mockGetDoc = vi.fn();
const mockSetDoc = vi.fn();
// where() is a spy so the allowlist-query assertion can check the lowercased email.
const mockWhere = vi.fn((...a: unknown[]) => ({ __where: a }));

vi.mock('firebase/firestore', () => ({
    doc: (...a: unknown[]) => ({ __doc: a }),
    getDoc: (...a: unknown[]) => mockGetDoc(...a),
    setDoc: (...a: unknown[]) => mockSetDoc(...a),
    serverTimestamp: () => 'ts',
    collection: (...a: unknown[]) => ({ __collection: a }),
    query: (...a: unknown[]) => ({ __query: a }),
    where: (...a: unknown[]) => mockWhere(...a),
    getDocs: (...a: unknown[]) => mockGetDocs(...a),
}));

// Test-harness gate: default OFF so the real (mocked-Firebase) path runs. A
// single test flips it on to spec the bypass.
const mockIsTestHarnessEnabled = vi.fn(() => false);
vi.mock('../shared/config', () => ({
    isTestHarnessEnabled: () => mockIsTestHarnessEnabled(),
}));

import * as AuthModule from './AuthContext';
import { AuthProvider, useAuth } from './AuthContext';
import { ProtectedRoute } from '../components/layout/ProtectedRoute';

// useAuth mocked for ProtectedRoute's gate tests (it is the only thing
// ProtectedRoute reads). Re-import the real module elsewhere via the provider.
vi.mock('../components/auth/Login', () => ({
    Login: () => <div data-testid="login-screen">Login</div>,
}));


beforeEach(() => {
    vi.clearAllMocks();
    mockIsTestHarnessEnabled.mockReturnValue(false);
    // Default auth listener: no user, and report "settled" so loading -> false.
    mockOnAuthStateChanged.mockImplementation((_auth: unknown, cb: (u: unknown) => void) => {
        cb(null);
        return () => {};
    });
});

afterEach(() => {
    cleanup();
});


// ---------------------------------------------------------------------------
// A test harness that surfaces the AuthContext value so we can call its methods.
// ---------------------------------------------------------------------------
let ctx: ReturnType<typeof useAuth> | null = null;

function Capture() {
    ctx = useAuth();
    return <div data-testid="ready">{ctx.loading ? 'loading' : 'ready'}</div>;
}

async function renderAuth() {
    ctx = null;
    render(
        <AuthProvider>
            <Capture />
        </AuthProvider>
    );
    // AuthProvider renders children only when !loading; wait for it to settle.
    await waitFor(() => expect(screen.getByTestId('ready')).toBeTruthy());
}


// ===========================================================================
// 1. The email-signup ALLOWLIST GATE (security-critical)
// ===========================================================================
describe('AuthContext signUpWithEmail -- authorized_emails allowlist gate', () => {
    it('REFUSES to create an account when the email is not on the allowlist', async () => {
        mockGetDocs.mockResolvedValue({ empty: true }); // not in authorized_emails
        await renderAuth();

        await expect(
            ctx!.signUpWithEmail('stranger@example.com', 'pw')
        ).rejects.toThrow(/not authorized/i);

        // The account was NEVER created -- the gate blocks before Firebase.
        expect(mockCreateUser).not.toHaveBeenCalled();
    });

    it('creates the account when the email IS on the allowlist', async () => {
        mockGetDocs.mockResolvedValue({ empty: false }); // present in authorized_emails
        mockCreateUser.mockResolvedValue({ user: { uid: 'u1' } });
        await renderAuth();

        await ctx!.signUpWithEmail('allowed@example.com', 'pw');

        expect(mockCreateUser).toHaveBeenCalledTimes(1);
        // Created with the auth sentinel + the given credentials.
        const [, email, password] = mockCreateUser.mock.calls[0];
        expect(email).toBe('allowed@example.com');
        expect(password).toBe('pw');
    });

    it('queries the allowlist with a lowercased email (case-insensitive gate)', async () => {
        mockGetDocs.mockResolvedValue({ empty: false });
        mockCreateUser.mockResolvedValue({});
        await renderAuth();

        await ctx!.signUpWithEmail('MixedCase@Example.COM', 'pw');

        // The where() clause must have been built with the lowercased email, so
        // an allowlist entry stored lowercase still matches a mixed-case signup.
        expect(mockWhere).toHaveBeenCalledWith('email', '==', 'mixedcase@example.com');
    });

    it('propagates a Firebase create error (e.g. email-already-in-use) to the caller', async () => {
        mockGetDocs.mockResolvedValue({ empty: false });
        mockCreateUser.mockRejectedValue(new Error('auth/email-already-in-use'));
        await renderAuth();

        await expect(
            ctx!.signUpWithEmail('allowed@example.com', 'pw')
        ).rejects.toThrow(/email-already-in-use/);
    });
});


// ===========================================================================
// 2. The other AuthContext methods delegate to Firebase and re-throw on error
// ===========================================================================
describe('AuthContext sign-in / reset delegation', () => {
    it('signInWithEmail delegates to Firebase with the credentials', async () => {
        mockSignInEmail.mockResolvedValue({});
        await renderAuth();

        await ctx!.signInWithEmail('user@example.com', 'pw');

        const [, email, password] = mockSignInEmail.mock.calls[0];
        expect(email).toBe('user@example.com');
        expect(password).toBe('pw');
    });

    it('signInWithEmail re-throws a Firebase auth error', async () => {
        mockSignInEmail.mockRejectedValue(new Error('auth/wrong-password'));
        await renderAuth();

        await expect(
            ctx!.signInWithEmail('user@example.com', 'bad')
        ).rejects.toThrow(/wrong-password/);
    });

    it('resetPassword delegates to sendPasswordResetEmail with the email', async () => {
        mockResetEmail.mockResolvedValue(undefined);
        await renderAuth();

        await ctx!.resetPassword('user@example.com');

        const [, email] = mockResetEmail.mock.calls[0];
        expect(email).toBe('user@example.com');
    });

    it('logout delegates to Firebase signOut', async () => {
        mockSignOut.mockResolvedValue(undefined);
        await renderAuth();

        await ctx!.logout();

        expect(mockSignOut).toHaveBeenCalledTimes(1);
    });
});


// ===========================================================================
// 3. loading state + test-harness bypass
// ===========================================================================
describe('AuthContext lifecycle', () => {
    it('starts in loading and flips to ready once the auth state settles', async () => {
        // Hold the callback so we can observe the loading->ready transition.
        let settle: ((u: unknown) => void) | null = null;
        mockOnAuthStateChanged.mockImplementation((_a: unknown, cb: (u: unknown) => void) => {
            settle = cb;
            return () => {};
        });

        ctx = null;
        render(
            <AuthProvider>
                <Capture />
            </AuthProvider>
        );
        // While loading, AuthProvider renders NOTHING (children gated on !loading).
        expect(screen.queryByTestId('ready')).toBeNull();

        settle!(null); // auth state resolves -> loading false
        await waitFor(() => expect(screen.getByTestId('ready')).toBeTruthy());
        expect(screen.getByTestId('ready').textContent).toBe('ready');
    });

    it('installs a mock user and skips Firebase entirely when the test harness is enabled', async () => {
        mockIsTestHarnessEnabled.mockReturnValue(true);
        await renderAuth();

        // The real Firebase auth listener must NOT have been attached.
        expect(mockOnAuthStateChanged).not.toHaveBeenCalled();
        expect(ctx!.user?.uid).toBe('vff-test-harness');
        // The mock user's getIdToken resolves (SchemaForm needs it for the WS token).
        await expect(ctx!.user!.getIdToken()).resolves.toBe('vff-test-harness-token');
    });
});


// ===========================================================================
// 4. useAuth outside a provider throws (the misuse guard)
// ===========================================================================
describe('useAuth guard', () => {
    it('throws when used outside an AuthProvider', () => {
        function Orphan() {
            useAuth();
            return null;
        }
        // Silence the expected React error boundary console noise.
        const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
        expect(() => render(<Orphan />)).toThrow(/must be used within an AuthProvider/);
        spy.mockRestore();
    });
});


// ===========================================================================
// 5. ProtectedRoute gate: loading -> spinner, no user -> Login, user -> children
//
// ProtectedRoute is tested in ISOLATION by spying on useAuth, so all THREE of
// its branches run -- including the loading-spinner branch. (Rendering it inside
// the real AuthProvider would NOT exercise that branch: AuthProvider gates its
// children on `{!loading && children}`, so ProtectedRoute never even mounts while
// loading. Driving useAuth directly is the only way to reach the spinner.)
// ===========================================================================
describe('ProtectedRoute gate', () => {
    // Restore the useAuth spy after each case so it cannot leak into the
    // AuthProvider-based tests (which need the real useAuth). Scoped to this
    // block so it does not touch the module-level vi.mock factories.
    afterEach(() => {
        vi.mocked(AuthModule.useAuth).mockRestore?.();
    });

    function renderGate(authValue: { user: unknown; loading: boolean }) {
        vi.spyOn(AuthModule, 'useAuth').mockReturnValue(
            authValue as unknown as ReturnType<typeof useAuth>
        );
        return render(
            <ProtectedRoute>
                <div data-testid="protected">secret</div>
            </ProtectedRoute>
        );
    }

    it('renders the loading spinner (not the content) while auth is loading', () => {
        renderGate({ user: null, loading: true });

        // The real spinner branch (ProtectedRoute.tsx) runs: the auth-loading
        // container is present, and neither the Login screen nor the protected
        // content is shown.
        expect(document.querySelector('.auth-loading')).not.toBeNull();
        expect(document.querySelector('.auth-spinner')).not.toBeNull();
        expect(screen.queryByTestId('protected')).toBeNull();
        expect(screen.queryByTestId('login-screen')).toBeNull();
    });

    it('renders the Login screen when not loading and there is no user', () => {
        renderGate({ user: null, loading: false });

        expect(screen.getByTestId('login-screen')).toBeTruthy();
        expect(screen.queryByTestId('protected')).toBeNull();
        expect(document.querySelector('.auth-loading')).toBeNull();
    });

    it('renders the protected children when a user is present', () => {
        renderGate({ user: { uid: 'u1' }, loading: false });

        expect(screen.getByTestId('protected')).toBeTruthy();
        expect(screen.queryByTestId('login-screen')).toBeNull();
    });
});
