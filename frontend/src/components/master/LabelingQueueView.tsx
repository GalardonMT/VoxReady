'use client';

import React, { useEffect, useRef, useState } from 'react';
import { labelingService, type LabelingQueuePage } from '../../services/labelingService';
import {
  formatCaseDateTime,
  formatDuration,
  formatScore,
  labelingAlerts,
  labelingReasonLabel,
  preserveLabelingSelection,
} from '../../services/labelingModel';
import type { LabelingCase, LabelingCaseStatus } from '../../types/api';
import { MasterScreen } from './MasterDashboard';
import { LabelingCaseWorkspace } from './LabelingCaseWorkspace';
import { LABELING_CASE_TARGET_KEY } from '../../services/qualityReviewModel';

interface LabelingQueueViewProps {
  onNavigate?: (screen: MasterScreen) => void;
}

const EMPTY_PAGE: LabelingQueuePage = { items: [], total: 0 };

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : 'No fue posible cargar la cola de etiquetado.';
}

export const LabelingQueueView: React.FC<LabelingQueueViewProps> = () => {
  const [pending, setPending] = useState<LabelingQueuePage>(EMPTY_PAGE);
  const [reviewed, setReviewed] = useState<LabelingQueuePage>(EMPTY_PAGE);
  const [status, setStatus] = useState<LabelingCaseStatus>('pending');
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const selectedCaseIdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyQueues = (queues: { pending: LabelingQueuePage; reviewed: LabelingQueuePage }) => {
    setPending(queues.pending);
    setReviewed(queues.reviewed);
    const selected = preserveLabelingSelection(
      selectedCaseIdRef.current,
      queues.pending.items,
      queues.reviewed.items,
    );
    selectedCaseIdRef.current = selected;
    setSelectedCaseId(selected);
    const selectedCase = [...queues.pending.items, ...queues.reviewed.items]
      .find(item => item.caseId === selected);
    if (selectedCase) setStatus(selectedCase.status);
  };

  useEffect(() => {
    let ignore = false;
    const controller = new AbortController();
    const requestedCaseId = sessionStorage.getItem(LABELING_CASE_TARGET_KEY);
    if (requestedCaseId) {
      selectedCaseIdRef.current = requestedCaseId;
      sessionStorage.removeItem(LABELING_CASE_TARGET_KEY);
    }

    async function loadInitialQueues() {
      try {
        const queues = await labelingService.listQueues(controller.signal);
        if (!ignore) {
          applyQueues(queues);
          setError(null);
        }
      } catch (loadError) {
        if (!ignore) setError(readableError(loadError));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    void loadInitialQueues();
    return () => {
      ignore = true;
      controller.abort();
    };
  }, []);

  const refresh = async () => {
    setRefreshing(true);
    try {
      applyQueues(await labelingService.listQueues());
      setError(null);
    } catch (loadError) {
      setError(readableError(loadError));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const selectCase = (caseId: string) => {
    selectedCaseIdRef.current = caseId;
    setSelectedCaseId(caseId);
  };

  const changeStatus = (nextStatus: LabelingCaseStatus) => {
    setStatus(nextStatus);
    const nextItems = nextStatus === 'pending' ? pending.items : reviewed.items;
    if (!nextItems.some(item => item.caseId === selectedCaseIdRef.current)) {
      const nextId = nextItems[0]?.caseId ?? null;
      selectedCaseIdRef.current = nextId;
      setSelectedCaseId(nextId);
    }
  };

  const page = status === 'pending' ? pending : reviewed;
  const activeCase = page.items.find(item => item.caseId === selectedCaseId) ?? null;

  return (
    <div className="canvas-content">
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <aside style={{ width: '250px', flexShrink: 0 }} aria-label="Casos de etiquetado">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <div className="label" style={{ margin: 0 }}>Casos en cola</div>
            <span className="tagm" style={{ background: 'var(--soft)', color: 'var(--accent2)', fontWeight: 700, fontSize: '11px' }}>
              {page.total} {status === 'pending' ? 'pendientes' : 'revisados'}
            </span>
          </div>

          <div style={{ display: 'flex', gap: '6px', marginBottom: '10px' }} role="tablist" aria-label="Estado de los casos">
            {(['pending', 'reviewed'] as const).map(option => (
              <button
                key={option}
                type="button"
                role="tab"
                aria-selected={status === option}
                className={status === option ? 'btn pri' : 'btn ghost'}
                onClick={() => changeStatus(option)}
                style={{ flex: 1, padding: '6px 8px', fontSize: '11px' }}
              >
                {option === 'pending' ? 'Pendientes' : 'Revisadas'}
              </button>
            ))}
          </div>

          {error && (
            <div className="box" role="alert" style={{ padding: '12px', marginBottom: '10px', borderColor: 'var(--accent2)' }}>
              <div style={{ fontSize: '12px', color: 'var(--accent2)', marginBottom: '8px' }}>{error}</div>
              <button type="button" className="btn ghost" onClick={() => void refresh()} disabled={refreshing}>
                {refreshing ? 'Reintentando…' : 'Reintentar'}
              </button>
            </div>
          )}

          {loading ? (
            <div className="box" role="status" style={{ padding: '14px', color: 'var(--muted)' }}>
              Cargando casos…
            </div>
          ) : page.items.length === 0 && !error ? (
            <div className="box" style={{ padding: '14px', color: 'var(--muted)', fontSize: '12px' }}>
              No hay casos {status === 'pending' ? 'pendientes' : 'revisados'}.
            </div>
          ) : (
            page.items.map(item => (
              <CaseCard
                key={item.caseId}
                item={item}
                selected={item.caseId === selectedCaseId}
                onSelect={() => selectCase(item.caseId)}
              />
            ))
          )}

          {!loading && !error && page.items.length > 0 && (
            <button type="button" className="btn ghost" onClick={() => void refresh()} disabled={refreshing} style={{ width: '100%', marginTop: '2px' }}>
              {refreshing ? 'Actualizando…' : 'Actualizar cola'}
            </button>
          )}
        </aside>

        <section className="card col" style={{ padding: '20px' }} aria-live="polite">
          {activeCase ? (
            <LabelingCaseWorkspace
              key={activeCase.caseId}
              item={activeCase}
              onQueuesChanged={refresh}
            />
          ) : (
            <div style={{ minHeight: '300px', display: 'grid', placeItems: 'center', color: 'var(--muted)' }}>
              {loading ? 'Cargando detalle del caso…' : 'Selecciona un caso para revisar su información.'}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

function CaseCard({ item, selected, onSelect }: { item: LabelingCase; selected: boolean; onSelect: () => void }) {
  const alerts = labelingAlerts(item);
  return (
    <button
      type="button"
      className="box"
      onClick={onSelect}
      aria-pressed={selected}
      style={{
        width: '100%', padding: '12px', marginBottom: '10px', cursor: 'pointer', textAlign: 'left',
        borderLeft: selected ? '4px solid var(--accent2)' : '4px solid transparent',
        background: selected ? 'var(--soft)' : 'var(--panel)', borderRadius: '6px',
        boxShadow: selected ? '0 2px 8px rgba(0,0,0,0.06)' : 'none', transition: 'all 0.15s ease',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
        <span style={{ fontSize: '13px', fontWeight: 600 }}>Caso #{item.caseNumber}</span>
        <span style={{ fontSize: '11px', color: 'var(--muted)' }}>{formatDuration(item.session.durationSeconds)}</span>
      </div>
      <div style={{ fontSize: '10.5px', color: 'var(--muted)', marginBottom: '4px' }}>
        {formatCaseDateTime(item.session.finishedAt)}
      </div>
      <div className="legend" style={{ margin: 0, fontSize: '11.5px', color: alerts.length ? 'var(--accent2)' : 'var(--muted)', fontWeight: alerts.length ? 600 : 400 }}>
        {labelingReasonLabel(item)}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', fontSize: '11px', color: 'var(--ink)', marginTop: '5px' }}>
        <span>{item.scenario.title}</span>
        <strong>{formatScore(item.report.overallScore)}</strong>
      </div>
    </button>
  );
}
