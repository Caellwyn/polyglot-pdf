import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { Login } from '../auth/Login';
import '../auth/Login.css';

interface ProtectedRouteProps {
    children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
    // No loading branch: AuthProvider renders `{!loading && children}`
    // (AuthContext.tsx), so a ProtectedRoute never mounts while auth is loading --
    // the auth-init wait is owned upstream (bd polyglot-pdf-31u1).
    const { user } = useAuth();

    if (!user) {
        return <Login />;
    }

    return <>{children}</>;
};
