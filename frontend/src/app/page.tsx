'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { LoginView } from '../components/auth/LoginView';
import { useAuth } from '../context/AuthContext';

export default function RootPage() {
  const router = useRouter();
  const { user, loading, authError } = useAuth();

  useEffect(() => {
    if (user) {
      if (user.role === 'master_config') {
        router.replace('/master');
      } else if (user.role === 'client_admin') {
        router.replace('/admin');
      } else {
        router.replace('/spokesperson');
      }
    }
  }, [user, router]);

  // While MSAL is processing the redirect response, show a loading state
  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          color: 'var(--muted)',
          fontSize: '14px',
        }}
      >
        <p>Autenticando…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <>
        {authError && (
          <div className="auth-error-banner">
            <div className="auth-error-banner-inner">
              <span className="auth-error-icon">⚠️</span>
              <span>{authError}</span>
            </div>
          </div>
        )}
        <LoginView
          onLoginSuccess={() => {
            // El useEffect redirigirá automáticamente al cambiar user
          }}
        />
      </>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        color: 'var(--muted)',
        fontSize: '14px',
      }}
    >
      <p>Redirigiendo a tu espacio de trabajo...</p>
    </div>
  );
}

