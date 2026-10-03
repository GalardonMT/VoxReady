'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../context/AuthContext';
import { protectedRouteDestination } from '../../services/routeAccess';
import type { Role } from '../../types/api';

export function RoleGate({ role, children }: { role: Role; children: React.ReactNode }) {
  const router = useRouter();
  const { user, loading, authError } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    } else if (!loading && user) {
      const destination = protectedRouteDestination(
        user.role,
        role === 'master_config' ? '/master' : role === 'client_admin' ? '/admin' : '/spokesperson'
      );
      if (destination) router.replace(destination);
    }
  }, [loading, user, role, router]);

  if (authError) {
    return (
      <main className="canvas">
        <p>{authError}</p>
        <button type="button" onClick={() => window.location.reload()}>
          Reintentar
        </button>
      </main>
    );
  }

  if (loading || !user || user.role !== role) return null;
  return <>{children}</>;
}
