'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { UserSession } from '../types/api';
import { TEST_USERS } from '../mock/mockData';

interface AuthContextType {
  user: UserSession | null;
  loginAs: (user: UserSession) => void;
  loginWithEmail: (email: string) => boolean;
  logout: () => void;
  testUsers: UserSession[];
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserSession | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem('voxready_user');
    if (saved) {
      try {
        setUser(JSON.parse(saved));
      } catch {
        setUser(null);
      }
    }
  }, []);

  const loginAs = (u: UserSession) => {
    setUser(u);
    localStorage.setItem('voxready_user', JSON.stringify(u));
  };

  const loginWithEmail = (email: string): boolean => {
    const cleanEmail = email.trim().toLowerCase();
    const found = TEST_USERS.find((u) => u.email.toLowerCase() === cleanEmail);
    if (found) {
      setUser(found);
      localStorage.setItem('voxready_user', JSON.stringify(found));
      return true;
    }
    return false;
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('voxready_user');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loginAs,
        loginWithEmail,
        logout,
        testUsers: TEST_USERS
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
