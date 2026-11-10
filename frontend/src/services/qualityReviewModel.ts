import type {
  LabelingMetricQualityAggregate,
  LabelingQualitySummary,
  LabelingReview,
  LabelingRubricQualityAggregate,
} from '../types/api';

export type QualityPeriod = '7' | '30' | '90' | 'all';

export interface ReviewedCaseEvidence {
  caseId: string;
  caseNumber: string;
  review: LabelingReview;
}

export const LABELING_CASE_TARGET_KEY = 'voxready_labeling_case_target';

export function qualityPeriodBounds(period: QualityPeriod, now = new Date()): { from: string | null; to: string } {
  const to = now.toISOString();
  if (period === 'all') return { from: null, to };
  const from = new Date(now.getTime() - Number(period) * 24 * 60 * 60 * 1000);
  return { from: from.toISOString(), to };
}

export function rubricEvidence(summary: LabelingQualitySummary): LabelingRubricQualityAggregate[] {
  return [...summary.rubricAreas].sort((left, right) =>
    left.rubricVersionId.localeCompare(right.rubricVersionId)
      || left.areaKey.localeCompare(right.areaKey));
}

export function metricEvidence(summary: LabelingQualitySummary): LabelingMetricQualityAggregate[] {
  return summary.metrics
    .filter(item => !item.metricKey.startsWith('gov.'))
    .sort((left, right) => left.metricKey.localeCompare(right.metricKey)
      || left.mappingVersion - right.mappingVersion
      || left.unit.localeCompare(right.unit));
}

export function governanceContext(summary: LabelingQualitySummary) {
  return summary.categories.find(item => item.categoryKey === 'governance') ?? null;
}

export function currentEvidence(
  cases: Array<{ caseId: string; caseNumber: string }>,
  reviewsByCase: Map<string, LabelingReview[]>,
  bounds: { from: string | null; to: string },
): ReviewedCaseEvidence[] {
  const from = bounds.from ? Date.parse(bounds.from) : Number.NEGATIVE_INFINITY;
  const to = Date.parse(bounds.to);
  return cases.flatMap(item => {
    const review = reviewsByCase.get(item.caseId)?.find(candidate => candidate.isCurrent);
    if (!review) return [];
    const submitted = Date.parse(review.submittedAt);
    return submitted >= from && submitted < to ? [{ ...item, review }] : [];
  }).sort((left, right) => Date.parse(right.review.submittedAt) - Date.parse(left.review.submittedAt));
}

export function rubricComments(evidence: ReviewedCaseEvidence[], areaKey: string) {
  return evidence.flatMap(item => {
    const correction = item.review.rubricCorrections.find(candidate => candidate.areaKey === areaKey);
    const comment = correction?.comment?.trim();
    return comment ? [{ ...item, comment }] : [];
  }).slice(0, 3);
}

export function metricComments(evidence: ReviewedCaseEvidence[], metricKey: string, unit: string) {
  return evidence.flatMap(item => {
    const correction = item.review.metricCorrections.find(candidate =>
      candidate.metricKey === metricKey && candidate.unit === unit);
    const comment = correction?.comment?.trim();
    return comment ? [{ ...item, comment }] : [];
  }).slice(0, 3);
}

export function shortIdentity(value: string): string {
  return value.length <= 12 ? value : `${value.slice(0, 8)}…`;
}

export function formatDelta(value: number | null, unit = 'pts'): string {
  if (value === null) return 'Sin datos';
  const sign = value > 0 ? '+' : '';
  return `${sign}${new Intl.NumberFormat('es-CL', { maximumFractionDigits: 2 }).format(value)} ${unit}`;
}
