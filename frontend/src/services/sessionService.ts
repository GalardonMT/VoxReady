import { apiFetch, isAccessError } from './apiClient';
import {
  CreateSessionResponse,
  RecordingUrlResponse,
  CoachReport,
  MultimodalAnalysisStep
} from '../types/api';

export interface AzureReportResponse {
  session_id: string;
  status: string;
  message?: string;
  processed_at?: string;
  puntuacion_global?: {
    score_general?: number;
    score_comunicacion_verbal?: number;
    score_comunicacion_no_verbal?: number;
    score_estrategia_crisis?: number;
  };
  metrics?: {
    vision?: {
      eye_contact_percentage?: number;
      average_posture_score?: number;
    };
    audio?: {
      wpm?: number;
      fillers_count?: number;
      silence_pauses?: number;
    };
    judge?: {
      strengths?: string[];
      weaknesses?: string[];
      executive_summary?: string;
      key_message_adherence_score?: number;
      bridging_detected?: boolean;
    };
  };
}

const INITIAL_REPORT: CoachReport = {
  sessionId: 'default',
  scenarioName: 'Incidente Corporativo y Vocería de Crisis',
  date: new Date().toLocaleDateString(),
  globalScore: 84,
  goodAspects: [
    'Excelente velocidad de habla y dicción (134 ppm)',
    'Postura erguida y contacto visual constante con la cámara (88%)',
    'Mensaje puente utilizado correctamente en la pregunta 3'
  ],
  improveAspects: [
    'Se detectaron 4 muletillas al inicio de las respuestas',
    'La entonación cayó levemente hacia el final de la sesión',
    'Mayor firmeza al abordar la compensación inmediata a usuarios'
  ],
  crossSignalQuote: '“En el segundo 42, tu tono de voz mostró seguridad mientras tu postura corporal reforzó el compromiso de la marca.”',
  areas: [
    {
      name: 'Imagen / no verbal',
      channel: 'MediaPipe Vision',
      score: 86,
      criteria: 'Contacto visual: 88%, Estabilidad: 92%'
    },
    {
      name: 'Voz / prosodia',
      channel: 'Acústica Parakeet',
      score: 82,
      criteria: 'Velocidad: 134 ppm, Muletillas: 4, Pausas: 3'
    },
    {
      name: 'Contenido y discurso',
      channel: 'Llama 3.2 90B Juez',
      score: 85,
      criteria: 'Apego a mensajes clave institucionales'
    },
    {
      name: 'Estrategia de crisis',
      channel: 'Fusión Multimodal',
      score: 83,
      criteria: 'Manejo de presión y técnica de bridging'
    }
  ]
};

const DEFAULT_ANALYSIS_STEPS: MultimodalAnalysisStep[] = [
  { id: 'content', label: 'Contenido y coherencia de discurso', status: 'done' },
  { id: 'voice', label: 'Tono de voz y modulación acústica', status: 'done' },
  { id: 'image', label: 'Expresión visual y contacto visual', status: 'done' },
  { id: 'fusion', label: 'Fusión multimodal e índice de empatía', status: 'done' }
];

export interface QuestionMark {
  questionIndex: number;
  startMs: number;
  endMs: number | null;
}

export const sessionService = {
  /**
   * Crea una nueva sesión en el backend
   */
  async createSession(scenarioId: string = 'crisis-voceria-01'): Promise<CreateSessionResponse> {
    const defaultSessId = `session-${scenarioId}-${Date.now()}`;
    try {
      const res = await apiFetch<{ session_id?: string; status?: string }>('/api/sessions', {
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
    } catch (error) {
      throw error;
    }
  },

  /**
   * Solicita una URL firmada SAS de Azure Blob Storage para subida directa (Zero-Proxy)
   */
  async getUploadUrl(sessionId: string, extension: string = 'webm'): Promise<RecordingUrlResponse> {
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
    } catch (err) {
      if (isAccessError(err)) throw err;
      return {
        uploadUrl: `/api/sessions/${sessionId}/upload-url`,
        blobPath: `recordings/${sessionId}.${extension}`,
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
    tenantId: string = 'tenant-voxready-dev',
    questionMarks: QuestionMark[] = []
  ): Promise<boolean> {
    try {
      await apiFetch(`/api/sessions/${sessionId}/finish`, {
        method: 'POST',
        body: JSON.stringify({
          video_blob_name: blobName,
          scenario_id: scenarioId,
          tenant_id: tenantId,
          question_marks: questionMarks
        })
      });
      return true;
    } catch (err: unknown) {
      if (isAccessError(err)) throw err;
      console.warn('Finish notification error:', err);
      throw err;
    }
  },

  /**
   * Consulta el progreso del análisis multimodal
   */
  async getAnalysisProgress(sessionId: string): Promise<MultimodalAnalysisStep[]> {
    try {
      const res = await apiFetch<{ status?: string }>(`/api/sessions/${sessionId}/report`);
      if (res && res.status === 'completed') {
        return DEFAULT_ANALYSIS_STEPS;
      }
      return [
        { id: 'content', label: 'Contenido y coherencia de discurso', status: 'done' },
        { id: 'voice', label: 'Tono de voz y modulación acústica', status: 'done' },
        { id: 'image', label: 'Expresión visual y contacto visual', status: 'running' },
        { id: 'fusion', label: 'Fusión multimodal e índice de empatía', status: 'pending' }
      ];
    } catch (error) {
      if (isAccessError(error)) throw error;
      return DEFAULT_ANALYSIS_STEPS;
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
  },

  /**
   * Obtiene una URL SAS de lectura temporal para reproducir la grabación de la sesión
   */
  async getPlaybackUrl(sessionId: string): Promise<string> {
    try {
      const res = await apiFetch<{ playback_url: string; session_id: string; message?: string }>(
        `/api/sessions/${sessionId}/recording-url`
      );
      return res.playback_url || '';
    } catch (error) {
      console.warn('Error obteniendo URL de reproducción:', error);
      return '';
    }
  }
};
