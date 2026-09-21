'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { INITIAL_LABELING_QUEUE } from '../../mock/mockData';
import { MasterScreen } from './MasterDashboard';

interface LabelingQueueViewProps {
  onNavigate?: (screen: MasterScreen) => void;
}

export const LabelingQueueView: React.FC<LabelingQueueViewProps> = () => {
  const { t } = useI18n();
  const d = t.L.m3;

  const [activeCaseIndex, setActiveCaseIndex] = useState(0);
  const activeCase = INITIAL_LABELING_QUEUE[activeCaseIndex] || INITIAL_LABELING_QUEUE[0];

  const [expertScores, setExpertScores] = useState<Record<string, number>>({
    expression: activeCase.expertScores?.expression ?? activeCase.aiScores.expression,
    tone: activeCase.expertScores?.tone ?? activeCase.aiScores.tone,
    coherence: activeCase.expertScores?.coherence ?? activeCase.aiScores.coherence,
    empathy: activeCase.expertScores?.empathy ?? activeCase.aiScores.empathy
  });

  const [expertComment, setExpertComment] = useState(activeCase.expertComment || '');
  const [confirmedNotice, setConfirmedNotice] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);

  // When switching cases, sync scores & comment
  const handleSelectCase = (idx: number) => {
    setActiveCaseIndex(idx);
    const selected = INITIAL_LABELING_QUEUE[idx];
    setExpertScores({
      expression: selected.expertScores?.expression ?? selected.aiScores.expression,
      tone: selected.expertScores?.tone ?? selected.aiScores.tone,
      coherence: selected.expertScores?.coherence ?? selected.aiScores.coherence,
      empathy: selected.expertScores?.empathy ?? selected.aiScores.empathy
    });
    setExpertComment(selected.expertComment || '');
    setIsPlaying(false);
  };

  const handleScoreChange = (areaKey: string, val: string) => {
    const num = parseInt(val, 10);
    if (!isNaN(num)) {
      setExpertScores((prev) => ({ ...prev, [areaKey]: Math.max(0, Math.min(100, num)) }));
    }
  };

  const handleConfirm = () => {
    setConfirmedNotice(true);
    setTimeout(() => {
      setConfirmedNotice(false);
      // Advance to next case in queue
      if (activeCaseIndex < INITIAL_LABELING_QUEUE.length - 1) {
        handleSelectCase(activeCaseIndex + 1);
      }
    }, 2000);
  };

  const handleSkip = () => {
    if (activeCaseIndex < INITIAL_LABELING_QUEUE.length - 1) {
      handleSelectCase(activeCaseIndex + 1);
    } else {
      handleSelectCase(0);
    }
  };

  return (
    <div className="canvas-content">
      {confirmedNotice && (
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
            Calibración experta guardada. Caso {activeCase.caseNumber} calibrado y encolado para el ciclo de reentrenamiento.
          </span>
        </div>
      )}

      <div className="row" style={{ alignItems: 'flex-start' }}>
        {/* Left Queue List */}
        <div style={{ width: '250px', flexShrink: 0 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '10px'
            }}
          >
            <div className="label" style={{ margin: 0 }}>
              {d.queueL}
            </div>
            <span
              className="tagm"
              style={{
                background: 'var(--soft)',
                color: 'var(--accent2)',
                fontWeight: 700,
                fontSize: '11px'
              }}
            >
              23 pendientes
            </span>
          </div>

          {INITIAL_LABELING_QUEUE.map((item, idx) => {
            const isSelected = idx === activeCaseIndex;
            return (
              <div
                key={item.id}
                className="box"
                style={{
                  padding: '12px',
                  marginBottom: '10px',
                  cursor: 'pointer',
                  borderLeft: isSelected
                    ? '4px solid var(--accent2)'
                    : '4px solid transparent',
                  background: isSelected ? 'var(--soft)' : 'var(--panel)',
                  borderRadius: '6px',
                  boxShadow: isSelected ? '0 2px 8px rgba(0,0,0,0.06)' : 'none',
                  transition: 'all 0.15s ease'
                }}
                onClick={() => handleSelectCase(idx)}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '4px'
                  }}
                >
                  <span style={{ fontSize: '13px', fontWeight: 600 }}>
                    Caso {item.caseNumber}
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
                    {item.videoDuration}
                  </span>
                </div>
                <div
                  className="legend"
                  style={{
                    margin: 0,
                    fontSize: '11.5px',
                    color: item.reason === 'low_confidence' ? 'var(--accent2)' : 'var(--muted)',
                    fontWeight: item.reason === 'low_confidence' ? 600 : 400
                  }}
                >
                  {item.reasonLabel}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--ink)', marginTop: '5px' }}>
                  {item.scenarioName}
                </div>
              </div>
            );
          })}
        </div>

        {/* Right Inspection & Adjudication */}
        <div className="card col" style={{ padding: '20px' }}>
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
            <div>
              <div className="label" style={{ margin: 0, fontSize: '15px' }}>
                Caso {activeCase.caseNumber} — Revisión de Calidad
              </div>
              <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '2px' }}>
                Escenario: <b>{activeCase.scenarioName}</b> · Duración: <b>{activeCase.videoDuration}</b>
              </div>
            </div>
            <span
              className="tagm"
              style={{
                background: activeCase.reason === 'low_confidence' ? 'var(--accentsoft)' : 'var(--soft)',
                color: activeCase.reason === 'low_confidence' ? 'var(--accent2)' : 'var(--ink)',
                fontWeight: 600,
                padding: '4px 10px'
              }}
            >
              {activeCase.reasonLabel}
            </span>
          </div>

          <div className="grid2" style={{ marginBottom: '16px', gap: '16px' }}>
            {/* Video Player Box */}
            <div
              className="vid"
              style={{
                minHeight: '210px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                padding: '12px',
                position: 'relative'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="tag" style={{ background: 'rgba(0,0,0,0.6)', color: '#fff' }}>
                  📹 {d.rec}
                </span>
                <span
                  style={{
                    background: 'rgba(0,0,0,0.6)',
                    color: '#fff',
                    fontSize: '11px',
                    padding: '2px 8px',
                    borderRadius: '4px'
                  }}
                >
                  Turno 3 de 8
                </span>
              </div>

              <div style={{ textAlign: 'center', margin: 'auto' }}>
                <button
                  type="button"
                  onClick={() => setIsPlaying(!isPlaying)}
                  style={{
                    background: 'rgba(255,255,255,0.2)',
                    border: 'none',
                    borderRadius: '50%',
                    width: '54px',
                    height: '54px',
                    color: '#fff',
                    fontSize: '24px',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '8px'
                  }}
                >
                  {isPlaying ? '⏸' : '▶'}
                </button>
                <div style={{ fontSize: '12.5px', color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,0.8)' }}>
                  {activeCase.scenarioName}
                </div>
              </div>

              {/* Scrubber controls */}
              <div
                style={{
                  background: 'rgba(0,0,0,0.5)',
                  padding: '6px 10px',
                  borderRadius: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}
              >
                <span style={{ color: '#fff', fontSize: '11px' }}>01:14</span>
                <div
                  style={{
                    flex: 1,
                    height: '4px',
                    background: 'rgba(255,255,255,0.3)',
                    borderRadius: '2px',
                    position: 'relative',
                    cursor: 'pointer'
                  }}
                >
                  <div
                    style={{
                      width: '38%',
                      height: '100%',
                      background: 'var(--accent2)',
                      borderRadius: '2px'
                    }}
                  />
                </div>
                <span style={{ color: '#fff', fontSize: '11px' }}>{activeCase.videoDuration}</span>
              </div>
            </div>

            {/* AI vs Expert Adjustment */}
            <div
              style={{
                background: 'var(--soft)',
                padding: '14px 16px',
                borderRadius: '8px',
                border: '1px solid var(--line)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between'
              }}
            >
              <div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '12px'
                  }}
                >
                  <span className="legend" style={{ fontWeight: 600, color: 'var(--ink)' }}>
                    {d.proposal}
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
                    Puntaje (0 - 100)
                  </span>
                </div>

                {[
                  { name: d.areas[0], key: 'expression', ai: activeCase.aiScores.expression },
                  { name: d.areas[1], key: 'tone', ai: activeCase.aiScores.tone },
                  { name: d.areas[2], key: 'coherence', ai: activeCase.aiScores.coherence },
                  { name: d.areas[3], key: 'empathy', keyFlag: true, ai: activeCase.aiScores.empathy }
                ].map((area) => {
                  const currentExpScore = expertScores[area.key] ?? area.ai;
                  const delta = currentExpScore - area.ai;

                  return (
                    <div
                      key={area.key}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: '12.5px',
                        margin: '10px 0',
                        padding: '6px 8px',
                        borderRadius: '6px',
                        background: area.keyFlag ? 'rgba(219, 100, 39, 0.08)' : 'transparent'
                      }}
                    >
                      <span style={{ fontWeight: area.keyFlag ? 600 : 500 }}>
                        {area.name} {area.keyFlag ? '⚠️' : ''}:
                      </span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ color: 'var(--muted)', fontSize: '12px' }}>
                          IA: <b>{area.ai}</b>
                        </span>
                        <span style={{ color: 'var(--muted)' }}>→</span>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={currentExpScore}
                          onChange={(e) => handleScoreChange(area.key, e.target.value)}
                          style={{
                            width: '54px',
                            height: '28px',
                            border: '1px solid var(--line)',
                            borderRadius: '6px',
                            textAlign: 'center',
                            fontWeight: 700,
                            background: 'var(--panel)',
                            color: 'var(--ink)'
                          }}
                        />
                        {delta !== 0 && (
                          <span
                            style={{
                              fontSize: '11px',
                              fontWeight: 700,
                              color: delta > 0 ? 'green' : 'crimson',
                              minWidth: '32px'
                            }}
                          >
                            {delta > 0 ? `+${delta}` : delta}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div
                style={{
                  fontSize: '11px',
                  color: 'var(--muted)',
                  marginTop: '10px',
                  paddingTop: '8px',
                  borderTop: '1px solid var(--line)'
                }}
              >
                Ajuste humano retroalimenta el optimizador bayesiano para futuros entrenamientos.
              </div>
            </div>
          </div>

          <div className="label">{d.commentL}</div>
          <textarea
            className="area"
            value={expertComment}
            onChange={(e) => setExpertComment(e.target.value)}
            placeholder={d.commentPh}
            style={{ minHeight: '75px', marginBottom: '18px', lineHeight: 1.5 }}
          />

          <div style={{ display: 'flex', gap: '12px' }}>
            <button type="button" className="btn pri" onClick={handleConfirm}>
              ✓ {d.confirm}
            </button>
            <button type="button" className="btn ghost" onClick={handleSkip}>
              ↷ {d.skip}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
