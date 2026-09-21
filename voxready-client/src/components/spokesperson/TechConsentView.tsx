'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';

interface TechConsentViewProps {
  onNavigate: (screen: VoceroScreen) => void;
}

export const TechConsentView: React.FC<TechConsentViewProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.u3;

  const [chk1, setChk1] = useState(false);
  const [chk2, setChk2] = useState(false);

  const isEnabled = chk1 && chk2;

  return (
    <div className="canvas-content">
      <div className="row">
        {/* Left Column: Tech validation */}
        <div className="card col">
          <div className="label">{d.camL}</div>
          <div className="self" style={{ minHeight: '220px' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '38px', marginBottom: '8px' }}>👤</div>
              <div style={{ fontSize: '13px', color: '#cdd4da' }}>{d.camL}</div>
            </div>
            <div
              className="reclamp"
              style={{ background: 'rgba(0, 0, 0, 0.45)', color: '#fff' }}
            >
              <i className="recdot" style={{ background: '#3b6d11' }} />
              <span>{d.camOk}</span>
            </div>
          </div>

          <div style={{ marginTop: '16px' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '12.5px',
                marginBottom: '6px'
              }}
            >
              <span>🎤 {d.mic}</span>
              <span style={{ color: 'var(--success)', fontWeight: 600 }}>{d.micOk}</span>
            </div>
            <div className="meter">
              <i style={{ width: '68%', background: 'var(--success)' }} />
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '12.5px',
                margin: '14px 0 6px'
              }}
            >
              <span>💡 {d.light}</span>
              <span style={{ color: '#ba7517', fontWeight: 600 }}>{d.lightW}</span>
            </div>
            <div className="meter">
              <i style={{ width: '55%', background: '#ba7517' }} />
            </div>
          </div>
        </div>

        {/* Right Column: Consent & Legal */}
        <div className="card col">
          <div className="label">{d.consentL}</div>
          <div
            className="area"
            style={{
              minHeight: '120px',
              fontSize: '12.5px',
              lineHeight: 1.5,
              color: 'var(--ink)'
            }}
          >
            {d.legal}
          </div>

          <div style={{ marginTop: '14px' }}>
            <label
              style={{
                display: 'flex',
                gap: '10px',
                alignItems: 'flex-start',
                fontSize: '12.5px',
                cursor: 'pointer',
                marginBottom: '10px'
              }}
            >
              <input
                type="checkbox"
                checked={chk1}
                onChange={(e) => setChk1(e.target.checked)}
                style={{
                  width: '16px',
                  height: '16px',
                  accentColor: 'var(--accent2)',
                  marginTop: '2px',
                  cursor: 'pointer'
                }}
              />
              <span>{d.chk1}</span>
            </label>

            <label
              style={{
                display: 'flex',
                gap: '10px',
                alignItems: 'flex-start',
                fontSize: '12.5px',
                cursor: 'pointer'
              }}
            >
              <input
                type="checkbox"
                checked={chk2}
                onChange={(e) => setChk2(e.target.checked)}
                style={{
                  width: '16px',
                  height: '16px',
                  accentColor: 'var(--accent2)',
                  marginTop: '2px',
                  cursor: 'pointer'
                }}
              />
              <span>{d.chk2}</span>
            </label>
          </div>

          <div
            style={{
              marginTop: '20px',
              display: 'flex',
              gap: '10px',
              alignItems: 'center'
            }}
          >
            <button
              type="button"
              className={`btn pri ${!isEnabled ? 'disabled' : ''}`}
              onClick={() => {
                if (isEnabled) onNavigate('u4');
              }}
            >
              {d.beginBtn} →
            </button>
            <button
              type="button"
              className="btn ghost"
              onClick={() => onNavigate('u2')}
            >
              {d.cancel}
            </button>
          </div>

          <div className="legend" style={{ marginTop: '8px' }}>
            {d.sesLang}
          </div>
        </div>
      </div>
    </div>
  );
};
