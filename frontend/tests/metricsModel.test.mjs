import { test } from 'node:test';
import assert from 'node:assert/strict';
import { changedThresholds, validateMetricThresholds, updateThreshold } from '../src/services/metricsModel.ts';

const metric = {
  key: 'voice.wpm', category: 'voice', label: 'Ritmo', description: '', unit: 'WPM',
  min: 50, max: 220, step: 1, control: 'range',
  thresholdKeys: ['warningLow', 'optimalLow', 'optimalHigh', 'warningHigh'],
  thresholds: { warningLow: 100, optimalLow: 120, optimalHigh: 150, warningHigh: 170 },
};

test('threshold validation accepts ordered boundaries and rejects overlap and out-of-range values', () => {
  assert.deepEqual(validateMetricThresholds(metric), []);
  assert.ok(validateMetricThresholds({ ...metric, thresholds: { ...metric.thresholds, optimalLow: 99 } }).length > 0);
  assert.ok(validateMetricThresholds({ ...metric, thresholds: { ...metric.thresholds, warningHigh: 221 } }).length > 0);
  assert.ok(validateMetricThresholds({ ...metric, thresholds: { ...metric.thresholds, warningHigh: NaN } }).length > 0);
});

test('updating a boundary preserves other boundaries and reports differences', () => {
  const updated = updateThreshold(metric, 'optimalLow', 125);
  assert.equal(updated.thresholds.optimalLow, 125);
  assert.equal(metric.thresholds.optimalLow, 120);
  assert.deepEqual(changedThresholds([metric], [updated]), [
    { key: 'voice.wpm', label: 'Ritmo', field: 'optimalLow', before: 120, after: 125, unit: 'WPM' },
  ]);
});

test('a scalar configuration must stay within its fixed scale', () => {
  const rate = { ...metric, key: 'gov.random_sample', control: 'number', min: 0, max: 30,
    thresholdKeys: ['rate'],
    thresholds: { rate: 10 } };
  assert.deepEqual(validateMetricThresholds(rate), []);
  assert.ok(validateMetricThresholds({ ...rate, thresholds: { rate: 31 } }).length > 0);
  assert.ok(validateMetricThresholds({ ...rate, thresholds: { rate: 10.5 } }).length > 0);
  assert.ok(validateMetricThresholds({ ...rate, thresholds: { rate: 10, extra: 2 } }).length > 0);
});
