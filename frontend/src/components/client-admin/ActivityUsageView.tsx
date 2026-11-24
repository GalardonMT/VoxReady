'use client';

import React, { useEffect, useState } from 'react';
import { clientAdminService } from '../../services/clientAdminService';
import type { ClientRecentActivityPage, ClientUsageResponse } from '../../types/api';
import { Pagination } from '../common/Pagination';

const emptyUsage: ClientUsageResponse = {
  periodDays: 30,
  summary: {
    assignedSpokespersons: 0,
    activeSpokespersons: 0,
    participationRate: 0,
    completedSessions: 0,
    previousCompletedSessions: 0,
    sessionChangePct: null,
    trainingSeconds: 0,
  },
  statusBreakdown: { completed: 0, inProgress: 0, abandoned: 0 },
  trend: [],
  scenarios: [],
  spokespersons: [],
  recentActivity: [],
};

function duration(seconds: number): string {
  if (seconds < 60) return `${seconds} s`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours} h ${minutes} min` : `${minutes} min`;
}

function dateTime(value: string | null): string {
  if (!value) return 'Sin actividad';
  return new Intl.DateTimeFormat('es-CL', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

const activityLabels = {
  active: 'Activo',
  low_activity: 'Baja actividad',
  not_started: 'No ha comenzado',
} as const;

const eventLabels = {
  session_completed: 'completó una sesión',
  session_activity: 'registró actividad en una sesión',
  microlesson_completed: 'completó una microlección',
  microlesson_started: 'inició una microlección',
} as const;

export const ActivityUsageView: React.FC = () => {
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [userId, setUserId] = useState('');
  const [scenarioId, setScenarioId] = useState('');
  const [usage, setUsage] = useState<ClientUsageResponse>(emptyUsage);
  const [spokespersonOptions, setSpokespersonOptions] = useState<ClientUsageResponse['spokespersons']>([]);
  const [scenarioOptions, setScenarioOptions] = useState<Array<{ id: string; title: string }>>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recentQuery, setRecentQuery] = useState('');
  const [recentPage, setRecentPage] = useState(1);
  const [recent, setRecent] = useState<ClientRecentActivityPage>({
    items: [], total: 0, page: 1, pageSize: 5, totalPages: 1,
  });
  const [recentLoading, setRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [peoplePage, setPeoplePage] = useState(1);

  useEffect(() => {
    let active = true;
    clientAdminService.usage({
      days,
      userId: userId || undefined,
      scenarioId: scenarioId || undefined,
    }).then(result => {
      if (active) {
        setUsage(result);
        if (!userId && !scenarioId) {
          setSpokespersonOptions(result.spokespersons);
          setScenarioOptions(result.scenarios.map(item => ({ id: item.scenarioId, title: item.title })));
        }
      }
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : 'No se pudo cargar la actividad.');
    }).finally(() => {
      if (active) setIsLoading(false);
    });
    return () => {
      active = false;
    };
  }, [days, scenarioId, userId]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      clientAdminService.recentActivity({
        days,
        userId: userId || undefined,
        scenarioId: scenarioId || undefined,
        query: recentQuery,
        page: recentPage,
        pageSize: 5,
      }).then(result => {
        if (active) {
          setRecent(result);
          if (result.page !== recentPage) setRecentPage(result.page);
          setRecentError(null);
        }
      }).catch(cause => {
        if (active) setRecentError(cause instanceof Error ? cause.message : 'No se pudo cargar la actividad reciente.');
      }).finally(() => {
        if (active) setRecentLoading(false);
      });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [days, recentPage, recentQuery, scenarioId, userId]);

  const changeFilter = (update: () => void) => {
    setIsLoading(true);
    setError(null);
    setRecentLoading(true);
    setRecentPage(1);
    setPeoplePage(1);
    update();
  };

  const changeRecentPage = (page: number) => {
    setRecentLoading(true);
    setRecentError(null);
    setRecentPage(page);
  };

  const maxSessions = Math.max(1, ...usage.trend.map(point => point.sessions));
  const statusTotal = Math.max(
    1,
    usage.statusBreakdown.completed + usage.statusBreakdown.inProgress + usage.statusBreakdown.abandoned,
  );
  const peoplePageSize = 5;
  const peopleTotalPages = Math.max(1, Math.ceil(usage.spokespersons.length / peoplePageSize));
  const safePeoplePage = Math.min(peoplePage, peopleTotalPages);
  const visiblePeople = usage.spokespersons.slice(
    (safePeoplePage - 1) * peoplePageSize,
    safePeoplePage * peoplePageSize,
  );

  const summaryCards = [
    { label: 'Voceros activos', value: usage.summary.activeSpokespersons, detail: `de ${usage.summary.assignedSpokespersons} asignados` },
    { label: 'Sesiones completadas', value: usage.summary.completedSessions, detail: usage.summary.sessionChangePct === null ? 'Sin período comparable' : `${usage.summary.sessionChangePct >= 0 ? '+' : ''}${usage.summary.sessionChangePct}% vs. período anterior` },
    { label: 'Tiempo de entrenamiento', value: duration(usage.summary.trainingSeconds), detail: `Últimos ${usage.periodDays} días` },
    { label: 'Participación', value: `${usage.summary.participationRate}%`, detail: 'voceros con actividad' },
  ];

  return (
    <div className="canvas-content">
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="master-heading" style={{ marginBottom: 0 }}>
          <div>
            <h2 style={{ fontSize: '20px' }}>📈 Actividad y uso</h2>
            <p className="legend">Adopción de la plataforma sin exponer grabaciones ni respuestas personales.</p>
          </div>
          <div className="master-filters">
            <label>Período
              <select className="field" value={days} onChange={event => changeFilter(() => setDays(Number(event.target.value) as 7 | 30 | 90))}>
                <option value={7}>7 días</option>
                <option value={30}>30 días</option>
                <option value={90}>90 días</option>
              </select>
            </label>
            <label>Vocero
              <select className="field" value={userId} onChange={event => changeFilter(() => setUserId(event.target.value))}>
                <option value="">Todos</option>
                {spokespersonOptions.map(person => (
                  <option key={person.id} value={person.id}>{person.displayName || person.email}</option>
                ))}
              </select>
            </label>
            <label>Escenario
              <select className="field" value={scenarioId} onChange={event => changeFilter(() => setScenarioId(event.target.value))}>
                <option value="">Todos</option>
                {scenarioOptions.map(option => <option key={option.id} value={option.id}>{option.title}</option>)}
              </select>
            </label>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div
          className="card"
          role="status"
          aria-live="polite"
          style={{
            minHeight: '360px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '14px',
            color: 'var(--muted)',
          }}
        >
          <div className="upload-overlay-spinner" style={{ width: '42px', height: '42px' }} />
          <strong style={{ color: 'var(--ink)', fontSize: '14px' }}>Actualizando actividad y uso...</strong>
          <span style={{ fontSize: '12px' }}>Estamos cargando las métricas para los filtros seleccionados.</span>
        </div>
      ) : error ? <div role="alert" className="card master-error">{error}</div> : <>
        <div className="grid4" style={{ marginBottom: '16px' }}>
          {summaryCards.map(card => <div className="stat" key={card.label}>
            <div className="k">{card.label}</div>
            <div className="v">{card.value}</div>
            <div className="legend">{card.detail}</div>
          </div>)}
        </div>

        <div className="grid2" style={{ marginBottom: '16px' }}>
          <section className="card">
            <div className="label">Sesiones por día</div>
            {usage.trend.length === 0 ? <p className="spokesperson-empty">Sin actividad en este período.</p> : (
              <div style={{ height: '210px', display: 'flex', alignItems: 'end', gap: '8px', paddingTop: '18px' }}>
                {usage.trend.map(point => <div key={point.activityDate} style={{ flex: 1, minWidth: '18px', textAlign: 'center' }} title={`${point.sessions} sesiones · ${point.activeSpokespersons} voceros`}>
                  <div style={{ fontSize: '10px', fontWeight: 600 }}>{point.sessions}</div>
                  <div style={{ height: `${Math.max(8, point.sessions * 150 / maxSessions)}px`, background: 'var(--accent)', borderRadius: '5px 5px 2px 2px' }} />
                  <div style={{ fontSize: '9px', color: 'var(--muted)', marginTop: '5px' }}>{new Intl.DateTimeFormat('es-CL', { day: '2-digit', month: '2-digit' }).format(new Date(point.activityDate))}</div>
                </div>)}
              </div>
            )}
          </section>

          <section className="card">
            <div className="label">Estado de las sesiones</div>
            {([
              ['Completadas', usage.statusBreakdown.completed, 'var(--success)'],
              ['En proceso', usage.statusBreakdown.inProgress, 'var(--accent)'],
              ['Abandonadas', usage.statusBreakdown.abandoned, 'var(--danger)'],
            ] as const).map(([label, value, color]) => <div key={label} style={{ marginTop: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}><span>{label}</span><strong>{value}</strong></div>
              <div className="bar" style={{ marginTop: '6px', width: '100%' }}><div style={{ height: '100%', width: `${value * 100 / statusTotal}%`, minWidth: value ? '5px' : 0, background: color, borderRadius: '3px' }} /></div>
            </div>)}
          </section>
        </div>

        <section className="card" style={{ padding: 0, overflowX: 'auto', marginBottom: '16px' }}>
          <div style={{ padding: '16px 18px 8px' }}><div className="label">Actividad por vocero</div></div>
          <table className="wf">
            <thead><tr><th>Vocero</th><th>Última actividad</th><th>Sesiones</th><th>Tiempo entrenado</th><th>Estado</th></tr></thead>
            <tbody>{visiblePeople.map(person => <tr key={person.id}>
              <td><strong>{person.displayName || person.email}</strong><div className="legend">{person.email}</div></td>
              <td>{dateTime(person.lastActivityAt)}</td>
              <td>{person.completedSessions}</td>
              <td>{duration(person.trainingSeconds)}</td>
              <td><span className={`client-status ${person.activityStatus === 'active' ? 'active' : person.activityStatus === 'not_started' ? 'suspended' : ''}`}>{activityLabels[person.activityStatus]}</span></td>
            </tr>)}</tbody>
          </table>
          {usage.spokespersons.length === 0 && <p className="spokesperson-empty" style={{ margin: '16px' }}>No hay voceros para estos filtros.</p>}
          <Pagination
            page={safePeoplePage}
            totalPages={peopleTotalPages}
            totalItems={usage.spokespersons.length}
            itemLabel="voceros"
            onPageChange={setPeoplePage}
          />
        </section>

        <div className="grid2">
          <section className="card" style={{ padding: 0, overflowX: 'auto' }}>
            <div style={{ padding: '16px 18px 8px' }}><div className="label">Escenarios más utilizados</div></div>
            <table className="wf"><thead><tr><th>Escenario</th><th>Sesiones</th><th>Voceros</th></tr></thead>
              <tbody>{usage.scenarios.map(item => <tr key={item.scenarioId}><td>{item.title}</td><td>{item.sessions}</td><td>{item.activeSpokespersons}</td></tr>)}</tbody>
            </table>
            {usage.scenarios.length === 0 && <p className="spokesperson-empty" style={{ margin: '16px' }}>Sin escenarios utilizados.</p>}
          </section>

          <section className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: '10px', flexWrap: 'wrap' }}>
              <div className="label">Actividad reciente</div>
              <label style={{ minWidth: '190px' }}>
                <span className="label" style={{ display: 'block' }}>Buscar</span>
                <input
                  type="search"
                  className="field"
                  value={recentQuery}
                  onChange={event => {
                    setRecentLoading(true);
                    setRecentError(null);
                    setRecentPage(1);
                    setRecentQuery(event.target.value);
                  }}
                  placeholder="Vocero o actividad"
                />
              </label>
            </div>
            {recentLoading ? <div role="status" className="spokesperson-empty" style={{ marginTop: '12px' }}>Cargando actividad reciente...</div>
              : recentError ? <div role="alert" className="master-error">{recentError}</div>
              : recent.items.length === 0 ? <p className="spokesperson-empty">Sin actividad reciente.</p> : (
              <div style={{ display: 'grid', gap: '10px', marginTop: '10px' }}>
                {recent.items.map(item => <div key={item.id} style={{ borderBottom: '1px solid var(--line)', paddingBottom: '9px' }}>
                  <div style={{ fontSize: '12.5px' }}><strong>{item.displayName}</strong> {eventLabels[item.type]}.</div>
                  <div className="legend">{item.title} · {dateTime(item.occurredAt)}</div>
                </div>)}
              </div>
            )}
            {!recentLoading && !recentError && <Pagination
              page={recent.page}
              totalPages={recent.totalPages}
              totalItems={recent.total}
              itemLabel="actividades"
              onPageChange={changeRecentPage}
            />}
          </section>
        </div>
      </>}
    </div>
  );
};
