/** API calls use the access token only; user roles always come from GET /me. */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';
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

export class ApiError extends Error {
  constructor(public problem: ProblemDetails) {
    super(problem.detail || problem.title);
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
  return typeof window === 'undefined' ? null : sessionStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
  localStorage.removeItem('voxready_token');
  localStorage.removeItem('voxready_user');
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem('voxready_token');
  localStorage.removeItem('voxready_user');
}

export async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = tokenProvider ? await tokenProvider() : getAccessToken();
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json, application/problem+json');
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (!headers.has('x-correlation-id')) headers.set('x-correlation-id', `client-${crypto.randomUUID()}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`, {
      ...options, headers, cache: 'no-store',
    });
  } catch {
    throw new NetworkError();
  }
  if (!response.ok) {
    let problem: ProblemDetails;
    try { problem = await response.json(); }
    catch { problem = { title: response.statusText || 'Error de API', status: response.status }; }
    if (response.status === 401) {
      clearAccessToken();
      if (typeof window !== 'undefined') window.dispatchEvent(new Event('voxready:session-expired'));
    }
    throw new ApiError({ ...problem, status: response.status });
  }
  if (response.status === 204) return {} as T;
  return response.json() as Promise<T>;
}
