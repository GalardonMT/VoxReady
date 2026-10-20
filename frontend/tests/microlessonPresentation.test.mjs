import { test } from 'node:test';
import assert from 'node:assert/strict';
import { groupMicrolessons, chooseLesson, latestAssignmentIds } from '../src/services/microlessonPresentation.ts';

const lesson = (id, assignmentStatus, canOpen = true) => ({ id, assignmentStatus, canOpen, title: id });

test('catalog groups each active assignment and keeps unassigned lessons locked', () => {
  const groups = groupMicrolessons([
    lesson('new', 'assigned'), lesson('started', 'in_progress'),
    lesson('done', 'completed'), lesson('locked', null, false),
  ], [lesson('revoked', 'revoked', false)]);
  assert.deepEqual(groups.assigned.map(item => item.id), ['new']);
  assert.deepEqual(groups.inProgress.map(item => item.id), ['started']);
  assert.deepEqual(groups.completed.map(item => item.id), ['done']);
  assert.deepEqual(groups.catalog.map(item => item.id), ['locked']);
  assert.deepEqual(groups.archived.map(item => item.id), ['revoked']);
});

test('exact lesson navigation never opens a locked catalog item', () => {
  const items = [lesson('selected', 'assigned'), lesson('locked', null, false)];
  assert.equal(chooseLesson(items, 'selected')?.id, 'selected');
  assert.equal(chooseLesson(items, 'locked'), null);
  assert.equal(chooseLesson(items, 'missing'), null);
});

test('completed history preserves prior cycles without duplicating the latest assignment', () => {
  const latest = { ...lesson('done', 'completed'), assignmentId: 'cycle-2' };
  const prior = { ...lesson('done', 'completed', false), assignmentId: 'cycle-1' };
  const groups = groupMicrolessons([latest], [prior, { ...latest, canOpen: false, completedAt: '2026-10-20' }]);
  assert.deepEqual(groups.completed.map(item => item.assignmentId), ['cycle-2', 'cycle-1']);
  assert.equal(groups.completed[0].completedAt, '2026-10-20');
});

test('archived lesson keeps pending cycle visible only in history', () => {
  const archived = { ...lesson('archived', 'in_progress', false), status: 'archived', assignmentId: 'cycle-3' };
  const groups = groupMicrolessons([], [archived]);
  assert.deepEqual(groups.archived.map(item => item.assignmentId), ['cycle-3']);
  assert.equal(groups.inProgress.length, 0);
});

test('revoked active lesson remains visible as locked company catalog content', () => {
  const revoked = { ...lesson('revoked', 'revoked', false), status: 'active', assignmentId: 'cycle-4' };
  const groups = groupMicrolessons([revoked], [revoked]);
  assert.deepEqual(groups.catalog.map(item => item.id), ['revoked']);
  assert.deepEqual(groups.archived.map(item => item.assignmentId), ['cycle-4']);
});

test('only the newest cycle per vocero can be revoked', () => {
  const assignments = [
    { id: 'new-a', userId: 'a', status: 'completed' },
    { id: 'new-b', userId: 'b', status: 'assigned' },
    { id: 'old-a', userId: 'a', status: 'completed' },
  ];
  const latest = latestAssignmentIds(assignments);
  assert.equal(latest.has('new-a'), true);
  assert.equal(latest.has('new-b'), true);
  assert.equal(latest.has('old-a'), false);
});
