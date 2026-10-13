'use client';

import React, { useState, useEffect } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';
import { INITIAL_PROGRESS } from '../../mock/mockData';
import { sessionService } from '../../services/sessionService';
import { SessionHistoryItem } from '../../types/api';

interface ProgressViewProps {
  onNavigate: (screen: VoceroScreen, extra?: string) => void;
}

export const ProgressView: React.FC<ProgressViewProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.u7;

  // Session History State
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
    loadSessions();
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

  const formatDate = (isoString?: string) => {
    if (!isoString) return 'Fecha no registrada';
    try {
      const dateObj = new Date(isoString);
      return new Intl.DateTimeFormat('es', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      }).format(dateObj);
    } catch {
      return isoString;
    }
  };

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

  // Calendar State
  const now = new Date();
  const [calYear, setCalYear] = useState(now.getFullYear());
  const [calMonth, setCalMonth] = useState(now.getMonth());
  const [selectedDay, setSelectedDay] = useState<number | null>(15);
  const [isScheduled, setIsScheduled] = useState(false);

  const prevMonth = () => {
    if (calMonth === 0) {
      setCalMonth(11);
      setCalYear((y) => y - 1);
    } else {
      setCalMonth((m) => m - 1);
    }
  };

  const nextMonth = () => {
    if (calMonth === 11) {
      setCalMonth(0);
      setCalYear((y) => y + 1);
    } else {
      setCalMonth((m) => m + 1);
    }
  };

  // SVG Chart Calculations
  const chartData = INITIAL_PROGRESS.chartData;
  const chartColors = INITIAL_PROGRESS.chartColors;
  const W = 600;
  const H = 200;
  const pl = 34;
  const pr = 16;
  const pt = 14;
  const pb = 24;
  const numPoints = chartData[0].length;

  const getX = (i: number) => Math.round(pl + (i * (W - pl - pr)) / (numPoints - 1));
  const getY = (v: number) => Math.round(pt + ((100 - v) / (100 - 30)) * (H - pt - pb));

  // Calendar Grid generation
  const firstDayIndex = (new Date(calYear, calMonth, 1).getDay() + 6) % 7;
  const totalDays = new Date(calYear, calMonth + 1, 0).getDate();
  const emptyDays = Array.from({ length: firstDayIndex });
  const monthDays = Array.from({ length: totalDays }, (_, i) => i + 1);

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

      {/* Top Row: Trend Chart + Table */}
      <div className="row" style={{ marginBottom: '18px', alignItems: 'stretch' }}>
        {/* Trend Chart */}
        <div className="card" style={{ flex: 1.45, minWidth: 0 }}>
          <div className="label">{d.trendL}</div>
          <div style={{ marginTop: '10px' }}>
            <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
              {/* Horizontal Grid lines */}
              {[40, 60, 80, 100].map((val) => (
                <g key={val}>
                  <line
                    x1={pl}
                    y1={getY(val)}
                    x2={W - pr}
                    y2={getY(val)}
                    style={{ stroke: 'var(--line)' }}
                    strokeWidth="1"
                    strokeDasharray={val === 100 ? '0' : '3 3'}
                  />
                  <text
                    x="6"
                    y={getY(val) + 3}
                    fontSize="10"
                    style={{ fill: 'var(--muted)', fontWeight: 500 }}
                  >
                    {val}
                  </text>
                </g>
              ))}

              {/* Data Lines & Points */}
              {chartData.map((series, si) => {
                const points = series.map((v, i) => `${getX(i)},${getY(v)}`).join(' ');
                return (
                  <g key={si}>
                    <polyline
                      points={points}
                      fill="none"
                      stroke={chartColors[si]}
                      strokeWidth="2.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    {series.map((v, i) => (
                      <circle
                        key={i}
                        cx={getX(i)}
                        cy={getY(v)}
                        r="3.5"
                        fill={chartColors[si]}
                      />
                    ))}
                  </g>
                );
              })}

              {/* X Axis Labels */}
              {Array.from({ length: numPoints }).map((_, i) => (
                <text
                  key={i}
                  x={getX(i)}
                  y={H - 6}
                  fontSize="10"
                  style={{ fill: 'var(--muted)', fontWeight: 600 }}
                  textAnchor="middle"
                >
                  S{i + 1}
                </text>
              ))}
            </svg>
          </div>

          <div
            style={{
              display: 'flex',
              gap: '16px',
              flexWrap: 'wrap',
              marginTop: '12px',
              paddingTop: '8px',
              borderTop: '1px solid var(--line)'
            }}
          >
            {d.series.map((s, i) => (
              <span
                key={i}
                style={{
                  fontSize: '11.5px',
                  color: 'var(--muted)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span
                  style={{
                    width: '11px',
                    height: '11px',
                    borderRadius: '2px',
                    backgroundColor: chartColors[i]
                  }}
                />
                {s}
              </span>
            ))}
          </div>
        </div>

        {/* Progress Table */}
        <div className="card" style={{ flex: 1, minWidth: 0 }}>
          <div className="label">{d.tblTitle}</div>
          <table className="wf" style={{ marginTop: '10px' }}>
            <thead>
              <tr>
                {d.tblCols.map((h, i) => (
                  <th key={i} style={i ? { textAlign: 'center' } : {}}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.series.map((s, i) => {
                const seriesData = chartData[i];
                const cur = seriesData[seriesData.length - 1];
                const change = cur - seriesData[0];
                return (
                  <tr key={i}>
                    <td>
                      <span
                        style={{
                          display: 'inline-block',
                          width: '9px',
                          height: '9px',
                          borderRadius: '2px',
                          backgroundColor: chartColors[i],
                          marginRight: '8px'
                        }}
                      />
                      {s}
                    </td>
                    <td style={{ textAlign: 'center', fontWeight: 600 }}>{cur}</td>
                    <td
                      style={{
                        textAlign: 'center',
                        color: 'var(--success)',
                        fontWeight: 600
                      }}
                    >
                      ▲ +{change}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Bottom Row: Recommendations + Calendar */}
      <div className="grid2">
        {/* Recommendations */}
        <div className="card">
          <div className="label">{d.recoTitle}</div>
          {d.recos.map((r, i) => (
            <div
              key={i}
              className="box"
              style={{ padding: '14px', marginBottom: '10px' }}
            >
              <div style={{ fontSize: '13.5px', fontWeight: 600, marginBottom: '4px' }}>
                💡 {r.t}
              </div>
              <div className="legend" style={{ margin: '0 0 10px', fontSize: '12px' }}>
                {r.d}
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => onNavigate('lesson', r.t)}
              >
                {t.openLesson} →
              </button>
            </div>
          ))}
        </div>

        {/* Calendar Scheduler */}
        <div className="card">
          <div className="label">{d.calTitle}</div>
          <div className="legend" style={{ margin: '-2px 0 12px' }}>
            {d.calHelp}
          </div>

          <div className="calhead">
            <button
              type="button"
              className="btn ghost"
              style={{ padding: '4px 10px' }}
              onClick={prevMonth}
            >
              ‹
            </button>
            <span
              style={{
                fontSize: '13.5px',
                fontWeight: 600,
                textTransform: 'capitalize'
              }}
            >
              {d.months[calMonth]} {calYear}
            </span>
            <button
              type="button"
              className="btn ghost"
              style={{ padding: '4px 10px' }}
              onClick={nextMonth}
            >
              ›
            </button>
          </div>

          <div className="calgrid">
            {d.weekdays.map((w, idx) => (
              <div key={idx} className="dow">
                {w}
              </div>
            ))}
          </div>

          <div className="calgrid" style={{ marginTop: '6px' }}>
            {emptyDays.map((_, i) => (
              <div key={`empty-${i}`} />
            ))}
            {monthDays.map((day) => {
              const isSelected = selectedDay === day;
              return (
                <div
                  key={day}
                  className={`calday ${isSelected ? 'sel' : ''}`}
                  onClick={() => {
                    setSelectedDay(day);
                    setIsScheduled(false);
                  }}
                >
                  {day}
                </div>
              );
            })}
          </div>

          <div
            style={{
              marginTop: '16px',
              paddingTop: '12px',
              borderTop: '1px solid var(--line)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}
          >
            <span style={{ fontSize: '12.5px', color: 'var(--muted)' }}>
              {d.nextLabel}{' '}
              <b style={{ color: 'var(--accent2)' }}>
                {selectedDay
                  ? `${selectedDay} de ${d.months[calMonth]}`
                  : d.calNone}
              </b>
            </span>

            <button
              type="button"
              className="btn pri"
              onClick={() => setIsScheduled(true)}
            >
              {isScheduled ? '✓ Agendado' : d.calBtn}
            </button>
          </div>
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
                            <span>📅 {formatDate(s.createdAt)}</span>
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
                            background: 'linear-gradient(135deg, #4338ca 0%, #3730a3 100%)',
                            color: '#ffffff',
                            fontWeight: 600,
                            fontSize: '12.5px',
                            padding: '7px 14px',
                            borderRadius: '8px',
                            border: 'none',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            boxShadow: '0 2px 8px rgba(67, 56, 202, 0.25)'
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
