import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { dashboardBars, dashboardNumber } from '../src/services/masterDashboardModel.ts';
import { es } from '../src/locales/es.ts';
import { en } from '../src/locales/en.ts';
import { pt } from '../src/locales/pt.ts';

// Render the real TSX with controlled hook states, without a browser, API or DB.
const require = createRequire(import.meta.url);
const source = fs.readFileSync(new URL('../src/components/master/MasterDashboard.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
}).outputText;

function view({ data = null, loading = false, error = false, lang = 'es', labelingEnabled = true } = {}) {
  const states = [data, loading, error, 0];
  const mockReact = { ...React, useState: () => [states.shift(), () => {}], useEffect: () => {} };
  const compiledModule = { exports: {} };
  const imports = {
    react: mockReact,
    '../../context/I18nContext': { useI18n: () => ({ t: { es, en, pt }[lang], lang }) },
    '../../services/masterDashboardService': { masterDashboardService: {} },
    '../../services/masterDashboardModel': { dashboardBars, dashboardNumber },
  };
  vm.runInNewContext(`(function(require,module,exports){${compiled}\n})`, {})(
    name => imports[name] ?? require(name), compiledModule, compiledModule.exports,
  );
  return renderToStaticMarkup(React.createElement(compiledModule.exports.MasterDashboard, { onNavigate() {}, labelingEnabled }));
}

const empty = {
  activeClients: 0, pendingReviewCount: 0, publishedVersion: null,
  sessionsWeek: { count: 0, previousCount: 0, changePercent: null, changeStatus: 'no_previous_sessions' },
  scoreDistribution: { sampleCount: 0, bins: [{ label: '<50', count: 0 }], mean: null, standardDeviation: null, modalRanges: [] },
  quality: { status: 'definition_required', agreementPercent: null, kappa: null },
};

test('loading and connection errors never appear as valid zero counts or mock data', () => {
  const loading = view({ loading: true });
  assert.match(loading, /aria-busy="true"/);
  assert.match(loading, /role="status"/);
  assert.doesNotMatch(loading, /class="v"[^>]*>0</);
  const error = view({ error: true });
  assert.match(error, /role="alert"/);
  assert.match(error, /Reintentar/);
  assert.doesNotMatch(error, /Sin versión de métricas publicada/);
  assert.doesNotMatch(error, /class="v"[^>]*>0</);
  assert.doesNotMatch(error, /640|88%|1,420|Whisper|kappa &gt;/);
});

test('empty results show real zero counts and explicit absence of statistics/publication', () => {
  const html = view({ data: empty });
  assert.match(html, /class="v"[^>]*>0</);
  assert.match(html, /No hay puntajes disponibles/);
  assert.match(html, /Sin versión de métricas publicada/);
  assert.match(html, /variación no calculable/);
  assert.match(html, /Acuerdo y kappa pendientes de definición/);
  assert.match(html, /<b>— pts<\/b>/);
});

test('real result fields and proportional histogram render in every supported language', () => {
  const data = {
    ...empty, activeClients: 12, pendingReviewCount: 27,
    publishedVersion: { versionLabel: 'M-real' },
    sessionsWeek: { count: 15, previousCount: 10, changePercent: 50, changeStatus: 'available' },
    scoreDistribution: { sampleCount: 3, bins: [{ label: '50–60', count: 1 }, { label: '90–100', count: 2 }], mean: 75.5, standardDeviation: 9, modalRanges: ['90–100'] },
  };
  for (const lang of ['es', 'en', 'pt']) {
    const html = view({ data, lang });
    assert.match(html, /M-real/);
    assert.match(html, /\+50%/);
    assert.match(html, /height="48"/);
    assert.match(html, /height="96"/);
    assert.ok(html.includes({ es, en, pt }[lang].L.m1.qualityPending));
    assert.ok(html.includes(dashboardNumber(75.5, lang)));
  }
  assert.doesNotMatch(view({ data, labelingEnabled: false }), /Revisar cola/);
});
