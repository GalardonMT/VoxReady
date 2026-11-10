import type {
  LabelingCaseDetail,
  LabelingMetric,
  LabelingReview,
  LabelingReviewRequest,
} from '../types/api';

export interface ReviewFieldState {
  value: string;
  comment: string;
}

export interface LabelingReviewForm {
  overallComment: string;
  rubric: Record<string, ReviewFieldState>;
  metrics: Record<string, ReviewFieldState>;
  idempotencyKey: string;
}

export type ReviewFormAction =
  | { type: 'rubricValue'; key: string; value: string; nextIdempotencyKey: string }
  | { type: 'rubricComment'; key: string; value: string; nextIdempotencyKey: string }
  | { type: 'metricValue'; key: string; value: string; nextIdempotencyKey: string }
  | { type: 'metricComment'; key: string; value: string; nextIdempotencyKey: string }
  | { type: 'overallComment'; value: string; nextIdempotencyKey: string }
  | { type: 'replace'; form: LabelingReviewForm };

export function labelingReviewReducer(
  state: LabelingReviewForm,
  action: ReviewFormAction,
): LabelingReviewForm {
  if (action.type === 'replace') return action.form;
  if (action.type === 'overallComment') {
    return { ...state, overallComment: action.value, idempotencyKey: action.nextIdempotencyKey };
  }
  const group = action.type.startsWith('rubric') ? 'rubric' : 'metrics';
  const field = action.type.endsWith('Value') ? 'value' : 'comment';
  return {
    ...state,
    idempotencyKey: action.nextIdempotencyKey,
    [group]: {
      ...state[group],
      [action.key]: { ...state[group][action.key], [field]: action.value },
    },
  };
}

export function editableMetrics(detail: LabelingCaseDetail): LabelingMetric[] {
  return detail.metricGroups
    .filter(group => group.categoryKey !== 'governance')
    .flatMap(group => group.metrics)
    .filter(metric => metric.metricKind === 'observation' && metric.availability === 'available' && metric.editable);
}

export function createLabelingReviewForm(
  detail: LabelingCaseDetail,
  currentReview: LabelingReview | null,
  idempotencyKey: string,
): LabelingReviewForm {
  const areaCorrections = new Map(
    (currentReview?.rubricCorrections ?? []).map(item => [item.areaKey, item]),
  );
  const metricCorrections = new Map(
    (currentReview?.metricCorrections ?? []).map(item => [item.metricKey, item]),
  );
  return {
    overallComment: currentReview?.overallComment ?? '',
    idempotencyKey,
    rubric: Object.fromEntries(detail.rubric.areas.filter(area => area.editable).map(area => {
      const correction = areaCorrections.get(area.areaKey);
      return [area.areaId, {
        value: String(correction?.correctedValue ?? area.aiValue ?? ''),
        comment: correction?.comment ?? '',
      }];
    })),
    metrics: Object.fromEntries(editableMetrics(detail).map(metric => {
      const correction = metricCorrections.get(metric.metricKey);
      return [metric.metricKey, {
        value: String(correction?.correctedValue ?? metric.aiValue ?? ''),
        comment: correction?.comment ?? '',
      }];
    })),
  };
}

function parsedNumber(value: string): number | null {
  if (!value.trim()) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function decimalPlaces(value: string): number {
  const decimal = value.trim().split('.')[1];
  return decimal?.length ?? 0;
}

export function validateLabelingReview(
  detail: LabelingCaseDetail,
  form: LabelingReviewForm,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.overallComment.trim()) errors.overallComment = 'La observación general es obligatoria.';

  for (const area of detail.rubric.areas.filter(item => item.editable)) {
    const field = form.rubric[area.areaId];
    const value = parsedNumber(field?.value ?? '');
    if (value === null || value < 0 || value > 100 || decimalPlaces(field.value) > 2) {
      errors[`rubric.${area.areaId}`] = 'Debe estar entre 0 y 100, con hasta dos decimales.';
    } else if (area.aiValue !== null && value !== area.aiValue && !field.comment.trim()) {
      errors[`rubric.${area.areaId}.comment`] = 'Justifica el cambio respecto de la propuesta IA.';
    }
  }

  for (const metric of editableMetrics(detail)) {
    const field = form.metrics[metric.metricKey];
    const value = parsedNumber(field?.value ?? '');
    const observation = metric.observation;
    if (value === null) {
      errors[`metric.${metric.metricKey}`] = 'Ingresa un valor numérico.';
      continue;
    }
    if ((observation?.technicalMin !== null && observation?.technicalMin !== undefined && value < observation.technicalMin)
      || (observation?.technicalMax !== null && observation?.technicalMax !== undefined && value > observation.technicalMax)
      || (observation?.valueType === 'integer' && !Number.isInteger(value))
      || decimalPlaces(field.value) > metric.precision) {
      errors[`metric.${metric.metricKey}`] = 'El valor no cumple el rango o precisión de la métrica.';
    } else if (metric.aiValue !== null && value !== metric.aiValue && !field.comment.trim()) {
      errors[`metric.${metric.metricKey}.comment`] = 'Justifica el cambio respecto de la propuesta IA.';
    }
  }
  return errors;
}

export function buildLabelingReviewRequest(
  detail: LabelingCaseDetail,
  form: LabelingReviewForm,
  lease: { leaseToken: string; leaseGeneration: number; contentRevision: number },
  supersedesReviewId: string | null,
): LabelingReviewRequest {
  const errors = validateLabelingReview(detail, form);
  if (Object.keys(errors).length) throw new Error('La revisión contiene errores de validación.');
  const metrics = editableMetrics(detail);
  return {
    leaseToken: lease.leaseToken,
    leaseGeneration: lease.leaseGeneration,
    expectedContentRevision: lease.contentRevision,
    idempotencyKey: form.idempotencyKey,
    supersedesReviewId,
    overallComment: form.overallComment.trim().replace(/\s+/g, ' '),
    rubricCorrections: detail.rubric.areas.filter(area => area.editable).map(area => ({
      areaId: area.areaId,
      correctedValue: Number(form.rubric[area.areaId].value),
      comment: form.rubric[area.areaId].comment.trim() || null,
    })),
    metricCorrections: metrics.flatMap(metric => {
      const field = form.metrics[metric.metricKey];
      const value = Number(field.value);
      const changed = value !== metric.aiValue;
      return changed || field.comment.trim() ? [{
        metricKey: metric.metricKey,
        correctedValue: value,
        comment: field.comment.trim() || null,
      }] : [];
    }),
  };
}
