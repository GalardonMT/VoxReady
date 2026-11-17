'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '../auth/ProtectedRoute';
import { Pagination } from '../common/Pagination';
import { clientAdminService } from '../../services/clientAdminService';
import type {
  ClientPagedResponse,
  ClientSpokespersonDetail,
  ClientSpokespersonMicrolesson,
  ClientSpokespersonSession,
  MicrolessonAssignmentStatus,
} from '../../types/api';
import { ClientAdminHeader, type ClientAdminScreen } from './ClientAdminHeader';

type Period = 7 | 30 | 90;
type SessionStatus = 'all' | 'completed' | 'in_progress' | 'abandoned';
type LessonStatus = 'all' | MicrolessonAssignmentStatus;

const emptyPage = <T,>(): ClientPagedResponse<T> => ({
  items: [], total: 0, page: 1, pageSize: 5, totalPages: 1,
});

const participationLabels = {
  active: 'Activo',
  low_activity: 'Baja actividad',
  inactive: 'Inactivo',
  not_started: 'No ha comenzado',
} as const;

const sessionLabels = {
  completed: 'Completada',
  in_progress: 'En proceso',
  abandoned: 'Abandonada',
} as const;

const lessonLabels: Record<MicrolessonAssignmentStatus, string> = {
  assigned: 'Asignada',
  in_progress: 'En progreso',
  completed: 'Completada',
  revoked: 'Revocada',
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
    dateStyle: 'medium', timeStyle: 'short',
  }).format(new Date(value));
}

function statusClass(status: string): string {
  return status === 'active' || status === 'completed'
    ? 'client-status active'
    : status === 'in_progress' || status === 'assigned' || status === 'low_activity'
      ? 'client-status'
      : 'client-status suspended';
}

interface SpokespersonDetailPageProps {
  spokespersonId: string;
}

export const SpokespersonDetailPage: React.FC<SpokespersonDetailPageProps> = ({ spokespersonId }) => {
  const router = useRouter();

  const navigate = (screen: ClientAdminScreen) => {
    router.push(`/admin?screen=${screen}`);
  };

  return (
    <ProtectedRoute allowedRoles={['client_admin']}>
      <div className="platform-container">
        <ClientAdminHeader activeScreen="a2" onNavigate={navigate} />
        <main className="canvas">
          <SpokespersonDetailView spokespersonId={spokespersonId} />
        </main>
      </div>
    </ProtectedRoute>
  );
};

const SpokespersonDetailView: React.FC<SpokespersonDetailPageProps> = ({ spokespersonId }) => {
  const router = useRouter();
  const [days, setDays] = useState<Period>(30);
  const [detail, setDetail] = useState<ClientSpokespersonDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [sessionStatus, setSessionStatus] = useState<SessionStatus>('all');
  const [sessionScenario, setSessionScenario] = useState('');
  const [sessionQuery, setSessionQuery] = useState('');
  const [sessionPage, setSessionPage] = useState(1);
  const [sessions, setSessions] = useState<ClientPagedResponse<ClientSpokespersonSession>>(emptyPage());
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState<string | null>(null);

  const [lessonStatus, setLessonStatus] = useState<LessonStatus>('all');
  const [lessonQuery, setLessonQuery] = useState('');
  const [lessonPage, setLessonPage] = useState(1);
  const [lessons, setLessons] = useState<ClientPagedResponse<ClientSpokespersonMicrolesson>>(emptyPage());
  const [lessonsLoading, setLessonsLoading] = useState(true);
  const [lessonsError, setLessonsError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    clientAdminService.spokespersonDetail(spokespersonId, days)
      .then(result => {
        if (active) setDetail(result);
      })
      .catch(cause => {
        if (active) setDetailError(cause instanceof Error ? cause.message : 'No se pudo cargar el detalle del vocero.');
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => { active = false; };
  }, [days, spokespersonId]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      clientAdminService.spokespersonSessions(spokespersonId, {
        days,
        status: sessionStatus,
        scenarioId: sessionScenario || undefined,
        query: sessionQuery,
        page: sessionPage,
      }).then(result => {
        if (active) {
          setSessions(result);
          setSessionPage(result.page);
          setSessionsError(null);
        }
      }).catch(cause => {
        if (active) setSessionsError(cause instanceof Error ? cause.message : 'No se pudo cargar el historial de sesiones.');
      }).finally(() => {
        if (active) setSessionsLoading(false);
      });
    }, 200);
    return () => { active = false; window.clearTimeout(timer); };
  }, [days, sessionPage, sessionQuery, sessionScenario, sessionStatus, spokespersonId]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      clientAdminService.spokespersonMicrolessons(spokespersonId, {
        days, status: lessonStatus, query: lessonQuery, page: lessonPage,
      }).then(result => {
        if (active) {
          setLessons(result);
          setLessonPage(result.page);
          setLessonsError(null);
        }
      }).catch(cause => {
        if (active) setLessonsError(cause instanceof Error ? cause.message : 'No se pudieron cargar las microlecciones.');
      }).finally(() => {
        if (active) setLessonsLoading(false);
      });
    }, 200);
    return () => { active = false; window.clearTimeout(timer); };
  }, [days, lessonPage, lessonQuery, lessonStatus, spokespersonId]);

  const changePeriod = (period: Period) => {
    setDetailLoading(true);
    setSessionsLoading(true);
    setLessonsLoading(true);
    setSessionPage(1);
    setLessonPage(1);
    setDays(period);
  };

  const maxSessions = useMemo(
    () => Math.max(1, ...(detail?.trend.map(point => point.sessions) || [])),
    [detail],
  );

  return (
    <div className="canvas-content">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: '16px', flexWrap: 'wrap', marginBottom: '14px' }}>
        <button type="button" className="btn" onClick={() => router.push('/admin?screen=a2')}>← Volver a Voceros</button>
        <label style={{ minWidth: '150px' }}>
          <span className="label" style={{ display: 'block' }}>Período</span>
          <select className="field" value={days} onChange={event => changePeriod(Number(event.target.value) as Period)}>
            <option value={7}>7 días</option>
            <option value={30}>30 días</option>
            <option value={90}>90 días</option>
          </select>
        </label>
      </div>

      {detailLoading ? (
        <div className="card" role="status" aria-live="polite" style={{ minHeight: '420px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '14px', color: 'var(--muted)' }}>
          <div className="upload-overlay-spinner" style={{ width: '42px', height: '42px' }} />
          <strong style={{ color: 'var(--ink)', fontSize: '14px' }}>Actualizando detalle del vocero...</strong>
          <span style={{ fontSize: '12px' }}>Cargando actividad, sesiones y microlecciones del período.</span>
        </div>
      ) : detailError ? (
        <div className="card master-error" role="alert">
          <strong>No se pudo abrir este vocero.</strong>
          <div style={{ marginTop: '6px' }}>{detailError}</div>
        </div>
      ) : detail && (
        <>
          <section className="card" style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '18px', flexWrap: 'wrap' }}>
            <div>
              <div className="label">Detalle individual del vocero</div>
              <h1 style={{ margin: '5px 0 2px', fontSize: '22px', color: 'var(--ink)' }}>
                {detail.spokesperson.displayName || 'Sin nombre registrado'}
              </h1>
              <div className="legend">{detail.spokesperson.email} · Idioma {detail.spokesperson.preferredLanguage.toUpperCase()}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <span className={statusClass(detail.spokesperson.participationStatus)}>{participationLabels[detail.spokesperson.participationStatus]}</span>
              <div className="legend" style={{ marginTop: '7px' }}>Última actividad: {dateTime(detail.spokesperson.lastActivityAt)}</div>
            </div>
          </section>

          {detail.alerts.length > 0 && (
            <section className="card" style={{ marginBottom: '16px' }}>
              <div className="label" style={{ marginBottom: '10px' }}>Alertas de seguimiento</div>
              <div style={{ display: 'grid', gap: '8px' }}>
                {detail.alerts.map(alert => (
                  <div key={alert.type} style={{ padding: '10px 12px', borderRadius: '8px', background: alert.severity === 'warning' ? '#fff5e6' : alert.severity === 'attention' ? '#fff0f0' : 'var(--soft)', border: '1px solid var(--line)', fontSize: '12.5px' }}>
                    {alert.severity === 'attention' ? '⚠️' : alert.severity === 'warning' ? '🔔' : 'ℹ️'} {alert.message}
                  </div>
                ))}
              </div>
            </section>
          )}

          <div className="grid4" style={{ marginBottom: '16px' }}>
            {[
              ['Sesiones completadas', detail.summary.completedSessions, `Últimos ${days} días`],
              ['Tiempo entrenado', duration(detail.summary.trainingSeconds), 'Sesiones y microlecciones'],
              ['Escenarios utilizados', detail.summary.scenariosUsed, 'Escenarios distintos'],
              ['Microlecciones completadas', detail.summary.completedMicrolessons, `Últimos ${days} días`],
            ].map(([label, value, note]) => (
              <div className="stat" key={label}>
                <div className="k">{label}</div>
                <div className="v">{value}</div>
                <div className="legend">{note}</div>
              </div>
            ))}
          </div>

          <div className="grid2" style={{ marginBottom: '16px' }}>
            <section className="card">
              <div className="label">Actividad por día</div>
              {detail.trend.length === 0 ? <p className="spokesperson-empty">Sin sesiones en este período.</p> : (
                <div style={{ height: '210px', display: 'flex', alignItems: 'end', gap: '8px', paddingTop: '18px' }}>
                  {detail.trend.map(point => (
                    <div key={point.activityDate} style={{ flex: 1, minWidth: '18px', textAlign: 'center' }} title={`${point.sessions} sesiones`}>
                      <div style={{ fontSize: '10px', fontWeight: 600 }}>{point.sessions}</div>
                      <div style={{ height: `${Math.max(8, point.sessions * 150 / maxSessions)}px`, background: 'var(--accent)', borderRadius: '5px 5px 2px 2px' }} />
                      <div style={{ fontSize: '9px', color: 'var(--muted)', marginTop: '5px' }}>{new Intl.DateTimeFormat('es-CL', { day: '2-digit', month: '2-digit' }).format(new Date(point.activityDate))}</div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="card" style={{ padding: 0, overflowX: 'auto' }}>
              <div style={{ padding: '16px 18px 8px' }}><div className="label">Escenarios utilizados</div></div>
              <table className="wf">
                <thead><tr><th>Escenario</th><th>Sesiones</th></tr></thead>
                <tbody>{detail.scenarios.map(item => <tr key={item.scenarioId}><td>{item.title}</td><td>{item.sessions}</td></tr>)}</tbody>
              </table>
              {detail.scenarios.length === 0 && <p className="spokesperson-empty" style={{ margin: '16px' }}>Todavía no ha utilizado escenarios.</p>}
            </section>
          </div>

          <section className="card" style={{ padding: 0, overflowX: 'auto', marginBottom: '16px' }}>
            <div style={{ padding: '16px 18px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: '10px', flexWrap: 'wrap' }}>
              <div><div className="label">Historial de sesiones</div><div className="legend">Solo datos operativos; no muestra grabaciones ni respuestas.</div></div>
              <div className="master-filters">
                <label>Estado
                  <select className="field" value={sessionStatus} onChange={event => { setSessionsLoading(true); setSessionPage(1); setSessionStatus(event.target.value as SessionStatus); }}>
                    <option value="all">Todos</option><option value="completed">Completadas</option><option value="in_progress">En proceso</option><option value="abandoned">Abandonadas</option>
                  </select>
                </label>
                <label>Escenario
                  <select className="field" value={sessionScenario} onChange={event => { setSessionsLoading(true); setSessionPage(1); setSessionScenario(event.target.value); }}>
                    <option value="">Todos</option>
                    {detail.scenarios.map(item => <option key={item.scenarioId} value={item.scenarioId}>{item.title}</option>)}
                  </select>
                </label>
                <label>Buscar
                  <input className="field" type="search" value={sessionQuery} onChange={event => { setSessionsLoading(true); setSessionPage(1); setSessionQuery(event.target.value); }} placeholder="Escenario" />
                </label>
              </div>
            </div>
            {sessionsLoading ? <div role="status" className="spokesperson-empty" style={{ margin: '16px' }}>Cargando sesiones...</div>
              : sessionsError ? <div role="alert" className="master-error" style={{ margin: '16px' }}>{sessionsError}</div>
              : sessions.items.length === 0 ? <p className="spokesperson-empty" style={{ margin: '16px' }}>No hay sesiones para estos filtros.</p>
              : <table className="wf"><thead><tr><th>Fecha</th><th>Escenario</th><th>Duración</th><th>Estado</th></tr></thead><tbody>
                {sessions.items.map(item => <tr key={item.id}><td>{dateTime(item.activityAt)}</td><td>{item.scenarioTitle}</td><td>{item.durationSeconds === null ? 'Sin dato' : duration(item.durationSeconds)}</td><td><span className={statusClass(item.status)}>{sessionLabels[item.status]}</span></td></tr>)}
              </tbody></table>}
            {!sessionsLoading && !sessionsError && <Pagination page={sessions.page} totalPages={sessions.totalPages} totalItems={sessions.total} itemLabel="sesiones" onPageChange={page => { setSessionsLoading(true); setSessionPage(page); }} />}
          </section>

          <section className="card" style={{ padding: 0, overflowX: 'auto' }}>
            <div style={{ padding: '16px 18px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: '16px', flexWrap: 'wrap' }}>
              <div>
                <div className="label">Microlecciones</div>
                <div className="legend">Seguimiento de las microlecciones asignadas al vocero durante el período.</div>
              </div>
              <div className="master-filters">
                <label>Estado
                  <select className="field" value={lessonStatus} onChange={event => { setLessonsLoading(true); setLessonPage(1); setLessonStatus(event.target.value as LessonStatus); }}>
                    <option value="all">Todas</option><option value="assigned">Asignadas</option><option value="in_progress">En progreso</option><option value="completed">Completadas</option><option value="revoked">Revocadas</option>
                  </select>
                </label>
                <label>Buscar
                  <input className="field" type="search" value={lessonQuery} onChange={event => { setLessonsLoading(true); setLessonPage(1); setLessonQuery(event.target.value); }} placeholder="Título o escenario" />
                </label>
              </div>
            </div>
            {lessonsLoading ? <div role="status" className="spokesperson-empty" style={{ margin: '16px' }}>Cargando microlecciones...</div>
              : lessonsError ? <div role="alert" className="master-error" style={{ margin: '16px' }}>{lessonsError}</div>
              : lessons.items.length === 0 ? <p className="spokesperson-empty" style={{ margin: '16px' }}>No hay microlecciones para estos filtros.</p>
              : <table className="wf"><thead><tr><th>Microlección</th><th>Escenario</th><th>Asignada</th><th>Finalizada</th><th>Duración</th><th>Estado</th></tr></thead><tbody>
                {lessons.items.map(item => <tr key={item.assignmentId}><td><strong>{item.title}</strong></td><td>{item.scenarioTitle}</td><td>{dateTime(item.assignedAt)}</td><td>{item.completedAt ? dateTime(item.completedAt) : '—'}</td><td>{item.durationMinutes ? `${item.durationMinutes} min` : '—'}</td><td><span className={statusClass(item.status)}>{lessonLabels[item.status]}</span></td></tr>)}
              </tbody></table>}
            {!lessonsLoading && !lessonsError && <Pagination page={lessons.page} totalPages={lessons.totalPages} totalItems={lessons.total} itemLabel="microlecciones" onPageChange={page => { setLessonsLoading(true); setLessonPage(page); }} />}
          </section>
        </>
      )}
    </div>
  );
};
