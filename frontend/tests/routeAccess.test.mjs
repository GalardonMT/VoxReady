import { test } from 'node:test';
import assert from 'node:assert/strict';
import { protectedRouteDestination, roleHome } from '../src/services/routeAccess.ts';

test('direct protected routes send unauthenticated visitors to login', () => {
  for (const route of ['/spokesperson', '/admin', '/master']) {
    assert.equal(protectedRouteDestination(null, route), '/login');
  }
});

test('each role can open its own route and is redirected from other direct routes', () => {
  for (const role of ['spokesperson', 'client_admin', 'master_config']) {
    const home = roleHome(role);
    for (const route of ['/spokesperson', '/admin', '/master']) {
      assert.equal(protectedRouteDestination(role, route), route === home ? null : home);
    }
  }
});
