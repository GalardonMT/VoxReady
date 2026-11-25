import { API_BASE_URL, apiFetch } from './apiClient';

async function diagnosticFetch(url: string, options: RequestInit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'No se pudo completar la comprobación.');
    return result;
  } catch (cause) {
    if (controller.signal.aborted) throw new Error('La API no respondió a la comprobación en 30 segundos. Verifica que la API local siga ejecutándose.');
    throw cause;
  } finally { clearTimeout(timer); }
}

export type PendingRole = 'client_admin' | 'spokesperson';
export type PendingAccess = {
  id: string; clientId: string; role: PendingRole; displayName: string;
  email: string | null; createdAt: string; expiresAt: string | null;
  usedAt: string | null; state: 'pending' | 'invited' | 'expired' | 'activated';
  accountChoice: boolean;
};

export type InvitationInspection = { role: PendingRole; expiresAt: string; activationAvailable: boolean;
  accountChoice: boolean; message: string };
export type IdentityStatus = { tokenValidated: boolean; stableIdentifierPresent: boolean; scopeValidated: boolean;
  emailClaimPresent: boolean; emailVerifiedBooleanTrue: boolean; activationAvailable: boolean;
  verifiedPrimaryEmailClaimPresent: boolean; verifiedSecondaryEmailClaimPresent: boolean;
  emailDomainOwnerVerifiedBooleanTrue: boolean;
  clientAdminActivationAvailable: boolean; spokespersonActivationAvailable: boolean;
  fixedEmailActivationAvailable: boolean;
  emailProofConfigurationConfirmed: boolean; legacyReviewConfirmed: boolean };

export async function inspectInvitation(token: string): Promise<InvitationInspection> {
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) {
    throw new Error('El enlace no es válido. Solicita uno nuevo al configurador maestro.');
  }
  const response = await fetch(`${API_BASE_URL}/api/access-invitations/inspect`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }), cache: 'no-store', referrerPolicy: 'no-referrer', credentials: 'omit',
  });
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'No se pudo comprobar el enlace.');
  return body as InvitationInspection;
}

async function identityRequest<T>(path: string, bearer: string, body?: { token: string }): Promise<T> {
  const options: RequestInit = {
    method: body ? 'POST' : 'GET', headers: { Authorization: `Bearer ${bearer}`, 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}), cache: 'no-store', referrerPolicy: 'no-referrer', credentials: 'omit',
  };
  // La finalización de activación mantiene su comportamiento: un timeout de UI
  // no debe presentarse como prueba de que una transacción no llegó a completarse.
  if (!body) return diagnosticFetch(`${API_BASE_URL}/api/access-invitations/${path}`, options);
  const response = await fetch(`${API_BASE_URL}/api/access-invitations/${path}`, options);
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'No se pudo completar la operación.');
  return result as T;
}

export const checkInvitationIdentity = (bearer: string) => identityRequest<IdentityStatus>('identity-status', bearer);
export async function checkDirectoryIdentity(bearer: string, graphBearer: string): Promise<Record<string, boolean>> {
  return diagnosticFetch(`${API_BASE_URL}/api/access-invitations/directory-status`, {
    method: 'POST', headers: { Authorization: `Bearer ${bearer}`,
      'X-VoxReady-Graph-Authorization': `Bearer ${graphBearer}`, Accept: 'application/json' },
    cache: 'no-store', referrerPolicy: 'no-referrer', credentials: 'omit',
  });
}
export function completeInvitation(token: string, bearer: string) {
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) throw new Error('El enlace no es válido.');
  return identityRequest<{ userId: string; clientId: string; role: PendingRole }>('complete', bearer, { token });
}
const base = (clientId: string) => `/api/master/clients/${encodeURIComponent(clientId)}/pending-accesses`;
export const pendingAccessService = {
  list(clientId: string) {
    return apiFetch<{ items: PendingAccess[]; activationAvailable: boolean;
      activationByRole: Record<PendingRole, boolean> }>(base(clientId));
  },
  create(clientId: string, payload: { role: PendingRole; displayName: string; email?: string }) {
    return apiFetch<PendingAccess>(base(clientId), { method: 'POST', body: JSON.stringify(payload) });
  },
  invitation(clientId: string, id: string, allowAccountChoice = false) {
    return apiFetch<{ activationPath: string; expiresAt: string; accountChoice: boolean }>(`${base(clientId)}/${encodeURIComponent(id)}/invitation`, {
      method: 'POST', ...(allowAccountChoice ? { body: JSON.stringify({ allowAccountChoice: true }) } : {}),
    });
  },
};
