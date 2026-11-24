import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import React from 'react';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/app/(spokesperson)/spokesperson/page.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(`${source}\nexport { SpokespersonContent };`, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;

// Exercise the actual page's header callbacks with controlled practice state.
// Media capture and backend calls belong to child views and are not mounted here.
function page(screen = 'u4', pendingNav = null) {
  const values = [screen, '', 'u1', null, 'session', 'scenario', pendingNav, null];
  const changes = new Map();
  let stateIndex = 0;
  const routes = [];
  let logouts = 0;
  const mockReact = { ...React, useState: () => {
    const index = stateIndex++;
    return [values[index], value => changes.set(index, value)];
  } };
  const imports = {
    react: mockReact,
    'next/navigation': { useRouter: () => ({ push: route => routes.push(route) }) },
    '../../../context/AuthContext': { useAuth: () => ({
      user: { userId: 'preview', clientId: 'client', displayName: 'Vocero', initials: 'V' },
      logout: () => { logouts++; },
    }) },
  };
  const components = new Map();
  const compiledModule = { exports: {} };
  vm.runInNewContext(`(function(require,module,exports){${compiled}\n})`, { window: { scrollTo() {} } })(
    name => {
      if (name in imports) return imports[name];
      if (!name.includes('/components/')) return require(name);
      const componentName = name.split('/').at(-1);
      const component = () => null;
      components.set(componentName, component);
      return { [componentName]: component };
    }, compiledModule, compiledModule.exports,
  );
  const tree = compiledModule.exports.SpokespersonContent();
  const children = React.Children.toArray(tree.props.children);
  const header = children.find(child => child.type === components.get('PlatformHeader')).props;
  const modal = children.find(child => child.type === components.get('CancelExerciseModal')).props;
  return { header, modal, changes, routes, logouts: () => logouts };
}

test('active practice intercepts section, home and logout actions from the shared header', () => {
  for (const action of ['section', 'home', 'logout']) {
    const p = page();
    if (action === 'section') p.header.navigation.props.onNavigate('u7');
    if (action === 'home') p.header.onHome();
    if (action === 'logout') p.header.onLogout();
    const expected = action === 'logout' ? { type: 'logout' } : { type: 'screen', screen: action === 'home' ? 'u1' : 'u7', extra: undefined };
    assert.deepEqual({ ...p.changes.get(6) }, expected);
    assert.equal(p.changes.has(0), false);
    assert.equal(p.logouts(), 0);
    assert.deepEqual(p.routes, []);
  }
});

test('continuing a practice only clears the pending navigation', () => {
  const p = page('u4', { type: 'logout' });
  assert.equal(p.modal.isOpen, true);
  p.modal.onContinue();
  assert.equal(p.changes.get(6), null);
  assert.equal(p.changes.has(0), false);
  assert.equal(p.changes.has(7), false);
  assert.equal(p.logouts(), 0);
});

test('confirmed exits discard the selected practice before navigating or logging out', () => {
  const section = page('u4', { type: 'screen', screen: 'u7' });
  section.modal.onConfirmCancel();
  assert.equal(section.changes.get(7), null);
  assert.equal(section.changes.get(0), 'u7');
  const logout = page('u4', { type: 'logout' });
  logout.modal.onConfirmCancel();
  assert.equal(logout.changes.get(7), null);
  assert.equal(logout.logouts(), 1);
  assert.deepEqual(logout.routes, ['/login']);
});

test('outside an active practice the header navigates and logs out directly', () => {
  const p = page('u1');
  p.header.navigation.props.onNavigate('lesson');
  assert.equal(p.changes.get(0), 'lesson');
  assert.equal(p.changes.get(2), 'u1');
  p.header.onLogout();
  assert.equal(p.logouts(), 1);
  assert.deepEqual(p.routes, ['/login']);
  assert.equal(p.changes.has(6), false);
});
