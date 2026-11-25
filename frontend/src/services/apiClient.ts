/**
 * Base API Client for VoxReady Backend
 * Handles RFC 7807 Problem Details errors, authentication tokens, and correlation IDs.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_BACKEND_API_URL ||
  'http://localhost:8000/v1';

export const INTERVIEW_API_BASE_URL =
  process.env.NEXT_PUBLIC_INTERVIEW_API_URL || API_BASE_URL;

const TOKEN_KEY = 'voxready_access_token';
let tokenProvider: (() => Promise<string | null>) | null = null;

export function registerTokenProvider(provider: (() => Promise<string | null>) | null): void {
  tokenProvider = provider;
}

export interface ProblemDetails {
  type?: string;
  title: string;
  status: number;
  detail?: string;
  correlationId?: string;
  code?: string;
}

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const item = detail as Record<string, unknown>;
    const message = item.msg || item.message;
    return typeof message === 'string' ? message : JSON.stringify(detail);
  }
  return String(detail);
}

export class ApiError extends Error {
  constructor(public problem: ProblemDetails) {
    let msg: string;
    const detail = problem.detail as unknown;
    if (typeof detail === 'string') {
      msg = detail;
    } else if (Array.isArray(detail)) {
      msg = detail.map(detailMessage).join(', ');
    } else if (detail && typeof detail === 'object') {
      msg = detailMessage(detail);
    } else {
      msg = problem.title || 'Error en la petición';
    }
    super(msg);
    this.name = 'ApiError';
  }
}

export class NetworkError extends Error {
  constructor() {
    super('No se pudo conectar con la API. Comprueba tu conexión e inténtalo de nuevo.');
    this.name = 'NetworkError';
  }
}

export function isAccessError(error: unknown): boolean {
  return error instanceof ApiError && (error.problem.status === 401 || error.problem.status === 403);
}

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem('voxready_token');
}

export function setAccessToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem('voxready_token', token);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem('voxready_token');
}

export async function getAuthToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null;

  if (tokenProvider) {
    try {
      const customToken = await tokenProvider();
      if (customToken) return customToken;
    } catch {}
  }

  // 1. Check storage (set by AuthContext after login)
  const token = getAccessToken();
  if (token) return token;

  // 2. Try MSAL silent token renewal (if configured and user is signed in)
  try {
    const { msalInstance, loginRequest, isAzureConfigured } = await import('./authConfig');
    if (isAzureConfigured) {
      const accounts = msalInstance.getAllAccounts();
      if (accounts.length > 0) {
        const response = await msalInstance.acquireTokenSilent({
          ...loginRequest,
          account: msalInstance.getActiveAccount() || accounts[0],
        });
        if (response.accessToken) {
          setAccessToken(response.accessToken);
          return response.accessToken;
        }
      }
    }
  } catch (err: unknown) {
    clearAccessToken();

    // If the error requires user interaction, redirect to Microsoft login
    if (err && typeof err === 'object' && 'name' in err &&
        (err as { name: string }).name === 'InteractionRequiredAuthError') {
      try {
        const { msalInstance, loginRedirectRequest } = await import('./authConfig');
        await msalInstance.acquireTokenRedirect(loginRedirectRequest);
      } catch {
        // redirect will navigate away
      }
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

  // Correlation ID para trazabilidad
  if (!headers['x-correlation-id']) {
    headers['x-correlation-id'] = `client-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers
    });
  } catch {
    throw new NetworkError();
  }

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
    if (response.status === 403 && response.headers.get('X-VoxReady-Access-Blocked') === 'company') {
      clearAccessToken();
      if (typeof window !== 'undefined') window.dispatchEvent(new Event('voxready:company-blocked'));
    }
    if (response.status === 401) {
      clearAccessToken();
      if (typeof window !== 'undefined') window.dispatchEvent(new Event('voxready:session-expired'));
    }
    throw new ApiError({ ...problem, status: response.status });
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}
