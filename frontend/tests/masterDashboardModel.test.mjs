import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dashboardBars, dashboardNumber } from '../src/services/masterDashboardModel.ts';

test('histogram heights follow counts and preserve all modal ties', () => {
  const bars = dashboardBars({ bins: [{ label: 'a', count: 2 }, { label: 'b', count: 4 }, { label: 'c', count: 4 }] });
  assert.deepEqual(bars.map(bar => bar.height), [48, 96, 96]);
  assert.deepEqual(bars.map(bar => bar.modal), [false, true, true]);
});

test('empty histogram has zero height and no invented modal range', () => {
  const bars = dashboardBars({ bins: [{ count: 0 }, { count: 0 }] });
  assert.ok(bars.every(bar => bar.height === 0 && !bar.modal));
});

test('absence and zero are distinct; values respect the selected language', () => {
  assert.equal(dashboardNumber(null, 'es'), '—');
  assert.equal(dashboardNumber(undefined, 'en'), '—');
  assert.equal(dashboardNumber(0, 'pt'), '0');
  assert.equal(dashboardNumber(72.4, 'es'), '72,4');
  assert.equal(dashboardNumber(72.4, 'en'), '72.4');
  assert.equal(dashboardNumber(50, 'en', true), '+50');
  assert.equal(dashboardNumber(-100, 'en', true), '-100');
});
