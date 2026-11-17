'use client';

import React, { useEffect, useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { clientAdminService } from '../../services/clientAdminService';
import {
  clientScenarioLabels,
  clientScenarioService,
  type ClientScenarioSummary,
} from '../../services/clientScenarioService';

export const ClientDashboard: React.FC = () => {
  const { t } = useI18n();
  const d = t.L.a1;

  const [scenarios, setScenarios] = useState<ClientScenarioSummary[]>([]);
  const [scenarioTotal, setScenarioTotal] = useState<number | null>(null);
  const [spokespersonCount, setSpokespersonCount] = useState<number | null>(null);
  const [completedSessions, setCompletedSessions] = useState<number | null>(null);
  const [participationRate, setParticipationRate] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadScenarios() {
      try {
        const response = await clientScenarioService.list({ page: 1, pageSize: 100 });
        if (isMounted) {
          setScenarios(response.items);
          setScenarioTotal(response.total);
        }
      } catch {
        if (isMounted) {
          setScenarios([]);
          setScenarioTotal(null);
        }
      } finally {
        if (isMounted) setIsLoading(false);
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

    void loadScenarios();
    void loadSpokespersonCount();
    void loadUsageSummary();

    return () => {
      isMounted = false;
    };
  }, []);

  const statValues: Array<number | string> = [
    scenarioTotal ?? '—',
    spokespersonCount ?? '—',
    completedSessions ?? '—',
    participationRate === null ? '—' : `${participationRate}%`,
  ];

  return (
    <div className="canvas-content">
      <div className="grid4" style={{ marginBottom: '20px' }}>
        {d.st.map((label, index) => (
          <div key={label} className="stat">
            <div className="k">{label}</div>
            <div className="v">{statValues[index]}</div>
          </div>
        ))}
      </div>

      <div
        className="card"
        style={{
          marginBottom: '10px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '14px 18px',
        }}
      >
        <div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--ink)' }}>
            📋 Escenarios asignados ({scenarioTotal ?? 0})
          </div>
          <div style={{ fontSize: '12.5px', color: 'var(--muted)', marginTop: '2px' }}>
            Escenarios activos asignados por el configurador Maestro a tu organización
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {isLoading ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--muted)' }}>
            Cargando escenarios asignados...
          </div>
        ) : scenarios.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center' }}>
            <p style={{ color: 'var(--muted)', fontSize: '14px' }}>
              El configurador Maestro todavía no ha asignado escenarios activos a tu organización.
            </p>
          </div>
        ) : (
          <table className="wf">
            <thead>
              <tr>
                <th>Escenario</th>
                <th>Categoría</th>
                <th>Público interno</th>
                <th>Óptica</th>
                <th>Dificultad</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((scenario) => (
                <tr key={scenario.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--ink)' }}>{scenario.title}</div>
                    <div style={{ fontSize: '11.5px', color: 'var(--muted)', marginTop: '2px' }}>
                      {scenario.estimatedMinutes} min · {scenario.questionCount}{' '}
                      {scenario.questionCount === 1 ? 'pregunta' : 'preguntas'}
                    </div>
                  </td>
                  <td>{clientScenarioLabels.category[scenario.category]}</td>
                  <td>
                    <span className="pill on" style={{ fontSize: '11px', padding: '2px 8px' }}>
                      {clientScenarioLabels.audience[scenario.audience]}
                    </span>
                  </td>
                  <td>{clientScenarioLabels.optics[scenario.optics]}</td>
                  <td>{clientScenarioLabels.difficulty[scenario.difficulty]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
