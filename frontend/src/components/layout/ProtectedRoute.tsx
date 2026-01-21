import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { Login } from '../auth/Login';

interface ProtectedRouteProps {
    children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <div className="flex min-h-screen items-center justify-center">
                <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-indigo-600"></div>
            </div>
        );
    }

    if (!user) {
        return <Login />;
    }

    return <>{children}</>;
};
