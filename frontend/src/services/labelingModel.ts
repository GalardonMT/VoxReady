import type { LabelingCase, LabelingCaseListResponse, LabelingCaseStatus } from '../types/api';

const REASON_LABELS: Record<LabelingCase['queueReason'], string> = {
  critical: 'Puntaje crítico',
  borderline: 'Puntaje límite',
  disparity: 'Diferencia entre áreas',
  routine: 'Muestreo de control',
};

function timestamp(value: string | null | undefined): number {
  if (!value) return Number.NEGATIVE_INFINITY;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}
export function prepareLabelingCases(
  response: LabelingCaseListResponse,
  status: LabelingCaseStatus,
): LabelingCase[] {
  const items = response.items.filter(item => item.status === status);
  return [...items]
    .sort((left, right) => {
      const leftDate = status === 'pending'
        ? timestamp(left.session.finishedAt)
        : timestamp(left.latestReview?.submittedAt);
      const rightDate = status === 'pending'
        ? timestamp(right.session.finishedAt)
        : timestamp(right.latestReview?.submittedAt);
      return rightDate - leftDate || right.caseId.localeCompare(left.caseId);
    })
    .slice(0, 10);
}
export function preserveLabelingSelection(
  selectedCaseId: string | null,
  pending: LabelingCase[],
  reviewed: LabelingCase[],
): string | null {
  const all = [...pending, ...reviewed];
  if (selectedCaseId && all.some(item => item.caseId === selectedCaseId)) {
    return selectedCaseId;
  }
  return pending[0]?.caseId ?? reviewed[0]?.caseId ?? null;
}

export function labelingReasonLabel(item: LabelingCase): string {
  if (item.queueReason === 'critical' && item.criticalAreas.length > 0) {
    return `${REASON_LABELS.critical} · ${item.criticalAreas.map(area => area.label).join(', ')}`;
  }
  return REASON_LABELS[item.queueReason];
}

export function labelingAlerts(item: LabelingCase): string[] {
  const alerts = item.criticalAreas.map(area => `${area.label}: ${formatScore(area.value)}`);
  if ((item.report.overallScore ?? 100) < 50) {
    alerts.unshift(`Puntaje general crítico: ${formatScore(item.report.overallScore)}`);
  }
  return alerts;
}

export function formatScore(value: number | null): string {
  return value === null || !Number.isFinite(value) ? 'Sin puntaje' : `${Math.round(value * 10) / 10} pts`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return '--:--';
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  return `${String(minutes).padStart(2, '0')}:${String(rounded % 60).padStart(2, '0')}`;
}

export function formatCaseDateTime(
  value: string | null,
  locale = 'es-CL',
  timeZone?: string,
): string {
  if (!value) return 'Fecha no disponible';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Fecha no disponible';
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'short',
    timeStyle: 'short',
    ...(timeZone ? { timeZone } : {}),
  }).format(date);
}
