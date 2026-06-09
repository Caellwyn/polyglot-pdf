import React, { createContext, useContext, useEffect, useState } from 'react';
import {
    User,
    signInWithPopup,
    GoogleAuthProvider,
    signOut as firebaseSignOut,
    onAuthStateChanged,
    sendPasswordResetEmail,
    browserLocalPersistence,
    setPersistence,
    createUserWithEmailAndPassword,
    signInWithEmailAndPassword,
} from 'firebase/auth';
import { auth, db } from '../firebase/config';
import { doc, getDoc, setDoc, serverTimestamp, collection, query, where, getDocs } from 'firebase/firestore';
import { isTestHarnessEnabled } from '../shared/config';

interface AuthContextType {
    user: User | null;
    loading: boolean;
    signInWithGoogle: () => Promise<void>;
    signInWithEmail: (email: string, password: string) => Promise<void>;
    signUpWithEmail: (email: string, password: string) => Promise<void>;
    logout: () => Promise<void>;
    resetPassword: (email: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // TEST-ONLY auth bypass (bd polyglot-pdf-g8w). The browser E2E voice harness
        // cannot sign in through Firebase, so when the harness gate is set (the same
        // double-gate as the injection hook in connection.ts: __VFF_LOCAL_DEV AND
        // __VFF_TEST_HARNESS) we install a mock user and skip the real Firebase
        // listener entirely. DOUBLE-GATED so it can NEVER run in production or in
        // normal local dev. No network, no Firestore write.
        if (isTestHarnessEnabled()) {
            const mockUser = {
                uid: 'vff-test-harness',
                email: 'harness@test.local',
                displayName: 'VFF Test Harness',
                photoURL: null,
                // getIdToken must resolve (SchemaForm calls user.getIdToken() for the
                // WS token). The local backend runs with VFF_DISABLE_AUTH=true so the
                // value is ignored -- a dummy string is enough to avoid a throw.
                getIdToken: async () => 'vff-test-harness-token',
            } as unknown as User;
            console.log('[Auth] TEST harness bypass active -- mock user installed (__VFF_TEST_HARNESS)');
            setUser(mockUser);
            setLoading(false);
            return;
        }

        // Enable local persistence
        setPersistence(auth, browserLocalPersistence).catch(console.error);

        const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
            setUser(currentUser);

            if (currentUser) {
                // Create user profile if it doesn't exist
                try {
                    const userRef = doc(db, 'users', currentUser.uid);
                    const userSnap = await getDoc(userRef);

                    if (!userSnap.exists()) {
                        await setDoc(userRef, {
                            uid: currentUser.uid,
                            email: currentUser.email,
                            displayName: currentUser.displayName,
                            photoURL: currentUser.photoURL,
                            createdAt: serverTimestamp(),
                            lastLogin: serverTimestamp(),
                            role: 'user' // default role
                        });
                        console.log('[Auth] Created new user profile for:', currentUser.uid);
                    } else {
                        // Update last login
                        await setDoc(userRef, { lastLogin: serverTimestamp() }, { merge: true });
                    }
                } catch (err) {
                    console.error('[Auth] Error syncing user profile:', err);
                }

                // Log basic info (no PII/PHI in insecure logs)
                console.log('[Auth] User connected:', currentUser.uid);
            }
            setLoading(false);
        });

        return () => unsubscribe();
    }, []);

    const signInWithGoogle = async () => {
        const provider = new GoogleAuthProvider();
        try {
            await signInWithPopup(auth, provider);
        } catch (error) {
            console.error('[Auth] Google Sign-In Error:', error);
            throw error;
        }
    };

    const signInWithEmail = async (email: string, password: string) => {
        try {
            await signInWithEmailAndPassword(auth, email, password);
        } catch (error) {
            console.error('[Auth] Email Sign-In Error:', error);
            throw error;
        }
    };

    const signUpWithEmail = async (email: string, password: string) => {
        // Check against authorized_emails collection before creating account
        const q = query(collection(db, 'authorized_emails'), where('email', '==', email.toLowerCase()));
        const snap = await getDocs(q);
        if (snap.empty) {
            throw new Error('This email is not authorized. Please contact the administrator.');
        }
        try {
            await createUserWithEmailAndPassword(auth, email, password);
        } catch (error) {
            console.error('[Auth] Email Sign-Up Error:', error);
            throw error;
        }
    };

    const logout = async () => {
        try {
            await firebaseSignOut(auth);
        } catch (error) {
            console.error('[Auth] Logout Error:', error);
            throw error;
        }
    };

    const resetPassword = async (email: string) => {
        await sendPasswordResetEmail(auth, email);
    };

    const value = {
        user,
        loading,
        signInWithGoogle,
        signInWithEmail,
        signUpWithEmail,
        logout,
        resetPassword
    };

    return (
        <AuthContext.Provider value={value}>
            {!loading && children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
