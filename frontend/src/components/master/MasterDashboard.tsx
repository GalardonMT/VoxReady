'use client';

import React, { useEffect, useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { metricsService } from '../../services/metricsService';
import type { MetricsVersion } from '../../services/metricsModel';

export type MasterScreen = 'm1' | 'm2' | 'm3' | 'm4' | 'm5' | 'm6' | 'm7' | 'm8';

interface MasterDashboardProps {
  onNavigate: (screen: MasterScreen) => void;
}

export const MasterDashboard: React.FC<MasterDashboardProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.m1;
  const [latestVersion, setLatestVersion] = useState<MetricsVersion | null>(null);
  const [versionLoading, setVersionLoading] = useState(true);
  const [versionError, setVersionError] = useState('');
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let active = true;
    metricsService.getLatestPublished().then(version => {
      if (active) setLatestVersion(version);
    }).catch(cause => {
      if (active) setVersionError(cause instanceof Error ? cause.message : 'No se pudo consultar la versión publicada.');
    }).finally(() => { if (active) setVersionLoading(false); });
    return () => { active = false; };
  }, [retryVersion]);

  const retryLatestVersion = () => {
    setVersionError('');
    setVersionLoading(true);
    setRetryVersion(value => value + 1);
  };

  const stats = [
    { label: d.st[0], value: '9', sub: 'Tenants corporativos activos' },
    { label: d.st[1], value: '640', sub: '+18% vs semana previa' },
    { label: d.st[2], value: '23', sub: 'Pendientes de calibración', alert: true },
    { label: d.st[3], value: '88%', sub: 'Concordancia kappa > 0.82' }
  ];

  return (
    <div className="canvas-content">
      {/* Global KPIs */}
      <div className="grid4" style={{ marginBottom: '20px' }}>
        {stats.map((stat, i) => (
          <div key={i} className="stat">
            <div className="k">{stat.label}</div>
            <div
              className="v"
              style={{ color: stat.alert ? 'var(--accent2)' : 'var(--accent)' }}
            >
              {stat.value}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>
              {stat.sub}
            </div>
          </div>
        ))}
      </div>

      <div className="row" style={{ alignItems: 'stretch' }}>
        {/* Standard Version Card */}
        <div className="card col" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '12px'
              }}
            >
              <div className="label" style={{ margin: 0 }}>
                {d.verL}
              </div>
              <span
                className="tagm"
                style={{
                  background: 'var(--accentsoft)',
                  color: 'var(--accent)',
                  fontWeight: 600
                }}
              >
                {versionLoading ? 'Consultando' : versionError ? 'No disponible' : latestVersion ? 'Publicada' : 'Sin publicación'}
              </span>
            </div>

            <div
              style={{
                fontSize: '26px',
                fontWeight: 700,
                color: 'var(--accent)',
                margin: '6px 0'
              }}
            >
              {versionLoading ? 'Cargando…' : latestVersion?.versionLabel ?? '—'}
            </div>
            <div className="legend" style={{ marginBottom: '16px', lineHeight: 1.5 }}>
              {versionError ? <span role="alert">{versionError} <button type="button" className="btn ghost" onClick={retryLatestVersion}>Reintentar</button></span> :
                latestVersion ? 'Última versión de métricas publicada. Las sesiones anteriores conservan su propia versión.' :
                  versionLoading ? 'Consultando la base de datos…' : 'No hay una versión de métricas publicada.'}
            </div>

            <div
              style={{
                background: 'var(--soft)',
                padding: '12px 14px',
                borderRadius: '8px',
                border: '1px solid var(--line)',
                fontSize: '12px',
                marginBottom: '16px'
              }}
            >
              <div style={{ fontWeight: 600, color: 'var(--ink)', marginBottom: '4px' }}>
                Pipeline multimodal de evaluación:
              </div>
              <div style={{ color: 'var(--muted)' }}>
                • Audio & prosodia: Modelo Whisper-v3 + pyannote (ES, EN, PT)
                <br />
                • Expresión y mirada: MediaPipe FaceMesh + gaze tracking 60fps
                <br />
                • Fusión multimodal: Red bayesiana de congruencia cruzada
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              type="button"
              className="btn pri"
              onClick={() => onNavigate('m2')}
            >
              {d.openRub}
            </button>
            <button
              type="button"
              className="btn ghost"
              onClick={() => onNavigate('m3')}
            >
              Revisar cola ({stats[2].value}) →
            </button>
          </div>
        </div>

        {/* Global Score Distribution Histogram */}
        <div className="card col" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '10px'
              }}
            >
              <div className="label" style={{ margin: 0 }}>
                {d.distL}
              </div>
              <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
                N = 1,420 sesiones evaluadas
              </span>
            </div>

            <div style={{ marginTop: '12px' }}>
              <svg viewBox="0 0 400 135" width="100%" height="135" style={{ display: 'block' }}>
                {/* Bars of normal distribution */}
                {[
                  { x: 30, h: 18, count: 62, label: '<50' },
                  { x: 75, h: 42, count: 145, label: '50-60' },
                  { x: 120, h: 74, count: 268, label: '60-70' },
                  { x: 165, h: 96, count: 480, label: '70-80' },
                  { x: 210, h: 78, count: 325, label: '80-90' },
                  { x: 255, h: 36, count: 140, label: '90-100' }
                ].map((bar, idx) => (
                  <g key={idx}>
                    <rect
                      x={bar.x}
                      y={110 - bar.h}
                      width="34"
                      height={bar.h}
                      rx="4"
                      fill={idx === 3 ? 'var(--accent2)' : 'var(--accent)'}
                      opacity={idx === 3 ? 1 : 0.85}
                    />
                    <text
                      x={bar.x + 17}
                      y={125}
                      fontSize="9"
                      fill="var(--muted)"
                      textAnchor="middle"
                    >
                      {bar.label}
                    </text>
                    <text
                      x={bar.x + 17}
                      y={104 - bar.h}
                      fontSize="9"
                      fontWeight="600"
                      fill="var(--ink)"
                      textAnchor="middle"
                    >
                      {bar.count}
                    </text>
                  </g>
                ))}
                <line x1="20" y1="110" x2="310" y2="110" stroke="var(--line)" strokeWidth="1" />
              </svg>
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderTop: '1px solid var(--line)',
              paddingTop: '10px',
              marginTop: '12px',
              fontSize: '11.5px',
              color: 'var(--muted)'
            }}
          >
            <span>Media global: <b>72.4 pts</b></span>
            <span>Desviación estándar: <b>±9.2 pts</b></span>
            <span style={{ color: 'var(--accent2)', fontWeight: 600 }}>Zona modal: 70-80 pts</span>
          </div>
        </div>
      </div>
    </div>
  );
};
