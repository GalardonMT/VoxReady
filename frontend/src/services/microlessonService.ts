import { apiFetch } from './apiClient';
import type {
  ClientInfo,
  LifecycleStatus,
  Microlesson,
  MicrolessonInput,
  MicrolessonScenario,
  MicrolessonAssignment,
  MicrolessonCatalog,
  MicrolessonRecommendations,
  MicrolessonSpokesperson,
  SpokespersonMicrolessonDetail,
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
  async spokespersons(clientId: string): Promise<MicrolessonSpokesperson[]> {
    return (await apiFetch<{ items: MicrolessonSpokesperson[] }>(`${masterBase}/clients/${id(clientId)}/spokespersons`)).items;
  },
  async assignments(microlessonId: string): Promise<MicrolessonAssignment[]> {
    return (await apiFetch<{ items: MicrolessonAssignment[] }>(`${masterBase}/${id(microlessonId)}/assignments`)).items;
  },
  async assign(microlessonId: string, userIds: string[], sortOrder: number): Promise<MicrolessonAssignment[]> {
    return (await apiFetch<{ items: MicrolessonAssignment[] }>(`${masterBase}/${id(microlessonId)}/assignments`, json('POST', { userIds, sortOrder }))).items;
  },
  reorder(microlessonId: string, assignmentId: string, sortOrder: number): Promise<MicrolessonAssignment> {
    return apiFetch(`${masterBase}/${id(microlessonId)}/assignments/${id(assignmentId)}/order`, json('PATCH', { sortOrder }));
  },
  revoke(microlessonId: string, assignmentId: string): Promise<MicrolessonAssignment> {
    return apiFetch(`${masterBase}/${id(microlessonId)}/assignments/${id(assignmentId)}/revoke`, { method: 'POST' });
  },
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
  list(): Promise<MicrolessonCatalog> {
    return apiFetch('/microlessons');
  },
  recommendations(): Promise<MicrolessonRecommendations> {
    return apiFetch('/microlessons/recommendations');
  },
  detail(microlessonId: string): Promise<SpokespersonMicrolessonDetail> {
    return apiFetch(`/microlessons/${id(microlessonId)}`);
  },
  start(microlessonId: string): Promise<{ assignmentId: string; assignmentStatus: 'in_progress'; sortOrder: number }> {
    return apiFetch(`/microlessons/${id(microlessonId)}/start`, { method: 'POST' });
  },
  complete(microlessonId: string): Promise<{ assignmentId: string; assignmentStatus: 'completed'; sortOrder: number }> {
    return apiFetch(`/microlessons/${id(microlessonId)}/complete`, { method: 'POST' });
  },
  restart(microlessonId: string): Promise<{ assignmentId: string; assignmentStatus: 'assigned'; sortOrder: number }> {
    return apiFetch(`/microlessons/${id(microlessonId)}/restart`, { method: 'POST' });
  },
  async playbackUrl(microlessonId: string): Promise<string> {
    return (await apiFetch<{ playbackUrl: string }>(`/microlessons/${id(microlessonId)}/video-url`)).playbackUrl;
  },
};
