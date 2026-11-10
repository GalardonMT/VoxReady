import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildLabelingReviewRequest,
  createLabelingReviewForm,
  editableMetrics,
  labelingReviewReducer,
  validateLabelingReview,
} from '../src/services/labelingReviewModel.ts';

const areaIds = {
  expression: '11111111-1111-4111-8111-111111111111',
  voice: '22222222-2222-4222-8222-222222222222',
  coherence: '33333333-3333-4333-8333-333333333333',
  empathy: '44444444-4444-4444-8444-444444444444',
};

function detail() {
  const areas = Object.entries(areaIds).map(([areaKey, areaId], index) => ({
    areaId, areaKey, label: areaKey, aiValue: 80 + index, editable: true,
  }));
  return {
    caseId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', caseNumber: '8844', status: 'pending',
    queueReason: 'routine', reasonDetail: { kind: 'routine' },
    client: { code: 'CLI-X', displayName: 'Cliente' }, speakerCode: 'VOC-X',
    scenario: { title: 'Crisis' }, session: { startedAt: null, finishedAt: null, durationSeconds: 250 },
    report: { reportId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', generatedAt: '2026-10-27T00:00:00Z', overallScore: 82 },
    criticalAreas: [], lease: { state: 'available', ownerCode: null, expiresAt: null }, latestReview: null,
    contentRevision: 1, sourceStatus: 'complete', sourceIssues: [], snapshotSchemaVersion: 1,
    rubric: { rubricVersionId: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', areas },
    metricGroups: [
      { categoryKey: 'voice', label: 'Voz', metrics: [
        { metricKey: 'voice.wpm', categoryKey: 'voice', metricKind: 'observation', label: 'Ritmo', availability: 'available', aiValue: 130, unit: 'WPM', precision: 1, mappingVersion: 1, observation: { valueType: 'decimal', canonicalUnit: 'WPM', conversion: 'identity', technicalMin: 0, technicalMax: null }, editable: true, unavailableReason: null, publishedThresholds: {} },
        { metricKey: 'voice.pauses', categoryKey: 'voice', metricKind: 'observation', label: 'Pausas', availability: 'available', aiValue: 2, unit: 'count', precision: 0, mappingVersion: 1, observation: { valueType: 'integer', canonicalUnit: 'count', conversion: 'identity', technicalMin: 0, technicalMax: 20 }, editable: true, unavailableReason: null, publishedThresholds: {} },
      ] },
      { categoryKey: 'governance', label: 'Gobernanza', metrics: [
        { metricKey: 'gov.random_sample', categoryKey: 'governance', metricKind: 'configuration', label: 'Muestreo', availability: 'not_emitted', aiValue: null, unit: '%', precision: 0, mappingVersion: 1, observation: null, editable: false, unavailableReason: 'CONFIGURATION', publishedThresholds: {} },
      ] },
    ],
    recording: { availability: 'available', durationSeconds: 250 }, currentReview: null,
  };
}

test('form starts from IA/current review and excludes governance', () => {
  const source = detail();
  const current = {
    reviewId: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', caseId: source.caseId,
    reviewNo: 1, reviewerCode: 'EXP-X', isCurrent: true, supersedesReviewId: null,
    submittedAt: '2026-10-27T01:00:00Z', contentRevision: 2, overallComment: 'Anterior',
    rubricCorrections: [{ areaKey: 'expression', aiValue: 80, correctedValue: 78, comment: 'Ajuste' }],
    metricCorrections: [{ metricKey: 'voice.wpm', aiValue: 130, correctedValue: 125, unit: 'WPM', comment: 'Silencio' }],
  };
  const form = createLabelingReviewForm(source, current, 'key-1');
  assert.equal(form.rubric[areaIds.expression].value, '78');
  assert.equal(form.metrics['voice.wpm'].value, '125');
  assert.equal(form.overallComment, 'Anterior');
  assert.deepEqual(editableMetrics(source).map(metric => metric.metricKey), ['voice.wpm', 'voice.pauses']);
});
test('reducer keeps unrelated draft fields and rotates idempotency key on edits', () => {
  const source = detail();
  const initial = createLabelingReviewForm(source, null, 'key-1');
  const changed = labelingReviewReducer(initial, {
    type: 'rubricValue', key: areaIds.expression, value: '77', nextIdempotencyKey: 'key-2',
  });
  assert.equal(changed.rubric[areaIds.expression].value, '77');
  assert.equal(changed.rubric[areaIds.voice].value, initial.rubric[areaIds.voice].value);
  assert.equal(changed.idempotencyKey, 'key-2');
  assert.equal(initial.rubric[areaIds.expression].value, '80');
});
test('validation enforces comments, rubric range, metric precision and integer type', () => {
  const source = detail();
  const form = createLabelingReviewForm(source, null, 'key-1');
  form.overallComment = '';
  form.rubric[areaIds.expression].value = '101';
  form.metrics['voice.wpm'].value = '125.55';
  form.metrics['voice.pauses'].value = '2.5';
  const errors = validateLabelingReview(source, form);
  assert.ok(errors.overallComment);
  assert.ok(errors[`rubric.${areaIds.expression}`]);
  assert.ok(errors['metric.voice.wpm']);
  assert.ok(errors['metric.voice.pauses']);

  form.overallComment = 'Observación';
  form.rubric[areaIds.expression] = { value: '79', comment: '' };
  form.metrics['voice.wpm'] = { value: '125.5', comment: '' };
  form.metrics['voice.pauses'] = { value: '2', comment: '' };
  const comments = validateLabelingReview(source, form);
  assert.ok(comments[`rubric.${areaIds.expression}.comment`]);
  assert.ok(comments['metric.voice.wpm.comment']);
});

test('request includes all editable rubric areas, only changed metrics and successor identity', () => {
  const source = detail();
  const form = createLabelingReviewForm(source, null, 'idem-1');
  form.overallComment = '  Observación   experta ';
  form.rubric[areaIds.expression] = { value: '79', comment: 'Se ajustó' };
  form.metrics['voice.wpm'] = { value: '125.5', comment: 'Se excluyó silencio' };
  const request = buildLabelingReviewRequest(source, form, {
    leaseToken: 'secret', leaseGeneration: 3, contentRevision: 7,
  }, 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee');
  assert.equal(request.rubricCorrections.length, 4);
  assert.deepEqual(request.metricCorrections.map(item => item.metricKey), ['voice.wpm']);
  assert.equal(request.expectedContentRevision, 7);
  assert.equal(request.supersedesReviewId, 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee');
  assert.equal(request.overallComment, 'Observación experta');
  assert.equal(request.idempotencyKey, 'idem-1');
});
