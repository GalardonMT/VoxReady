'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { MasterScreen } from './MasterDashboard';

interface RubricEditorViewProps {
  onNavigate?: (screen: MasterScreen) => void;
}

interface RubricAreaItem {
  id: string;
  name: string;
  channel: string;
  criteria: string;
  weight: number;
}

export const RubricEditorView: React.FC<RubricEditorViewProps> = () => {
  const { t } = useI18n();
  const d = t.L.m2;

  const [currentVersion, setCurrentVersion] = useState('v0.4');
  const [publishedNotice, setPublishedNotice] = useState(false);
  const [draftNotice, setDraftNotice] = useState(false);

  const [areas, setAreas] = useState<RubricAreaItem[]>([
    {
      id: 'expression',
      name: d.rows[0][0],
      channel: d.rows[0][1],
      criteria: d.rows[0][2],
      weight: 25
    },
    {
      id: 'tone',
      name: d.rows[1][0],
      channel: d.rows[1][1],
      criteria: d.rows[1][2],
      weight: 25
    },
    {
      id: 'coherence',
      name: d.rows[2][0],
      channel: d.rows[2][1],
      criteria: d.rows[2][2],
      weight: 30
    },
    {
      id: 'empathy',
      name: d.rows[3][0],
      channel: d.rows[3][1],
      criteria: d.rows[3][2],
      weight: 20
    }
  ]);

  const [descText, setDescText] = useState(d.descV);
  const [activeLangs, setActiveLangs] = useState<{ [key: string]: boolean }>({
    ES: true,
    EN: true,
    PT: true
  });

  const totalWeight = areas.reduce((acc, curr) => acc + curr.weight, 0);

  const handleWeightChange = (id: string, delta: number) => {
    setAreas((prev) =>
      prev.map((item) => {
        if (item.id === id) {
          const newWeight = Math.max(5, Math.min(60, item.weight + delta));
          return { ...item, weight: newWeight };
        }
        return item;
      })
    );
  };

  const handlePublish = () => {
    setCurrentVersion('v0.5');
    setPublishedNotice(true);
    setDraftNotice(false);
    setTimeout(() => setPublishedNotice(false), 4500);
  };

  const handleSaveDraft = () => {
    setDraftNotice(true);
    setPublishedNotice(false);
    setTimeout(() => setDraftNotice(false), 3000);
  };

  const toggleLang = (code: string) => {
    setActiveLangs((prev) => ({ ...prev, [code]: !prev[code] }));
  };

  return (
    <div className="canvas-content">
      {publishedNotice && (
        <div
          style={{
            padding: '12px 18px',
            marginBottom: '16px',
            borderRadius: '8px',
            background: 'var(--accentsoft)',
            color: 'var(--accent)',
            border: '1px solid var(--accent)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <span>✓</span>
          <span>
            Versión {currentVersion} publicada con éxito. Sincronizada transversalmente con los 9 tenants de clientes.
          </span>
        </div>
      )}

      {draftNotice && (
        <div
          style={{
            padding: '12px 18px',
            marginBottom: '16px',
            borderRadius: '8px',
            background: 'var(--soft)',
            color: 'var(--ink)',
            border: '1px solid var(--line)',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <span>💾</span>
          <span>Borrador guardado localmente para revisión de equipo.</span>
        </div>
      )}

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '12px'
        }}
      >
        <div className="label" style={{ margin: 0 }}>
          {d.areasL}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            className="tagm"
            style={{
              background: totalWeight === 100 ? 'var(--accentsoft)' : '#fde8e8',
              color: totalWeight === 100 ? 'var(--accent)' : '#9c2020',
              fontWeight: 600,
              fontSize: '12px'
            }}
          >
            Suma de pesos: {totalWeight}% {totalWeight === 100 ? '✓' : '(Debe sumar 100%)'}
          </span>
          <span
            className="tagm"
            style={{
              background: 'var(--soft)',
              color: 'var(--muted)',
              fontSize: '11.5px'
            }}
          >
            Versión actual: {currentVersion}
          </span>
        </div>
      </div>

      {/* Areas Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: '18px' }}>
        <table className="wf">
          <thead>
            <tr>
              {d.th.map((h, i) => (
                <th key={i} style={{ textAlign: i === 3 ? 'center' : 'left' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {areas.map((row) => (
              <tr key={row.id}>
                <td style={{ fontWeight: 600, width: '180px' }}>{row.name}</td>
                <td style={{ width: '190px' }}>
                  <span className="tagm">{row.channel}</span>
                </td>
                <td style={{ fontSize: '12.5px', color: 'var(--ink)' }}>{row.criteria}</td>
                <td style={{ textAlign: 'center', width: '140px' }}>
                  <div
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      background: 'var(--soft)',
                      padding: '3px 8px',
                      borderRadius: '6px'
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => handleWeightChange(row.id, -5)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        color: 'var(--muted)',
                        fontWeight: 'bold',
                        padding: '0 4px'
                      }}
                      title="Disminuir peso"
                    >
                      −
                    </button>
                    <span style={{ fontWeight: 700, color: 'var(--accent)', minWidth: '32px' }}>
                      {row.weight}%
                    </span>
                    <button
                      type="button"
                      onClick={() => handleWeightChange(row.id, 5)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        color: 'var(--muted)',
                        fontWeight: 'bold',
                        padding: '0 4px'
                      }}
                      title="Aumentar peso"
                    >
                      +
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="row" style={{ alignItems: 'flex-start' }}>
        {/* Level Descriptors */}
        <div className="card col">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '8px'
            }}
          >
            <div className="label" style={{ margin: 0 }}>
              {d.descL}
            </div>
            <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
              Criterio de clasificación para scoring cualitativo
            </span>
          </div>
          <textarea
            className="area"
            value={descText}
            onChange={(e) => setDescText(e.target.value)}
            style={{ minHeight: '120px', whiteSpace: 'pre-line', lineHeight: 1.6 }}
          />
        </div>

        {/* Multilingual Support */}
        <div className="card" style={{ width: '280px', flexShrink: 0 }}>
          <div className="label">{d.multiL}</div>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '12px' }}>
            {['ES', 'EN', 'PT'].map((code) => {
              const isOn = activeLangs[code];
              return (
                <button
                  key={code}
                  type="button"
                  className={`pill ${isOn ? 'on' : ''}`}
                  onClick={() => toggleLang(code)}
                  style={{ cursor: 'pointer', border: 'none' }}
                >
                  {code} {code === 'ES' ? '(Español)' : code === 'EN' ? '(English)' : '(Português)'}
                </button>
              );
            })}
          </div>
          <div className="legend" style={{ fontSize: '11.5px', lineHeight: 1.5, margin: 0 }}>
            {d.multiLeg}
          </div>
          <div
            style={{
              marginTop: '14px',
              paddingTop: '10px',
              borderTop: '1px solid var(--line)',
              fontSize: '11px',
              color: 'var(--muted)'
            }}
          >
            Vocabularios y pausas calibradas de forma independiente para cada variante idiomática.
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
        <button
          type="button"
          className="btn pri"
          onClick={handlePublish}
          disabled={totalWeight !== 100}
        >
          🚀 {d.publish}
        </button>
        <button type="button" className="btn ghost" onClick={handleSaveDraft}>
          💾 {d.draft}
        </button>
      </div>
    </div>
  );
};
