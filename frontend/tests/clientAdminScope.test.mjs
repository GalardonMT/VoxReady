import { readFileSync, existsSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const adminPage = readFileSync(new URL('../src/app/(admin)/admin/page.tsx', import.meta.url), 'utf8');
const dashboard = readFileSync(
  new URL('../src/components/client-admin/ClientDashboard.tsx', import.meta.url),
  'utf8',
);
const activityView = readFileSync(
  new URL('../src/components/client-admin/ActivityUsageView.tsx', import.meta.url),
  'utf8',
);
const spokespersonView = readFileSync(
  new URL('../src/components/client-admin/SpokespersonListView.tsx', import.meta.url),
  'utf8',
);
const clientHeader = readFileSync(
  new URL('../src/components/client-admin/ClientAdminHeader.tsx', import.meta.url),
  'utf8',
);
const spokespersonDetail = readFileSync(
  new URL('../src/components/client-admin/SpokespersonDetailPage.tsx', import.meta.url),
  'utf8',
);
const spokespersonDetailRoute = new URL(
  '../src/app/(admin)/admin/voceros/detalle/page.tsx',
  import.meta.url,
);
const pagination = readFileSync(new URL('../src/components/common/Pagination.tsx', import.meta.url), 'utf8');
const editorUrl = new URL('../src/components/client-admin/TopicEditorView.tsx', import.meta.url);
const retentionViewUrl = new URL('../src/components/client-admin/RetentionPolicyView.tsx', import.meta.url);
const clientAdminService = readFileSync(
  new URL('../src/services/clientAdminService.ts', import.meta.url),
  'utf8',
);
const apiTypes = readFileSync(new URL('../src/types/api.ts', import.meta.url), 'utf8');

test('client admin has no topic editor section', () => {
  assert.equal(existsSync(editorUrl), false);
  assert.doesNotMatch(adminPage, /TopicEditorView|Editor de Tema/);
});

test('client admin has no retention policy section', () => {
  assert.equal(existsSync(retentionViewUrl), false);
  assert.doesNotMatch(adminPage, /RetentionPolicyView|adminScreen === 'a3'/);
  assert.doesNotMatch(clientHeader, /Política de Retención|id: 'a3'/);
  assert.doesNotMatch(clientAdminService, /retentionPolicy|client\/retention-policy/);
  assert.doesNotMatch(apiTypes, /ClientRetentionPolicy/);
});

test('client admin can open the read-only spokesperson list', () => {
  assert.match(adminPage, /SpokespersonListView/);
  assert.match(clientHeader, /label: 'Voceros'/);
  assert.match(dashboard, /clientAdminService\.spokespersons\(\)/);
});

test('client admin can inspect real activity and usage', () => {
  assert.match(adminPage, /ActivityUsageView/);
  assert.match(clientHeader, /label: 'Actividad'/);
  assert.match(dashboard, /clientAdminService\.usage\(\{ days: 30 \}\)/);
  assert.match(activityView, /isLoading \? \(/);
  assert.match(activityView, /Actualizando actividad y uso/);
  assert.match(activityView, /itemLabel="actividades"/);
  assert.match(activityView, /itemLabel="voceros"/);
  assert.match(spokespersonView, /itemLabel="voceros"/);
  assert.match(pagination, /paginationItems\(page, totalPages\)/);
  assert.match(pagination, /aria-current=\{item === page \? 'page'/);
  assert.match(activityView, /Vocero o actividad/);
});

test('client admin can open a protected, read-only spokesperson detail', () => {
  assert.equal(existsSync(spokespersonDetailRoute), true);
  assert.match(spokespersonView, /\/admin\/voceros\/detalle\/\?id=\$\{encodeURIComponent\(person\.id\)\}/);
  assert.match(spokespersonDetail, /allowedRoles=\{\['client_admin'\]\}/);
  assert.match(spokespersonDetail, /Historial de sesiones/);
  assert.match(spokespersonDetail, /Microlecciones/);
  assert.match(spokespersonDetail, /<th>Asignada<\/th><th>Finalizada<\/th>/);
  assert.match(spokespersonDetail, /Alertas de seguimiento/);
  assert.match(spokespersonDetail, /itemLabel="sesiones"/);
  assert.doesNotMatch(spokespersonDetail, /Actividad reciente|recentActivity\(/);
  assert.doesNotMatch(spokespersonDetail, /Política de Retención/);
  assert.doesNotMatch(spokespersonDetail, /grabación.*href|transcripci[oó]n.*href/i);
});

test('assigned topics are read-only for client admin', () => {
  assert.doesNotMatch(dashboard, /saveTopic|deleteTopic|Nuevo tema|Editar tema|Eliminar tema/);
  assert.equal(existsSync(new URL('../src/services/topicService.ts', import.meta.url)), false);
  assert.match(dashboard, /Escenarios activos asignados por el configurador Maestro/);
  assert.match(dashboard, /clientScenarioService\.list/);
});
