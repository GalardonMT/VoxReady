'use client';

import React, { useState, useEffect } from 'react';
import { useI18n } from '../../context/I18nContext';
import { topicService } from '../../services/topicService';
import { clientAdminService } from '../../services/clientAdminService';
import { TopicConfig } from '../../types/api';

export const ClientDashboard: React.FC = () => {
  const { t } = useI18n();
  const d = t.L.a1;

  const [topics, setTopics] = useState<TopicConfig[]>([]);
  const [spokespersonCount, setSpokespersonCount] = useState<number | null>(null);
  const [completedSessions, setCompletedSessions] = useState<number | null>(null);
  const [participationRate, setParticipationRate] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    async function loadTopics() {
      setIsLoading(true);
      try {
        const data = await topicService.getTopics();
        if (isMounted) {
          setTopics(data);
        }
      } catch {
        // Manejado por topicService
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }
    async function loadSpokespersonCount() {
      try {
        const items = await clientAdminService.spokespersons();
        if (isMounted) setSpokespersonCount(items.length);
      } catch {
        if (isMounted) setSpokespersonCount(null);
      }
    }
    async function loadUsageSummary() {
      try {
        const result = await clientAdminService.usage({ days: 30 });
        if (isMounted) {
          setCompletedSessions(result.summary.completedSessions);
          setParticipationRate(result.summary.participationRate);
        }
      } catch {
        if (isMounted) {
          setCompletedSessions(null);
          setParticipationRate(null);
        }
      }
    }
    loadTopics();
    loadSpokespersonCount();
    loadUsageSummary();
    return () => {
      isMounted = false;
    };
  }, []);

  const statValues: Array<number | string> = [
    topics.length,
    spokespersonCount ?? '—',
    completedSessions ?? '—',
    participationRate === null ? '—' : `${participationRate}%`,
  ];

  return (
    <div className="canvas-content">
      {/* KPI Stats */}
      <div className="grid4" style={{ marginBottom: '20px' }}>
        {d.st.map((k, i) => (
          <div key={i} className="stat">
            <div className="k">{k}</div>
            <div className="v">{statValues[i]}</div>
          </div>
        ))}
      </div>

      {/* Assigned topics are managed by the Master role and are read-only here. */}
      <div
        className="card"
        style={{
          marginBottom: '10px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '14px 18px'
        }}
      >
        <div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--ink)' }}>
            📋 {d.themesL} ({topics.length})
          </div>
          <div style={{ fontSize: '12.5px', color: 'var(--muted)', marginTop: '2px' }}>
            Temas y escenarios asignados por el configurador Maestro a tu organización
          </div>
        </div>
      </div>

      {/* Themes Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {isLoading ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--muted)' }}>
            Cargando temas configurados...
          </div>
        ) : topics.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center' }}>
            <p style={{ color: 'var(--muted)', fontSize: '14px' }}>
              El configurador Maestro todavía no ha asignado temas a tu organización.
            </p>
          </div>
        ) : (
          <table className="wf">
            <thead>
              <tr>
                <th>{d.th[0] || 'Tema'}</th>
                <th>{d.th[1] || 'Público interno'}</th>
                <th>Óptica</th>
                <th>{d.th[2] || 'Idiomas'}</th>
              </tr>
            </thead>
            <tbody>
              {topics.map((topic) => (
                <tr key={topic.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--ink)' }}>{topic.name}</div>
                    {topic.context && (
                      <div
                        style={{
                          fontSize: '11.5px',
                          color: 'var(--muted)',
                          maxWidth: '280px',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          marginTop: '2px'
                        }}
                      >
                        {topic.context}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className="pill on" style={{ fontSize: '11px', padding: '2px 8px' }}>
                      {topic.audience || 'Dirección'}
                    </span>
                  </td>
                  <td>
                    <span
                      style={{
                        fontSize: '11.5px',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        background: 'var(--soft)',
                        fontWeight: 500
                      }}
                    >
                      {topic.optics || 'Empática'}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      {(topic.languages || ['ES']).map((lang) => (
                        <span key={lang} className="tagm" style={{ padding: '1px 6px', fontSize: '10.5px' }}>
                          {lang}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
