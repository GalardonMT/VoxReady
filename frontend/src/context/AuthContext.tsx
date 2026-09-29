'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import type { UserSession } from '../types/api';
import { ApiError, NetworkError, clearAccessToken, getAccessToken } from '../services/apiClient';
import { authMode, completeExternalLogin, loadIdentity, loginLocal, beginExternalLogin, beginExternalLogout } from '../services/authService';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'expired' | 'offline';
interface AuthContextType {
  user: UserSession | null;
  status: AuthStatus;
  error: string;
  mode: typeof authMode;
  loginWithEmail: (email: string) => Promise<void>;
  loginExternal: () => Promise<void>;
  logout: () => void;
  retry: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserSession | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [error, setError] = useState('');

  const refresh = async () => {
    if (!getAccessToken()) { setUser(null); setStatus('anonymous'); return; }
    setStatus('loading');
    try {
      const identity = await loadIdentity();
      setUser(identity); setError(''); setStatus('authenticated');
    } catch (cause) {
      setUser(null);
      if (cause instanceof NetworkError) { setStatus('offline'); setError(cause.message); }
      else if (cause instanceof ApiError && cause.problem.status === 401) {
        setStatus('expired'); setError('Tu sesión caducó. Inicia sesión nuevamente.');
      } else { setStatus('anonymous'); setError(cause instanceof Error ? cause.message : 'No se pudo validar la sesión.'); }
    }
  };

  useEffect(() => {
    let active = true;
    async function initialize() {
      try {
        const identity = await completeExternalLogin();
        if (identity && active) { setUser(identity); setStatus('authenticated'); return; }
      } catch (cause) {
        if (active) {
          setError(cause instanceof Error ? cause.message : 'Error de identidad.');
          setStatus(cause instanceof NetworkError ? 'offline' : cause instanceof ApiError && cause.problem.status === 401 ? 'expired' : 'anonymous');
        }
        return;
      }
      if (active) await refresh();
    }
    initialize();
    const expired = () => { setUser(null); setStatus('expired'); setError('Tu sesión caducó. Inicia sesión nuevamente.'); };
    window.addEventListener('voxready:session-expired', expired);
    return () => { active = false; window.removeEventListener('voxready:session-expired', expired); };
  }, []);

  const loginWithEmail = async (email: string) => {
    setStatus('loading'); setError('');
    try { const identity = await loginLocal(email); setUser(identity); setStatus('authenticated'); }
    catch (cause) { setUser(null); setStatus(cause instanceof NetworkError ? 'offline' : 'anonymous'); setError(cause instanceof Error ? cause.message : 'No se pudo iniciar sesión.'); throw cause; }
  };
  const retry = async () => {
    if (authMode === 'azure') {
      try {
        const identity = await completeExternalLogin();
        if (identity) { setUser(identity); setError(''); setStatus('authenticated'); return; }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Error de identidad.');
        setStatus(cause instanceof NetworkError ? 'offline' : 'anonymous');
        return;
      }
    }
    await refresh();
  };
  const logout = () => {
    clearAccessToken(); setUser(null); setError(''); setStatus('anonymous');
    if (authMode === 'azure') void beginExternalLogout().catch((cause) => {
      setError(cause instanceof Error ? cause.message : 'No se pudo cerrar la sesión de Azure.');
    });
  };
  return (
    <AuthContext.Provider value={{ user, status, error, mode: authMode, loginWithEmail, loginExternal: beginExternalLogin, logout, retry }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
