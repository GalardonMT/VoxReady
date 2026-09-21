'use client';

import React from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';

interface LessonViewProps {
  lessonTitle?: string;
  onNavigate: (screen: VoceroScreen) => void;
}

export const LessonView: React.FC<LessonViewProps> = ({
  lessonTitle = 'Mensajes puente (Bridging)',
  onNavigate
}) => {
  const { t } = useI18n();
  const d = t.L.lesson;

  return (
    <div className="canvas-content">
      <div style={{ marginBottom: '14px' }}>
        <button
          type="button"
          className="btn ghost"
          onClick={() => onNavigate('u1')}
        >
          {t.back}
        </button>
      </div>

      <div className="card">
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '16px',
            borderBottom: '1px solid var(--line)',
            paddingBottom: '12px'
          }}
        >
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--ink)' }}>
            📚 {lessonTitle}
          </h3>
          <span className="tagm" style={{ fontWeight: 600 }}>
            ⏱️ {d.mins}
          </span>
        </div>

        <div className="label">{d.objL}</div>
        <p
          style={{
            marginBottom: '18px',
            color: 'var(--ink)',
            fontSize: '13px',
            lineHeight: 1.5
          }}
        >
          {d.obj}
        </p>

        <div
          className="ph"
          style={{
            height: '180px',
            marginBottom: '18px',
            borderRadius: '10px',
            background: '#1b222a',
            borderColor: 'var(--line2)',
            color: '#c9d1d9',
            flexDirection: 'column',
            gap: '8px'
          }}
        >
          <span style={{ fontSize: '36px' }}>▶️</span>
          <span style={{ fontSize: '13px', fontWeight: 500 }}>{d.vidL}</span>
        </div>

        <div className="label">{d.exL}</div>
        <div
          className="area"
          style={{
            marginBottom: '20px',
            minHeight: '80px',
            whiteSpace: 'pre-line',
            lineHeight: 1.5,
            fontSize: '13px',
            background: 'var(--soft)'
          }}
        >
          {d.exV}
        </div>

        <div>
          <button
            type="button"
            className="btn pri"
            style={{ padding: '10px 20px', fontSize: '13.5px' }}
            onClick={() => onNavigate('u2')}
          >
            {d.cta}
          </button>
        </div>
      </div>
    </div>
  );
};
