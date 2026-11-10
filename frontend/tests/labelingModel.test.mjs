import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  formatCaseDateTime,
  formatDuration,
  labelingAlerts,
  prepareLabelingCases,
  preserveLabelingSelection,
} from '../src/services/labelingModel.ts';

function labelingCase(index, status = 'pending', finishedAt) {
  const caseId = `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`;
  return {
    caseId,
    caseNumber: String(8800 + index),
    status,
    queueReason: index === 1 ? 'critical' : 'routine',
    reasonDetail: { kind: index === 1 ? 'critical' : 'routine' },
    client: { code: 'CLI-12345678', displayName: 'Organización' },
    speakerCode: 'VOC-12345678',
    scenario: { title: `Escenario ${index}` },
    session: {
      startedAt: '2026-10-27T13:55:00Z',
      finishedAt: finishedAt ?? `2026-10-${String(Math.min(index, 28)).padStart(2, '0')}T14:00:00Z`,
      durationSeconds: 250,
    },
    report: {
      reportId: `10000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
      generatedAt: '2026-10-27T14:05:00Z',
      overallScore: index === 1 ? 48 : 75,
    },
    criticalAreas: index === 1
      ? [{ areaKey: 'empathy', label: 'Empatía', value: 42 }]
      : [],
    lease: { state: status === 'pending' ? 'available' : 'not_claimable', ownerCode: null, expiresAt: null },
    latestReview: status === 'reviewed' ? {
      reviewId: `20000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
      reviewNo: 1,
      reviewerCode: 'EXP-12345678',
      submittedAt: finishedAt ?? `2026-11-${String(Math.min(index, 28)).padStart(2, '0')}T10:00:00Z`,
    } : null,
  };
}

test('pending cases are newest first and capped at ten cards', () => {
  const items = Array.from({ length: 12 }, (_, index) => labelingCase(index + 1));
  const prepared = prepareLabelingCases({ items, total: 12, limit: 10 }, 'pending');
  assert.equal(prepared.length, 10);
  assert.equal(prepared[0].caseNumber, '8812');
  assert.equal(prepared.at(-1).caseNumber, '8803');
});
test('reviewed cases use latest review time and exclude cases from another state', () => {
  const older = labelingCase(1, 'reviewed', '2026-10-10T10:00:00Z');
  const newer = labelingCase(2, 'reviewed', '2026-10-20T10:00:00Z');
  const pending = labelingCase(3, 'pending', '2026-10-30T10:00:00Z');
  const prepared = prepareLabelingCases({ items: [older, pending, newer], total: 2, limit: 10 }, 'reviewed');
  assert.deepEqual(prepared.map(item => item.caseId), [newer.caseId, older.caseId]);
});
test('empty lists remain empty and selection is preserved only while the case exists', () => {
  assert.deepEqual(prepareLabelingCases({ items: [], total: 0, limit: 10 }, 'pending'), []);
  const first = labelingCase(1);
  const second = labelingCase(2, 'reviewed');
  assert.equal(preserveLabelingSelection(second.caseId, [first], [second]), second.caseId);
  assert.equal(preserveLabelingSelection('missing', [first], [second]), first.caseId);
  assert.equal(preserveLabelingSelection('missing', [], []), null);
});

test('card formatting exposes local date, duration, score alerts and critical areas', () => {
  const item = labelingCase(1, 'pending', '2026-10-27T14:04:10Z');
  assert.equal(formatDuration(250), '04:10');
  assert.equal(formatDuration(null), '--:--');
  assert.match(formatCaseDateTime(item.session.finishedAt, 'es-CL', 'UTC'), /27.*10.*26/);
  assert.deepEqual(labelingAlerts(item), ['Puntaje general crítico: 48 pts', 'Empatía: 42 pts']);
});
