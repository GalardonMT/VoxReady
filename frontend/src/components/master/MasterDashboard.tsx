'use client';

import React, { useEffect, useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { masterDashboardService } from '../../services/masterDashboardService';
import { dashboardBars, dashboardNumber } from '../../services/masterDashboardModel';
import type { MasterDashboardResponse } from '../../types/api';

export type MasterScreen = 'm1' | 'm2' | 'm3' | 'm4' | 'm5' | 'm6' | 'm7' | 'm8';

interface MasterDashboardProps {
  onNavigate: (screen: MasterScreen) => void;
  labelingEnabled?: boolean;
}

export const MasterDashboard: React.FC<MasterDashboardProps> = ({ onNavigate, labelingEnabled = true }) => {
  const { t, lang } = useI18n();
  const d = t.L.m1;
  const [data, setData] = useState<MasterDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    masterDashboardService.get(controller.signal).then(result => {
      if (active) setData(result);
    }).catch(() => {
      if (active) setError(true);
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [attempt]);

  const retry = () => {
    setData(null);
    setError(false);
    setLoading(true);
    setAttempt(value => value + 1);
  };

  const number = (value: number | null | undefined) => dashboardNumber(value, lang);
  const week = data?.sessionsWeek;
  const distribution = data?.scoreDistribution;
  const version = data?.publishedVersion;
  const bars = distribution ? dashboardBars(distribution) : [];
  const stats = [
    { label: d.st[0], value: number(data?.activeClients), sub: d.activeClientsHelp },
    { label: d.st[1], value: number(week?.count), sub: !week ? d.weekHelp :
      week.changeStatus === 'no_previous_sessions' ? `${d.weekHelp} · ${d.noPreviousSessions}` :
        `${d.weekHelp} · ${dashboardNumber(week.changePercent, lang, true)}% ${d.vsPrevious}` },
    { label: d.st[2], value: number(data?.pendingReviewCount), sub: d.pendingHelp, alert: true },
    { label: d.st[3], value: '—', sub: d.qualityPending },
  ];

  return (
    <div className="canvas-content" aria-busy={loading}>
      {loading && <p role="status">{d.loading}</p>}
      {error && <div className="card" role="alert" style={{ marginBottom: '20px' }}>
        <p>{d.loadError}</p>
        <button type="button" className="btn ghost" onClick={retry}>{d.retry}</button>
      </div>}
      <div className="grid4" style={{ marginBottom: '20px' }}>
        {stats.map(stat => <div key={stat.label} className="stat">
          <div className="k">{stat.label}</div>
          <div className="v" style={{ color: stat.alert ? 'var(--accent2)' : 'var(--accent)' }}>{stat.value}</div>
          <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>{stat.sub}</div>
        </div>)}
      </div>

      <div className="row" style={{ alignItems: 'stretch' }}>
        <div className="card col" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div className="label" style={{ margin: 0 }}>{d.verL}</div>
              <span className="tagm" style={{ background: 'var(--accentsoft)', color: 'var(--accent)', fontWeight: 600 }}>
                {loading ? d.loading : error ? d.unavailable : version ? d.published : d.noPublication}
              </span>
            </div>
            <div style={{ fontSize: '26px', fontWeight: 700, color: 'var(--accent)', margin: '6px 0' }}>
              {version?.versionLabel ?? '—'}
            </div>
            <div className="legend" style={{ marginBottom: '16px', lineHeight: 1.5 }}>
              {data ? version ? d.publishedHelp : d.noPublication : loading ? d.loading : d.unavailable}
            </div>
            <div style={{ background: 'var(--soft)', padding: '12px 14px', borderRadius: '8px', border: '1px solid var(--line)', fontSize: '12px', marginBottom: '16px' }}>
              <div style={{ fontWeight: 600, color: 'var(--ink)', marginBottom: '4px' }}>{d.pipelineTitle}</div>
              <div style={{ color: 'var(--muted)' }}>{d.pipelineAudio}<br />{d.pipelineVision}<br />{d.pipelineFusion}</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button type="button" className="btn pri" onClick={() => onNavigate('m2')}>{d.openRub}</button>
            {labelingEnabled && <button type="button" className="btn ghost" onClick={() => onNavigate('m3')}>
              {d.openQueue} ({number(data?.pendingReviewCount)}) →
            </button>}
          </div>
        </div>

        <div className="card col" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div className="label" style={{ margin: 0 }}>{d.distL}</div>
              <span style={{ fontSize: '11px', color: 'var(--muted)' }}>N = {number(distribution?.sampleCount)} {d.evaluatedSessions}</span>
            </div>
            <p className="legend">{d.distributionHelp}</p>
            {distribution?.sampleCount === 0 && <p role="status">{d.noScores}</p>}
            <div style={{ marginTop: '12px' }}>
              <svg viewBox="0 0 400 135" width="100%" height="135" style={{ display: 'block' }} role="img" aria-label={d.hist}>
                <title>{d.hist}</title>
                {bars.map(bar => <g key={bar.label}>
                  <rect x={bar.x} y={110 - bar.height} width="34" height={bar.height} rx="4"
                    fill={bar.modal ? 'var(--accent2)' : 'var(--accent)'} opacity={bar.modal ? 1 : 0.85} />
                  <text x={bar.x + 17} y={125} fontSize="9" fill="var(--muted)" textAnchor="middle">{bar.label}</text>
                  <text x={bar.x + 17} y={104 - bar.height} fontSize="9" fontWeight="600" fill="var(--ink)" textAnchor="middle">{number(bar.count)}</text>
                </g>)}
                <line x1="20" y1="110" x2="310" y2="110" stroke="var(--line)" strokeWidth="1" />
              </svg>
            </div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--line)', paddingTop: '10px', marginTop: '12px', fontSize: '11.5px', color: 'var(--muted)' }}>
            <span>{d.mean}: <b>{number(distribution?.mean)} {d.points}</b></span>
            <span>{d.deviation}: <b>{number(distribution?.standardDeviation)} {d.points}</b></span>
            <span style={{ color: 'var(--accent2)', fontWeight: 600 }}>{d.modal}: {distribution?.modalRanges.join(', ') || '—'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
