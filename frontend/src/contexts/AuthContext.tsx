import React, { createContext, useContext, useEffect, useState } from 'react';
import {
    User,
    signInWithPopup,
    GoogleAuthProvider,
    signOut as firebaseSignOut,
    onAuthStateChanged,
    sendPasswordResetEmail,
    browserLocalPersistence,
    setPersistence
} from 'firebase/auth';
import { auth } from '../firebase/config';

interface AuthContextType {
    user: User | null;
    loading: boolean;
    signInWithGoogle: () => Promise<void>;
    logout: () => Promise<void>;
    resetPassword: (email: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Enable local persistence
        setPersistence(auth, browserLocalPersistence).catch(console.error);

        import { doc, getDoc, setDoc, serverTimestamp } from 'firebase/firestore';
        import { db } from '../firebase/config';

        // ... (previous imports)

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
