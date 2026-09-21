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

const DEFAULT_ANALYSIS_STEPS: MultimodalAnalysisStep[] = [
  { id: 'content', label: 'Contenido y coherencia de discurso', status: 'done' },
  { id: 'voice', label: 'Tono de voz y modulación acústica', status: 'done' },
  { id: 'image', label: 'Expresión visual y contacto visual', status: 'running' },
  { id: 'fusion', label: 'Fusión multimodal e índice de empatía', status: 'pending' }
];


export interface CreateSessionResponse {
  sessionId: string;
  status: string;
  scenarioId: string;
  createdAt: string;
}

export interface RecordingUrlResponse {
  uploadUrl: string;
  blobPath: string;
  expiresAt: string;
  maxSizeBytes: number;
}

export interface AnalysisStatusResponse {
  sessionId: string;
  status: string;
  progressPercent: number;
  pipelines: {
    content: string;
    voice: string;
    image: string;
    fusion: string;
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
    try {
      return await apiFetch<CreateSessionResponse>('/sessions', {
        method: 'POST',
        body: JSON.stringify({ scenarioId })
      });
    } catch {
      return {
        sessionId: `sess-${Date.now()}`,
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
      await apiFetch(`/sessions/${sessionId}/consent`, {
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
   * Solicita una URL firmada de carga para la grabación
   */
  async getUploadUrl(sessionId: string): Promise<RecordingUrlResponse> {
    try {
      return await apiFetch<RecordingUrlResponse>(`/sessions/${sessionId}/recording-url`, {
        method: 'POST'
      });
    } catch {
      return {
        uploadUrl: `/v1/uploads/${sessionId}`,
        blobPath: `recordings/${sessionId}.webm`,
        expiresAt: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
        maxSizeBytes: 524288000
      };
    }
  },

  /**
   * Finaliza la sesión y encola el análisis multimodal
   */
  async finishSession(sessionId: string): Promise<boolean> {
    try {
      await apiFetch(`/sessions/${sessionId}/finish`, {
        method: 'POST'
      });
      return true;
    } catch {
      return true;
    }
  },

  /**
   * Consulta el progreso del análisis multimodal
   */
  async getAnalysisProgress(sessionId: string): Promise<MultimodalAnalysisStep[]> {
    try {
      const res = await apiFetch<AnalysisStatusResponse>(`/sessions/${sessionId}/analysis`);
      return [
        { id: 'content', label: 'Contenido y coherencia de discurso', status: res.pipelines.content as any },
        { id: 'voice', label: 'Tono de voz y modulación acústica', status: res.pipelines.voice as any },
        { id: 'image', label: 'Expresión visual y contacto visual', status: res.pipelines.image as any },
        { id: 'fusion', label: 'Fusión multimodal e índice de empatía', status: res.pipelines.fusion as any }
      ];
    } catch {
      return DEFAULT_ANALYSIS_STEPS;
    }
  },

  /**
   * Obtiene el reporte final tipo coach
   */
  async getCoachReport(sessionId: string): Promise<CoachReport> {
    try {
      return await apiFetch<CoachReport>(`/sessions/${sessionId}/report`);
    } catch {
      return INITIAL_REPORT;
    }
  }
};

