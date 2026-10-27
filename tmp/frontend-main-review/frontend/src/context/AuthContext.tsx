'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { UserSession } from '../types/api';
import { TEST_USERS } from '../mock/mockData';
import {
  loginRequest,
  loginRedirectRequest,
  isAzureConfigured,
} from '../services/authConfig';
import { InteractionStatus } from '@azure/msal-browser';
import { useMsal } from '@azure/msal-react';
import { API_BASE_URL, clearAccessToken, getAccessToken, setAccessToken } from '../services/apiClient';

interface AuthContextType {
  user: UserSession | null;
  loading: boolean;
  authError: string | null;
  loginWithEmail: (email: string) => Promise<boolean>;
  loginWithAzure: () => Promise<void>;
  logout: () => void;
  testUsers: UserSession[];
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

type ApiProfile = {
  userId: string;
  email: string | null;
  displayName: string | null;
  role: UserSession['role'];
  clientId: string | null;
  preferredLanguage: UserSession['preferredLanguage'];
};

async function responseDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === 'string' ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

async function profileForToken(token: string): Promise<UserSession> {
  const response = await fetch(`${API_BASE_URL}/me`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(await responseDetail(response, `No se pudo validar el perfil (${response.status}).`));
  const profile = await response.json() as ApiProfile;
  if (!['spokesperson', 'client_admin', 'master_config'].includes(profile.role)) {
    throw new Error('La API devolvió un rol no reconocido.');
  }
  const displayName = profile.displayName || profile.email || 'Usuario';
  return {
    userId: profile.userId,
    email: profile.email || '',
    displayName,
    role: profile.role,
    clientId: profile.clientId,
    clientName: '',
    initials: displayName.split(/\s+/).slice(0, 2).map(part => part[0]?.toUpperCase()).join(''),
    preferredLanguage: profile.preferredLanguage || 'es',
  };
}

async function authenticateDevelopmentUser(email: string): Promise<UserSession> {
  const tokenResponse = await fetch(`${API_BASE_URL}/dev/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.trim() }),
  });
  if (!tokenResponse.ok) {
    throw new Error(await responseDetail(tokenResponse, `No se pudo iniciar sesión (${tokenResponse.status}).`));
  }
  const body = await tokenResponse.json() as { accessToken?: string };
  if (!body.accessToken) throw new Error('La API no entregó un token de desarrollo.');
  setAccessToken(body.accessToken);
  try {
    return await profileForToken(body.accessToken);
  } catch (error) {
    clearAccessToken();
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Inner provider when MSAL IS available
// ---------------------------------------------------------------------------
function MsalAuthProvider({ children }: { children: React.ReactNode }) {
  const { instance, accounts, inProgress } = useMsal();
  const [user, setUser] = useState<UserSession | null>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('voxready_user');
      if (saved) {
        try {
          return JSON.parse(saved);
        } catch {
          /* ignore corrupt data */
        }
      }
    }
    return null;
  });
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  // Safety timer: ensure loading doesn't hang if MSAL startup or network hangs
  useEffect(() => {
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
      const storedToken = getAccessToken();
      if (storedToken) {
        try {
          const session = await profileForToken(storedToken);
          setUser(session);
          setAuthError(null);
          localStorage.setItem('voxready_user', JSON.stringify(session));
        } catch (error) {
          setUser(null);
          clearAccessToken();
          localStorage.removeItem('voxready_user');
          setAuthError(error instanceof Error ? error.message : 'No se pudo validar la sesión.');
        }
      } else {
        setUser(null);
        localStorage.removeItem('voxready_user');
      }
      setLoading(false);
      return;
    }

    try {
      const tokenResponse = await instance.acquireTokenSilent({
        ...loginRequest,
        account,
      });

      const accessToken = tokenResponse.accessToken;
      setAccessToken(accessToken);
      const session = await profileForToken(accessToken);
      setUser(session);
      setAuthError(null);
      localStorage.setItem('voxready_user', JSON.stringify(session));
    } catch (err) {
      console.warn('[Auth] Token acquisition or backend profile fetch failed:', err);
      setUser(null);
      clearAccessToken();
      localStorage.removeItem('voxready_user');
      setAuthError(err instanceof Error ? err.message : 'No se pudo validar la sesión.');
    } finally {
      setLoading(false);
    }
  }, [accounts, inProgress, instance]);

  useEffect(() => {
    const handle = setTimeout(() => {
      resolveAzureUser();
    }, 0);
    return () => clearTimeout(handle);
  }, [resolveAzureUser]);

  const loginWithAzure = async () => {
    setLoading(true);
    setAuthError(null);
    try {
      await instance.loginRedirect(loginRedirectRequest);
    } catch (err) {
      console.warn('[Auth] loginRedirect failed or cancelled:', err);
      setLoading(false);
      throw err;
    }
  };

  const loginWithEmail = async (email: string): Promise<boolean> => {
    setLoading(true);
    setAuthError(null);
    try {
      const session = await authenticateDevelopmentUser(email);
      setUser(session);
      localStorage.setItem('voxready_user', JSON.stringify(session));
      return true;
    } catch (error) {
      setUser(null);
      clearAccessToken();
      localStorage.removeItem('voxready_user');
      setAuthError(error instanceof Error ? error.message : 'No se pudo iniciar sesión.');
      return false;
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    setUser(null);
    setAuthError(null);
    localStorage.removeItem('voxready_user');
    clearAccessToken();

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
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    const storedToken = getAccessToken();
    if (!storedToken) {
      localStorage.removeItem('voxready_user');
      setLoading(false);
      return;
    }
    profileForToken(storedToken).then(session => {
      setUser(session);
      localStorage.setItem('voxready_user', JSON.stringify(session));
    }).catch(error => {
      clearAccessToken();
      localStorage.removeItem('voxready_user');
      setAuthError(error instanceof Error ? error.message : 'No se pudo validar la sesión.');
    }).finally(() => setLoading(false));
  }, []);

  const loginWithEmail = async (email: string): Promise<boolean> => {
    setLoading(true);
    setAuthError(null);
    try {
      const session = await authenticateDevelopmentUser(email);
      setUser(session);
      localStorage.setItem('voxready_user', JSON.stringify(session));
      return true;
    } catch (error) {
      setUser(null);
      clearAccessToken();
      localStorage.removeItem('voxready_user');
      setAuthError(error instanceof Error ? error.message : 'No se pudo iniciar sesión.');
      return false;
    } finally {
      setLoading(false);
    }
  };

  const loginWithAzure = async () => {
    console.warn('[Auth] Azure not configured — loginWithAzure is a no-op');
  };

  const logout = () => {
    setUser(null);
    setAuthError(null);
    localStorage.removeItem('voxready_user');
    clearAccessToken();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        authError,
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
