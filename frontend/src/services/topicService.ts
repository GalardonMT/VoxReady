/**
 * Service for Topics & Scenarios management (Client Admin)
 */
import { apiFetch, isAccessError } from './apiClient';
import { TopicConfig, InstitutionalOptics, InternalAudience } from '../types/api';
import { INITIAL_TOPICS } from '../mock/mockData';

const TOPICS_STORAGE_KEY = 'voxready_topics';

interface BackendTopic {
  id: string;
  name: string;
  context?: string;
  optics: string;
  audience: string;
  languages?: string[];
  keyMessages?: string[];
  redLines?: string[];
}

const opticsToFrontendMap: Record<string, InstitutionalOptics> = {
  'empathetic': 'Empática',
  'Empática': 'Empática',
  'formal': 'Formal',
  'Formal': 'Formal',
  'technical': 'Técnica',
  'Técnica': 'Técnica'
};

function getStoredTopics(): TopicConfig[] {
  if (typeof window === 'undefined') return INITIAL_TOPICS;
  const stored = localStorage.getItem(TOPICS_STORAGE_KEY);
  if (stored) {
    try {
      return JSON.parse(stored);
    } catch {
      // Ignorar error de parsing
    }
  }
  localStorage.setItem(TOPICS_STORAGE_KEY, JSON.stringify(INITIAL_TOPICS));
  return INITIAL_TOPICS;
}

function setStoredTopics(topics: TopicConfig[]) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOPICS_STORAGE_KEY, JSON.stringify(topics));
}

export const topicService = {
  /**
   * Obtiene la lista de temas configurados por el cliente
   */
  async getTopics(): Promise<TopicConfig[]> {
    try {
      const res = await apiFetch<{ items: BackendTopic[]; total: number }>('/topics');
      if (res && Array.isArray(res.items)) {
        const mapped: TopicConfig[] = res.items.map((item) => ({
          id: String(item.id),
          name: item.name,
          context: item.context || '',
          optics: opticsToFrontendMap[item.optics] || 'Empática',
          audience: (item.audience as InternalAudience) || 'Dirección',
          languages: (item.languages || ['es']).map((l: string) => l.toUpperCase()),
          keyMessages: item.keyMessages || [],
          redLines: item.redLines || []
        }));

        // Combinar con temas creados localmente que aún no estén en backend
        const localOnly = getStoredTopics().filter(
          (loc) => !mapped.some((rem) => rem.id === loc.id || rem.name.toLowerCase() === loc.name.toLowerCase())
        );
        const combined = [...mapped, ...localOnly];
        setStoredTopics(combined);
        return combined;
      }
    } catch (error) { if (isAccessError(error)) throw error;
      // Fallback a localStorage o datos iniciales
    }
    return getStoredTopics();
  }
};
