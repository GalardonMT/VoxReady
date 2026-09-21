/**
 * MSAL Configuration for Microsoft Entra External ID (CIAM).
 *
 * Reads public environment variables injected at build time by Next.js.
 * These must be prefixed with NEXT_PUBLIC_ to be available in the browser.
 */
import { Configuration, LogLevel, PublicClientApplication } from '@azure/msal-browser';

const tenantId = process.env.NEXT_PUBLIC_AZURE_TENANT_ID ?? '';
const clientId = process.env.NEXT_PUBLIC_AZURE_CLIENT_ID ?? '';
const redirectUri = process.env.NEXT_PUBLIC_AZURE_REDIRECT_URI ?? 'http://localhost:3000';
const apiScope = process.env.NEXT_PUBLIC_AZURE_API_SCOPE ?? '';
const authority = process.env.NEXT_PUBLIC_AZURE_AUTHORITY || `https://voxreadydev.ciamlogin.com/${tenantId}`;

/**
 * Whether Azure auth is fully configured.
 * When false the app falls back to the demo/mock login flow.
 */
export const isAzureConfigured = Boolean(tenantId && clientId);

const msalConfig: Configuration = {
  auth: {
    clientId,
    authority,
    redirectUri,
    postLogoutRedirectUri: redirectUri,
  },
  cache: {
    cacheLocation: 'localStorage',
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
      loggerCallback: (level, message, containsPii) => {
        if (containsPii || typeof window === 'undefined') return;
        if (level === LogLevel.Error) console.error('[MSAL]', message);
        else if (level === LogLevel.Warning) console.warn('[MSAL]', message);
      },
    },
  },
};

/** Singleton MSAL instance — created once, shared across the app. */
export const msalInstance = new PublicClientApplication(msalConfig);

/** Scopes requested when acquiring an access token for the backend API. */
export const loginRequest = {
  scopes: apiScope ? [apiScope] : [],
};

/** Scopes requested during the initial login redirect. */
export const loginRedirectRequest = {
  ...loginRequest,
  prompt: 'select_account' as const,
};
