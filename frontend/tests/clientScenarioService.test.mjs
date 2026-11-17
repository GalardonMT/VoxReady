import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  clientScenarioLabels,
} from '../src/services/clientScenarioModel.ts';
import {
  createClientScenarioService,
} from '../src/services/clientScenarioServiceCore.ts';

test('client scenario service exposes read-only operations only', () => {
  const clientScenarioService = createClientScenarioService(async () => ({}));
  assert.deepEqual(Object.keys(clientScenarioService).sort(), ['get', 'list']);
});

test('list requests the tenant-scoped endpoint with explicit pagination', async () => {
  const expected = {
    items: [{
      id: '33333333-3333-4333-8333-333333333333',
      title: 'Interrupción de servicio',
      category: 'operational',
      difficulty: 'intermediate',
      estimatedMinutes: 12,
      questionCount: 2,
      audience: 'technical',
      optics: 'formal',
    }],
    page: 2,
    pageSize: 25,
    total: 26,
  };
  let request;
  const clientScenarioService = createClientScenarioService(async (endpoint, options) => {
    request = { endpoint, options };
    return expected;
  });

  const result = await clientScenarioService.list({ page: 2, pageSize: 25 });

  assert.deepEqual(result, expected);
  assert.equal(
    request.endpoint,
    '/api/client/scenarios?page=2&pageSize=25',
  );
  assert.deepEqual(request.options, { cache: 'no-store' });
});

test('get encodes the scenario identifier and preserves the public detail contract', async () => {
  const expected = {
    id: 'scenario/id with spaces',
    title: 'Interrupción de servicio',
    category: 'operational',
    difficulty: 'intermediate',
    estimatedMinutes: 12,
    questionCount: 1,
    audience: 'technical',
    optics: 'formal',
    context: 'Una interrupción afecta los canales de atención.',
    keyMessages: ['Reconocemos el impacto.'],
    redLines: ['No especular sobre la causa.'],
    questions: [{ sequenceNo: 1, text: '¿Qué ocurrió?' }],
  };
  let request;
  const clientScenarioService = createClientScenarioService(async (endpoint, options) => {
    request = { endpoint, options };
    return expected;
  });

  const result = await clientScenarioService.get(expected.id);

  assert.deepEqual(result, expected);
  assert.equal(
    request.endpoint,
    '/api/client/scenarios/scenario%2Fid%20with%20spaces',
  );
  assert.deepEqual(request.options, { cache: 'no-store' });
  assert.deepEqual(Object.keys(result.questions[0]), ['sequenceNo', 'text']);
});

test('labels translate every backend code used by the read-only view', () => {
  assert.deepEqual(clientScenarioLabels, {
    category: {
      health: 'Sanitaria',
      operational: 'Operativa',
      reputational: 'Reputacional',
    },
    difficulty: {
      basic: 'Fácil',
      intermediate: 'Intermedio',
      hard: 'Difícil',
    },
    audience: {
      leadership: 'Dirección',
      frontline: 'Planta',
      technical: 'Técnicos',
    },
    optics: {
      empathetic: 'Empática',
      formal: 'Formal',
      technical: 'Técnica',
    },
  });
});
