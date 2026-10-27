'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { LoginView } from '../../../components/auth/LoginView';
import { useAuth } from '../../../context/AuthContext';

export default function LoginPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  // Si ya está autenticado, redirigir según su rol
  React.useEffect(() => {
    if (user) {
      if (user.role === 'master_config') router.push('/master');
      else if (user.role === 'client_admin') router.push('/admin');
      else router.push('/spokesperson');
    }
  }, [user, router]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', color: 'var(--muted)' }}>
        <p>Autenticando…</p>
      </div>
    );
  }

  const handleLoginSuccess = () => {
    // Redirigirá vía useEffect al cambiar user
  };

  return <LoginView onLoginSuccess={handleLoginSuccess} />;
}
