import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { es } from '../src/locales/es.ts';

const require = createRequire(import.meta.url);
const source = fs.readFileSync(new URL('../src/components/master/ClientSpokespersonsView.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
}).outputText;

const client = { id: 'client-1', name: 'Empresa Uno', status: 'suspended' };
const person = { id: 'person-1', displayName: 'Ana Torres', email: 'ana@example.test' };

function view({ people = [], selectedId = null, loading = false, error = '', progress = null, detailLoading = false, detailError = '' } = {}) {
  const states = [people, selectedId, loading, error, progress, detailLoading, detailError];
  const mockReact = {
    ...React,
    useState: () => [states.shift(), () => {}],
    useCallback: callback => callback,
    useEffect: () => {},
    useRef: () => ({ current: 0 }),
  };
  const module = { exports: {} };
  const imports = {
    react: mockReact,
    '../../context/I18nContext': { useI18n: () => ({ t: es }) },
    '../../services/clientService': { clientService: {} },
    '../spokesperson/ProgressView': { ProgressSummary: () => React.createElement('div', null, 'Gráfico de progreso') },
  };
  vm.runInNewContext(`(function(require,module,exports){${compiled}\n})`, {})(
    name => imports[name] ?? require(name), module, module.exports,
  );
  return renderToStaticMarkup(React.createElement(module.exports.ClientSpokespersonsView, { client, onBack() {} }));
}

test('client context, linked people and read-only selection are visible without editing controls', () => {
  const html = view({ people: [person] });
  assert.match(html, /Empresa Uno/);
  assert.match(html, /Ana Torres/);
  assert.match(html, /ana@example.test/);
  assert.match(html, /Ver voceros/);
  assert.doesNotMatch(html, /<form|type="checkbox"|Guardar vínculos|Elegir escenario/);
});

test('loading, errors and an empty client are distinct', () => {
  assert.match(view({ loading: true }), /role="status"[^>]*>Cargando voceros/);
  const failed = view({ error: 'Sin conexión' });
  assert.match(failed, /role="alert"/);
  assert.match(failed, /Reintentar/);
  assert.doesNotMatch(failed, /no tiene voceros asociados/);
  assert.match(view(), /no tiene voceros asociados/);
});

test('zero sessions remain a real zero; a failed detail does not show a count', () => {
  const zero = view({
    people: [person], selectedId: person.id,
    progress: { sessionsCount: 0, trendSessions: [], areas: [], recentSessions: [], lastN: 5 },
  });
  assert.match(zero, /Sesiones completadas/);
  assert.match(zero, /class="v">0</);
  assert.match(zero, /Gráfico de progreso/);
  assert.doesNotMatch(zero, /<form|type="checkbox"|Guardar vínculos/);
  const failed = view({ people: [person], selectedId: person.id, detailError: 'Sin conexión' });
  assert.match(failed, /role="alert"/);
  assert.doesNotMatch(failed, /class="v">0</);
});
