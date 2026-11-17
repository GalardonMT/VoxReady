import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';


const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const source = (path) => readFileSync(`${frontendRoot}/${path}`, 'utf8');

test('client admin navigation contains only dashboard, spokespersons, scenarios and activity', () => {
  const adminPage = source('src/app/(admin)/admin/page.tsx');
  const clientHeader = source('src/components/client-admin/ClientAdminHeader.tsx');

  assert.match(clientHeader, /Panel del Cliente/);
  assert.match(clientHeader, /Escenarios disponibles/);
  assert.match(clientHeader, /Voceros/);
  assert.match(clientHeader, /Actividad y uso/);
  assert.doesNotMatch(clientHeader, /Política de Retención|id: 'a3'/);
  assert.doesNotMatch(adminPage, /RetentionPolicyView|adminScreen === 'a3'/);
  assert.doesNotMatch(adminPage, /Editor de Tema|TopicEditorView/);
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
  assert.match(dashboard, /clientScenarioService\.list/);
  assert.match(dashboard, /clientAdminService\.usage/);
});

test('obsolete client scenario, topic and retention fixtures are removed', () => {
  const mockData = source('src/mock/mockData.ts');

  assert.doesNotMatch(
    mockData,
    /INITIAL_SCENARIOS|INITIAL_TOPICS|INITIAL_RETENTION_SETTINGS/,
  );
});
