import { apiFetch } from './apiClient';
import type {
  ClientInfo,
  ClientInput,
  SpokespersonCandidate,
  SpokespersonLinkResult,
} from '../types/api';

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
  async spokespersons(clientId?: string): Promise<SpokespersonCandidate[]> {
    const params = new URLSearchParams();
    if (clientId) params.set('clientId', clientId);
    const suffix = params.size ? `?${params.toString()}` : '';
    return (await apiFetch<{ items: SpokespersonCandidate[]; total: number }>(
      `/api/master/spokespersons${suffix}`,
    )).items;
  },
  linkSpokespersons(clientId: string, spokespersonIds: string[]): Promise<SpokespersonLinkResult> {
    return apiFetch<SpokespersonLinkResult>(`${base}/${encodeURIComponent(clientId)}/spokespersons`, {
      method: 'POST',
      body: JSON.stringify({ spokespersonIds }),
    });
  },
};
