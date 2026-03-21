import React, { useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import './Login.css';

type Mode = 'signin' | 'signup' | 'reset';

export const Login: React.FC = () => {
    const { signInWithGoogle, signInWithEmail, signUpWithEmail, resetPassword } = useAuth();
    const [mode, setMode] = useState<Mode>('signin');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const handleGoogleSignIn = async () => {
        setError(null);
        setBusy(true);
        try {
            await signInWithGoogle();
        } catch (err: any) {
            setError('Google sign-in failed. ' + err.message);
        } finally {
            setBusy(false);
        }
    };

    const handleEmailSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setInfo(null);
        setBusy(true);
        try {
            if (mode === 'signin') {
                await signInWithEmail(email, password);
            } else if (mode === 'signup') {
                await signUpWithEmail(email, password);
            } else {
                await resetPassword(email);
                setInfo('Password reset email sent. Check your inbox.');
                setMode('signin');
            }
        } catch (err: any) {
            setError(friendlyError(err));
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="login-page">
            <div className="login-blob login-blob--1" />
            <div className="login-blob login-blob--2" />
            <div className="login-blob login-blob--3" />

            <div className="login-card-outer">
                <div className="login-card">
                    <h2 className="login-title">Polyglot PDF</h2>
                    <p className="login-subtitle">AI-powered voice form filling</p>

                    {error && <div className="login-error"><p>{error}</p></div>}
                    {info  && <div className="login-info"><p>{info}</p></div>}

                    <form onSubmit={handleEmailSubmit} className="login-form">
                        <div className="login-field">
                            <label htmlFor="email" className="login-label">Email</label>
                            <input
                                id="email"
                                type="email"
                                value={email}
                                onChange={e => setEmail(e.target.value)}
                                className="login-input"
                                placeholder="you@example.com"
                                required
                                autoComplete="email"
                            />
                        </div>

                        {mode !== 'reset' && (
                            <div className="login-field">
                                <label htmlFor="password" className="login-label">Password</label>
                                <input
                                    id="password"
                                    type="password"
                                    value={password}
                                    onChange={e => setPassword(e.target.value)}
                                    className="login-input"
                                    placeholder="••••••••"
                                    required
                                    autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                                />
                            </div>
                        )}

                        <button type="submit" className="login-button login-button--primary" disabled={busy}>
                            {mode === 'signin' ? 'Sign in' : mode === 'signup' ? 'Create account' : 'Send reset email'}
                        </button>
                    </form>

                    <div className="login-divider"><span>or</span></div>

                    <button onClick={handleGoogleSignIn} className="login-button login-button--google" disabled={busy}>
                        <svg className="login-button-icon" viewBox="0 0 24 24" aria-hidden="true">
                            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
                            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                        </svg>
                        Sign in with Google
                    </button>

                    <div className="login-links">
                        {mode === 'signin' && <>
                            <button type="button" className="login-link" onClick={() => { setMode('signup'); setError(null); }}>Create account</button>
                            <button type="button" className="login-link" onClick={() => { setMode('reset'); setError(null); }}>Forgot password?</button>
                        </>}
                        {mode === 'signup' && (
                            <button type="button" className="login-link" onClick={() => { setMode('signin'); setError(null); }}>Already have an account? Sign in</button>
                        )}
                        {mode === 'reset' && (
                            <button type="button" className="login-link" onClick={() => { setMode('signin'); setError(null); }}>Back to sign in</button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

function friendlyError(err: any): string {
    const code = err?.code ?? '';
    if (code === 'auth/invalid-credential' || code === 'auth/wrong-password' || code === 'auth/user-not-found') {
        return 'Incorrect email or password.';
    }
    if (code === 'auth/email-already-in-use') return 'An account with this email already exists.';
    if (code === 'auth/weak-password') return 'Password must be at least 6 characters.';
    if (code === 'auth/invalid-email') return 'Please enter a valid email address.';
    if (code === 'auth/too-many-requests') return 'Too many attempts. Please try again later.';
    return err?.message ?? 'Something went wrong. Please try again.';
}
