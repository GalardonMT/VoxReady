'use client';

import React, { useEffect, useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';

interface AnalyzingViewProps {
  onNavigate: (screen: VoceroScreen) => void;
}

export const AnalyzingView: React.FC<AnalyzingViewProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.u5;

  const [step3Done, setStep3Done] = useState(false);
  const [step4Done, setStep4Done] = useState(false);

  useEffect(() => {
    const timer1 = setTimeout(() => setStep3Done(true), 1200);
    const timer2 = setTimeout(() => setStep4Done(true), 2400);
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  }, []);

  return (
    <div className="canvas-content">
      <div
        className="card"
        style={{
          textAlign: 'center',
          padding: '48px 32px',
          maxWidth: '680px',
          margin: '0 auto'
        }}
      >
        <div
          className="ph"
          style={{
            height: '70px',
            width: '70px',
            borderRadius: '50%',
            margin: '0 auto 20px',
            fontSize: '32px',
            background: 'var(--soft)',
            borderColor: 'var(--line)'
          }}
        >
          ⏱️
        </div>

        <h3
          style={{
            fontSize: '19px',
            fontWeight: 700,
            marginBottom: '6px',
            color: 'var(--ink)'
          }}
        >
          {d.head}
        </h3>
        <p style={{ fontSize: '13.5px', color: 'var(--muted)', marginBottom: '28px' }}>
          {d.small}
        </p>

        <div
          style={{
            maxWidth: '440px',
            margin: '0 auto',
            textAlign: 'left',
            background: 'var(--soft)',
            padding: '18px 22px',
            borderRadius: '10px',
            border: '1px solid var(--line)'
          }}
        >
          {/* Step 1 */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px',
              marginBottom: '12px'
            }}
          >
            <span>📄 {d.p1}</span>
            <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ Completado</span>
          </div>

          {/* Step 2 */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px',
              marginBottom: '12px'
            }}
          >
            <span>🎙️ {d.p2}</span>
            <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ Completado</span>
          </div>

          {/* Step 3 */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px',
              marginBottom: '12px'
            }}
          >
            <span>👁️ {d.p3}</span>
            {step3Done ? (
              <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ Completado</span>
            ) : (
              <span style={{ color: 'var(--accent2)', fontWeight: 600 }}>Procesando...</span>
            )}
          </div>

          {/* Step 4 */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px'
            }}
          >
            <span>🤝 {d.p4}</span>
            {step4Done ? (
              <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ Listo</span>
            ) : step3Done ? (
              <span style={{ color: 'var(--accent2)', fontWeight: 600 }}>Integrando...</span>
            ) : (
              <span style={{ color: 'var(--muted)' }}>En espera</span>
            )}
          </div>
        </div>

        <div style={{ marginTop: '28px' }}>
          <button
            type="button"
            className="btn pri"
            style={{ padding: '10px 24px', fontSize: '13.5px' }}
            onClick={() => onNavigate('u6')}
          >
            {d.viewReport}
          </button>
        </div>
      </div>
    </div>
  );
};
