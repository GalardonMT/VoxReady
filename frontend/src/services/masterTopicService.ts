import { apiFetch } from './apiClient';
import type { ClientInfo, LifecycleStatus, MasterScenarioFull, MasterScenarioInput,
  MasterTopicFull, MasterTopicInput, MasterTopicListItem } from '../types/api';

// Códigos en API/BD; etiquetas del diccionario técnico en la interfaz española.
export const masterTopicLabels = {
  category: { health: 'Sanitaria', operational: 'Operativa', reputational: 'Reputacional' },
  difficulty: { basic: 'Fácil', intermediate: 'Intermedio', hard: 'Difícil' },
  optics: { empathetic: 'Empática', formal: 'Formal', technical: 'Técnica' },
  audience: { leadership: 'Dirección', frontline: 'Planta', technical: 'Técnicos' },
  status: { active: 'Activo', archived: 'Archivado' }
} as const;

const base = '/api/master';
const json = (method: string, payload: unknown): RequestInit => ({ method, body: JSON.stringify(payload) });
const id = encodeURIComponent;

export const masterTopicService = {
  async clients(): Promise<ClientInfo[]> {
    return (await apiFetch<{ items: ClientInfo[] }>(`${base}/clients`)).items;
  },
  async topics(status: LifecycleStatus | 'all' = 'active'): Promise<MasterTopicListItem[]> {
    return (await apiFetch<{ items: MasterTopicListItem[] }>(`${base}/topics?status=${status}`)).items;
  },
  topic(topicId: string): Promise<MasterTopicFull> {
    return apiFetch(`${base}/topics/${id(topicId)}`);
  },
  saveTopic(payload: MasterTopicInput, topicId?: string): Promise<MasterTopicFull> {
    return apiFetch(`${base}/topics${topicId ? '/' + id(topicId) : ''}`, json(topicId ? 'PUT' : 'POST', payload));
  },
  topicStatus(topicId: string, status: LifecycleStatus): Promise<MasterTopicFull> {
    return apiFetch(`${base}/topics/${id(topicId)}/status`, json('PATCH', { status }));
  },
  saveScenario(topicId: string, payload: MasterScenarioInput, scenarioId?: string): Promise<MasterScenarioFull> {
    const path = scenarioId ? `${base}/scenarios/${id(scenarioId)}` : `${base}/topics/${id(topicId)}/scenarios`;
    return apiFetch(path, json(scenarioId ? 'PUT' : 'POST', payload));
  },
  scenarioStatus(scenarioId: string, status: LifecycleStatus): Promise<MasterScenarioFull> {
    return apiFetch(`${base}/scenarios/${id(scenarioId)}/status`, json('PATCH', { status }));
  }
};
