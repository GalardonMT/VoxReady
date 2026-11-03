/**
 * Service for Topics & Scenarios management (Client Admin)
 */
import { apiFetch } from './apiClient';
import { TopicConfig, RetentionSettings, InstitutionalOptics, InternalAudience } from '../types/api';

interface BackendTopic {
  id: string;
  name: string;
  context?: string;
  optics: string;
  audience: string;
  languages?: string[];
  retentionDays?: number;
  keyMessages?: string[];
  redLines?: string[];
}

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

export const topicService = {
  /**
   * Obtiene la lista de temas configurados por el cliente
   */
  async getTopics(): Promise<TopicConfig[]> {
    const res = await apiFetch<{ items: BackendTopic[]; total: number }>('/topics');
    if (res && Array.isArray(res.items)) {
      return res.items.map((item) => ({
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
    }
    return [];
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
    const isNew = !topicData.id || topicData.id === 'new';
    const topicId = topicData.id || '';

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

    let savedId: string;
    if (!isNew) {
      const res = await apiFetch<{ id?: string }>(`/topics/${topicId}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });
      savedId = res.id || topicId;
    } else {
      const res = await apiFetch<{ id: string }>('/topics', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      if (!res.id) {
        throw new Error('La API no entregó el identificador del tema creado.');
      }
      savedId = res.id;
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

    return savedTopic;
  },

  /**
   * Elimina un tema
   */
  async deleteTopic(id: string): Promise<TopicConfig[]> {
    await apiFetch(`/topics/${id}`, { method: 'DELETE' });
    return this.getTopics();
  },

  /**
   * Obtiene la configuración de política de retención
   */
  async getRetentionSettings(): Promise<RetentionSettings> {
    return apiFetch<RetentionSettings>('/privacy/retention');
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
    } catch (error) {
      throw error;
    }
  }
};
