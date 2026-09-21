'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';

export const RetentionPolicyView: React.FC = () => {
  const { t } = useI18n();
  const d = t.L.a3;

  const [keepOption, setKeepOption] = useState<'full' | 'metrics'>('full');
  const [selectedTerm, setSelectedTerm] = useState('90 días');
  const [deletionProcessed, setDeletionProcessed] = useState(false);

  return (
    <div className="canvas-content">
      {/* What is preserved */}
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="label">{d.q1}</div>
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            margin: '12px 0',
            cursor: 'pointer',
            fontSize: '13px'
          }}
        >
          <input
            type="radio"
            name="retentionKeep"
            checked={keepOption === 'full'}
            onChange={() => setKeepOption('full')}
            style={{ width: '16px', height: '16px', accentColor: 'var(--accent2)' }}
          />
          <span>{d.opt1}</span>
        </label>

        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            margin: '12px 0',
            cursor: 'pointer',
            fontSize: '13px'
          }}
        >
          <input
            type="radio"
            name="retentionKeep"
            checked={keepOption === 'metrics'}
            onChange={() => setKeepOption('metrics')}
            style={{ width: '16px', height: '16px', accentColor: 'var(--accent2)' }}
          />
          <span>{d.opt2}</span>
        </label>
      </div>

      {/* Retention Term */}
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="label">{d.termL}</div>
        <div style={{ display: 'flex', gap: '8px', marginTop: '10px', flexWrap: 'wrap' }}>
          {d.terms.map((term) => (
            <span
              key={term}
              className={`pill ${selectedTerm === term ? 'on' : ''}`}
              onClick={() => setSelectedTerm(term)}
            >
              {term}
            </span>
          ))}
        </div>
        <div className="legend" style={{ marginTop: '10px' }}>
          {d.termLeg}
        </div>
      </div>

      {/* Deletion requests */}
      <div className="card">
        <div className="label">{d.delL}</div>
        <table className="wf" style={{ marginTop: '10px' }}>
          <thead>
            <tr>
              {d.th.map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ fontWeight: 600 }}>{d.delRow[0]}</td>
              <td>{d.delRow[1]}</td>
              <td>
                <span
                  className="tagm"
                  style={{
                    color: deletionProcessed ? 'var(--success)' : '#ba7517'
                  }}
                >
                  {deletionProcessed ? 'Completado' : d.delRow[2] || 'Pendiente'}
                </span>
              </td>
              <td>
                <button
                  type="button"
                  className={`btn ${deletionProcessed ? 'disabled' : 'pri'}`}
                  style={{ padding: '4px 12px', fontSize: '11.5px' }}
                  onClick={() => setDeletionProcessed(true)}
                >
                  {deletionProcessed ? '✓ Atendido' : d.process}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        {deletionProcessed && (
          <div
            style={{
              marginTop: '10px',
              fontSize: '12px',
              color: 'var(--success)',
              fontWeight: 500
            }}
          >
            ✓ {d.processedMsg}
          </div>
        )}
      </div>
    </div>
  );
};
