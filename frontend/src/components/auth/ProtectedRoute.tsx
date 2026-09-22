'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../context/AuthContext';

type AppRole = 'spokesperson' | 'client_admin' | 'master_config';

interface ProtectedRouteProps {
  /** Which roles are allowed to access this page */
  allowedRoles: AppRole[];
  children: React.ReactNode;
}

/**
 * Wrapper component that enforces authentication and role-based access control.
 *
 * - If the user is not authenticated → redirects to `/login`.
 * - If the user is authenticated but lacks the required role → shows access denied.
 * - Otherwise → renders children normally.
 */
export function ProtectedRoute({ allowedRoles, children }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    }
  }, [user, loading, router]);

  // Loading state
  if (loading) {
    return (
      <div className="protected-loading">
        <p>Verificando acceso…</p>
      </div>
    );
  }

  // Not authenticated
  if (!user) {
    return null;
  }

  // Authenticated but wrong role
  if (!allowedRoles.includes(user.role as AppRole)) {
    return <AccessDenied userRole={user.role} />;
  }

  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// Access Denied sub-component
// ---------------------------------------------------------------------------
function AccessDenied({ userRole }: { userRole: string }) {
  const { logout } = useAuth();
  const router = useRouter();

  const roleLabels: Record<string, string> = {
    spokesperson: 'Vocero',
    client_admin: 'Administrador de cliente',
    master_config: 'Configurador maestro',
  };

  return (
    <div className="access-denied-view">
      <div className="access-denied-card">
        <div className="access-denied-icon">🔒</div>
        <h1 className="access-denied-title">Acceso restringido</h1>
        <p className="access-denied-text">
          Tu rol actual (<strong>{roleLabels[userRole] ?? userRole}</strong>) no tiene permisos
          para acceder a esta sección.
        </p>
        <p className="access-denied-text access-denied-hint">
          Si crees que esto es un error, contacta al administrador de tu organización.
        </p>
        <div className="access-denied-actions">
          <button
            type="button"
            className="login-btn"
            onClick={() => {
              // Navigate to the correct section for their role
              if (userRole === 'master_config') router.replace('/master');
              else if (userRole === 'client_admin') router.replace('/admin');
              else router.replace('/spokesperson');
            }}
          >
            Ir a mi espacio
          </button>
          <button
            type="button"
            className="access-denied-logout"
            onClick={() => {
              logout();
              router.replace('/login');
            }}
          >
            Cerrar sesión
          </button>
        </div>
      </div>
    </div>
  );
}
