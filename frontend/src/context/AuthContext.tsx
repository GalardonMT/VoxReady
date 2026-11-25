'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { UserSession } from '../types/api';
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
  loginWithAzure: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  logout: () => void;
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

// ---------------------------------------------------------------------------
// Inner provider when MSAL IS available
// ---------------------------------------------------------------------------
function MsalAuthProvider({ children }: { children: React.ReactNode }) {
  const { instance, accounts, inProgress } = useMsal();
  const [user, setUser] = useState<UserSession | null>(null);
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
    const account = instance.getActiveAccount() || accounts[0];
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
      console.warn('[Auth] No se pudo validar la sesión.');
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
      console.warn('[Auth] No se pudo iniciar o se canceló la autenticación.');
      setLoading(false);
      throw err;
    }
  };


  useEffect(() => {
    const blocked = () => {
      setUser(null); clearAccessToken(); localStorage.removeItem('voxready_user');
      setAuthError('Tu empresa está suspendida o no está disponible. Contacta al configurador maestro.');
    };
    const expired = () => {
      setUser(null); clearAccessToken(); localStorage.removeItem('voxready_user');
      setAuthError('Tu sesión terminó. Vuelve a ingresar mediante Microsoft Entra.');
    };
    window.addEventListener('voxready:company-blocked', blocked);
    window.addEventListener('voxready:session-expired', expired);
    return () => {
      window.removeEventListener('voxready:company-blocked', blocked);
      window.removeEventListener('voxready:session-expired', expired);
    };
  }, []);

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
        loginWithAzure,
        refreshProfile: resolveAzureUser,
        logout,
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
  const logout = () => {
    clearAccessToken(); localStorage.removeItem('voxready_user');
  };
  const loginWithAzure = async () => { throw new Error('Microsoft Entra no está configurado.'); };
  return <AuthContext.Provider value={{ user: null, loading: false,
    authError: 'Microsoft Entra no está configurado.', loginWithAzure, refreshProfile: async () => {}, logout }}>
    {children}
  </AuthContext.Provider>;
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
