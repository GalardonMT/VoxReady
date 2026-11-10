import test from 'node:test';
import assert from 'node:assert/strict';
import {
  currentEvidence,
  governanceContext,
  metricEvidence,
  qualityPeriodBounds,
  rubricEvidence,
} from '../src/services/qualityReviewModel.ts';

const aggregate = {
  sampleCount: 2, meanAiValue: 70, meanCorrectedValue: 75, meanDelta: 5,
  meanAbsoluteError: 5, changedCount: 2, increasedCount: 2,
  decreasedCount: 0, unchangedCount: 0,
};

function summary() {
  return {
    period: { from: null, to: null }, currentReviewsOnly: true, reviewedCases: 2,
    rubricAreas: [
      { ...aggregate, rubricVersionId: 'version-b', areaKey: 'voice' },
      { ...aggregate, rubricVersionId: 'version-a', areaKey: 'expression' },
    ],
    metrics: [
      { ...aggregate, metricKey: 'voice.wpm', mappingVersion: 2, unit: 'WPM' },
      { ...aggregate, metricKey: 'voice.wpm', mappingVersion: 1, unit: 'palabras/min' },
      { ...aggregate, metricKey: 'gov.agreement_target', mappingVersion: 1, unit: 'ratio' },
    ],
    categories: [
      { categoryKey: 'voice', reviewedMetricCount: 4, changedCount: 2 },
      { categoryKey: 'governance', reviewedMetricCount: 3, changedCount: 1 },
    ],
  };
}

test('period filters produce an exclusive upper bound and a stable lower bound', () => {
  const now = new Date('2026-11-09T12:00:00.000Z');
  assert.deepEqual(qualityPeriodBounds('7', now), {
    from: '2026-11-02T12:00:00.000Z', to: '2026-11-09T12:00:00.000Z',
  });
  assert.equal(qualityPeriodBounds('all', now).from, null);
});

test('rubric evidence remains separated by rubric version without mutating the response', () => {
  const input = summary();
  const original = structuredClone(input.rubricAreas);
  assert.deepEqual(rubricEvidence(input).map(item => item.rubricVersionId), ['version-a', 'version-b']);
  assert.deepEqual(input.rubricAreas, original);
});

test('metric evidence preserves mapping and unit identities and excludes governance calibration', () => {
  const items = metricEvidence(summary());
  assert.deepEqual(items.map(item => [item.metricKey, item.mappingVersion, item.unit]), [
    ['voice.wpm', 1, 'palabras/min'],
    ['voice.wpm', 2, 'WPM'],
  ]);
  assert.deepEqual(governanceContext(summary()), {
    categoryKey: 'governance', reviewedMetricCount: 3, changedCount: 1,
  });
});

test('recent evidence includes only current reviews inside the selected period', () => {
  const cases = [{ caseId: 'case-a', caseNumber: 'Caso #1' }, { caseId: 'case-b', caseNumber: 'Caso #2' }];
  const base = { reviewId: 'r', reviewNo: 1, reviewerCode: 'EXP-1', supersedesReviewId: null,
    contentRevision: 1, overallComment: 'ok', rubricCorrections: [], metricCorrections: [] };
  const reviews = new Map([
    ['case-a', [{ ...base, caseId: 'case-a', isCurrent: true, submittedAt: '2026-11-08T12:00:00Z' }]],
    ['case-b', [{ ...base, caseId: 'case-b', isCurrent: false, submittedAt: '2026-11-08T12:00:00Z' }]],
  ]);
  const result = currentEvidence(cases, reviews, {
    from: '2026-11-02T12:00:00Z', to: '2026-11-09T12:00:00Z',
  });
  assert.deepEqual(result.map(item => item.caseId), ['case-a']);
});
