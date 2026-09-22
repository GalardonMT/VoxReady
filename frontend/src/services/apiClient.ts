/**
 * Base API Client for VoxReady Backend
 * Handles RFC 7807 Problem Details errors, authentication tokens, and correlation IDs.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

export interface ProblemDetails {
  type?: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  correlationId?: string;
  code?: string;
}

export class ApiError extends Error {
  problem: ProblemDetails;

  constructor(problem: ProblemDetails) {
    super(problem.detail || problem.title || `API Error ${problem.status}`);
    this.name = 'ApiError';
    this.problem = problem;
  }
}

async function getAuthToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null;

  // 1. Check localStorage (set by AuthContext after login)
  const token = localStorage.getItem('voxready_token');
  if (token) return token;

  // 2. Try MSAL silent token renewal (if configured and user is signed in)
  try {
    const { msalInstance, loginRequest, isAzureConfigured } = await import('./authConfig');
    if (isAzureConfigured) {
      const accounts = msalInstance.getAllAccounts();
      if (accounts.length > 0) {
        const response = await msalInstance.acquireTokenSilent({
          ...loginRequest,
          account: accounts[0],
        });
        if (response.accessToken) {
          localStorage.setItem('voxready_token', response.accessToken);
          return response.accessToken;
        }
      }
    }
  } catch {
    // MSAL not available or silent renewal failed
  }

  // 3. Fallback: if user is logged in as a demo/dev user, try dev token if available
  const userJson = localStorage.getItem('voxready_user');
  if (userJson) {
    try {
      const user = JSON.parse(userJson);
      if (user.token) return user.token;
      const email = user.email || 'vocero@demo.voxready.io';
      const res = await fetch(`${API_BASE_URL}/dev/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.accessToken) {
          localStorage.setItem('voxready_token', data.accessToken);
          return data.accessToken;
        }
      }
    } catch {
      // Backend offline or dev token not enabled
    }
  }

  return null;
}

export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const token = await getAuthToken();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json, application/problem+json',
    ...(options.headers as Record<string, string> || {})
  };

  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Generar correlation-id para trazabilidad
  if (!headers['x-correlation-id']) {
    headers['x-correlation-id'] = `client-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  }

  const response = await fetch(url, {
    ...options,
    headers
  });

  if (!response.ok) {

    let problem: ProblemDetails;
    try {
      problem = await response.json();
    } catch {
      problem = {
        title: response.statusText || 'Error de comunicación con el servidor',
        status: response.status,
        detail: `HTTP status ${response.status} en ${endpoint}`
      };
    }
    throw new ApiError(problem);
  }

  // Manejar respuestas sin contenido (204 No Content)
  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}
