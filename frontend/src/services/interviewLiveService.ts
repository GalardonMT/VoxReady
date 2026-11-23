import { INTERVIEW_API_BASE_URL, getAuthToken } from './apiClient';

export interface SubmitInterviewTurnParams {
  sessionId: string;
  audioBlob: Blob;
  baseSequenceNo: number;
  turnIndex: number;
  turnKind: 'base' | 'follow_up';
  questionText: string;
  parentTurnId?: string | null;
  startOffsetMs?: number | null;
  endOffsetMs?: number | null;
  timeoutMs?: number;
}

export interface SubmitInterviewTurnResponse {
  turnId: string;
  sessionId: string;
  turnIndex: number;
  baseSequenceNo: number;
  turnKind: 'base' | 'follow_up';
  hasFollowUp: boolean;
  followUpQuestion: string | null;
  triggerReason: string | null;
  remainingFollowUpsForBase: number;
  asrStatus: string;
  degraded: boolean;
  geminiLatencyMs?: number | null;
  idempotentReplay?: boolean;
}

const DEFAULT_TURN_TIMEOUT_MS = 15000;

function degradedResponse(params: SubmitInterviewTurnParams): SubmitInterviewTurnResponse {
  return {
    turnId: '',
    sessionId: params.sessionId,
    turnIndex: params.turnIndex,
    baseSequenceNo: params.baseSequenceNo,
    turnKind: params.turnKind,
    hasFollowUp: false,
    followUpQuestion: null,
    triggerReason: null,
    remainingFollowUpsForBase: 0,
    asrStatus: 'failed',
    degraded: true,
    geminiLatencyMs: null
  };
}

export const interviewLiveService = {
  async submitTurn(params: SubmitInterviewTurnParams): Promise<SubmitInterviewTurnResponse> {
    const base = INTERVIEW_API_BASE_URL.replace(/\/+$/, '');
    const url = `${base}/interview-live/sessions/${encodeURIComponent(params.sessionId)}/turns`;
    const token = await getAuthToken();

    const ext = params.audioBlob.type.includes('mp4')
      ? 'mp4'
      : params.audioBlob.type.includes('ogg')
      ? 'ogg'
      : 'webm';

    const formData = new FormData();
    formData.append('audio', params.audioBlob, `turn_${params.turnIndex}.${ext}`);
    formData.append('baseSequenceNo', String(params.baseSequenceNo));
    formData.append('turnIndex', String(params.turnIndex));
    formData.append('turnKind', params.turnKind);
    formData.append('questionText', params.questionText);
    if (params.parentTurnId) {
      formData.append('parentTurnId', params.parentTurnId);
    }
    if (params.startOffsetMs !== null && params.startOffsetMs !== undefined) {
      formData.append('startOffsetMs', String(Math.max(0, Math.round(params.startOffsetMs))));
    }
    if (params.endOffsetMs !== null && params.endOffsetMs !== undefined) {
      formData.append('endOffsetMs', String(Math.max(0, Math.round(params.endOffsetMs))));
    }

    const headers: Record<string, string> = {
      Accept: 'application/json',
      'x-correlation-id': `turn-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timeoutMs = params.timeoutMs ?? DEFAULT_TURN_TIMEOUT_MS;
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: formData,
        signal: controller.signal
      });

      if (!response.ok) {
        console.warn(`[interviewLiveService] HTTP ${response.status} enviando turno ${params.turnIndex}. Degradando sin contrapregunta.`);
        return degradedResponse(params);
      }

      const data = (await response.json()) as SubmitInterviewTurnResponse;
      return {
        ...data,
        hasFollowUp: Boolean(data.hasFollowUp && data.followUpQuestion),
        followUpQuestion: data.followUpQuestion || null
      };
    } catch (err) {
      console.warn('[interviewLiveService] Timeout o error de red en /turns. Continuando entrevista sin contrapregunta:', err);
      return degradedResponse(params);
    } finally {
      clearTimeout(timeoutId);
    }
  }
};
