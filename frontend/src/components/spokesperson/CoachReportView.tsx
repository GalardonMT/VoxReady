'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';

interface CoachReportViewProps {
  onNavigate: (screen: VoceroScreen) => void;
}

export const CoachReportView: React.FC<CoachReportViewProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.u6;
  const [showVideoModal, setShowVideoModal] = useState(false);

  const areaScores = [
    { name: d.areas[0], score: 70, icon: '👁️', channel: 'Imagen / no verbal' },
    { name: d.areas[1], score: 81, icon: '🎙️', channel: 'Voz / prosodia' },
    { name: d.areas[2], score: 79, icon: '📄', channel: 'Contenido' },
    { name: d.areas[3], score: 58, icon: '🤝', channel: 'Señal cruzada (fusión)' }
  ];

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
            paddingBottom: '14px'
          }}
        >
          <div>
            <div className="label" style={{ margin: 0 }}>
              {d.globalL}
            </div>
            <div style={{ fontSize: '13px', color: 'var(--muted)' }}>
              {d.scenLine}
            </div>
          </div>

          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '36px', fontWeight: 800, color: 'var(--accent)', lineHeight: 1 }}>
              74
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600 }}>
              / 100
            </div>
          </div>
        </div>

        {/* What went well */}
        <div className="label">{d.good}</div>
        <ul style={{ paddingLeft: '20px', marginBottom: '16px', fontSize: '13px', color: 'var(--ink)' }}>
          {d.goodItems.map((item, idx) => (
            <li key={idx} style={{ marginBottom: '4px' }}>{item}</li>
          ))}
        </ul>

        {/* What to improve */}
        <div className="label">{d.improve}</div>
        <ul style={{ paddingLeft: '20px', marginBottom: '16px', fontSize: '13px', color: 'var(--ink)' }}>
          {d.improveItems.map((item, idx) => (
            <li key={idx} style={{ marginBottom: '4px' }}>{item}</li>
          ))}
        </ul>

        {/* Highlighted cross-signal quote */}
        <div
          className="box soft"
          style={{
            padding: '14px 18px',
            fontSize: '13px',
            lineHeight: 1.5,
            borderLeft: '4px solid var(--accent2)',
            color: 'var(--ink)',
            fontStyle: 'italic'
          }}
        >
          {d.quote}
        </div>
      </div>

      {/* Detail by area */}
      <div className="label">{d.detail}</div>
      <div className="grid4" style={{ marginBottom: '16px' }}>
        {areaScores.map((area, i) => (
          <div key={i} className="areaScore">
            <div className="top">
              <span className="name">
                {area.icon} {area.name}
              </span>
              <span className="sc">{area.score}</span>
            </div>
            <div className="meter" style={{ height: '8px', marginBottom: '6px' }}>
              <i
                style={{
                  width: `${area.score}%`,
                  background:
                    area.score >= 80
                      ? 'var(--success)'
                      : area.score >= 70
                      ? 'var(--accent)'
                      : 'var(--accent2)'
                }}
              />
            </div>
            <div style={{ fontSize: '10.5px', color: 'var(--muted)' }}>
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
          onClick={() => setShowVideoModal(true)}
        >
          {d.watch}
        </button>
        <button
          type="button"
          className="btn pri"
          onClick={() => onNavigate('u3')}
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

      {/* Recording Preview Modal */}
      {showVideoModal && (
        <div className="modal-overlay" onClick={() => setShowVideoModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '14px'
              }}
            >
              <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600 }}>
                Grabación de la sesión — Retiro de producto
              </h4>
              <button
                className="iconbtn"
                style={{ width: '28px', height: '28px' }}
                onClick={() => setShowVideoModal(false)}
              >
                ✕
              </button>
            </div>
            <div
              className="vid"
              style={{
                minHeight: '260px',
                marginBottom: '14px',
                background: '#151b22'
              }}
            >
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '40px', marginBottom: '8px' }}>▶️</div>
                <div style={{ fontSize: '13px', color: '#c9d1d9' }}>
                  Reproduciendo grabación sincronizada (Voz + Video + Transcripción)
                </div>
                <div style={{ fontSize: '11px', color: '#8b949e', marginTop: '6px' }}>
                  Duración: 06:12 · Sujeto a política de retención de 90 días
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                className="btn pri"
                onClick={() => setShowVideoModal(false)}
              >
                Cerrar reproductor
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
