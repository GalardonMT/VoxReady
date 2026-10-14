import { test } from 'node:test';
import assert from 'node:assert/strict';
import { practiceScenario, shouldShowVideo, withClient } from '../src/services/microlessonRules.ts';

const form = {
  clientId: 'client-a', scenarioId: 'scenario-a', title: 'Leccion', topicTag: null,
  durationMinutes: null, learningObjective: 'Objetivo', theoryContent: 'Teoria',
  exampleContent: null, status: 'active',
};

test('changing the client always clears the selected scenario', () => {
  assert.deepEqual(withClient(form, 'client-b'), { ...form, clientId: 'client-b', scenarioId: '' });
  assert.equal(form.scenarioId, 'scenario-a');
});

test('a lesson without video omits the player decision', () => {
  assert.equal(shouldShowVideo({ hasVideo: false }), false);
  assert.equal(shouldShowVideo({ hasVideo: true }), true);
});

test('practice uses the exact related scenario id', () => {
  assert.equal(practiceScenario({ scenarioId: 'scenario-expected' }), 'scenario-expected');
});
