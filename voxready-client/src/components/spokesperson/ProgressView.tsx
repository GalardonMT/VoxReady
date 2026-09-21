'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';
import { INITIAL_PROGRESS } from '../../mock/mockData';

interface ProgressViewProps {
  onNavigate: (screen: VoceroScreen, extra?: string) => void;
}

export const ProgressView: React.FC<ProgressViewProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.u7;

  // Calendar State
  const now = new Date();
  const [calYear, setCalYear] = useState(now.getFullYear());
  const [calMonth, setCalMonth] = useState(now.getMonth());
  const [selectedDay, setSelectedDay] = useState<number | null>(15);
  const [isScheduled, setIsScheduled] = useState(false);

  const prevMonth = () => {
    if (calMonth === 0) {
      setCalMonth(11);
      setCalYear((y) => y - 1);
    } else {
      setCalMonth((m) => m - 1);
    }
  };

  const nextMonth = () => {
    if (calMonth === 11) {
      setCalMonth(0);
      setCalYear((y) => y + 1);
    } else {
      setCalMonth((m) => m + 1);
    }
  };

  // SVG Chart Calculations
  const chartData = INITIAL_PROGRESS.chartData;
  const chartColors = INITIAL_PROGRESS.chartColors;
  const W = 600;
  const H = 200;
  const pl = 34;
  const pr = 16;
  const pt = 14;
  const pb = 24;
  const numPoints = chartData[0].length;

  const getX = (i: number) => Math.round(pl + (i * (W - pl - pr)) / (numPoints - 1));
  const getY = (v: number) => Math.round(pt + ((100 - v) / (100 - 30)) * (H - pt - pb));

  // Calendar Grid generation
  const firstDayIndex = (new Date(calYear, calMonth, 1).getDay() + 6) % 7;
  const totalDays = new Date(calYear, calMonth + 1, 0).getDate();
  const emptyDays = Array.from({ length: firstDayIndex });
  const monthDays = Array.from({ length: totalDays }, (_, i) => i + 1);

  return (
    <div className="canvas-content">
      {/* Top Row: Trend Chart + Table */}
      <div className="row" style={{ marginBottom: '18px', alignItems: 'stretch' }}>
        {/* Trend Chart */}
        <div className="card" style={{ flex: 1.45, minWidth: 0 }}>
          <div className="label">{d.trendL}</div>
          <div style={{ marginTop: '10px' }}>
            <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
              {/* Horizontal Grid lines */}
              {[40, 60, 80, 100].map((val) => (
                <g key={val}>
                  <line
                    x1={pl}
                    y1={getY(val)}
                    x2={W - pr}
                    y2={getY(val)}
                    style={{ stroke: 'var(--line)' }}
                    strokeWidth="1"
                    strokeDasharray={val === 100 ? '0' : '3 3'}
                  />
                  <text
                    x="6"
                    y={getY(val) + 3}
                    fontSize="10"
                    style={{ fill: 'var(--muted)', fontWeight: 500 }}
                  >
                    {val}
                  </text>
                </g>
              ))}

              {/* Data Lines & Points */}
              {chartData.map((series, si) => {
                const points = series.map((v, i) => `${getX(i)},${getY(v)}`).join(' ');
                return (
                  <g key={si}>
                    <polyline
                      points={points}
                      fill="none"
                      stroke={chartColors[si]}
                      strokeWidth="2.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    {series.map((v, i) => (
                      <circle
                        key={i}
                        cx={getX(i)}
                        cy={getY(v)}
                        r="3.5"
                        fill={chartColors[si]}
                      />
                    ))}
                  </g>
                );
              })}

              {/* X Axis Labels */}
              {Array.from({ length: numPoints }).map((_, i) => (
                <text
                  key={i}
                  x={getX(i)}
                  y={H - 6}
                  fontSize="10"
                  style={{ fill: 'var(--muted)', fontWeight: 600 }}
                  textAnchor="middle"
                >
                  S{i + 1}
                </text>
              ))}
            </svg>
          </div>

          <div
            style={{
              display: 'flex',
              gap: '16px',
              flexWrap: 'wrap',
              marginTop: '12px',
              paddingTop: '8px',
              borderTop: '1px solid var(--line)'
            }}
          >
            {d.series.map((s, i) => (
              <span
                key={i}
                style={{
                  fontSize: '11.5px',
                  color: 'var(--muted)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span
                  style={{
                    width: '11px',
                    height: '11px',
                    borderRadius: '2px',
                    backgroundColor: chartColors[i]
                  }}
                />
                {s}
              </span>
            ))}
          </div>
        </div>

        {/* Progress Table */}
        <div className="card" style={{ flex: 1, minWidth: 0 }}>
          <div className="label">{d.tblTitle}</div>
          <table className="wf" style={{ marginTop: '10px' }}>
            <thead>
              <tr>
                {d.tblCols.map((h, i) => (
                  <th key={i} style={i ? { textAlign: 'center' } : {}}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.series.map((s, i) => {
                const seriesData = chartData[i];
                const cur = seriesData[seriesData.length - 1];
                const change = cur - seriesData[0];
                return (
                  <tr key={i}>
                    <td>
                      <span
                        style={{
                          display: 'inline-block',
                          width: '9px',
                          height: '9px',
                          borderRadius: '2px',
                          backgroundColor: chartColors[i],
                          marginRight: '8px'
                        }}
                      />
                      {s}
                    </td>
                    <td style={{ textAlign: 'center', fontWeight: 600 }}>{cur}</td>
                    <td
                      style={{
                        textAlign: 'center',
                        color: 'var(--success)',
                        fontWeight: 600
                      }}
                    >
                      ▲ +{change}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Bottom Row: Recommendations + Calendar */}
      <div className="grid2">
        {/* Recommendations */}
        <div className="card">
          <div className="label">{d.recoTitle}</div>
          {d.recos.map((r, i) => (
            <div
              key={i}
              className="box"
              style={{ padding: '14px', marginBottom: '10px' }}
            >
              <div style={{ fontSize: '13.5px', fontWeight: 600, marginBottom: '4px' }}>
                💡 {r.t}
              </div>
              <div className="legend" style={{ margin: '0 0 10px', fontSize: '12px' }}>
                {r.d}
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => onNavigate('lesson', r.t)}
              >
                {t.openLesson} →
              </button>
            </div>
          ))}
        </div>

        {/* Calendar Scheduler */}
        <div className="card">
          <div className="label">{d.calTitle}</div>
          <div className="legend" style={{ margin: '-2px 0 12px' }}>
            {d.calHelp}
          </div>

          <div className="calhead">
            <button
              type="button"
              className="btn ghost"
              style={{ padding: '4px 10px' }}
              onClick={prevMonth}
            >
              ‹
            </button>
            <span
              style={{
                fontSize: '13.5px',
                fontWeight: 600,
                textTransform: 'capitalize'
              }}
            >
              {d.months[calMonth]} {calYear}
            </span>
            <button
              type="button"
              className="btn ghost"
              style={{ padding: '4px 10px' }}
              onClick={nextMonth}
            >
              ›
            </button>
          </div>

          <div className="calgrid">
            {d.weekdays.map((w, idx) => (
              <div key={idx} className="dow">
                {w}
              </div>
            ))}
          </div>

          <div className="calgrid" style={{ marginTop: '6px' }}>
            {emptyDays.map((_, i) => (
              <div key={`empty-${i}`} />
            ))}
            {monthDays.map((day) => {
              const isSelected = selectedDay === day;
              return (
                <div
                  key={day}
                  className={`calday ${isSelected ? 'sel' : ''}`}
                  onClick={() => {
                    setSelectedDay(day);
                    setIsScheduled(false);
                  }}
                >
                  {day}
                </div>
              );
            })}
          </div>

          <div
            style={{
              marginTop: '16px',
              paddingTop: '12px',
              borderTop: '1px solid var(--line)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}
          >
            <span style={{ fontSize: '12.5px', color: 'var(--muted)' }}>
              {d.nextLabel}{' '}
              <b style={{ color: 'var(--accent2)' }}>
                {selectedDay
                  ? `${selectedDay} de ${d.months[calMonth]}`
                  : d.calNone}
              </b>
            </span>

            <button
              type="button"
              className="btn pri"
              onClick={() => setIsScheduled(true)}
            >
              {isScheduled ? '✓ Agendado' : d.calBtn}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
