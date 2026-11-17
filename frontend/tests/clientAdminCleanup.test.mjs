import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';


const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const source = (path) => readFileSync(`${frontendRoot}/${path}`, 'utf8');

test('client admin navigation keeps only dashboard, scenarios and retention', () => {
  const adminPage = source('src/app/(admin)/admin/page.tsx');

  assert.match(adminPage, /Panel del Cliente/);
  assert.match(adminPage, /Escenarios disponibles/);
  assert.match(adminPage, /Política de Retención/);
  assert.doesNotMatch(adminPage, /Editor de Tema|TopicEditorView|adminScreen === 'a2'/);
});

test('legacy client topic editor and mutation service are removed', () => {
  assert.equal(
    existsSync(`${frontendRoot}/src/components/client-admin/TopicEditorView.tsx`),
    false,
  );
  assert.equal(existsSync(`${frontendRoot}/src/services/topicService.ts`), false);
  assert.doesNotMatch(source('src/services/index.ts'), /topicService/);
});

test('client dashboard contains no simulated KPIs or editable topic table', () => {
  const dashboard = source('src/components/client-admin/ClientDashboard.tsx');

  assert.doesNotMatch(dashboard, /\b38\b|\b152\b|\b71\b/);
  assert.doesNotMatch(dashboard, /deleteTopic|getTopics|Nuevo tema|Editar tema/);
  assert.match(dashboard, /onNavigate\('a4'\)/);
  assert.match(dashboard, /onNavigate\('a3'\)/);
});

test('obsolete client scenario, topic and retention fixtures are removed', () => {
  const mockData = source('src/mock/mockData.ts');

  assert.doesNotMatch(
    mockData,
    /INITIAL_SCENARIOS|INITIAL_TOPICS|INITIAL_RETENTION_SETTINGS/,
  );
});
