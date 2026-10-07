'use client';

import React, { useState, useEffect } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';
import { sessionService } from '../../services/sessionService';
import { CoachReport } from '../../types/api';

interface CoachReportViewProps {
  onNavigate: (screen: VoceroScreen) => void;
  sessionId?: string;
}

export const CoachReportView: React.FC<CoachReportViewProps> = ({
  onNavigate,
  sessionId = 'session-e2e-final-002'
}) => {
  const { t } = useI18n();
  const d = t.L.u6;
  const [showVideoModal, setShowVideoModal] = useState(false);
  const [report, setReport] = useState<CoachReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [videoLoading, setVideoLoading] = useState(false);
  const [videoError, setVideoError] = useState<string>('');

  useEffect(() => {
    async function loadReport() {
      try {
        const data = await sessionService.getCoachReport(sessionId);
        setReport(data);
      } catch (e) {
        console.warn('Error cargando coach report:', e);
      } finally {
        setLoading(false);
      }
    }
    loadReport();
  }, [sessionId]);

  const globalScore = report?.globalScore ?? 75;
  const goodItems = report?.goodAspects && report.goodAspects.length > 0 ? report.goodAspects : d.goodItems;
  const improveItems = report?.improveAspects && report.improveAspects.length > 0 ? report.improveAspects : d.improveItems;
  const quote = report?.crossSignalQuote || d.quote;

  const areaScores = report?.areas && report.areas.length === 4
    ? [
        { name: d.areas[0], score: report.areas[0].score, icon: '👁️', channel: report.areas[0].criteria || 'MediaPipe Vision' },
        { name: d.areas[1], score: report.areas[1].score, icon: '🎙️', channel: report.areas[1].criteria || 'Voz / Parakeet' },
        { name: d.areas[2], score: report.areas[2].score, icon: '📄', channel: report.areas[2].criteria || 'NVIDIA LLM Apego' },
        { name: d.areas[3], score: report.areas[3].score, icon: '🤝', channel: report.areas[3].criteria || 'Control de Crisis' }
      ]
    : [
        { name: d.areas[0], score: 70, icon: '👁️', channel: 'Contacto visual: 30% · Estabilidad: 91%' },
        { name: d.areas[1], score: 80, icon: '🎙️', channel: '128 WPM · 2 muletillas' },
        { name: d.areas[2], score: 85, icon: '📄', channel: 'Apego a mensajes clave institucionales' },
        { name: d.areas[3], score: 80, icon: '🤝', channel: 'Técnica puente detectada' }
      ];

  const getScoreColor = (sc: number) => {
    if (sc >= 75) return '#10b981'; // Verde sobresaliente
    if (sc >= 50) return '#f59e0b'; // Amarillo aceptable
    return '#ef4444'; // Rojo crítico
  };

  return (
    <div className="canvas-content">
      {/* Global Evaluation Card */}
      <div className="card" style={{ marginBottom: '18px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '16px',
            borderBottom: '1px solid var(--line)',
            paddingBottom: '14px',
            flexWrap: 'wrap',
            gap: '12px'
          }}
        >
          <div>
            <div className="label" style={{ margin: 0 }}>
              {d.globalL}
            </div>
            <div style={{ fontSize: '13px', color: 'var(--muted)', marginTop: '2px' }}>
              Sesión: <code style={{ color: 'var(--accent2)', fontWeight: 600 }}>{sessionId}</code> · Inferencia multimodal NVIDIA & MediaPipe
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ textAlign: 'center' }}>
              <div
                style={{
                  fontSize: '38px',
                  fontWeight: 900,
                  color: getScoreColor(globalScore),
                  lineHeight: 1
                }}
              >
                {globalScore}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600, marginTop: '2px' }}>
                / 100 PUNTOS
              </div>
            </div>
            <div
              style={{
                fontSize: '11.5px',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: globalScore >= 75 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                color: getScoreColor(globalScore),
                border: `1px solid ${getScoreColor(globalScore)}40`
              }}
            >
              {globalScore >= 75 ? 'Sobresaliente' : globalScore >= 50 ? 'Aceptable' : 'Crítico'}
            </div>
          </div>
        </div>

        {/* Resumen Ejecutivo del Juez LLM */}
        <div
          className="box soft"
          style={{
            padding: '14px 18px',
            fontSize: '13.5px',
            lineHeight: 1.55,
            borderLeft: '4px solid #10b981',
            color: 'var(--ink)',
            marginBottom: '18px',
            background: 'var(--soft)'
          }}
        >
          <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700, color: 'var(--muted)', marginBottom: '4px' }}>
            Dictamen del Juez de Crisis (NVIDIA Llama 3.2 90B):
          </div>
          “{quote}”
        </div>

        {/* What went well */}
        <div className="label">{d.good}</div>
        <ul style={{ paddingLeft: '20px', marginBottom: '16px', fontSize: '13px', color: 'var(--ink)' }}>
          {goodItems.map((item, idx) => (
            <li key={idx} style={{ marginBottom: '5px' }}>{item}</li>
          ))}
        </ul>

        {/* What to improve */}
        <div className="label">{d.improve}</div>
        <ul style={{ paddingLeft: '20px', marginBottom: '16px', fontSize: '13px', color: 'var(--ink)' }}>
          {improveItems.map((item, idx) => (
            <li key={idx} style={{ marginBottom: '5px' }}>{item}</li>
          ))}
        </ul>
      </div>

      {/* Detail by area */}
      <div className="label">{d.detail}</div>
      <div className="grid4" style={{ marginBottom: '16px' }}>
        {areaScores.map((area, i) => (
          <div key={i} className="areaScore" style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: '8px', padding: '14px' }}>
            <div className="top" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span className="name" style={{ fontSize: '13px', fontWeight: 600 }}>
                {area.icon} {area.name}
              </span>
              <span className="sc" style={{ fontSize: '16px', fontWeight: 800, color: getScoreColor(area.score) }}>
                {area.score}%
              </span>
            </div>
            <div className="meter" style={{ height: '8px', marginBottom: '8px', background: 'var(--soft)', borderRadius: '999px', overflow: 'hidden' }}>
              <i
                style={{
                  display: 'block',
                  height: '100%',
                  width: `${area.score}%`,
                  background: getScoreColor(area.score),
                  borderRadius: '999px'
                }}
              />
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', lineHeight: 1.4 }}>
              {area.channel}
            </div>
          </div>
        ))}
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '20px' }}>
        <button
          type="button"
          className="btn"
          onClick={async () => {
            setShowVideoModal(true);
            setVideoLoading(true);
            setVideoError('');
            setVideoUrl('');
            try {
              const url = await sessionService.getPlaybackUrl(sessionId);
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
          }}
        >
          {d.watch}
        </button>
        <button
          type="button"
          className="btn pri"
          onClick={() => onNavigate('u2')}
        >
          🔁 {d.redo}
        </button>
        <button
          type="button"
          className="btn ghost"
          onClick={() => onNavigate('u7')}
        >
          📈 Ver mi historial y progreso →
        </button>
      </div>

      {/* Modal de Video con Reproductor Real */}
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
                  Sesión: <code style={{ color: '#818cf8' }}>{sessionId}</code>
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
                    onClick={async () => {
                      setVideoLoading(true);
                      setVideoError('');
                      try {
                        const url = await sessionService.getPlaybackUrl(sessionId);
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
                    }}
                  >
                    🔄 Reintentar
                  </button>
                </div>
              )}

              {!videoLoading && !videoError && videoUrl && (
                <video
                  controls
                  autoPlay
                  playsInline
                  style={{
                    width: '100%',
                    display: 'block',
                    background: '#000',
                    maxHeight: '480px'
                  }}
                >
                  <source src={videoUrl} type="video/webm" />
                  Tu navegador no soporta la reproducción de video.
                </video>
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
              <span style={{ fontSize: '11px', color: '#475569' }}>
                Almacenamiento seguro · Azure Blob Storage · URL válida por 60 min
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
