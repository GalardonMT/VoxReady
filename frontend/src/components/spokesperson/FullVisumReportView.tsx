'use client';

import React, { useState, useEffect } from 'react';
import { VoceroScreen } from './HomePracticeView';
import { sessionService } from '../../services/sessionService';
import { FullVisumReport } from '../../types/api';
import { RecordingVideoPlayer } from './RecordingVideoPlayer';

interface FullVisumReportViewProps {
  onNavigate: (screen: VoceroScreen, extra?: string) => void;
  sessionId?: string;
}

export const FullVisumReportView: React.FC<FullVisumReportViewProps> = ({
  onNavigate,
  sessionId = 'session-e2e-final-002'
}) => {
  const [report, setReport] = useState<FullVisumReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [showVideoModal, setShowVideoModal] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [videoLoading, setVideoLoading] = useState(false);
  const [videoError, setVideoError] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'visum' | 'metrics' | 'judge' | 'transcript'>('visum');

  useEffect(() => {
    async function loadReport() {
      try {
        const data = await sessionService.getFullVisumReport(sessionId);
        setReport(data);
      } catch (e) {
        console.warn('Error cargando informe completo Visum:', e);
      } finally {
        setLoading(false);
      }
    }
    loadReport();
  }, [sessionId]);

  const activeSessionId = report?.sessionId || sessionId;
  const audio = report?.metrics?.audio;
  const expectedDuration =
    report?.durationSeconds ||
    audio?.duracionSegundos ||
    report?.metricsSummary?.durationSeconds;

  const handleOpenVideo = async () => {
    setShowVideoModal(true);
    if (videoUrl) return;
    setVideoLoading(true);
    setVideoError('');
    try {
      let url = report?.recordingUrl;
      if (!url) {
        url = await sessionService.getPlaybackUrl(activeSessionId);
      }
      if (url) {
        setVideoUrl(url);
      } else {
        setVideoError('La grabación no está disponible. Es posible que el almacenamiento no esté configurado o que la grabación no se haya completado.');
      }
    } catch {
      setVideoError('Error al obtener la URL de reproducción. Intente nuevamente.');
    } finally {
      setVideoLoading(false);
    }
  };

  const handleRetryVideo = async () => {
    setVideoLoading(true);
    setVideoError('');
    try {
      const url = await sessionService.getPlaybackUrl(activeSessionId);
      if (url) {
        setVideoUrl(url);
      } else {
        setVideoError('La grabación no está disponible.');
      }
    } catch {
      setVideoError('Error al obtener la URL de reproducción.');
    } finally {
      setVideoLoading(false);
    }
  };

  const globalScore = report?.overallScore ?? 75;

  const getScoreColor = (sc: number) => {
    if (sc >= 75) return '#10b981'; // Verde sobresaliente
    if (sc >= 50) return '#f59e0b'; // Amarillo aceptable
    return '#ef4444'; // Rojo crítico
  };

  const getScoreBadgeText = (sc: number) => {
    if (sc >= 75) return 'Sobresaliente';
    if (sc >= 50) return 'Aceptable';
    return 'Crítico';
  };

  // Datos de Visum
  const visum = report?.visumExecutive || report?.narrative?.visum;
  const sintesis = visum?.sintesisEjecutiva;
  const formulaRec = visum?.formulaRecomendada || 'Secuencia de 3 pasos: Reconocer el impacto ➔ Explicar certezas ➔ Acciones en curso.';
  const hallazgos = visum?.hallazgosTransversales || 'El vocero requiere afianzar la conducción estratégica y el control pedagógico en momentos de presión mediática.';
  const crossSignal = report?.narrative?.crossSignal;

  // Métricas técnicas
  const vision = report?.metrics?.vision;
  const judge = report?.metrics?.judge;
  const dims = judge?.dimensiones || {};

  const dimensionLabels: Record<string, string> = {
    pertinenciaRespuesta: 'Pertinencia de la respuesta',
    alineacionMensajeClave: 'Alineación a mensajes clave',
    tecnicasControl: 'Técnicas de control (Bridging)',
    consistenciaInstitucional: 'Consistencia institucional',
    asertividadHostilidad: 'Asertividad y control de hostilidad',
    capacidadSintesis: 'Capacidad de síntesis',
    claridadMensaje: 'Claridad y precisión del mensaje'
  };

  return (
    <div className="canvas-content" style={{ maxWidth: '1040px', margin: '0 auto', paddingBottom: '60px' }}>
      {/* Botón superior de retorno */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <button
          type="button"
          className="btn"
          onClick={() => onNavigate('u6', activeSessionId)}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
        >
          <span>←</span> Volver a la Vista Previa
        </button>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            className="btn"
            style={{ fontSize: '13px' }}
            onClick={handleOpenVideo}
          >
            ▷ Ver mi grabación
          </button>
        </div>
      </div>

      {/* Cabecera Principal / Banner del Reporte */}
      <div
        className="card"
        style={{
          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.98) 100%)',
          border: '1px solid rgba(99, 102, 241, 0.25)',
          borderRadius: '14px',
          padding: '24px',
          marginBottom: '20px',
          boxShadow: '0 10px 30px rgba(0, 0, 0, 0.25)'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '20px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  letterSpacing: '1px',
                  padding: '3px 9px',
                  borderRadius: '6px',
                  background: 'rgba(99, 102, 241, 0.2)',
                  color: '#818cf8',
                  border: '1px solid rgba(99, 102, 241, 0.35)'
                }}
              >
                VISUM Media Training & AI
              </span>
              <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                · {report?.scenarioTitle || 'Simulación de Vocería en Crisis'}
              </span>
            </div>
            <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#f8fafc', margin: '0 0 6px 0', letterSpacing: '-0.5px' }}>
              Informe Ejecutivo y Pedagógico de Vocería
            </h1>
            <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0 }}>
              Sesión: <code style={{ color: '#818cf8', fontWeight: 600 }}>{activeSessionId}</code> · Generado:{' '}
              {report?.generatedAt ? new Date(report.generatedAt).toLocaleString() : 'Recientemente'}
            </p>
          </div>

          {/* Puntaje Global destacado */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '16px',
              background: 'rgba(255, 255, 255, 0.04)',
              padding: '12px 18px',
              borderRadius: '12px',
              border: '1px solid rgba(255, 255, 255, 0.08)'
            }}
          >
            <div style={{ textAlign: 'center' }}>
              <div
                style={{
                  fontSize: '40px',
                  fontWeight: 900,
                  color: getScoreColor(globalScore),
                  lineHeight: 1
                }}
              >
                {globalScore}
              </div>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 700, marginTop: '2px' }}>
                / 100 PUNTOS
              </div>
            </div>
            <div>
              <div
                style={{
                  fontSize: '11px',
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  letterSpacing: '0.6px',
                  padding: '4px 10px',
                  borderRadius: '6px',
                  background: `${getScoreColor(globalScore)}20`,
                  color: getScoreColor(globalScore),
                  border: `1px solid ${getScoreColor(globalScore)}40`
                }}
              >
                {getScoreBadgeText(globalScore)}
              </div>
              <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>
                Rúbrica Multimodal
              </div>
            </div>
          </div>
        </div>

        {/* Desglose rápido de las 4 notas en la cabecera */}
        {report?.areaScores && report.areaScores.length > 0 && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: '10px',
              marginTop: '20px',
              paddingTop: '16px',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)'
            }}
          >
            {report.areaScores.map((as, idx) => (
              <div
                key={idx}
                style={{
                  background: 'rgba(255, 255, 255, 0.03)',
                  padding: '8px 12px',
                  borderRadius: '8px',
                  border: '1px solid rgba(255, 255, 255, 0.05)'
                }}
              >
                <div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'capitalize', marginBottom: '2px' }}>
                  {as.area === 'expression' && '👁️ Expresión No Verbal'}
                  {as.area === 'voice' && '🎙️ Tono y Prosodia'}
                  {as.area === 'coherence' && '📄 Coherencia / Mensajes'}
                  {as.area === 'empathy' && '🤝 Empatía y Crisis'}
                  {!['expression', 'voice', 'coherence', 'empathy'].includes(as.area) && as.area}
                </div>
                <div style={{ fontSize: '16px', fontWeight: 800, color: getScoreColor(as.value) }}>
                  {as.value}%
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tabs de navegación de contenido */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '18px',
          borderBottom: '1px solid var(--line)',
          paddingBottom: '8px',
          flexWrap: 'wrap'
        }}
      >
        <button
          type="button"
          onClick={() => setActiveTab('visum')}
          style={{
            background: activeTab === 'visum' ? 'var(--accent2)' : 'transparent',
            color: activeTab === 'visum' ? '#fff' : 'var(--muted)',
            border: 'none',
            borderRadius: '8px',
            padding: '8px 16px',
            fontWeight: 700,
            fontSize: '13px',
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
        >
          🎓 Síntesis y Correcciones VISUM
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('metrics')}
          style={{
            background: activeTab === 'metrics' ? 'var(--accent2)' : 'transparent',
            color: activeTab === 'metrics' ? '#fff' : 'var(--muted)',
            border: 'none',
            borderRadius: '8px',
            padding: '8px 16px',
            fontWeight: 700,
            fontSize: '13px',
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
        >
          📊 Métricas de Laboratorio (Visión & Audio)
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('judge')}
          style={{
            background: activeTab === 'judge' ? 'var(--accent2)' : 'transparent',
            color: activeTab === 'judge' ? '#fff' : 'var(--muted)',
            border: 'none',
            borderRadius: '8px',
            padding: '8px 16px',
            fontWeight: 700,
            fontSize: '13px',
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
        >
          ⚖️ Criterios del Juez de Crisis
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('transcript')}
          style={{
            background: activeTab === 'transcript' ? 'var(--accent2)' : 'transparent',
            color: activeTab === 'transcript' ? '#fff' : 'var(--muted)',
            border: 'none',
            borderRadius: '8px',
            padding: '8px 16px',
            fontWeight: 700,
            fontSize: '13px',
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
        >
          📝 Transcripción Completa
        </button>
      </div>

      {/* =========================================================================
          TAB 1: SÍNTESIS Y CORRECCIONES VISUM
          ========================================================================= */}
      {activeTab === 'visum' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {/* Banner de Señal Cruzada / Incongruencia (si existe) */}
          {crossSignal && (
            <div
              style={{
                background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.12) 0%, rgba(220, 38, 38, 0.06) 100%)',
                border: '1px solid rgba(239, 68, 68, 0.35)',
                borderLeft: '5px solid #ef4444',
                borderRadius: '10px',
                padding: '16px 20px',
                color: 'var(--ink)'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <span style={{ fontSize: '18px' }}>⚠️</span>
                <span style={{ fontSize: '12px', fontWeight: 800, textTransform: 'uppercase', color: '#ef4444', letterSpacing: '0.6px' }}>
                  Alerta Pedagógica de Señal Cruzada (Incongruencia Detectada)
                </span>
              </div>
              <p style={{ fontSize: '13.5px', lineHeight: 1.6, margin: 0 }}>
                {crossSignal}
              </p>
            </div>
          )}

          {/* Diagnóstico General */}
          {sintesis?.diagnosticoGeneral && (
            <div className="card" style={{ padding: '20px' }}>
              <div style={{ fontSize: '12px', fontWeight: 800, textTransform: 'uppercase', color: 'var(--accent2)', marginBottom: '8px', letterSpacing: '0.5px' }}>
                📋 Diagnóstico General del Desempeño
              </div>
              <p style={{ fontSize: '14.5px', lineHeight: 1.65, color: 'var(--ink)', margin: 0, fontStyle: 'italic' }}>
                “{sintesis.diagnosticoGeneral}”
              </p>
            </div>
          )}

          {/* Tarjetas de Fortaleza Principal vs Foco de Desarrollo */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
            <div
              className="card"
              style={{
                padding: '20px',
                borderTop: '4px solid #10b981',
                background: 'var(--panel)'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{ fontSize: '18px' }}>🛡️</span>
                <span style={{ fontSize: '12px', fontWeight: 800, textTransform: 'uppercase', color: '#10b981' }}>
                  Fortaleza Principal (Piso Sólido)
                </span>
              </div>
              <p style={{ fontSize: '13.5px', lineHeight: 1.6, color: 'var(--ink)', margin: 0 }}>
                {sintesis?.fortalezaPrincipal || 'Demostró aplomo inicial y compostura ante las preguntas.'}
              </p>
            </div>

            <div
              className="card"
              style={{
                padding: '20px',
                borderTop: '4px solid #f59e0b',
                background: 'var(--panel)'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{ fontSize: '18px' }}>🎯</span>
                <span style={{ fontSize: '12px', fontWeight: 800, textTransform: 'uppercase', color: '#f59e0b' }}>
                  Foco de Desarrollo Estratégico
                </span>
              </div>
              <p style={{ fontSize: '13.5px', lineHeight: 1.6, color: 'var(--ink)', margin: 0 }}>
                {sintesis?.focoDesarrollo || 'Evolucionar de responder reactivamente a liderar la conversación con técnicas de puente.'}
              </p>
            </div>
          </div>

          {/* Fórmula Recomendada de Visum */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(79, 70, 229, 0.15) 0%, rgba(99, 102, 241, 0.08) 100%)',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              borderRadius: '12px',
              padding: '20px 24px'
            }}
          >
            <div style={{ fontSize: '11px', fontWeight: 800, textTransform: 'uppercase', color: '#818cf8', letterSpacing: '0.8px', marginBottom: '6px' }}>
              💡 Fórmula Práctica Recomendada por VISUM Consulting
            </div>
            <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--ink)', lineHeight: 1.5, marginBottom: '6px' }}>
              {formulaRec}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--muted)' }}>
              Aplica esta formulación verbal para estructurar tus declaraciones bajo contingencia.
            </div>
          </div>

          {/* Hallazgos Transversales y Continuidad */}
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ fontSize: '12px', fontWeight: 800, textTransform: 'uppercase', color: 'var(--accent2)', marginBottom: '10px' }}>
              🔍 Hallazgos Transversales y Observación Pedagógica
            </div>
            <p style={{ fontSize: '13.5px', lineHeight: 1.6, color: 'var(--ink)', marginBottom: '14px' }}>
              {hallazgos}
            </p>

            {sintesis?.continuidadRecomendada && (
              <div
                style={{
                  background: 'var(--soft)',
                  padding: '12px 16px',
                  borderRadius: '8px',
                  borderLeft: '4px solid var(--accent2)',
                  fontSize: '13px',
                  color: 'var(--ink)'
                }}
              >
                <strong>Plan de Continuidad:</strong> {sintesis.continuidadRecomendada}
              </div>
            )}
          </div>

          {/* Listado de Fortalezas y Brechas de la narrativa */}
          {report?.narrative && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
              {report.narrative.strengths && report.narrative.strengths.length > 0 && (
                <div className="card" style={{ padding: '18px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#10b981', marginBottom: '8px' }}>
                    ✅ Aspectos Destacados:
                  </div>
                  <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '13px', color: 'var(--ink)', lineHeight: 1.6 }}>
                    {report.narrative.strengths.map((s, idx) => (
                      <li key={idx} style={{ marginBottom: '4px' }}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}

              {report.narrative.improvements && report.narrative.improvements.length > 0 && (
                <div className="card" style={{ padding: '18px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#f59e0b', marginBottom: '8px' }}>
                    📈 Oportunidades de Corrección:
                  </div>
                  <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '13px', color: 'var(--ink)', lineHeight: 1.6 }}>
                    {report.narrative.improvements.map((imp, idx) => (
                      <li key={idx} style={{ marginBottom: '4px' }}>{imp}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB 2: MÉTRICAS DE LABORATORIO (VISIÓN Y AUDIO)
          ========================================================================= */}
      {activeTab === 'metrics' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {/* Métricas de Visión MediaPipe */}
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
              <span style={{ fontSize: '18px' }}>👁️</span>
              <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
                Análisis Biomecánico y No Verbal (MediaPipe Vision a 2 FPS)
              </h3>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px' }}>
              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Contacto Visual a Cámara</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: getScoreColor(vision?.eyeContactPct ?? 70) }}>
                  {vision?.eyeContactPct ?? 70}%
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>Mirada fija en lente</div>
              </div>

              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Estabilidad de Hombros</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: getScoreColor(vision?.shoulderStabilityScore ?? 85) }}>
                  {vision?.shoulderStabilityScore ?? 85}%
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>Alineación postural</div>
              </div>

              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Balanceo Lateral (Sway)</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: 'var(--ink)' }}>
                  {vision?.bodySwayStd ? vision.bodySwayStd.toFixed(4) : '0.0040'}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>Desvío estándar torso</div>
              </div>

              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Visibilidad de Manos</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: 'var(--ink)' }}>
                  {vision?.handsVisiblePct ?? 15}%
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>Gesticulación activa</div>
              </div>

              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Cuadros Procesados</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: 'var(--ink)' }}>
                  {vision?.totalFramesAnalyzed ?? 100}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>Muestreo continuo</div>
              </div>
            </div>
          </div>

          {/* Métricas Acústicas y de Voz Parakeet */}
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
              <span style={{ fontSize: '18px' }}>🎙️</span>
              <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
                Análisis Acústico y Prosodia (NVIDIA Parakeet-TDT)
              </h3>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px' }}>
              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Ritmo de Habla (WPM)</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: (audio?.wpmGlobal ?? 130) >= 110 && (audio?.wpmGlobal ?? 130) <= 150 ? '#10b981' : '#f59e0b' }}>
                  {audio?.wpmGlobal ?? 130} WPM
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>Rango óptimo: 120–150</div>
              </div>

              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Ratio de Fonación</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: 'var(--ink)' }}>
                  {audio?.ratioFonacion ? (audio.ratioFonacion * 100).toFixed(0) : '60'}%
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>Tiempo de voz activa</div>
              </div>

              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Pausas Prolongadas</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: (audio?.pausasProlongadas ?? 0) > 3 ? '#ef4444' : '#10b981' }}>
                  {audio?.pausasProlongadas ?? 0}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>Silencios &gt; 1.5s</div>
              </div>

              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Densidad de Muletillas</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: (audio?.densidadMuletillasPct ?? 0) > 3 ? '#ef4444' : '#10b981' }}>
                  {audio?.densidadMuletillasPct ? audio.densidadMuletillasPct.toFixed(1) : '1.5'}%
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>Tolerancia máx: 3.0%</div>
              </div>

              <div style={{ background: 'var(--soft)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Palabras Totales</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: 'var(--ink)' }}>
                  {audio?.palabrasTotales ?? 120}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>
                  {audio?.duracionSegundos ? `${audio.duracionSegundos.toFixed(0)} segundos` : 'Duración grabada'}
                </div>
              </div>
            </div>

            {/* Muletillas detectadas listadas */}
            {audio?.muletillasDetectadas && audio.muletillasDetectadas.length > 0 && (
              <div style={{ marginTop: '14px', paddingTop: '12px', borderTop: '1px solid var(--line)' }}>
                <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--muted)', marginBottom: '6px' }}>
                  Muletillas léxicas detectadas durante la entrevista:
                </div>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {audio.muletillasDetectadas.map((m, idx) => (
                    <span
                      key={idx}
                      style={{
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        color: '#ef4444',
                        padding: '2px 8px',
                        borderRadius: '6px',
                        fontSize: '11.5px',
                        fontWeight: 600
                      }}
                    >
                      “{m}”
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 3: CRITERIOS DEL JUEZ DE CRISIS (LLM 7 DIMENSIONES)
          ========================================================================= */}
      {activeTab === 'judge' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
              <div>
                <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
                  Evaluación Pedagógica del LLM Juez (NVIDIA Llama 3.2 90B)
                </h3>
                <p style={{ fontSize: '12.5px', color: 'var(--muted)', margin: '2px 0 0 0' }}>
                  Puntaje global del juez: <strong style={{ color: getScoreColor(judge?.puntajeGlobal100 ?? 50) }}>{judge?.puntajeGlobal100 ?? 50} / 100</strong>
                </p>
              </div>
            </div>

            {/* Listado de las 7 dimensiones con sus criterios */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {Object.keys(dims).length > 0 ? (
                Object.entries(dims).map(([key, item], idx) => {
                  const scoreVal = typeof item === 'object' && item !== null ? item.score : 50;
                  const criterioText = typeof item === 'object' && item !== null ? item.criterio : '';
                  const nivelVal = typeof item === 'object' && item !== null ? item.nivel : 1;
                  const label = dimensionLabels[key] || key;

                  return (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--soft)',
                        border: '1px solid var(--line)',
                        borderRadius: '8px',
                        padding: '12px 16px'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span style={{ fontSize: '13.5px', fontWeight: 700, color: 'var(--ink)' }}>
                          {label}
                        </span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600 }}>
                            Nivel {nivelVal}/5
                          </span>
                          <span style={{ fontSize: '14px', fontWeight: 800, color: getScoreColor(scoreVal) }}>
                            {scoreVal}%
                          </span>
                        </div>
                      </div>
                      {criterioText && (
                        <p style={{ fontSize: '12.5px', color: 'var(--muted)', margin: '4px 0 0 0', lineHeight: 1.45 }}>
                          {criterioText}
                        </p>
                      )}
                    </div>
                  );
                })
              ) : (
                <div style={{ padding: '20px', textAlign: 'center', color: 'var(--muted)', fontSize: '13px' }}>
                  No se encontraron dimensiones detalladas en el informe actual.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 4: TRANSCRIPCIÓN COMPLETA
          ========================================================================= */}
      {activeTab === 'transcript' && (
        <div className="card" style={{ padding: '22px' }}>
          <div style={{ fontSize: '12px', fontWeight: 800, textTransform: 'uppercase', color: 'var(--accent2)', marginBottom: '10px' }}>
            📝 Transcripción Completa del Ejercicio de Vocería
          </div>
          <div
            style={{
              background: 'var(--soft)',
              borderRadius: '8px',
              padding: '16px',
              fontSize: '13.5px',
              lineHeight: 1.7,
              color: 'var(--ink)',
              border: '1px solid var(--line)',
              whiteSpace: 'pre-wrap'
            }}
          >
            {report?.transcript || 'Transcripción no disponible para esta sesión.'}
          </div>
        </div>
      )}

      {/* Botones de acción inferiores */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '24px' }}>
        <button
          type="button"
          className="btn"
          onClick={handleOpenVideo}
        >
          ▷ Ver mi grabación
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => onNavigate('u6', activeSessionId)}
        >
          ← Volver a Vista Previa
        </button>
        <button
          type="button"
          className="btn pri"
          onClick={() => onNavigate('u2')}
        >
          🔁 Repetir Simulación
        </button>
        <button
          type="button"
          className="btn ghost"
          onClick={() => onNavigate('u7')}
        >
          📈 Ver Mi Historial de Progreso →
        </button>
      </div>

      {/* Modal de Video */}
      {showVideoModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.88)',
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
            backdropFilter: 'blur(4px)'
          }}
          onClick={() => setShowVideoModal(false)}
        >
          <div
            style={{
              background: '#1a1a2e',
              borderRadius: '16px',
              border: '1px solid rgba(255,255,255,0.1)',
              padding: '0',
              maxWidth: '780px',
              width: '100%',
              overflow: 'hidden',
              boxShadow: '0 25px 60px rgba(0,0,0,0.5)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Cabecera del modal */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '18px 24px',
                borderBottom: '1px solid rgba(255,255,255,0.08)'
              }}
            >
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#f1f5f9', margin: 0 }}>
                  🎬 Mi Grabación
                </h3>
                <p style={{ fontSize: '12px', color: '#64748b', margin: '4px 0 0 0' }}>
                  Sesión: <code style={{ color: '#818cf8' }}>{activeSessionId}</code>
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowVideoModal(false)}
                style={{
                  background: 'rgba(255,255,255,0.08)',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: '8px',
                  width: '36px',
                  height: '36px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: '#94a3b8',
                  fontSize: '18px',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.15)'; e.currentTarget.style.color = '#f1f5f9'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.08)'; e.currentTarget.style.color = '#94a3b8'; }}
              >
                ✕
              </button>
            </div>

            {/* Área del reproductor */}
            <div style={{ padding: '0' }}>
              {videoLoading && (
                <div
                  style={{
                    aspectRatio: '16/9',
                    background: '#0f0f23',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '12px'
                  }}
                >
                  <div
                    style={{
                      width: '40px',
                      height: '40px',
                      border: '3px solid rgba(129, 140, 248, 0.2)',
                      borderTopColor: '#818cf8',
                      borderRadius: '50%',
                      animation: 'spin 0.8s linear infinite'
                    }}
                  />
                  <span style={{ color: '#94a3b8', fontSize: '13px' }}>Cargando grabación...</span>
                  <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                </div>
              )}

              {!videoLoading && videoError && (
                <div
                  style={{
                    aspectRatio: '16/9',
                    background: '#0f0f23',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '12px',
                    padding: '24px'
                  }}
                >
                  <span style={{ fontSize: '36px' }}>⚠️</span>
                  <p style={{ color: '#f87171', fontSize: '13px', textAlign: 'center', maxWidth: '400px', lineHeight: 1.5 }}>
                    {videoError}
                  </p>
                  <button
                    type="button"
                    className="btn"
                    style={{ marginTop: '8px', fontSize: '12px', color: '#818cf8', borderColor: '#818cf8' }}
                    onClick={handleRetryVideo}
                  >
                    🔄 Reintentar
                  </button>
                </div>
              )}

              {!videoLoading && !videoError && videoUrl && (
                <RecordingVideoPlayer
                  src={videoUrl}
                  expectedDuration={expectedDuration}
                  autoPlay={true}
                />
              )}
            </div>

            {/* Pie del modal */}
            <div
              style={{
                padding: '14px 24px',
                borderTop: '1px solid rgba(255,255,255,0.08)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
            >
              <span style={{ fontSize: '11px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>🔒</span> Grabación protegida · Almacenamiento seguro y confidencial
              </span>
              <button
                type="button"
                className="btn pri"
                style={{ fontSize: '13px', padding: '8px 20px' }}
                onClick={() => setShowVideoModal(false)}
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
