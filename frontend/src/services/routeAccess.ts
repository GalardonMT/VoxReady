import type { Role } from '../types/api';

export function roleHome(role: Role): string {
  return role === 'master_config' ? '/master' : role === 'client_admin' ? '/admin' : '/spokesperson';
}

export function protectedRouteDestination(role: Role | null, path: '/spokesperson' | '/admin' | '/master'): string | null {
  if (!role) return '/login';
  const home = roleHome(role);
  return path === home ? null : home;
}
