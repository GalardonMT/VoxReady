'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../context/AuthContext';
import { protectedRouteDestination } from '../../services/routeAccess';
import type { Role } from '../../types/api';

export function RoleGate({ role, children }: { role: Role; children: React.ReactNode }) {
  const router = useRouter();
  const { user, status, error, retry } = useAuth();
  useEffect(() => {
    if (status === 'anonymous' || status === 'expired') router.replace('/login');
    else if (status === 'authenticated' && user) {
      const destination = protectedRouteDestination(user.role, role === 'master_config' ? '/master' : role === 'client_admin' ? '/admin' : '/spokesperson');
      if (destination) router.replace(destination);
    }
  }, [status, user, role, router]);
  if (status === 'offline') return <main className="canvas"><p>{error}</p><button type="button" onClick={retry}>Reintentar</button></main>;
  if (status !== 'authenticated' || !user || user.role !== role) return null;
  return <>{children}</>;
}
