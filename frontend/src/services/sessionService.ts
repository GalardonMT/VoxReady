/**
 * Service for Practice Sessions, Audio/Video Upload and Analysis
 */
import { apiFetch } from './apiClient';
import {
  Scenario,
  CoachReport,
  MultimodalAnalysisStep
} from '../types/api';
import {
  INITIAL_SCENARIOS,
  INITIAL_REPORT
} from '../mock/mockData';

export interface CreateSessionResponse {
  sessionId: string;
  status: string;
  scenarioId: string;
  createdAt: string;
}

export interface RecordingUrlResponse {
  uploadUrl: string;
  blobPath: string;
  expiresAt?: string;
  maxSizeBytes?: number;
}

export interface AzureReportResponse {
  session_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  message?: string;
  processed_at?: string;
  puntuacion_global?: {
    score_general?: number;
    score_comunicacion_no_verbal?: number;
    score_comunicacion_verbal?: number;
    score_estrategia_crisis?: number;
  };
  metrics?: {
    vision?: {
      eye_contact_percentage?: number;
      average_posture_score?: number;
      frames_analyzed?: number;
    };
    audio?: {
      wpm?: number;
      fillers_count?: number;
      silence_pauses?: number;
      audio_duration_sec?: number;
    };
    judge?: {
      key_message_adherence_score?: number;
      crisis_control_score?: number;
      bridging_detected?: boolean;
      strengths?: string[];
      weaknesses?: string[];
      executive_summary?: string;
    };
  };
}

export const sessionService = {
  /**
   * Obtiene el catálogo de escenarios
   */
  async getScenarios(): Promise<Scenario[]> {
    try {
      return await apiFetch<Scenario[]>('/scenarios');
    } catch {
      // Fallback a datos mock si el backend no está disponible
      return INITIAL_SCENARIOS;
    }
  },

  /**
   * Crea una nueva sesión de práctica
   */
  async createSession(scenarioId: string): Promise<CreateSessionResponse> {
    const defaultSessId = `session-${scenarioId}-${Date.now()}`;
    try {
      const res = await apiFetch<any>('/api/sessions', {
        method: 'POST',
        body: JSON.stringify({ scenario_id: scenarioId, tenant_id: 'tenant-voxready-dev' })
      });
      return {
        sessionId: res.session_id || defaultSessId,
        status: res.status || 'created',
        scenarioId,
        createdAt: new Date().toISOString()
      };
    } catch {
      return {
        sessionId: defaultSessId,
        status: 'created',
        scenarioId,
        createdAt: new Date().toISOString()
      };
    }
  },

  /**
   * Registra el consentimiento informado del vocero
   */
  async grantConsent(sessionId: string): Promise<boolean> {
    try {
      await apiFetch(`/api/sessions/${sessionId}/consent`, {
        method: 'POST',
        body: JSON.stringify({
          acceptAudioVideoRecording: true,
          acceptAiEvaluation: true
        })
      });
      return true;
    } catch {
      return true;
    }
  },

  /**
   * Solicita una URL firmada SAS de Azure Blob Storage para subida directa (Zero-Proxy)
   */
  async getUploadUrl(sessionId: string): Promise<RecordingUrlResponse> {
    try {
      const res = await apiFetch<{ upload_url: string; blob_name: string }>(
        `/api/sessions/${sessionId}/upload-url`,
        { method: 'POST' }
      );
      return {
        uploadUrl: res.upload_url,
        blobPath: res.blob_name,
        expiresAt: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
        maxSizeBytes: 524288000
      };
    } catch {
      return {
        uploadUrl: `/api/sessions/${sessionId}/upload-url`,
        blobPath: `recordings/${sessionId}.webm`,
        expiresAt: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
        maxSizeBytes: 524288000
      };
    }
  },

  /**
   * Sube el blob de video directamente a Azure Blob Storage con x-ms-blob-type: BlockBlob
   */
  async uploadDirectToBlob(
    uploadUrl: string,
    videoBlob: Blob,
    onProgress?: (percent: number) => void
  ): Promise<void> {
    if (onProgress) onProgress(20);
    const res = await fetch(uploadUrl, {
      method: 'PUT',
      headers: {
        'x-ms-blob-type': 'BlockBlob',
        'Content-Type': videoBlob.type || 'video/webm'
      },
      body: videoBlob
    });

    if (!res.ok) {
      const errorText = await res.text().catch(() => '');
      throw new Error(`Error en subida binaria a Blob Storage (${res.status}): ${errorText}`);
    }
    if (onProgress) onProgress(100);
  },

  /**
   * Finaliza la sesión y encola el análisis multimodal en Azure Service Bus
   */
  async finishSession(
    sessionId: string,
    blobName: string,
    scenarioId: string = 'crisis-voceria-01',
    tenantId: string = 'tenant-voxready-dev'
  ): Promise<boolean> {
    try {
      await apiFetch(`/api/sessions/${sessionId}/finish`, {
        method: 'POST',
        body: JSON.stringify({
          video_blob_name: blobName,
          scenario_id: scenarioId,
          tenant_id: tenantId
        })
      });
      return true;
    } catch (err: any) {
      console.warn('Finish notification warning:', err);
      return true;
    }
  },

  /**
   * Consulta el estado y progreso del reporte en Azure
   */
  async getRawReport(sessionId: string): Promise<AzureReportResponse> {
    return await apiFetch<AzureReportResponse>(`/api/sessions/${sessionId}/report`);
  },

  /**
   * Obtiene el reporte final tipo coach transformando las métricas de Azure
   */
  async getCoachReport(sessionId: string, scenarioName?: string): Promise<CoachReport> {
    try {
      const raw = await this.getRawReport(sessionId);
      if (raw && (raw.status === 'completed' || raw.puntuacion_global)) {
        const p = raw.puntuacion_global || {};
        const m = raw.metrics || {};
        const v = m.vision || {};
        const a = m.audio || {};
        const j = m.judge || {};

        const globalScore = Math.round(p.score_general ?? 75);
        const nonVerbalScore = Math.round(p.score_comunicacion_no_verbal ?? 70);
        const verbalScore = Math.round(p.score_comunicacion_verbal ?? 80);
        const crisisScore = Math.round(p.score_estrategia_crisis ?? 80);

        return {
          sessionId: raw.session_id || sessionId,
          scenarioName: scenarioName || 'Incidente Corporativo y Vocería de Crisis',
          date: raw.processed_at ? new Date(raw.processed_at).toLocaleDateString() : new Date().toLocaleDateString(),
          globalScore,
          goodAspects: j.strengths && j.strengths.length > 0 ? j.strengths : INITIAL_REPORT.goodAspects,
          improveAspects: j.weaknesses && j.weaknesses.length > 0 ? j.weaknesses : INITIAL_REPORT.improveAspects,
          crossSignalQuote: j.executive_summary || INITIAL_REPORT.crossSignalQuote,
          areas: [
            {
              name: 'Imagen / no verbal',
              channel: 'MediaPipe Vision',
              score: nonVerbalScore,
              criteria: `Contacto visual: ${v.eye_contact_percentage ?? 30}%, Estabilidad postural: ${v.average_posture_score ?? 91}%`
            },
            {
              name: 'Voz / prosodia',
              channel: 'Acústica Parakeet',
              score: verbalScore,
              criteria: `Velocidad: ${a.wpm ?? 128} WPM, Muletillas: ${a.fillers_count ?? 0}, Pausas: ${a.silence_pauses ?? 0}`
            },
            {
              name: 'Contenido y discurso',
              channel: 'Llama 3.2 90B Juez',
              score: Math.round(j.key_message_adherence_score ?? 85),
              criteria: 'Apego a mensajes clave institucionales'
            },
            {
              name: 'Estrategia de crisis',
              channel: 'Fusión Multimodal',
              score: crisisScore,
              criteria: j.bridging_detected ? 'Técnica de bridging detectada' : 'Control y manejo de crisis'
            }
          ],
          metrics: m
        };
      }
    } catch (e) {
      console.warn('Error fetching raw coach report, falling back to mock:', e);
    }
    return INITIAL_REPORT;
  }
};
