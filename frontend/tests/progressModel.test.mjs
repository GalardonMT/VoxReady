import assert from 'node:assert/strict';
import { areaLabel, calendarRange, isSchedulableDate, localDateKey } from '../src/services/progressModel.ts';

assert.equal(areaLabel('expression'), 'Expresión');
assert.equal(areaLabel('voice_tone'), 'Tono de voz');
assert.equal(areaLabel('critical_thinking'), 'Critical thinking');
assert.deepEqual(calendarRange(2026, 9), { fromDate: '2026-09-30', toDate: '2026-11-02' });
assert.equal(localDateKey(new Date(2026, 9, 1, 23, 30)), '2026-10-01');
assert.equal(isSchedulableDate('2026-10-13', new Date(2026, 9, 13)), true);
assert.equal(isSchedulableDate('2026-10-12', new Date(2026, 9, 13)), false);

console.log('progressModel tests passed');
