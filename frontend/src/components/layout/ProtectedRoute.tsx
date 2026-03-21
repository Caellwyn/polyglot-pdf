import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { Login } from '../auth/Login';
import '../auth/Login.css';

interface ProtectedRouteProps {
    children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <div className="auth-loading">
                <div className="auth-spinner"></div>
            </div>
        );
    }

    if (!user) {
        return <Login />;
    }

    return <>{children}</>;
};
