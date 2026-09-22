'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { UserSession } from '../types/api';
import { TEST_USERS } from '../mock/mockData';
import {
  msalInstance,
  loginRequest,
  loginRedirectRequest,
  isAzureConfigured,
} from '../services/authConfig';
import { InteractionStatus } from '@azure/msal-browser';
import { useMsal } from '@azure/msal-react';
import { API_BASE_URL } from '../services/apiClient';

interface AuthContextType {
  user: UserSession | null;
  loading: boolean;
  authError: string | null;
  loginAs: (user: UserSession) => void;
  loginWithEmail: (email: string) => boolean;
  loginWithAzure: () => Promise<void>;
  logout: () => void;
  testUsers: UserSession[];
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ---------------------------------------------------------------------------
// Inner provider when MSAL IS available
// ---------------------------------------------------------------------------
function MsalAuthProvider({ children }: { children: React.ReactNode }) {
  const { instance, accounts, inProgress } = useMsal();
  const [user, setUser] = useState<UserSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  // Restore from localStorage on first render (fast paint while MSAL resolves)
  useEffect(() => {
    const saved = localStorage.getItem('voxready_user');
    if (saved) {
      try {
        setUser(JSON.parse(saved));
      } catch {
        /* ignore corrupt data */
      }
    }
    // Safety timer: ensure loading doesn't hang if MSAL startup or network hangs
    const timer = setTimeout(() => {
      setLoading(false);
    }, 2500);
    return () => clearTimeout(timer);
  }, []);

  /**
   * After MSAL finishes processing the redirect (inProgress === 'none')
   * and an account is available, acquire an API token silently and
   * fetch the user profile from the backend.
   */
  const resolveAzureUser = useCallback(async () => {
    if (inProgress !== InteractionStatus.None) return;
    const account = accounts[0];
    if (!account) {
      setLoading(false);
      return;
    }

    try {
      const tokenResponse = await instance.acquireTokenSilent({
        ...loginRequest,
        account,
      });

      const accessToken = tokenResponse.accessToken;
      localStorage.setItem('voxready_token', accessToken);

      // Fetch the real profile from the backend
      const res = await fetch(`${API_BASE_URL}/me`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          Accept: 'application/json',
        },
      });

      if (res.ok) {
        const profile = await res.json();
        const session: UserSession = {
          userId: profile.userId,
          email: profile.email ?? account.username ?? '',
          displayName: profile.displayName ?? account.name ?? '',
          role: profile.role,
          clientId: profile.clientId ?? '',
          clientName: '',
          initials: (profile.displayName ?? account.name ?? '??')
            .split(' ')
            .map((w: string) => w[0])
            .join('')
            .slice(0, 2)
            .toUpperCase(),
          preferredLanguage: profile.preferredLanguage ?? 'es',
        };
        setUser(session);
        setAuthError(null);
        localStorage.setItem('voxready_user', JSON.stringify(session));
      } else if (res.status === 403) {
        // User authenticated via Entra but not provisioned in VoxReady
        let detail = 'Tu cuenta no está autorizada en VoxReady. Contacta al administrador de tu organización.';
        try {
          const body = await res.json();
          if (body.detail) detail = body.detail;
        } catch { /* use default message */ }
        setAuthError(detail);
        setUser(null);
        localStorage.removeItem('voxready_user');
        localStorage.removeItem('voxready_token');
      } else {
        console.warn('[Auth] Backend /me returned', res.status);
        let detail = `Error al obtener perfil del usuario (${res.status}).`;
        try {
          const body = await res.json();
          if (body.detail) detail = body.detail;
        } catch { /* use default message */ }
        setAuthError(detail);
        setUser(null);
        localStorage.removeItem('voxready_user');
        localStorage.removeItem('voxready_token');
      }
    } catch (err) {
      console.warn('[Auth] Token acquisition or backend profile fetch failed:', err);
    } finally {
      setLoading(false);
    }
  }, [accounts, inProgress, instance]);

  useEffect(() => {
    resolveAzureUser();
  }, [resolveAzureUser]);

  const loginWithAzure = async () => {
    setLoading(true);
    setAuthError(null);
    try {
      await instance.loginRedirect(loginRedirectRequest);
    } catch (err) {
      console.warn('[Auth] loginRedirect failed or cancelled:', err);
      setLoading(false);
    }
  };

  const loginAs = (u: UserSession) => {
    setUser(u);
    setAuthError(null);
    localStorage.setItem('voxready_user', JSON.stringify(u));
    localStorage.removeItem('voxready_token');
  };

  const loginWithEmail = (email: string): boolean => {
    const cleanEmail = email.trim().toLowerCase();
    const found = TEST_USERS.find((u) => u.email.toLowerCase() === cleanEmail);
    if (found) {
      loginAs(found);
      return true;
    }
    return false;
  };

  const logout = () => {
    setUser(null);
    setAuthError(null);
    localStorage.removeItem('voxready_user');
    localStorage.removeItem('voxready_token');

    if (accounts.length > 0) {
      instance.logoutRedirect({ postLogoutRedirectUri: '/' });
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        authError,
        loginAs,
        loginWithEmail,
        loginWithAzure,
        logout,
        testUsers: TEST_USERS,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Fallback provider when MSAL IS NOT available (no Azure config)
// ---------------------------------------------------------------------------
function FallbackAuthProvider({ children }: { children: React.ReactNode }) {
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
      loginAs(found);
      return true;
    }
    return false;
  };

  const loginWithAzure = async () => {
    console.warn('[Auth] Azure not configured — loginWithAzure is a no-op');
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('voxready_user');
    localStorage.removeItem('voxready_token');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading: false,
        authError: null,
        loginAs,
        loginWithEmail,
        loginWithAzure,
        logout,
        testUsers: TEST_USERS,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Exported provider — picks the right implementation
// ---------------------------------------------------------------------------
export function AuthProvider({ children }: { children: React.ReactNode }) {
  if (isAzureConfigured) {
    return <MsalAuthProvider>{children}</MsalAuthProvider>;
  }
  return <FallbackAuthProvider>{children}</FallbackAuthProvider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
