import {
  AccountInfo, BrowserCacheLocation, InteractionRequiredAuthError,
  PublicClientApplication,
} from '@azure/msal-browser';
import {
  API_BASE_URL, ApiError, NetworkError, apiFetch, clearAccessToken,
  getAccessToken, registerTokenProvider, setAccessToken,
} from './apiClient';
import type { Role, UserSession } from '../types/api';

const MODE = process.env.NEXT_PUBLIC_AUTH_MODE;
const CLIENT_ID = process.env.NEXT_PUBLIC_AZURE_CLIENT_ID;
const AUTHORITY = process.env.NEXT_PUBLIC_AZURE_AUTHORITY;
const REDIRECT_URI = process.env.NEXT_PUBLIC_AZURE_REDIRECT_URI;
const API_SCOPE = process.env.NEXT_PUBLIC_AZURE_API_SCOPE;
const AZURE_CONFIGURED = !!(CLIENT_ID && AUTHORITY && REDIRECT_URI && API_SCOPE);

export const authMode = MODE === 'local' && process.env.NODE_ENV !== 'production'
  ? 'local'
  : (MODE === 'azure' || (!MODE && AZURE_CONFIGURED)) ? 'azure' : 'unconfigured';

type Profile = {
  userId: string; email: string | null; displayName: string | null; role: Role;
  clientId: string | null; clientName: string | null; preferredLanguage: 'es' | 'en' | 'pt';
};

let clientPromise: Promise<PublicClientApplication> | null = null;

async function azureClient(): Promise<PublicClientApplication> {
  if (authMode !== 'azure' || !AZURE_CONFIGURED) {
    throw new Error('Falta configurar Microsoft Entra External ID.');
  }
  if (!clientPromise) {
    clientPromise = (async () => {
      const client = new PublicClientApplication({
        auth: {
          clientId: CLIENT_ID!, authority: AUTHORITY!, redirectUri: REDIRECT_URI!,
          postLogoutRedirectUri: REDIRECT_URI!,
          knownAuthorities: [new URL(AUTHORITY!).hostname],
        },
        cache: { cacheLocation: BrowserCacheLocation.SessionStorage },
      });
      await client.initialize();
      return client;
    })();
  }
  return clientPromise;
}

function accountFor(client: PublicClientApplication): AccountInfo | null {
  return client.getActiveAccount() || client.getAllAccounts()[0] || null;
}

async function azureAccessToken(): Promise<string | null> {
  const client = await azureClient();
  const account = accountFor(client);
  if (!account) return null;
  try {
    const result = await client.acquireTokenSilent({ account, scopes: [API_SCOPE!] });
    setAccessToken(result.accessToken);
    return result.accessToken;
  } catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
      clearAccessToken();
      window.dispatchEvent(new Event('voxready:session-expired'));
      throw new ApiError({ title: 'unauthorized', status: 401, detail: 'Tu sesión de Azure caducó.' });
    }
    throw error;
  }
}

if (authMode === 'azure') registerTokenProvider(azureAccessToken);

export async function loadIdentity(): Promise<UserSession> {
  const profile = await apiFetch<Profile>('/me');
  if (!['spokesperson', 'client_admin', 'master_config'].includes(profile.role)) {
    throw new Error('La API devolvió un rol no reconocido.');
  }
  if (profile.role !== 'master_config' && !profile.clientId) {
    throw new Error('La cuenta no tiene un cliente asignado.');
  }
  const name = profile.displayName || profile.email || 'Usuario';
  return {
    ...profile, email: profile.email || '', displayName: name,
    clientName: profile.clientName || '',
    initials: name.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join(''),
  };
}

export async function loginLocal(email: string): Promise<UserSession> {
  if (authMode !== 'local') throw new Error('El acceso local no está habilitado.');
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/dev/token`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim() }),
    });
  } catch { throw new NetworkError(); }
  if (!response.ok) throw new Error(response.status === 404 ? 'Usuario local no disponible.' : 'No se pudo iniciar sesión.');
  const body = await response.json();
  if (!body.accessToken) throw new Error('La API no entregó un token.');
  setAccessToken(body.accessToken);
  try { return await loadIdentity(); }
  catch (error) { if (!(error instanceof NetworkError)) clearAccessToken(); throw error; }
}

export async function beginExternalLogin(): Promise<void> {
  const client = await azureClient();
  await client.loginRedirect({ scopes: [API_SCOPE!] });
}

export async function completeExternalLogin(): Promise<UserSession | null> {
  if (authMode !== 'azure') return null;
  const client = await azureClient();
  const result = await client.handleRedirectPromise({ navigateToLoginRequestUrl: false });
  if (result?.account) client.setActiveAccount(result.account);
  if (!accountFor(client)) return null;
  await azureAccessToken();
  return loadIdentity();
}

export async function beginExternalLogout(): Promise<void> {
  if (authMode !== 'azure') return;
  const client = await azureClient();
  const account = accountFor(client);
  clearAccessToken();
  await client.logoutRedirect({ account: account || undefined, postLogoutRedirectUri: REDIRECT_URI! });
}

export async function restoreAzureToken(): Promise<boolean> {
  if (authMode !== 'azure') return !!getAccessToken();
  return !!(await azureAccessToken());
}
