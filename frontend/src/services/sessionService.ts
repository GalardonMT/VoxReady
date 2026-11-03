import { ApiError, apiFetch, isAccessError } from './apiClient';
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
  async createSession(scenarioId: string): Promise<CreateSessionResponse> {
    if (!scenarioId) throw new Error('Debes seleccionar un escenario antes de crear la sesión.');
    const res = await apiFetch<{ session_id?: string; sessionId?: string; status?: string }>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: scenarioId })
    });
    const sessionId = res.session_id || res.sessionId;
    if (!sessionId) throw new Error('La API no entregó un identificador de sesión.');
    return {
      sessionId,
      status: res.status || 'created',
      scenarioId,
      createdAt: new Date().toISOString()
    };
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
  async getUploadUrl(sessionId: string): Promise<RecordingUrlResponse> {
    try {
      const res = await apiFetch<{ upload_url: string; blob_name: string; max_size_bytes: number; expires_at: string }>(
        `/api/sessions/${sessionId}/upload-url`,
        { method: 'POST' }
      );
      if (!res.blob_name) throw new Error('La API no entregó la ruta del archivo de grabación.');
      return {
        uploadUrl: res.upload_url,
        blobPath: res.blob_name,
        expiresAt: res.expires_at,
        maxSizeBytes: res.max_size_bytes
      };
    } catch (err) {
      throw err;
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
    scenarioId: string,
    tenantId: string | null,
    turnsOrMarks: (TurnInterval | QuestionMark)[] = []
  ): Promise<boolean> {
    if (!blobName) throw new Error('La ruta de grabación no está disponible.');
    const finalBlobName = blobName;
    const formattedTurns: TurnInterval[] = [];
    const questionMarks: QuestionMark[] = [];

    turnsOrMarks.forEach((item, idx) => {
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
      if (error instanceof ApiError && error.problem.status === 409) {
        return [
          { id: 'content', label: 'Contenido y coherencia de discurso', status: 'running' },
          { id: 'voice', label: 'Tono de voz y modulación acústica', status: 'running' },
          { id: 'image', label: 'Expresión visual y contacto visual', status: 'running' },
          { id: 'fusion', label: 'Fusión multimodal e índice de empatía', status: 'pending' }
        ];
      }
      throw error;
    }
  },

  /**
   * Consulta el estado y progreso del reporte en Azure, gestionando HTTP 409 como análisis en curso
   */
  async getRawReport(sessionId: string): Promise<AzureReportResponse> {
    try {
      return await apiFetch<AzureReportResponse>(`/api/sessions/${sessionId}/report`);
    } catch (error: unknown) {
      // HTTP 409 Conflict: El análisis continúa ejecutándose en el worker
      if (error instanceof ApiError && error.problem.status === 409) {
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
        const full = raw as FullVisumReport;
        if (!full.durationSeconds) {
          const d = full.metrics?.audio?.duracionSegundos || full.metricsSummary?.durationSeconds;
          if (d) full.durationSeconds = d;
        }
        return full;
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

        const rawGlobalScore = raw.overallScore ?? p.score_general;
        if (typeof rawGlobalScore !== 'number') {
          throw new Error('El reporte no contiene una puntuación global válida.');
        }
        const globalScore = Math.round(rawGlobalScore);
        
        // Extraer scores de las 4 áreas si están presentes en areaScores
        const areaMap: Record<string, number> = {};
        if (raw.areaScores && Array.isArray(raw.areaScores)) {
          raw.areaScores.forEach((as) => {
            areaMap[as.area] = as.value;
          });
        }

        const nonVerbalScore = Math.round(areaMap['expression'] ?? p.score_comunicacion_no_verbal ?? globalScore);
        const verbalScore = Math.round(areaMap['voice'] ?? p.score_comunicacion_verbal ?? globalScore);
        const coherenceScore = Math.round(areaMap['coherence'] ?? j.key_message_adherence_score ?? globalScore);
        const crisisScore = Math.round(areaMap['empathy'] ?? p.score_estrategia_crisis ?? globalScore);

        // Fortalezas y mejoras desde narrative o judge
        const narrative = (raw.narrative || {}) as { strengths?: string[]; improvements?: string[]; crossSignal?: string };
        const strengths = narrative.strengths && narrative.strengths.length > 0
          ? narrative.strengths
          : (j.strengths || []);
        const improvements = narrative.improvements && narrative.improvements.length > 0
          ? narrative.improvements
          : (j.weaknesses || []);
        const crossSignalQuote = narrative.crossSignal || j.executive_summary || '';

        // Métricas visuales legibles
        const eyePct = v.eyeContactPct ?? v.eye_contact_percentage;
        const postureScore = v.shoulderStabilityScore ?? v.average_posture_score;
        const wpmVal = a.wpmGlobal ?? a.wpm;
        const fillersCount = a.fillers_count ?? a.muletillasDetectadas?.length;
        const pausesCount = a.pausasProlongadas ?? a.silence_pauses;
        const rawDuration = a.duracionSegundos ?? a.duracion_segundos ?? raw.durationSeconds;
        const durationSecs = typeof rawDuration === 'number' ? rawDuration : undefined;

        return {
          sessionId: raw.sessionId || raw.session_id || sessionId,
          scenarioName: raw.scenarioTitle || scenarioName || `Sesión ${sessionId}`,
          date: raw.generatedAt ? new Date(raw.generatedAt).toLocaleDateString() : (raw.processed_at ? new Date(raw.processed_at).toLocaleDateString() : new Date().toLocaleDateString()),
          globalScore,
          goodAspects: strengths,
          improveAspects: improvements,
          crossSignalQuote,
          recordingUrl: raw.recordingUrl,
          durationSeconds: durationSecs && durationSecs > 0 ? durationSecs : undefined,
          areas: [
            {
              name: 'Imagen / no verbal',
              channel: 'MediaPipe Vision',
              score: nonVerbalScore,
              criteria: `Contacto visual: ${eyePct ?? 'N/D'}% · Estabilidad: ${postureScore ?? 'N/D'}%`
            },
            {
              name: 'Voz / prosodia',
              channel: 'Acústica Parakeet',
              score: verbalScore,
              criteria: `Velocidad: ${wpmVal ?? 'N/D'} WPM · Muletillas: ${fillersCount ?? 'N/D'} · Pausas: ${pausesCount ?? 'N/D'}`
            },
            {
              name: 'Contenido y discurso',
              channel: 'Juez LLM configurado',
              score: coherenceScore,
              criteria: 'Apego a mensajes clave y coherencia estratégica'
            },
            {
              name: 'Estrategia de crisis y empatía',
              channel: 'Fusión Multimodal',
              score: crisisScore,
              criteria: j.bridging_detected ? 'Técnica de bridging detectada' : 'Control y manejo de crisis'
            }
          ],
          metrics: m
        };
      }
    } catch (error) {
      throw error;
    }
    throw new Error('El reporte todavía no está disponible.');
  },

  /**
   * Obtiene una URL SAS de lectura temporal para reproducir la grabación de la sesión
   */
  async getPlaybackUrl(sessionId: string): Promise<string> {
    try {
      // 1. Probar desde getRawReport (si ya incluye recordingUrl con SAS prefirmada)
      try {
        const raw = await this.getRawReport(sessionId);
        if (raw && raw.recordingUrl) {
          return raw.recordingUrl;
        }
      } catch (errReport) {
        console.warn('Aviso: getRawReport en getPlaybackUrl no retornó recordingUrl:', errReport);
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
    } catch (error) {
      throw error;
    }
  }
};
