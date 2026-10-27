import { apiFetch } from './apiClient';

export interface CatalogScenario {
  id: string;
  title: string;
  context: string;
  category: 'health' | 'reputational' | 'operational';
  audience: string;
  difficulty: 'basic' | 'intermediate' | 'hard';
  estimatedMinutes: number;
  questionCount: number;
  languages: string[];
}

export interface ScenarioPage {
  items: CatalogScenario[];
  page: number;
  pageSize: number;
  total: number;
}

export interface SessionSetup {
  sessionId: string;
  scenarioId: string;
  status: string;
  questions: { id: string; sequenceNo: number; text: string }[];
  retentionPolicy: { version: string; keep: 'full_recording' | 'metrics_only'; termDays: number | null };
}

export const sessionFlowService = {
  listScenarios(filters: { category?: string; q?: string; page?: number; pageSize?: number } = {}) {
    const query = new URLSearchParams();
    if (filters.category) query.set('category', filters.category);
    if (filters.q) query.set('q', filters.q);
    query.set('page', String(filters.page ?? 1));
    query.set('pageSize', String(filters.pageSize ?? 20));
    return apiFetch<ScenarioPage>(`/scenarios?${query}`);
  },
  getScenario(id: string) {
    return apiFetch<CatalogScenario>(`/scenarios/${encodeURIComponent(id)}`);
  },
  createSession(scenarioId: string, idempotencyKey: string, language: string) {
    return apiFetch<{ sessionId: string; scenarioId: string; status: string; questionCount: number }>('/sessions', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ scenarioId, language })
    });
  },
  getSession(id: string) {
    return apiFetch<SessionSetup>(`/sessions/${encodeURIComponent(id)}`);
  },
  grantConsent(id: string, policyVersion: string) {
    return apiFetch<{ sessionId: string; status: string; consentId: string }>(`/sessions/${encodeURIComponent(id)}/consent`, {
      method: 'POST',
      body: JSON.stringify({ acceptRecording: true, acknowledgeDeletion: true, policyVersion })
    });
  }
};
