import { apiFetch } from './apiClient';
import type { MasterDashboardResponse } from '../types/api';

export const masterDashboardService = {
  get: (signal?: AbortSignal) => apiFetch<MasterDashboardResponse>(
    '/api/master/dashboard', { signal, cache: 'no-store' },
  ),
};
