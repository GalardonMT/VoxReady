import { apiFetch } from './apiClient';
import type {
  ClientInfo,
  ClientInput,
  ClientSpokesperson,
  SpokespersonCandidate,
  SpokespersonLinkResult,
} from '../types/api';
import type { ProgressResponse } from './progressService';

const base = '/api/master/clients';

export const clientService = {
  async list(): Promise<ClientInfo[]> {
    return (await apiFetch<{ items: ClientInfo[]; total: number }>(`${base}?status=all`)).items;
  },
  create(payload: ClientInput): Promise<ClientInfo> {
    return apiFetch<ClientInfo>(base, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  setStatus(clientId: string, status: 'active' | 'suspended') {
    return apiFetch<{ id: string; status: 'active' | 'suspended' }>(`${base}/${encodeURIComponent(clientId)}/status`, {
      method: 'PATCH', body: JSON.stringify({ status }),
    });
  },
  async spokespersons(clientId?: string): Promise<SpokespersonCandidate[]> {
    const params = new URLSearchParams();
    if (clientId) params.set('clientId', clientId);
    const suffix = params.size ? `?${params.toString()}` : '';
    return (await apiFetch<{ items: SpokespersonCandidate[]; total: number }>(
      `/api/master/spokespersons${suffix}`,
    )).items;
  },
  async clientSpokespersons(clientId: string): Promise<ClientSpokesperson[]> {
    return (await apiFetch<{ items: ClientSpokesperson[]; total: number }>(
      `${base}/${encodeURIComponent(clientId)}/spokespersons`,
    )).items;
  },
  spokespersonProgress(clientId: string, spokespersonId: string): Promise<ProgressResponse> {
    return apiFetch<ProgressResponse>(
      `${base}/${encodeURIComponent(clientId)}/spokespersons/${encodeURIComponent(spokespersonId)}/progress`,
    );
  },
  linkSpokespersons(clientId: string, spokespersonIds: string[]): Promise<SpokespersonLinkResult> {
    return apiFetch<SpokespersonLinkResult>(`${base}/${encodeURIComponent(clientId)}/spokespersons`, {
      method: 'POST',
      body: JSON.stringify({ spokespersonIds }),
    });
  },
};
