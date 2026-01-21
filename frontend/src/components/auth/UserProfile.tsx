import React, { useEffect, useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { doc, getDoc, updateDoc } from 'firebase/firestore';
import { db } from '../../firebase/config';

interface UserProfileData {
    displayName: string;
    email: string;
    photoURL?: string;
    role?: string;
}

export const UserProfile: React.FC = () => {
    const { user, logout } = useAuth();
    const [profile, setProfile] = useState<UserProfileData | null>(null);
    const [isEditing, setIsEditing] = useState(false);
    const [newName, setNewName] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchProfile() {
            if (!user) return;
            try {
                const docRef = doc(db, 'users', user.uid);
                const docSnap = await getDoc(docRef);
                if (docSnap.exists()) {
                    const data = docSnap.data() as UserProfileData;
                    setProfile(data);
                    setNewName(data.displayName || user.displayName || '');
                } else {
                    // Fallback to Auth data if no profile yet (should be created on login)
                    setProfile({
                        displayName: user.displayName || '',
                        email: user.email || '',
                        photoURL: user.photoURL || ''
                    });
                    setNewName(user.displayName || '');
                }
            } catch (err) {
                console.error("Error fetching profile:", err);
            } finally {
                setLoading(false);
            }
        }
        fetchProfile();
    }, [user]);

    const handleSave = async () => {
        if (!user) return;
        try {
            const docRef = doc(db, 'users', user.uid);
            await updateDoc(docRef, {
                displayName: newName
            });
            setProfile(prev => prev ? { ...prev, displayName: newName } : null);
            setIsEditing(false);
        } catch (err) {
            console.error("Error updating profile:", err);
            alert("Failed to update profile");
        }
    };

    if (loading) return <div>Loading Profile...</div>;
    if (!user) return null;

    return (
        <div className="max-w-md mx-auto mt-10 p-6 bg-white rounded-lg shadow-md">
            <div className="flex items-center space-x-4 mb-6">
                {user.photoURL ? (
                    <img src={user.photoURL} alt="Profile" className="w-16 h-16 rounded-full" />
                ) : (
                    <div className="w-16 h-16 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-bold text-xl">
                        {user.displayName?.[0] || user.email?.[0]?.toUpperCase()}
                    </div>
                )}
                <div>
                    <h2 className="text-xl font-bold">{profile?.displayName || user.displayName}</h2>
                    <p className="text-gray-500 text-sm">{user.email}</p>
                    {profile?.role && (
                        <span className="inline-block bg-gray-100 rounded-full px-3 py-1 text-xs font-semibold text-gray-700 mr-2 mb-2">
                            {profile.role}
                        </span>
                    )}
                </div>
            </div>

            <div className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-gray-700">Display Name</label>
                    {isEditing ? (
                        <div className="flex mt-1">
                            <input
                                type="text"
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                                className="flex-1 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                            />
                            <button
                                onClick={handleSave}
                                className="ml-2 inline-flex justify-center rounded-md border border-transparent bg-indigo-600 py-2 px-4 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
                            >
                                Save
                            </button>
                            <button
                                onClick={() => setIsEditing(false)}
                                className="ml-2 inline-flex justify-center rounded-md border border-gray-300 bg-white py-2 px-4 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
                            >
                                Cancel
                            </button>
                        </div>
                    ) : (
                        <div className="flex mt-1 justify-between items-center">
                            <p className="text-gray-900">{profile?.displayName || 'Not set'}</p>
                            <button
                                onClick={() => setIsEditing(true)}
                                className="text-indigo-600 hover:text-indigo-900 text-sm font-medium"
                            >
                                Edit
                            </button>
                        </div>
                    )}
                </div>

                <div className="pt-4 border-t border-gray-200">
                    <button
                        onClick={logout}
                        className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                    >
                        Sign Out
                    </button>
                </div>
            </div>
        </div>
    );
};
