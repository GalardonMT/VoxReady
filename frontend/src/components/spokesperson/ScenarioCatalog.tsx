'use client';

import React, { useState, useEffect } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';
import { INITIAL_SCENARIOS } from '../../mock/mockData';
import { topicService } from '../../services/topicService';
import { Scenario } from '../../types/api';

interface ScenarioCatalogProps {
  onNavigate: (screen: VoceroScreen) => void;
}

export const ScenarioCatalog: React.FC<ScenarioCatalogProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.u2;

  const [activeFilter, setActiveFilter] = useState('Todos');
  const [searchQuery, setSearchQuery] = useState('');
  const [scenarios, setScenarios] = useState<Scenario[]>(INITIAL_SCENARIOS);

  useEffect(() => {
    async function loadAdminTopics() {
      const topics = await topicService.getTopics();
      const adminScenarios: Scenario[] = topics.map(t => {
        let category: 'Sanitaria' | 'Reputacional' | 'Operativa' = 'Operativa';
        if (t.optics === 'Empática') category = 'Sanitaria';
        if (t.optics === 'Formal') category = 'Reputacional';
        if (t.optics === 'Técnica') category = 'Operativa';

        return {
          id: t.id,
          name: t.name,
          category,
          context: t.context,
          audience: t.audience,
          difficulty: 'Intermedio',
          estimatedMinutes: 5,
          questionsCount: 5,
          languages: t.languages,
          imageUrl: ''
        };
      });

      // Avoid exact duplicates by ID just in case
      const newScenarios = adminScenarios.filter(
        as => !INITIAL_SCENARIOS.some(is => is.id === as.id)
      );

      setScenarios([...INITIAL_SCENARIOS, ...newScenarios]);
    }

    loadAdminTopics();
  }, []);

  const filteredScenarios = scenarios.filter((s) => {
    const matchesCategory =
      activeFilter === 'Todos' ||
      s.category.toLowerCase() === activeFilter.toLowerCase();
    const matchesSearch =
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.context.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  return (
    <div className="canvas-content">
      {/* Filters and search bar */}
      <div
        style={{
          display: 'flex',
          gap: '10px',
          marginBottom: '20px',
          alignItems: 'center',
          flexWrap: 'wrap'
        }}
      >
        <div style={{ display: 'flex', gap: '8px' }}>
          {d.filters.map((f) => (
            <span
              key={f}
              className={`pill ${activeFilter === f ? 'on' : ''}`}
              onClick={() => setActiveFilter(f)}
            >
              {f}
            </span>
          ))}
        </div>

        <div style={{ marginLeft: 'auto', width: '240px' }}>
          <input
            type="text"
            className="field"
            placeholder={d.search}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Scenarios Grid */}
      <div className="grid3">
        {filteredScenarios.map((scen) => (
          <div key={scen.id} className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div
              className="ph"
              style={{
                height: '95px',
                marginBottom: '12px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, var(--ph1) 0%, var(--ph2) 100%)',
                fontSize: '28px'
              }}
            >
              {scen.category === 'Sanitaria' ? '🏥' : scen.category === 'Operativa' ? '⚙️' : '📢'}
            </div>

            <h4 style={{ fontSize: '15px', fontWeight: 600, margin: '0 0 6px', color: 'var(--ink)' }}>
              {scen.name}
            </h4>

            <p
              style={{
                fontSize: '12px',
                color: 'var(--muted)',
                marginBottom: '14px',
                flex: 1,
                lineHeight: 1.45
              }}
            >
              {scen.context}
            </p>

            <div className="meta" style={{ marginBottom: '14px' }}>
              <span className="tagm">⏱️ ≈ {scen.estimatedMinutes} min</span>
              <span className="tagm">❓ {scen.questionsCount} preguntas</span>
              <span className="tagm">🏷️ {scen.difficulty}</span>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingTop: '8px',
                borderTop: '1px solid var(--line)'
              }}
            >
              <span className="pill on" style={{ fontSize: '11px', padding: '2px 10px' }}>
                {scen.audience}
              </span>
              <button
                type="button"
                className="btn pri"
                onClick={() => onNavigate('u3')}
              >
                {d.start} →
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
