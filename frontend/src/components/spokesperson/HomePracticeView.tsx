'use client';

import React from 'react';
import { useI18n } from '../../context/I18nContext';

export type VoceroScreen =
  | 'u1'
  | 'u2'
  | 'u3'
  | 'u4'
  | 'u5'
  | 'u6'
  | 'u7'
  | 'lesson';

interface HomePracticeViewProps {
  onNavigate: (screen: VoceroScreen, extra?: string) => void;
}

export const HomePracticeView: React.FC<HomePracticeViewProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.u1;

  return (
    <div className="canvas-content">
      {/* KPI Stats Row */}
      <div className="row" style={{ marginBottom: '18px' }}>
        <div className="stat col">
          <div className="k">{d.s1}</div>
          <div className="v">12</div>
        </div>
        <div
          className="stat col"
          style={{ cursor: 'pointer' }}
          onClick={() => onNavigate('u7')}
          title="Ver mi progreso detallado"
        >
          <div className="k">{d.s2}</div>
          <div className="v">74</div>
        </div>
        <div className="stat col">
          <div className="k">{d.s3}</div>
          <div className="v" style={{ fontSize: '17px', color: 'var(--accent2)' }}>
            {d.s3v}
          </div>
        </div>
      </div>

      <div className="row">
        {/* Suggested Scenarios */}
        <div className="card col">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              marginBottom: '4px'
            }}
          >
            <div className="label" style={{ margin: 0 }}>
              {d.sugT}
            </div>
            <button
              type="button"
              className="btn ghost"
              style={{ fontSize: '11.5px', padding: '2px 8px' }}
              onClick={() => onNavigate('u2')}
            >
              Ver catálogo completo →
            </button>
          </div>
          <div className="legend" style={{ margin: '0 0 14px' }}>
            {d.sugHelp}
          </div>

          <div className="scard" style={{ marginBottom: '12px' }}>
            <h4>{d.c1n}</h4>
            <p className="ctx">{d.c1c}</p>
            <div className="meta">
              {d.c1m.map((m, i) => (
                <span key={i} className="tagm">
                  {m}
                </span>
              ))}
            </div>
            <div>
              <button
                type="button"
                className="btn pri"
                onClick={() => onNavigate('u3')}
              >
                🎙️ {t.practice}
              </button>
            </div>
          </div>

          <div className="scard">
            <h4>{d.c2n}</h4>
            <p className="ctx">{d.c2c}</p>
            <div className="meta">
              {d.c2m.map((m, i) => (
                <span key={i} className="tagm">
                  {m}
                </span>
              ))}
            </div>
            <div>
              <button
                type="button"
                className="btn nav"
                onClick={() => onNavigate('u3')}
              >
                🎙️ {t.practice}
              </button>
            </div>
          </div>
        </div>

        {/* Microlessons */}
        <div className="card" style={{ width: '270px', flexShrink: 0 }}>
          <div className="label">{d.microT}</div>
          {[
            { id: 'bridging', name: d.m1 },
            { id: 'hostile', name: d.m2 },
            { id: 'nonverbal', name: d.m3 }
          ].map((m) => (
            <div
              key={m.id}
              className="box"
              style={{
                padding: '12px',
                marginBottom: '10px',
                cursor: 'pointer',
                transition: 'border-color 0.15s ease'
              }}
              onClick={() => onNavigate('lesson', m.name)}
            >
              <div style={{ fontSize: '13.5px', fontWeight: 600, marginBottom: '3px' }}>
                📖 {m.name}
              </div>
              <div className="legend" style={{ margin: 0 }}>
                {d.microMeta}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
