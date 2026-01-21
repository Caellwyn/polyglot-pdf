import React, { useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';


export const Login: React.FC = () => {
    const { signInWithGoogle, user } = useAuth();
    const [error, setError] = useState<string | null>(null);

    // Note: Since we might not have a router yet (checking dependencies), 
    // we'll handle redirection simply or assume browser reload for now.
    // Ideally we use useNavigate() from react-router-dom.

    const handleGoogleSignIn = async () => {
        try {
            setError(null);
            await signInWithGoogle();
        } catch (err: any) {
            setError('Failed to sign in via Google. ' + err.message);
        }
    };

    return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 py-12 sm:px-6 lg:px-8">
            <div className="sm:mx-auto sm:w-full sm:max-w-md">
                <h2 className="mt-6 text-center text-3xl font-bold tracking-tight text-gray-900">
                    Sign in to Polyglot PDF
                </h2>
                <p className="mt-2 text-center text-sm text-gray-600">
                    Or <a href="#" className="font-medium text-indigo-600 hover:text-indigo-500">contact support</a>
                </p>
            </div>

            <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
                <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10">
                    {error && (
                        <div className="mb-4 bg-red-50 border-l-4 border-red-400 p-4">
                            <div className="flex">
                                <div className="ml-3">
                                    <p className="text-sm text-red-700">{error}</p>
                                </div>
                            </div>
                        </div>
                    )}

                    <div>
                        <button
                            onClick={handleGoogleSignIn}
                            className="flex w-full justify-center rounded-md border border-transparent bg-indigo-600 py-2 px-4 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                        >
                            Sign in with Google
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
