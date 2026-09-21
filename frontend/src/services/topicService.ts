/**
 * Service for Topics & Scenarios management (Client Admin)
 */
import { apiFetch } from './apiClient';
import { TopicConfig, RetentionSettings, InstitutionalOptics, InternalAudience } from '../types/api';
import { INITIAL_TOPICS, INITIAL_RETENTION_SETTINGS } from '../mock/mockData';

const TOPICS_STORAGE_KEY = 'voxready_topics';

// Mapeo de ópticas entre UI (Español) y Backend (Inglés)
const opticsToBackendMap: Record<string, 'empathetic' | 'formal' | 'technical'> = {
  'Empática': 'empathetic',
  'empathetic': 'empathetic',
  'Formal': 'formal',
  'formal': 'formal',
  'Técnica': 'technical',
  'technical': 'technical'
};

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
      const res = await apiFetch<{ items: any[]; total: number }>('/topics');
      if (res && Array.isArray(res.items)) {
        const mapped: TopicConfig[] = res.items.map((item) => ({
          id: String(item.id),
          name: item.name,
          context: item.context || '',
          optics: opticsToFrontendMap[item.optics] || 'Empática',
          audience: (item.audience as InternalAudience) || 'Dirección',
          languages: (item.languages || ['es']).map((l: string) => l.toUpperCase()),
          retention: item.retentionDays ? `${item.retentionDays} días` : '90 días',
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
    } catch {
      // Fallback a localStorage o datos iniciales
    }
    return getStoredTopics();
  },

  /**
   * Obtiene un tema específico por su ID
   */
  async getTopicById(id: string): Promise<TopicConfig | null> {
    const topics = await this.getTopics();
    return topics.find((t) => t.id === id) || null;
  },

  /**
   * Guarda o actualiza un tema institucional
   */
  async saveTopic(topicData: Partial<TopicConfig>): Promise<TopicConfig> {
    const currentList = getStoredTopics();
    const isNew = !topicData.id || topicData.id === 'new';
    const topicId = isNew ? `top-${Date.now()}` : topicData.id!;

    const opticsVal = topicData.optics || 'Empática';
    const backendOptics = opticsToBackendMap[opticsVal] || 'empathetic';

    const normalizedLanguages = (
      topicData.languages && topicData.languages.length > 0 ? topicData.languages : ['ES']
    ).map((l) => l.toUpperCase());

    const backendLangs = normalizedLanguages.map(
      (l) => l.toLowerCase() as 'es' | 'en' | 'pt'
    );

    const validKeyMessages =
      topicData.keyMessages && topicData.keyMessages.length > 0
        ? topicData.keyMessages
        : [topicData.name || 'Mensaje institucional principal.'];

    const validRedLines = topicData.redLines || [];

    const payload = {
      name: topicData.name?.trim() || 'Nuevo tema de crisis',
      context: topicData.context?.trim() || 'Contexto de crisis',
      optics: backendOptics,
      audience: topicData.audience || 'Dirección',
      languages: backendLangs,
      keyMessages: validKeyMessages,
      redLines: validRedLines
    };

    let savedId = topicId;

    // Intentar sincronizar con backend si está disponible
    try {
      if (!isNew && !topicId.startsWith('top-')) {
        await apiFetch(`/topics/${topicId}`, {
          method: 'PUT',
          body: JSON.stringify(payload)
        });
      } else {
        const res = await apiFetch<{ id: string; name: string }>('/topics', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
        if (res && res.id) {
          savedId = res.id;
        }
      }
    } catch {
      // Backend no disponible: se persiste localmente sin interrumpir la experiencia
    }

    const savedTopic: TopicConfig = {
      id: savedId,
      name: payload.name,
      context: payload.context,
      optics: opticsToFrontendMap[backendOptics] || 'Empática',
      audience: payload.audience as InternalAudience,
      languages: normalizedLanguages,
      retention: topicData.retention || '90 días',
      keyMessages: validKeyMessages,
      redLines: validRedLines
    };

    let updatedList: TopicConfig[];
    if (isNew) {
      updatedList = [savedTopic, ...currentList];
    } else {
      updatedList = currentList.map((t) => (t.id === topicId ? savedTopic : t));
    }

    setStoredTopics(updatedList);
    return savedTopic;
  },

  /**
   * Elimina un tema
   */
  async deleteTopic(id: string): Promise<TopicConfig[]> {
    try {
      if (!id.startsWith('top-')) {
        await apiFetch(`/topics/${id}`, { method: 'DELETE' });
      }
    } catch {
      // Si el backend falla, remover localmente de todas formas
    }

    const currentList = getStoredTopics();
    const filtered = currentList.filter((t) => t.id !== id);
    setStoredTopics(filtered);
    return filtered;
  },

  /**
   * Obtiene la configuración de política de retención
   */
  async getRetentionSettings(): Promise<RetentionSettings> {
    try {
      return await apiFetch<RetentionSettings>('/privacy/retention');
    } catch {
      return INITIAL_RETENTION_SETTINGS;
    }
  },

  /**
   * Actualiza la política de retención
   */
  async updateRetentionSettings(settings: Partial<RetentionSettings>): Promise<RetentionSettings> {
    try {
      return await apiFetch<RetentionSettings>('/privacy/retention', {
        method: 'PUT',
        body: JSON.stringify(settings)
      });
    } catch {
      return { ...INITIAL_RETENTION_SETTINGS, ...settings };
    }
  }
};
