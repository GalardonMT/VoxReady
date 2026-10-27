'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';
import { sessionFlowService, type CatalogScenario, type SessionSetup } from '../../services/sessionFlowService';
import { sessionService } from '../../services/sessionService';
import type { MicrolessonRecommendations, SessionHistoryItem } from '../../types/api';
import { microlessonService } from '../../services/microlessonService';
import {
  progressService,
  type CalendarResponse,
  type ProgressArea,
  type ProgressResponse,
  type ScheduleItem
} from '../../services/progressService';
import {
  areaLabel,
  calendarDateKey,
  calendarRange,
  isSchedulableDate,
  localDateKey
} from '../../services/progressModel';

interface ProgressViewProps {
  onNavigate: (screen: VoceroScreen, extra?: string) => void;
  onSessionStart: (setup: SessionSetup) => void;
}

const MONTHS = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
];
const WEEKDAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const COLORS = ['#173955', '#e65f22', '#289c87', '#929292', '#7357b5', '#2f7ebc', '#b44c76'];

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Ocurrió un error inesperado.';
}

function formatDate(value: string): string {
  const date = value.length === 10 ? new Date(`${value}T12:00:00`) : new Date(value);
  return new Intl.DateTimeFormat('es-CL', { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
}

function formatDateTime(value: string | undefined | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('es-CL', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).format(date);
}

function colorForArea(area: ProgressArea, index: number): string {
  const known: Record<string, string> = {
    expression: '#173955', expresion: '#173955', voice: '#e65f22', tone: '#e65f22',
    voice_tone: '#e65f22', coherence: '#289c87', coherencia: '#289c87',
    empathy: '#929292', empatia: '#929292'
  };
  return known[area.areaKey.toLowerCase()] ?? COLORS[index % COLORS.length];
}

export const ProgressView: React.FC<ProgressViewProps> = ({ onNavigate, onSessionStart }) => {
  const { t } = useI18n();
  const d = t.L.u7;
  const today = useMemo(() => new Date(), []);
  const todayKey = localDateKey(today);

  // Session History State (Visum Report History)
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionHistoryItem[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const loadSessions = async () => {
    setIsLoadingSessions(true);
    try {
      const data = await sessionService.getUserSessions('completed');
      setSessions(data);
    } catch (e) {
      console.warn('Error cargando historial de sesiones:', e);
    } finally {
      setIsLoadingSessions(false);
    }
  };

  useEffect(() => {
    void Promise.resolve().then(loadSessions);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isHistoryModalOpen) {
        setIsHistoryModalOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isHistoryModalOpen]);

  const getScoreBadgeStyle = (score: number) => {
    if (score >= 80) {
      return {
        bg: 'rgba(34, 197, 94, 0.15)',
        text: 'var(--success, #16a34a)',
        border: 'rgba(34, 197, 94, 0.35)',
        label: 'Sobresaliente'
      };
    }
    if (score >= 60) {
      return {
        bg: 'rgba(245, 158, 11, 0.15)',
        text: '#d97706',
        border: 'rgba(245, 158, 11, 0.35)',
        label: 'En desarrollo'
      };
    }
    return {
      bg: 'rgba(239, 68, 68, 0.15)',
      text: 'var(--danger, #dc2626)',
      border: 'rgba(239, 68, 68, 0.35)',
      label: 'Requiere atención'
    };
  };

  const filteredSessions = sessions.filter((s) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (s.scenarioTitle && s.scenarioTitle.toLowerCase().includes(q)) ||
      (s.sessionId && s.sessionId.toLowerCase().includes(q)) ||
      (s.createdAt && s.createdAt.toLowerCase().includes(q))
    );
  });

  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [progressLoading, setProgressLoading] = useState(true);
  const [progressError, setProgressError] = useState('');
  const [calendar, setCalendar] = useState<CalendarResponse | null>(null);
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [calendarError, setCalendarError] = useState('');
  const [scenarios, setScenarios] = useState<CatalogScenario[]>([]);
  const [scenarioError, setScenarioError] = useState('');
  const [calYear, setCalYear] = useState(today.getFullYear());
  const [calMonth, setCalMonth] = useState(today.getMonth());
  const [selectedDate, setSelectedDate] = useState(todayKey);
  const [editing, setEditing] = useState<ScheduleItem | null>(null);
  const [formDate, setFormDate] = useState(todayKey);
  const [scenarioId, setScenarioId] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [recommendations, setRecommendations] = useState<MicrolessonRecommendations | null>(null);
  const [recommendationsLoading, setRecommendationsLoading] = useState(true);
  const [recommendationsError, setRecommendationsError] = useState('');

  const loadRecommendations = useCallback(async () => {
    setRecommendationsLoading(true);
    setRecommendationsError('');
    try {
      setRecommendations(await microlessonService.recommendations());
    } catch (error) {
      setRecommendationsError(errorText(error));
    } finally {
      setRecommendationsLoading(false);
    }
  }, []);

  const loadProgress = useCallback(async () => {
    setProgressLoading(true);
    setProgressError('');
    try {
      setProgress(await progressService.getProgress(5));
    } catch (error) {
      setProgressError(errorText(error));
    } finally {
      setProgressLoading(false);
    }
  }, []);

  const loadCalendar = useCallback(async () => {
    setCalendarLoading(true);
    setCalendarError('');
    try {
      const range = calendarRange(calYear, calMonth);
      setCalendar(await progressService.getCalendar(range.fromDate, range.toDate));
    } catch (error) {
      setCalendarError(errorText(error));
    } finally {
      setCalendarLoading(false);
    }
  }, [calMonth, calYear]);

  const loadScenarios = useCallback(async () => {
    setScenarioError('');
    try {
      const activeScenarios: CatalogScenario[] = [];
      let page = 1;
      while (true) {
        const response = await sessionFlowService.listScenarios({ page, pageSize: 100 });
        activeScenarios.push(...response.items);
        if (!response.items.length || activeScenarios.length >= response.total) break;
        page += 1;
      }
      setScenarios(activeScenarios);
      setScenarioId((current) => current || activeScenarios[0]?.id || '');
    } catch (error) {
      setScenarioError(errorText(error));
    }
  }, []);

  useEffect(() => { void Promise.resolve().then(loadProgress); }, [loadProgress]);
  useEffect(() => { void Promise.resolve().then(loadCalendar); }, [loadCalendar]);
  useEffect(() => { void Promise.resolve().then(loadScenarios); }, [loadScenarios]);
  useEffect(() => {
    let active = true;
    microlessonService.recommendations().then(result => { if (active) setRecommendations(result); })
      .catch(error => { if (active) setRecommendationsError(errorText(error)); })
      .finally(() => { if (active) setRecommendationsLoading(false); });
    return () => { active = false; };
  }, []);

  const prevMonth = () => {
    setCalMonth((month) => {
      if (month === 0) { setCalYear((year) => year - 1); return 11; }
      return month - 1;
    });
  };
  const nextMonth = () => {
    setCalMonth((month) => {
      if (month === 11) { setCalYear((year) => year + 1); return 0; }
      return month + 1;
    });
  };

  const firstDayIndex = (new Date(calYear, calMonth, 1).getDay() + 6) % 7;
  const totalDays = new Date(calYear, calMonth + 1, 0).getDate();
  const selectedSchedules = calendar?.schedules.filter(
    (item) => item.date === selectedDate && item.status === 'scheduled'
  ) ?? [];
  const selectedSessions = calendar?.sessions.filter((item) => calendarDateKey(item.completedAt) === selectedDate) ?? [];
  const canScheduleSelected = isSchedulableDate(selectedDate, today);

  const selectDay = (day: number) => {
    const date = localDateKey(new Date(calYear, calMonth, day));
    setSelectedDate(date);
    setEditing(null);
    setFormDate(date);
    setActionError('');
  };

  const saveSchedule = async () => {
    if (!scenarioId || !formDate) return;
    setBusyId(editing?.id ?? 'create');
    setActionError('');
    try {
      if (editing) await progressService.updateSchedule(editing.id, formDate, scenarioId);
      else await progressService.createSchedule(formDate, scenarioId);
      setSelectedDate(formDate);
      const selected = new Date(`${formDate}T12:00:00`);
      setCalYear(selected.getFullYear());
      setCalMonth(selected.getMonth());
      setEditing(null);
      await loadCalendar();
    } catch (error) {
      setActionError(errorText(error));
    } finally {
      setBusyId('');
    }
  };

  const editSchedule = (item: ScheduleItem) => {
    setEditing(item);
    setFormDate(item.date);
    setScenarioId(item.scenario?.available ? item.scenario.id : scenarios[0]?.id ?? '');
    setActionError('');
  };

  const cancelSchedule = async (item: ScheduleItem) => {
    if (!window.confirm('¿Quieres cancelar esta práctica agendada?')) return;
    setBusyId(item.id);
    setActionError('');
    try {
      await progressService.cancelSchedule(item.id);
      if (editing?.id === item.id) setEditing(null);
      await loadCalendar();
    } catch (error) {
      setActionError(errorText(error));
    } finally {
      setBusyId('');
    }
  };

  const startSchedule = async (item: ScheduleItem) => {
    setBusyId(item.id);
    setActionError('');
    try {
      const started = await progressService.startSchedule(item.id);
      onSessionStart(await sessionFlowService.getSession(started.sessionId));
    } catch (error) {
      setActionError(errorText(error));
    } finally {
      setBusyId('');
    }
  };

  return (
    <div className="canvas-content">
      {/* Action Header: Mi Progreso + Historial de Sesiones */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '18px',
          flexWrap: 'wrap',
          gap: '12px'
        }}
      >
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--ink)', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>📈</span>
            <span>{d.title || 'Mi Progreso'}</span>
          </h2>
          <p style={{ fontSize: '12.5px', color: 'var(--muted)', margin: '4px 0 0' }}>
            {d.note || 'Evolución de tus habilidades voceras y registro histórico de prácticas.'}
          </p>
        </div>

        <button
          type="button"
          className="btn pri"
          onClick={() => {
            setIsHistoryModalOpen(true);
            loadSessions();
          }}
          style={{
            background: 'linear-gradient(135deg, #17354F 0%, #224b6e 100%)',
            color: '#ffffff',
            fontWeight: 600,
            fontSize: '13px',
            padding: '10px 18px',
            borderRadius: '9px',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 4px 14px rgba(23, 53, 79, 0.25)',
            border: 'none',
            cursor: 'pointer',
            transition: 'transform 0.15s, box-shadow 0.15s'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'translateY(-1px)';
            e.currentTarget.style.boxShadow = '0 6px 18px rgba(23, 53, 79, 0.35)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'none';
            e.currentTarget.style.boxShadow = '0 4px 14px rgba(23, 53, 79, 0.25)';
          }}
        >
          <span style={{ fontSize: '15px' }}>📋</span>
          <span>Ver Historial de Sesiones</span>
          {sessions.length > 0 && (
            <span
              style={{
                background: 'rgba(255, 255, 255, 0.22)',
                padding: '2px 8px',
                borderRadius: '12px',
                fontSize: '11px',
                fontWeight: 700
              }}
            >
              {sessions.length}
            </span>
          )}
        </button>
      </div>

      <ProgressSummary
        progress={progress}
        loading={progressLoading}
        error={progressError}
        onRetry={loadProgress}
        onChooseScenario={() => onNavigate('u2')}
      />

      <div className="grid2" style={{ marginTop: '18px' }}>
        <div className="card">
          <div className="label">RECOMENDACIONES PARA TI</div>
          {recommendationsLoading && <p role="status">Cargando tus microlecciones…</p>}
          {recommendationsError && <ErrorBox message={recommendationsError} onRetry={loadRecommendations} />}
          {!recommendationsLoading && !recommendationsError && recommendations?.items.length === 0 && <div className="progress-empty-recommendations">
            <p>No tienes microlecciones asignadas por ahora.</p>
            <button type="button" className="btn" onClick={() => onNavigate('lesson')}>Explorar microlecciones</button>
          </div>}
          {!recommendationsLoading && !recommendationsError && recommendations?.items.map(item => (
            <article key={item.assignmentId ?? item.id} className="box progress-recommendation">
              <div className="progress-recommendation-heading"><strong>{item.title}</strong><span className="tagm">{item.assignmentStatus === 'in_progress' ? 'En progreso' : 'Asignada'}</span></div>
              <p className="legend">{item.learningObjective}</p>
              <div className="legend">{item.durationMinutes ? `≈ ${item.durationMinutes} min · ` : ''}Escenario: {item.scenarioTitle}</div>
              <button type="button" className="btn" onClick={() => onNavigate('lesson', item.id)}>Abrir microlección →</button>
            </article>
          ))}
          {!recommendationsLoading && !recommendationsError && (recommendations?.total ?? 0) > 3 && <button type="button" className="btn ghost" onClick={() => onNavigate('lesson')}>Ver todas</button>}
        </div>

        <div className="card">
          <div className="label">PROGRAMA TU PRÓXIMA SESIÓN</div>
          <div className="legend" style={{ margin: '-2px 0 10px' }}>
            Elige un día para revisar su actividad o agendar una práctica.
          </div>
          <div className="progress-symbols" aria-label="Simbología del calendario">
            <span><i className="progress-dot scheduled" /> Agendada</span>
            <span><i className="progress-dot completed" /> Realizada</span>
            <span><b>2</b> Varias actividades</span>
          </div>
          <div className="calhead">
            <button type="button" className="btn ghost" style={{ padding: '4px 10px' }} onClick={prevMonth} aria-label="Mes anterior">‹</button>
            <span style={{ fontSize: '13.5px', fontWeight: 600, textTransform: 'capitalize' }}>{MONTHS[calMonth]} {calYear}</span>
            <button type="button" className="btn ghost" style={{ padding: '4px 10px' }} onClick={nextMonth} aria-label="Mes siguiente">›</button>
          </div>
          <div className="calgrid">
            {WEEKDAYS.map((weekday, index) => <div key={index} className="dow">{weekday}</div>)}
          </div>
          <div className="calgrid" style={{ marginTop: '6px' }} aria-label={`Calendario de ${MONTHS[calMonth]} de ${calYear}`}>
            {Array.from({ length: firstDayIndex }).map((_, index) => <div key={`empty-${index}`} />)}
            {Array.from({ length: totalDays }, (_, index) => index + 1).map((day) => {
              const date = localDateKey(new Date(calYear, calMonth, day));
              const schedules = calendar?.schedules.filter((item) => item.date === date && item.status === 'scheduled') ?? [];
              const sessions = calendar?.sessions.filter((item) => calendarDateKey(item.completedAt) === date) ?? [];
              const count = schedules.length + sessions.length;
              return (
                <button
                  type="button"
                  key={day}
                  className={`calday ${selectedDate === date ? 'sel' : ''}`}
                  onClick={() => selectDay(day)}
                  aria-pressed={selectedDate === date}
                  aria-current={date === todayKey ? 'date' : undefined}
                  aria-label={`${day} de ${MONTHS[calMonth]}: ${count ? `${count} actividades` : 'sin actividades'}`}
                >
                  <span>{day}</span>
                  <span className="progress-day-markers" aria-hidden="true">
                    {schedules.length > 0 && <i className="progress-dot scheduled" />}
                    {sessions.length > 0 && <i className="progress-dot completed" />}
                    {count > 1 && <b>{count}</b>}
                  </span>
                </button>
              );
            })}
          </div>

          {calendarLoading && <p className="legend" role="status">Cargando calendario…</p>}
          {calendarError && <ErrorBox message={calendarError} onRetry={loadCalendar} />}
          {!calendarLoading && !calendarError && (
            <DayPanel
              date={selectedDate}
              schedules={selectedSchedules}
              sessions={selectedSessions}
              overdueBefore={todayKey}
              busyId={busyId}
              onEdit={editSchedule}
              onCancel={cancelSchedule}
              onStart={startSchedule}
              onReport={(sessionId) => onNavigate('u6', sessionId)}
            />
          )}

          {canScheduleSelected && (
            <div className="progress-form">
              <div style={{ fontWeight: 600, fontSize: '13px' }}>{editing ? 'Editar práctica' : 'Agendar una práctica'}</div>
              <label className="progress-field">Fecha
                <input type="date" value={formDate} min={todayKey} max={localDateKey(new Date(today.getFullYear(), today.getMonth() + 12, today.getDate()))} onChange={(event) => setFormDate(event.target.value)} />
              </label>
              <label className="progress-field">Escenario
                <select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)} disabled={!scenarios.length}>
                  {!scenarios.length && <option value="">No hay escenarios disponibles</option>}
                  {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.title}</option>)}
                </select>
              </label>
              {scenarioError && <ErrorBox message={scenarioError} onRetry={loadScenarios} />}
              {actionError && <div className="progress-error" role="alert">{actionError}</div>}
              <div className="progress-actions">
                {editing && <button type="button" className="btn ghost" onClick={() => { setEditing(null); setFormDate(selectedDate); }}>Cerrar edición</button>}
                <button type="button" className="btn pri" disabled={!scenarioId || busyId !== '' || !isSchedulableDate(formDate, today)} onClick={() => void saveSchedule()}>
                  {busyId === (editing?.id ?? 'create') ? 'Guardando…' : editing ? 'Guardar cambios' : 'Agendar práctica'}
                </button>
              </div>
            </div>
          )}
          {!canScheduleSelected && <p className="legend">Las fechas pasadas se conservan solo para consultar el historial.</p>}
        </div>
      </div>

      <div className="card" style={{ marginTop: '18px' }}>
        <div className="label">SESIONES RECIENTES</div>
        {progressError && <p className="legend">No se pudo cargar esta lista.</p>}
        {!progressError && !progressLoading && progress?.recentSessions.length === 0 && <p className="legend">Aún no hay sesiones completadas.</p>}
        <div className="progress-recent-list">
          {progress?.recentSessions.map((session) => (
            <div className="progress-recent-item" key={session.sessionId}>
              <div><strong>{session.scenarioTitle}</strong><span>{formatDateTime(session.completedAt)} · Puntaje {session.overallScore ?? '—'}</span></div>
              <button type="button" className="btn" onClick={() => onNavigate('u6', session.sessionId)}>Ver informe</button>
            </div>
          ))}
        </div>
      </div>

      {/* Modal Emergente Glassmorphic de Historial de Sesiones */}
      {isHistoryModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-historial-title"
          onClick={() => setIsHistoryModalOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.72)',
            backdropFilter: 'blur(6px)',
            zIndex: 1200,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px'
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--panel)',
              borderRadius: '16px',
              border: '1px solid var(--line)',
              width: '100%',
              maxWidth: '820px',
              maxHeight: '88vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 25px 60px rgba(0,0,0,0.3)',
              overflow: 'hidden'
            }}
          >
            {/* Header del Modal */}
            <div
              style={{
                padding: '18px 24px',
                borderBottom: '1px solid var(--line)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'var(--stat)'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '24px' }}>📋</span>
                <div>
                  <h3
                    id="modal-historial-title"
                    style={{
                      fontSize: '17px',
                      fontWeight: 700,
                      color: 'var(--ink)',
                      margin: 0
                    }}
                  >
                    Historial de Sesiones de Entrenamiento
                  </h3>
                  <p
                    style={{
                      fontSize: '12px',
                      color: 'var(--muted)',
                      margin: '2px 0 0 0'
                    }}
                  >
                    Sesiones completadas con análisis de IA y reporte detallado de Visum
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setIsHistoryModalOpen(false)}
                title="Cerrar modal"
                style={{
                  background: 'transparent',
                  border: '1px solid var(--line)',
                  borderRadius: '8px',
                  width: '34px',
                  height: '34px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: 'var(--muted)',
                  fontSize: '16px',
                  transition: 'all 0.15s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--soft)';
                  e.currentTarget.style.color = 'var(--ink)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = 'var(--muted)';
                }}
              >
                ✕
              </button>
            </div>

            {/* Barra de Filtro y Métricas */}
            <div
              style={{
                padding: '12px 24px',
                borderBottom: '1px solid var(--line)',
                display: 'flex',
                gap: '12px',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'var(--panel)',
                flexWrap: 'wrap'
              }}
            >
              <div style={{ position: 'relative', flex: 1, minWidth: '220px' }}>
                <span
                  style={{
                    position: 'absolute',
                    left: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    fontSize: '13px',
                    color: 'var(--muted)'
                  }}
                >
                  🔍
                </span>
                <input
                  type="text"
                  placeholder="Buscar por escenario o fecha..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px 8px 32px',
                    fontSize: '13px',
                    borderRadius: '8px',
                    border: '1px solid var(--line)',
                    background: 'var(--stat)',
                    color: 'var(--ink)',
                    outline: 'none'
                  }}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
                  Total completadas: <b style={{ color: 'var(--ink)' }}>{sessions.length}</b>
                </span>
                <button
                  type="button"
                  onClick={loadSessions}
                  disabled={isLoadingSessions}
                  title="Actualizar listado"
                  style={{
                    background: 'var(--soft)',
                    border: '1px solid var(--line)',
                    borderRadius: '6px',
                    padding: '6px 10px',
                    fontSize: '12px',
                    cursor: 'pointer',
                    color: 'var(--ink)'
                  }}
                >
                  {isLoadingSessions ? '⌛ Actualizando...' : '🔄 Actualizar'}
                </button>
              </div>
            </div>

            {/* Cuerpo del Modal (Scrollable) */}
            <div
              style={{
                padding: '18px 24px',
                overflowY: 'auto',
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                gap: '12px'
              }}
            >
              {isLoadingSessions && sessions.length === 0 ? (
                <div
                  style={{
                    padding: '40px 20px',
                    textAlign: 'center',
                    color: 'var(--muted)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '12px'
                  }}
                >
                  <div
                    style={{
                      width: '36px',
                      height: '36px',
                      border: '3px solid var(--line)',
                      borderTopColor: 'var(--accent)',
                      borderRadius: '50%',
                      animation: 'spin 0.8s linear infinite'
                    }}
                  />
                  <span style={{ fontSize: '13.5px' }}>Cargando sesiones de entrenamiento...</span>
                  <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                </div>
              ) : filteredSessions.length === 0 ? (
                <div
                  style={{
                    padding: '45px 20px',
                    textAlign: 'center',
                    background: 'var(--stat)',
                    borderRadius: '12px',
                    border: '1px dashed var(--line)'
                  }}
                >
                  <span style={{ fontSize: '38px', display: 'block', marginBottom: '8px' }}>🌱</span>
                  <h4 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px 0' }}>
                    {searchQuery ? 'No se encontraron sesiones para la búsqueda' : 'Aún no tienes sesiones de entrenamiento completadas'}
                  </h4>
                  <p style={{ fontSize: '12.5px', color: 'var(--muted)', maxWidth: '420px', margin: '0 auto 16px', lineHeight: 1.5 }}>
                    {searchQuery
                      ? 'Prueba con otros términos de búsqueda o borra el filtro para ver todo el historial.'
                      : 'Realiza una simulación desde el catálogo para generar tu primera evaluación multimodal con el Juez y Visum.'}
                  </p>
                  {!searchQuery && (
                    <button
                      type="button"
                      className="btn pri"
                      onClick={() => {
                        setIsHistoryModalOpen(false);
                        onNavigate('u2');
                      }}
                      style={{
                        padding: '8px 16px',
                        fontSize: '13px'
                      }}
                    >
                      Ir al Catálogo de Prácticas →
                    </button>
                  )}
                </div>
              ) : (
                filteredSessions.map((s) => {
                  const badge = getScoreBadgeStyle(s.overallScore);
                  return (
                    <div
                      key={s.sessionId}
                      style={{
                        background: 'var(--stat)',
                        borderRadius: '12px',
                        border: '1px solid var(--line)',
                        padding: '16px 18px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '12px',
                        transition: 'box-shadow 0.2s, transform 0.2s'
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                          gap: '12px',
                          flexWrap: 'wrap'
                        }}
                      >
                        <div style={{ flex: 1, minWidth: '240px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                            <span style={{ fontSize: '15px', fontWeight: 700, color: 'var(--ink)' }}>
                              {s.scenarioTitle}
                            </span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', fontSize: '12px', color: 'var(--muted)' }}>
                            <span>📅 {formatDateTime(s.createdAt)}</span>
                            <span>•</span>
                            <span title={s.sessionId}>
                              ID: <code style={{ fontSize: '11px', color: 'var(--accent)' }}>{s.sessionId.slice(0, 16)}...</code>
                            </span>
                            <span>•</span>
                            <span style={{ color: 'var(--success)', fontWeight: 600 }}>✓ Completado</span>
                          </div>
                        </div>

                        {/* Puntuación */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px'
                          }}
                        >
                          <div
                            style={{
                              background: badge.bg,
                              color: badge.text,
                              border: `1px solid ${badge.border}`,
                              borderRadius: '8px',
                              padding: '6px 12px',
                              textAlign: 'center',
                              minWidth: '95px'
                            }}
                          >
                            <div style={{ fontSize: '17px', fontWeight: 800, lineHeight: 1.1 }}>
                              {s.overallScore} <span style={{ fontSize: '11px', fontWeight: 500 }}>/ 100</span>
                            </div>
                            <div style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px', marginTop: '2px' }}>
                              {badge.label}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Footer de la tarjeta con botón de acceso al reporte */}
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          paddingTop: '10px',
                          borderTop: '1px solid var(--line)',
                          flexWrap: 'wrap',
                          gap: '8px'
                        }}
                      >
                        <span style={{ fontSize: '11.5px', color: 'var(--muted)' }}>
                          Incluye métricas de visión, acústica, dictamen del juez y transcripción
                        </span>

                        <button
                          type="button"
                          className="btn pri"
                          onClick={() => {
                            setIsHistoryModalOpen(false);
                            onNavigate('u8', s.sessionId);
                          }}
                          style={{
                            background: 'var(--accent)',
                            color: '#ffffff',
                            fontWeight: 600,
                            fontSize: '12.5px',
                            padding: '7px 14px',
                            borderRadius: '8px',
                            border: '1px solid var(--accent)',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px'
                          }}
                        >
                          <span>📊 Ver Reporte Completo VISUM</span>
                          <span>→</span>
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Pie del Modal */}
            <div
              style={{
                padding: '12px 24px',
                borderTop: '1px solid var(--line)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                background: 'var(--stat)'
              }}
            >
              <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
                VoxReady Media Training · Informes auditables y métricas de desempeño
              </span>
              <button
                type="button"
                className="btn"
                onClick={() => setIsHistoryModalOpen(false)}
                style={{
                  fontSize: '12.5px',
                  padding: '6px 14px'
                }}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

function ErrorBox({ message, onRetry }: { message: string; onRetry: () => void | Promise<void> }) {
  return <div className="progress-error" role="alert"><span>{message}</span><button type="button" className="btn" onClick={() => void onRetry()}>Reintentar</button></div>;
}

function ProgressSummary({ progress, loading, error, onRetry, onChooseScenario }: {
  progress: ProgressResponse | null;
  loading: boolean;
  error: string;
  onRetry: () => Promise<void>;
  onChooseScenario: () => void;
}) {
  if (loading) return <div className="card" role="status">Cargando tu progreso…</div>;
  if (error) return <div className="card"><div className="label">MI PROGRESO</div><ErrorBox message={error} onRetry={onRetry} /></div>;
  if (!progress || progress.trendSessions.length === 0) {
    return <div className="card progress-empty"><div><div className="label">MI PROGRESO</div><h3>Completa tu primera práctica para comenzar a ver tu progreso</h3><p className="legend">Aquí aparecerán las tendencias y la comparación entre tus sesiones completadas.</p></div><button type="button" className="btn pri" onClick={onChooseScenario}>Elegir escenario</button></div>;
  }
  return (
    <div className="row" style={{ marginBottom: '18px', alignItems: 'stretch' }}>
      <TrendChart progress={progress} />
      <div className="card" style={{ flex: 1, minWidth: 0 }}>
        <div className="label">AVANCE POR ÁREA</div>
        <table className="wf" style={{ marginTop: '10px' }}>
          <thead><tr><th>Área</th><th style={{ textAlign: 'center' }}>Actual</th><th style={{ textAlign: 'center' }}>Cambio</th></tr></thead>
          <tbody>
            {progress.areas.map((area, index) => (
              <tr key={area.areaKey}>
                <td><i className="progress-area-key" style={{ backgroundColor: colorForArea(area, index) }} />{areaLabel(area.areaKey)}</td>
                <td style={{ textAlign: 'center', fontWeight: 600 }}>{area.current ?? '—'}</td>
                <td className={area.change === null || area.change === 0 ? 'change-neutral' : area.change > 0 ? 'change-up' : 'change-down'} style={{ textAlign: 'center', fontWeight: 600 }}>
                  {area.change === null || area.change === 0 ? '—' : area.change > 0 ? `▲ +${area.change}` : `▼ ${Math.abs(area.change)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TrendChart({ progress }: { progress: ProgressResponse }) {
  const W = 600, H = 200, pl = 34, pr = 16, pt = 14, pb = 28;
  const count = progress.trendSessions.length;
  const getX = (index: number) => count === 1 ? (pl + W - pr) / 2 : pl + index * (W - pl - pr) / (count - 1);
  const getY = (value: number) => pt + (100 - value) / 100 * (H - pt - pb);
  const segments = (area: ProgressArea) => {
    const result: string[][] = [];
    let current: string[] = [];
    area.values.forEach((value, index) => {
      if (value === null) { if (current.length) result.push(current); current = []; }
      else current.push(`${getX(index)},${getY(value)}`);
    });
    if (current.length) result.push(current);
    return result;
  };
  return (
    <div className="card" style={{ flex: 1.45, minWidth: 0 }}>
      <div className="label">TENDENCIA DE LAS ÁREAS (ÚLTIMAS {progress.lastN} SESIONES)</div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', marginTop: '10px' }} role="img" aria-labelledby="progress-chart-title progress-chart-desc">
        <title id="progress-chart-title">Tendencia de puntajes por área</title>
        <desc id="progress-chart-desc">Comparación de {progress.areas.length} áreas en {count} sesiones completadas.</desc>
        {[0, 20, 40, 60, 80, 100].map((value) => <g key={value}><line x1={pl} y1={getY(value)} x2={W - pr} y2={getY(value)} stroke="var(--line)" strokeDasharray={value === 0 || value === 100 ? undefined : '3 3'} /><text x="4" y={getY(value) + 3} fontSize="10" fill="var(--muted)">{value}</text></g>)}
        {progress.areas.map((area, areaIndex) => {
          const color = colorForArea(area, areaIndex);
          return <g key={area.areaKey}>
            {segments(area).map((points, segmentIndex) => points.length > 1 && <polyline key={segmentIndex} points={points.join(' ')} fill="none" stroke={color} strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />)}
            {area.values.map((value, index) => value === null ? null : (
              <circle key={index} cx={getX(index)} cy={getY(value)} r="4" fill={color} tabIndex={0} role="img" aria-label={`${areaLabel(area.areaKey)}, ${progress.trendSessions[index]?.label}, ${progress.trendSessions[index]?.scenarioTitle}, ${formatDate(progress.trendSessions[index]?.completedAt)}, ${value} puntos`}>
                <title>{areaLabel(area.areaKey)} · {progress.trendSessions[index]?.label} · {formatDate(progress.trendSessions[index]?.completedAt)} · {progress.trendSessions[index]?.scenarioTitle}: {value}</title>
              </circle>
            ))}
          </g>;
        })}
        {progress.trendSessions.map((session, index) => <text key={session.sessionId} x={getX(index)} y={H - 6} fontSize="10" fill="var(--muted)" fontWeight="600" textAnchor="middle">{session.label}</text>)}
      </svg>
      <div className="progress-legend">
        {progress.areas.map((area, index) => <span key={area.areaKey}><i style={{ backgroundColor: colorForArea(area, index) }} />{areaLabel(area.areaKey)}</span>)}
      </div>
    </div>
  );
}

function DayPanel({ date, schedules, sessions, overdueBefore, busyId, onEdit, onCancel, onStart, onReport }: {
  date: string;
  schedules: ScheduleItem[];
  sessions: CalendarResponse['sessions'];
  overdueBefore: string;
  busyId: string;
  onEdit: (item: ScheduleItem) => void;
  onCancel: (item: ScheduleItem) => void;
  onStart: (item: ScheduleItem) => void;
  onReport: (sessionId: string) => void;
}) {
  return <section className="progress-day-panel" aria-label={`Actividades del ${formatDate(date)}`}>
    <strong>{formatDate(date)}</strong>
    {!schedules.length && !sessions.length && <p className="legend">No hay actividades para este día.</p>}
    {schedules.filter((item) => item.status === 'scheduled').map((item) => (
      <div className="progress-day-item" key={item.id}>
        <div><span className="progress-status scheduled">{item.date < overdueBefore ? 'Pendiente atrasada' : 'Agendada'}</span><strong>{item.scenario?.title ?? 'Escenario no disponible'}</strong>{item.scenario && !item.scenario.available && <small>El escenario fue archivado. Selecciona otro para poder iniciar.</small>}</div>
        <div className="progress-actions">
          <button type="button" className="btn" onClick={() => onEdit(item)}>Editar</button>
          <button type="button" className="btn" disabled={busyId === item.id} onClick={() => onCancel(item)}>Cancelar</button>
          <button type="button" className="btn pri" disabled={!item.scenario?.available || busyId === item.id} onClick={() => onStart(item)}>{busyId === item.id ? 'Iniciando…' : 'Iniciar práctica'}</button>
        </div>
      </div>
    ))}
    {sessions.map((session) => (
      <div className="progress-day-item" key={session.sessionId}>
        <div>
          <span className="progress-status completed">Realizada</span>
          <strong>{session.scenario.title}</strong>
          <small>
            {session.completedAt ? `Hora: ${new Date(session.completedAt).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false })} · ` : ''}
            Puntaje: {session.report.overallScore ?? '—'}
          </small>
        </div>
        <button type="button" className="btn" onClick={() => onReport(session.sessionId)}>Ver informe</button>
      </div>
    ))}
  </section>;
}
