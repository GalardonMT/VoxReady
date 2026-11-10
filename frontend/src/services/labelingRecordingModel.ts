import type { LabelingRecordingTicket } from '../types/api';

export const MAX_RECORDING_RETRIES = 2;

export type RecordingFailureKind = 'deleted' | 'storage' | 'expired' | 'playback' | 'invalid';

export function recordingFailure(error: unknown): { kind: RecordingFailureKind; message: string } {
  const problem = error && typeof error === 'object' && 'problem' in error
    ? (error as { problem?: { status?: number; code?: string } }).problem
    : undefined;
  if (problem) {
    if (problem.status === 410 || problem.code === 'RECORDING_RETAINED_OR_DELETED') {
      return { kind: 'deleted', message: 'La grabación fue eliminada o alcanzó su período de retención.' };
    }
    if (problem.status === 503 || problem.code === 'STORAGE_UNAVAILABLE') {
      return { kind: 'storage', message: 'El almacenamiento no está disponible temporalmente.' };
    }
  }
  return { kind: 'playback', message: error instanceof Error ? error.message : 'No fue posible reproducir la grabación.' };
}

export function validateRecordingTicket(ticket: LabelingRecordingTicket): string | null {
  if (!ticket.url.startsWith('https://')) return 'La URL temporal no usa HTTPS.';
  if (!ticket.contentType.toLowerCase().startsWith('video/')) return 'El tipo de contenido no corresponde a un video.';
  if (!ticket.etag.trim()) return 'La evidencia no contiene ETag.';
  if (!Number.isFinite(Date.parse(ticket.expiresAt))) return 'La expiración de la URL no es válida.';
  return null;
}

export function recordingDuration(ticket: LabelingRecordingTicket, persistedDuration: number | null): number {
  const ticketDuration = ticket.durationSeconds;
  if (ticketDuration !== null && Number.isFinite(ticketDuration) && ticketDuration > 0) return ticketDuration;
  return persistedDuration !== null && Number.isFinite(persistedDuration) && persistedDuration > 0
    ? persistedDuration
    : 0;
}

export function recordingRefreshDelay(expiresAt: string, now: number, safetyWindowMs = 30_000): number {
  const expiry = Date.parse(expiresAt);
  if (!Number.isFinite(expiry)) return 0;
  return Math.max(0, expiry - now - safetyWindowMs);
}

export function canRetryRecording(attempts: number): boolean {
  return attempts < MAX_RECORDING_RETRIES;
}
