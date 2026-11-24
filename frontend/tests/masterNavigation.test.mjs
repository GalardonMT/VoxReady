import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { es } from '../src/locales/es.ts';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/components/master/MasterNavigation.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;
const compiledModule = { exports: {} };
const imports = {
  '../../context/I18nContext': { useI18n: () => ({ t: es }) },
  './MasterNavigation.module.css': {},
};
vm.runInNewContext(`(function(require,module,exports){${compiled}\n})`, {})(
  name => imports[name] ?? require(name), compiledModule, compiledModule.exports,
);
const view = props => renderToStaticMarkup(React.createElement(compiledModule.exports.MasterNavigation, {
  activeScreen: 'm1', labelingEnabled: true, onNavigate() {}, ...props,
}));

test('disabled labeling removes the queue entry while preserving the other evaluation screens', () => {
  assert.match(view(), /Cola de Etiquetado/);
  const disabled = view({ labelingEnabled: false });
  assert.doesNotMatch(disabled, /Cola de Etiquetado|Revisa casos pendientes/);
  assert.match(disabled, /Editor de Rúbrica/);
  assert.match(disabled, /Editor de métricas/);
});

test('nested active screens identify both their group and their current destination', () => {
  for (const [activeScreen, group, label] of [
    ['m7', 'evaluation', 'Editor de métricas'],
    ['m5', 'content', 'Editor de temas y escenarios'],
  ]) {
    const html = view({ activeScreen });
    assert.match(html, new RegExp(`data-trigger="${group}" data-active="true"`));
    assert.match(html, new RegExp(`aria-current="page"[^>]*>[\\s\\S]*?${label}`));
    assert.equal((html.match(/aria-current="page"/g) || []).length, 1);
  }
});

test('closed disclosures expose named native buttons and hide their options initially', () => {
  const html = view();
  assert.equal((html.match(/aria-expanded="false"/g) || []).length, 2);
  assert.equal((html.match(/hidden=""/g) || []).length, 2);
  assert.match(html, /aria-controls=/);
  assert.match(html, /aria-labelledby=/);
  assert.match(html, /Define criterios de evaluación/);
  assert.match(html, /Gestiona contenidos de aprendizaje/);
});
