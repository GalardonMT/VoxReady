import { apiFetch } from './apiClient';
import type { MetricDefinition, MetricsVersion } from './metricsModel';

export interface MetricsWorkspace {
  published: MetricsVersion | null;
  draft: MetricsVersion | null;
}

const endpoint = '/api/master/metrics';

export const metricsService = {
  getWorkspace: () => apiFetch<MetricsWorkspace>(endpoint),
  getLatestPublished: () => apiFetch<MetricsVersion | null>(`${endpoint}/latest`),
  createDraft: () => apiFetch<MetricsVersion>(`${endpoint}/draft`, { method: 'POST' }),
  saveDraft: (draft: MetricsVersion, metrics: MetricDefinition[]) =>
    apiFetch<MetricsVersion>(`${endpoint}/draft/${draft.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        revision: draft.revision,
        metrics: metrics.map(metric => ({ key: metric.key, thresholds: metric.thresholds })),
      }),
    }),
  publishDraft: (draft: MetricsVersion) =>
    apiFetch<MetricsVersion>(`${endpoint}/draft/${draft.id}/publish`, {
      method: 'POST',
      body: JSON.stringify({ revision: draft.revision }),
    }),
  discardDraft: (draft: MetricsVersion) =>
    apiFetch<void>(`${endpoint}/draft/${draft.id}`, {
      method: 'DELETE',
      body: JSON.stringify({ revision: draft.revision }),
    }),
};
