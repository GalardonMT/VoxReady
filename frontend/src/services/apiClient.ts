/**
 * Base API Client for VoxReady Backend
 * Handles RFC 7807 Problem Details errors, authentication tokens, and correlation IDs.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_BACKEND_API_URL ||
  'https://ca-backend-api.victoriousmushroom-8081606f.eastus2.azurecontainerapps.io';

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
  const token = localStorage.getItem('voxready_token');
  if (token) return token;

  const userJson = localStorage.getItem('voxready_user');
  let email = 'admin@demo.voxready.io';
  if (userJson) {
    try {
      const user = JSON.parse(userJson);
      if (user.token) return user.token;
      if (user.email) {
        if (user.role === 'client_admin') email = 'admin@demo.voxready.io';
        else if (user.role === 'master_config') email = 'master@voxready.io';
        else email = 'vocero@demo.voxready.io';
      }
    } catch {
      // Ignorar error al parsear user
    }
  }

  // En modo desarrollo o dev auth, retornar dev-token directamente
  if (process.env.NEXT_PUBLIC_DEV_AUTH === 'true' || typeof window !== 'undefined') {
    const devToken = 'dev-token-voxready';
    localStorage.setItem('voxready_token', devToken);
    return devToken;
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

  const devToken = process.env.NEXT_PUBLIC_DEV_AUTH === 'true' ? 'dev-token' : null;
  const effectiveToken = token || devToken;
  if (effectiveToken && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${effectiveToken}`;
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
