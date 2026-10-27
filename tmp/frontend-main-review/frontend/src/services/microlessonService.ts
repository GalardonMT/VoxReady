import { apiFetch } from './apiClient';
import type {
  ClientInfo,
  LifecycleStatus,
  Microlesson,
  MicrolessonInput,
  MicrolessonScenario,
} from '../types/api';

const masterBase = '/api/master/microlessons';
const id = encodeURIComponent;
const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

interface UploadTicket {
  uploadUrl: string;
  blobPath: string;
  fileName: string;
  contentType: string;
  expiresAt: string;
  maxSizeBytes: number;
}

export const masterMicrolessonService = {
  async clients(): Promise<ClientInfo[]> {
    return (await apiFetch<{ items: ClientInfo[] }>(`${masterBase}/clients?status=all`)).items;
  },
  async scenarios(clientId: string, status: LifecycleStatus | 'all' = 'active'): Promise<MicrolessonScenario[]> {
    return (await apiFetch<{ items: MicrolessonScenario[] }>(
      `${masterBase}/clients/${id(clientId)}/scenarios?status=${status}`
    )).items;
  },
  async list(filters: { clientId?: string; status?: LifecycleStatus | 'all' } = {}): Promise<Microlesson[]> {
    const query = new URLSearchParams({ status: filters.status ?? 'all' });
    if (filters.clientId) query.set('clientId', filters.clientId);
    return (await apiFetch<{ items: Microlesson[] }>(`${masterBase}?${query}`)).items;
  },
  detail(microlessonId: string): Promise<Microlesson> {
    return apiFetch(`${masterBase}/${id(microlessonId)}`);
  },
  save(payload: MicrolessonInput, microlessonId?: string): Promise<Microlesson> {
    return apiFetch(
      `${masterBase}${microlessonId ? `/${id(microlessonId)}` : ''}`,
      json(microlessonId ? 'PUT' : 'POST', payload)
    );
  },
  status(microlessonId: string, status: LifecycleStatus): Promise<Microlesson> {
    return apiFetch(`${masterBase}/${id(microlessonId)}/status`, json('PATCH', { status }));
  },
  async uploadVideo(microlessonId: string, file: File): Promise<Microlesson> {
    const ticket = await apiFetch<UploadTicket>(`${masterBase}/${id(microlessonId)}/video-upload-url`, json('POST', {
      fileName: file.name,
      contentType: file.type,
      sizeBytes: file.size,
    }));
    const uploaded = await fetch(ticket.uploadUrl, {
      method: 'PUT',
      headers: {
        'Content-Type': ticket.contentType,
        'x-ms-blob-type': 'BlockBlob',
        'x-ms-blob-content-type': ticket.contentType,
      },
      body: file,
    });
    if (!uploaded.ok) throw new Error(`Azure Blob Storage rechazo la subida (${uploaded.status}).`);
    return apiFetch(`${masterBase}/${id(microlessonId)}/video`, json('PUT', {
      blobPath: ticket.blobPath,
      fileName: ticket.fileName,
      contentType: ticket.contentType,
      sizeBytes: file.size,
    }));
  },
  removeVideo(microlessonId: string): Promise<Microlesson> {
    return apiFetch(`${masterBase}/${id(microlessonId)}/video`, { method: 'DELETE' });
  },
};

export const microlessonService = {
  async list(): Promise<Microlesson[]> {
    return (await apiFetch<{ items: Microlesson[] }>('/microlessons')).items;
  },
  detail(microlessonId: string): Promise<Microlesson> {
    return apiFetch(`/microlessons/${id(microlessonId)}`);
  },
  async playbackUrl(microlessonId: string): Promise<string> {
    return (await apiFetch<{ playbackUrl: string }>(`/microlessons/${id(microlessonId)}/video-url`)).playbackUrl;
  },
};
