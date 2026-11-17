import { apiFetch } from './apiClient';
import type {
  ClientPagedResponse,
  ClientRecentActivityPage,
  ClientSpokesperson,
  ClientSpokespersonDetail,
  ClientSpokespersonMicrolesson,
  ClientSpokespersonSession,
  ClientUsageResponse,
  MicrolessonAssignmentStatus,
} from '../types/api';

export const clientAdminService = {
  async spokespersons(): Promise<ClientSpokesperson[]> {
    const response = await apiFetch<{ items: ClientSpokesperson[]; total: number }>(
      '/api/client/spokespersons',
    );
    return response.items;
  },
  usage(filters: { days: 7 | 30 | 90; userId?: string; scenarioId?: string }): Promise<ClientUsageResponse> {
    const params = new URLSearchParams({ days: String(filters.days) });
    if (filters.userId) params.set('userId', filters.userId);
    if (filters.scenarioId) params.set('scenarioId', filters.scenarioId);
    return apiFetch<ClientUsageResponse>(`/api/client/usage?${params.toString()}`);
  },
  recentActivity(filters: {
    days: 7 | 30 | 90;
    userId?: string;
    scenarioId?: string;
    query?: string;
    page: number;
    pageSize?: number;
  }): Promise<ClientRecentActivityPage> {
    const params = new URLSearchParams({
      days: String(filters.days),
      page: String(filters.page),
      pageSize: String(filters.pageSize || 5),
    });
    if (filters.userId) params.set('userId', filters.userId);
    if (filters.scenarioId) params.set('scenarioId', filters.scenarioId);
    if (filters.query?.trim()) params.set('query', filters.query.trim());
    return apiFetch<ClientRecentActivityPage>(`/api/client/usage/recent?${params.toString()}`);
  },
  spokespersonDetail(id: string, days: 7 | 30 | 90): Promise<ClientSpokespersonDetail> {
    return apiFetch<ClientSpokespersonDetail>(
      `/api/client/spokespersons/${encodeURIComponent(id)}/detail?days=${days}`,
    );
  },
  spokespersonSessions(id: string, filters: {
    days: 7 | 30 | 90;
    status: 'all' | 'completed' | 'in_progress' | 'abandoned';
    scenarioId?: string;
    query?: string;
    page: number;
    pageSize?: number;
  }): Promise<ClientPagedResponse<ClientSpokespersonSession>> {
    const params = new URLSearchParams({
      days: String(filters.days),
      status: filters.status,
      page: String(filters.page),
      pageSize: String(filters.pageSize || 5),
    });
    if (filters.scenarioId) params.set('scenarioId', filters.scenarioId);
    if (filters.query?.trim()) params.set('query', filters.query.trim());
    return apiFetch<ClientPagedResponse<ClientSpokespersonSession>>(
      `/api/client/spokespersons/${encodeURIComponent(id)}/sessions?${params.toString()}`,
    );
  },
  spokespersonMicrolessons(id: string, filters: {
    days: 7 | 30 | 90;
    status: 'all' | MicrolessonAssignmentStatus;
    query?: string;
    page: number;
    pageSize?: number;
  }): Promise<ClientPagedResponse<ClientSpokespersonMicrolesson>> {
    const params = new URLSearchParams({
      days: String(filters.days),
      status: filters.status,
      page: String(filters.page),
      pageSize: String(filters.pageSize || 5),
    });
    if (filters.query?.trim()) params.set('query', filters.query.trim());
    return apiFetch<ClientPagedResponse<ClientSpokespersonMicrolesson>>(
      `/api/client/spokespersons/${encodeURIComponent(id)}/microlessons?${params.toString()}`,
    );
  },
};
