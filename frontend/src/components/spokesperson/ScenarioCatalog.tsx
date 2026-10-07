'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { useAuth } from '../../context/AuthContext';
import { sessionFlowService, type CatalogScenario, type SessionSetup } from '../../services/sessionFlowService';
import type { VoceroScreen } from './HomePracticeView';
import { masterTopicLabels } from '../../services/masterTopicService';

const categories = [
  { value: '', label: 'Todos' },
  { value: 'health', label: 'Sanitaria' },
  { value: 'reputational', label: 'Reputacional' },
  { value: 'operational', label: 'Operativa' }
];

interface Props {
  onSelected: (setup: SessionSetup) => void;
  onNavigate?: (screen: VoceroScreen, extra?: string) => void;
}

export const ScenarioCatalog: React.FC<Props> = ({ onSelected }) => {
  const { t } = useI18n();
  const { user } = useAuth();
  const [category, setCategory] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<CatalogScenario[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const pendingKey = useRef<{ scenarioId: string; key: string } | null>(null);

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      sessionFlowService.listScenarios({ category, q: search.trim(), page, pageSize: 9 })
        .then((data) => {
          if (!active) return;
          setItems(data.items);
          setTotal(data.total);
        })
        .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'No se pudo cargar el catálogo.'); })
        .finally(() => { if (active) setLoading(false); });
    }, search ? 250 : 0);
    return () => { active = false; clearTimeout(timer); };
  }, [category, search, page, user?.clientId, user?.userId]);

  const selectScenario = async (scenario: CatalogScenario) => {
    if (!user || pendingId) return;
    setPendingId(scenario.id);
    setError('');
    if (pendingKey.current?.scenarioId !== scenario.id) {
      pendingKey.current = { scenarioId: scenario.id, key: crypto.randomUUID() };
    }
    try {
      await sessionFlowService.getScenario(scenario.id);
      const created = await sessionFlowService.createSession(scenario.id, pendingKey.current.key, user.preferredLanguage);
      const setup = await sessionFlowService.getSession(created.sessionId);
      if (!setup.questions.length) throw new Error('La sesión no tiene preguntas disponibles.');
      pendingKey.current = null;
      onSelected(setup);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo crear la sesión.');
    } finally {
      setPendingId(null);
    }
  };

  return <div className="canvas-content">
    <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {categories.map((item) => <button type="button" key={item.value}
          className={`pill ${category === item.value ? 'on' : ''}`}
          onClick={() => { setLoading(true); setError(''); setCategory(item.value); setPage(1); }}>{item.label}</button>)}
      </div>
      <input type="search" className="field" style={{ marginLeft: 'auto', width: 240 }}
        placeholder={t.L.u2.search} value={search}
        onChange={(event) => { setLoading(true); setError(''); setSearch(event.target.value); setPage(1); }} />
    </div>
    {error && <p role="alert" style={{ color: 'var(--danger)' }}>{error}</p>}
    {loading ? <p>Cargando escenarios…</p> : items.length === 0 ? <p>No hay escenarios disponibles.</p> :
      <div className="grid3">{items.map((scenario) => <div className="card" key={scenario.id} style={{ display: 'flex', flexDirection: 'column' }}>
        <h4>{scenario.title}</h4>
        <p style={{ flex: 1 }}>{scenario.context}</p>
        <div className="meta" style={{ marginBottom: 14 }}>
          <span className="tagm">{categories.find((item) => item.value === scenario.category)?.label}</span>
          <span className="tagm">≈ {scenario.estimatedMinutes} min</span>
          <span className="tagm">{scenario.questionCount} preguntas</span>
          <span className="tagm">{masterTopicLabels.difficulty[scenario.difficulty]}</span>
          <span className="tagm">{masterTopicLabels.audience[scenario.audience as keyof typeof masterTopicLabels.audience] || scenario.audience}</span>
        </div>
        <button type="button" className="btn pri" disabled={pendingId !== null}
          onClick={() => void selectScenario(scenario)}>
          {pendingId === scenario.id ? 'Creando sesión…' : t.L.u2.start}
        </button>
      </div>)}</div>}
    {total > 9 && <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 20 }}>
      <button type="button" className="btn" disabled={page <= 1 || loading} onClick={() => { setLoading(true); setPage(page - 1); }}>Anterior</button>
      <span>Página {page} de {Math.ceil(total / 9)}</span>
      <button type="button" className="btn" disabled={page * 9 >= total || loading} onClick={() => { setLoading(true); setPage(page + 1); }}>Siguiente</button>
    </div>}
  </div>;
};
