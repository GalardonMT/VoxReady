import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeClient, validateClient } from '../src/services/clientRules.ts';

test('client name is trimmed and active remains the default valid status', () => {
  assert.equal(validateClient('  Empresa Uno  ', 'active'), null);
  assert.deepEqual(normalizeClient('  Empresa Uno  ', 'active'), {
    name: 'Empresa Uno',
    status: 'active',
  });
});

test('empty and oversized client names are rejected', () => {
  assert.equal(validateClient('   ', 'active'), 'Ingresa el nombre de la empresa.');
  assert.equal(validateClient('x'.repeat(151), 'active'), 'El nombre no puede superar los 150 caracteres.');
});

test('unknown client statuses are rejected', () => {
  assert.equal(validateClient('Empresa', 'archived'), 'Selecciona un estado válido.');
});
