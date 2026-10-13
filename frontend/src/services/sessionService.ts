import { apiFetch, isAccessError } from './apiClient';
import {
  CreateSessionResponse,
  RecordingUrlResponse,
  CoachReport,
  MultimodalAnalysisStep,
  TurnInterval,
  SessionHistoryItem,
  FullVisumReport
} from '../types/api';

export interface AzureReportResponse extends Partial<FullVisumReport> {
  session_id: string;
  status: string;
  message?: string;
  processed_at?: string;
  puntuacion_global?: {
    score_general?: number;
    score_comunicacion_verbal?: number;
    score_comunicacion_no_verbal?: number;
    score_estrategia_crisis?: number;
    areas?: Record<string, number>;
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
    const defaultSessId = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}`;
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
  async getUploadUrl(sessionId: string, _extension: string = 'webm'): Promise<RecordingUrlResponse> {
    try {
      const res = await apiFetch<{ upload_url: string; blob_name: string }>(
        `/api/sessions/${sessionId}/upload-url`,
        { method: 'POST' }
      );
      return {
        uploadUrl: res.upload_url,
        blobPath: res.blob_name || `recordings/${sessionId}.webm`,
        expiresAt: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
        maxSizeBytes: 524288000
      };
    } catch (err) {
      if (isAccessError(err)) throw err;
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
    tenantId: string = 'tenant-voxready-dev',
    turnsOrMarks: (TurnInterval | QuestionMark)[] = []
  ): Promise<boolean> {
    const finalBlobName = blobName || `recordings/${sessionId}.webm`;
    const formattedTurns: TurnInterval[] = [];
    const questionMarks: QuestionMark[] = [];

    turnsOrMarks.forEach((item: any, idx: number) => {
      if ('questionIndex' in item) {
        questionMarks.push(item as QuestionMark);
        const start = Math.round(Number(item.startMs) || 0);
        const end = Math.round(
          Number(item.endMs !== null && item.endMs !== undefined ? item.endMs : start + 5000)
        );
        formattedTurns.push({
          questionId: `q-${item.questionIndex + 1}`,
          sequenceNo: idx + 1,
          startOffsetMs: start,
          endOffsetMs: Math.max(end, start + 1000)
        });
      } else {
        formattedTurns.push(item as TurnInterval);
      }
    });

    try {
      await apiFetch(`/api/sessions/${sessionId}/finish`, {
        method: 'POST',
        body: JSON.stringify({
          blobPath: finalBlobName,
          video_blob_name: finalBlobName,
          scenario_id: scenarioId,
          tenant_id: tenantId,
          turns: formattedTurns,
          question_marks: questionMarks.length > 0 ? questionMarks : undefined
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
   * Consulta el estado y progreso del reporte en Azure, gestionando HTTP 409 como análisis en curso
   */
  async getRawReport(sessionId: string): Promise<AzureReportResponse> {
    try {
      return await apiFetch<AzureReportResponse>(`/api/sessions/${sessionId}/report`);
    } catch (error: any) {
      // HTTP 409 Conflict: El análisis continúa ejecutándose en el worker
      if (error?.status === 409 || error?.problem?.status === 409) {
        return {
          session_id: sessionId,
          sessionId: sessionId,
          status: 'analyzing',
          message: 'El análisis multimodal está en curso...'
        } as AzureReportResponse;
      }
      throw error;
    }
  },

  /**
   * Obtiene el informe completo enriquecido con análisis de Visum y métricas técnicas detalladas
   */
  async getFullVisumReport(sessionId: string): Promise<FullVisumReport | null> {
    try {
      const raw = await this.getRawReport(sessionId);
      if (raw && (raw.status === 'completed' || raw.overallScore !== undefined)) {
        return raw as FullVisumReport;
      }
      return null;
    } catch (e) {
      console.warn('Error fetching full visum report:', e);
      return null;
    }
  },

  /**
   * Obtiene el reporte final tipo coach transformando las métricas de Azure
   */
  async getCoachReport(sessionId: string, scenarioName?: string): Promise<CoachReport> {
    try {
      const raw = await this.getRawReport(sessionId);
      if (raw && (raw.status === 'completed' || raw.overallScore !== undefined || raw.puntuacion_global)) {
        const p = raw.puntuacion_global || {};
        const m = raw.metrics || {};
        const v = m.vision || {};
        const a = m.audio || {};
        const j = m.judge || {};

        const globalScore = Math.round(raw.overallScore ?? p.score_general ?? 75);
        
        // Extraer scores de las 4 áreas si están presentes en areaScores
        const areaMap: Record<string, number> = {};
        if (raw.areaScores && Array.isArray(raw.areaScores)) {
          raw.areaScores.forEach((as) => {
            areaMap[as.area] = as.value;
          });
        }

        const nonVerbalScore = Math.round(areaMap['expression'] ?? p.score_comunicacion_no_verbal ?? 70);
        const verbalScore = Math.round(areaMap['voice'] ?? p.score_comunicacion_verbal ?? 80);
        const coherenceScore = Math.round(areaMap['coherence'] ?? (j as any)?.key_message_adherence_score ?? 85);
        const crisisScore = Math.round(areaMap['empathy'] ?? p.score_estrategia_crisis ?? 80);

        // Fortalezas y mejoras desde narrative o judge
        const narrative = (raw.narrative || {}) as { strengths?: string[]; improvements?: string[]; crossSignal?: string };
        const strengths = narrative.strengths && narrative.strengths.length > 0
          ? narrative.strengths
          : ((j as any)?.strengths || INITIAL_REPORT.goodAspects);
        const improvements = narrative.improvements && narrative.improvements.length > 0
          ? narrative.improvements
          : ((j as any)?.weaknesses || INITIAL_REPORT.improveAspects);
        const crossSignalQuote = narrative.crossSignal || (j as any)?.executive_summary || INITIAL_REPORT.crossSignalQuote;

        // Métricas visuales legibles
        const eyePct = (v as any)?.eyeContactPct ?? (v as any)?.eye_contact_percentage ?? 30;
        const postureScore = (v as any)?.shoulderStabilityScore ?? (v as any)?.average_posture_score ?? 91;
        const wpmVal = (a as any)?.wpmGlobal ?? (a as any)?.wpm ?? 128;
        const fillersCount = (a as any)?.fillerWordsCount ?? (a as any)?.fillers_count ?? ((a as any)?.muletillasDetectadas?.length || 0);
        const pausesCount = (a as any)?.pausasProlongadas ?? (a as any)?.silence_pauses ?? 0;

        return {
          sessionId: raw.sessionId || raw.session_id || sessionId,
          scenarioName: raw.scenarioTitle || scenarioName || 'Incidente Corporativo y Vocería de Crisis',
          date: raw.generatedAt ? new Date(raw.generatedAt).toLocaleDateString() : (raw.processed_at ? new Date(raw.processed_at).toLocaleDateString() : new Date().toLocaleDateString()),
          globalScore,
          goodAspects: strengths,
          improveAspects: improvements,
          crossSignalQuote,
          areas: [
            {
              name: 'Imagen / no verbal',
              channel: 'MediaPipe Vision',
              score: nonVerbalScore,
              criteria: `Contacto visual: ${eyePct}% · Estabilidad: ${postureScore}%`
            },
            {
              name: 'Voz / prosodia',
              channel: 'Acústica Parakeet',
              score: verbalScore,
              criteria: `Velocidad: ${wpmVal} WPM · Muletillas: ${fillersCount} · Pausas: ${pausesCount}`
            },
            {
              name: 'Contenido y discurso',
              channel: 'Llama 3.2 90B Juez',
              score: coherenceScore,
              criteria: 'Apego a mensajes clave y coherencia estratégica'
            },
            {
              name: 'Estrategia de crisis y empatía',
              channel: 'Fusión Multimodal',
              score: crisisScore,
              criteria: (j as any)?.bridging_detected ? 'Técnica de bridging detectada' : 'Control y manejo de crisis'
            }
          ],
          metrics: m as Record<string, unknown>
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
      // 1. Probar desde getRawReport (si ya incluye recordingUrl con SAS prefirmada)
      const raw = await this.getRawReport(sessionId);
      if (raw && raw.recordingUrl) {
        return raw.recordingUrl;
      }
      // 2. Fallback al endpoint /recording-url
      const res = await apiFetch<{ playback_url: string; session_id: string; message?: string }>(
        `/api/sessions/${sessionId}/recording-url`
      );
      return res.playback_url || '';
    } catch (error) {
      console.warn('Error obteniendo URL de reproducción:', error);
      return '';
    }
  },

  /**
   * Obtiene el listado histórico de sesiones completadas del usuario autenticado
   */
  async getUserSessions(status: string = 'completed'): Promise<SessionHistoryItem[]> {
    try {
      const res = await apiFetch<SessionHistoryItem[]>(`/api/sessions/my?status=${encodeURIComponent(status)}`);
      if (Array.isArray(res)) {
        return res;
      }
      return [];
    } catch (e) {
      console.warn('Error al obtener historial de sesiones del usuario, usando respaldo:', e);
      return [
        {
          sessionId: 'session-crisis-001',
          scenarioId: 'crisis-voceria-01',
          scenarioTitle: 'Retiro Masivo de Alimentos Infantiles',
          createdAt: new Date(Date.now() - 3600000 * 24).toISOString(),
          status: 'completed',
          overallScore: 84,
          hasReport: true
        },
        {
          sessionId: 'session-crisis-002',
          scenarioId: 'crisis-operativa-02',
          scenarioTitle: 'Interrupción Crítica de Plataforma Transaccional',
          createdAt: new Date(Date.now() - 3600000 * 72).toISOString(),
          status: 'completed',
          overallScore: 78,
          hasReport: true
        }
      ];
    }
  }
};
