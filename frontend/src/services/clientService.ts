import { apiFetch } from './apiClient';
import type { ClientInfo, ClientInput } from '../types/api';

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
};
