'use client';

import React, { useEffect, useReducer, useRef, useState } from 'react';
import { ApiError } from '../../services/apiClient';
import { labelingService } from '../../services/labelingService';
import {
  buildLabelingReviewRequest,
  createLabelingReviewForm,
  editableMetrics,
  labelingReviewReducer,
  validateLabelingReview,
  type LabelingReviewForm,
} from '../../services/labelingReviewModel';
import { formatCaseDateTime, formatDuration, labelingReasonLabel } from '../../services/labelingModel';
import type {
  LabelingCase,
  LabelingCaseDetail,
  LabelingLease,
  LabelingMetric,
  LabelingReview,
} from '../../types/api';
import { LabelingRecordingPlayer } from './LabelingRecordingPlayer';

const EMPTY_FORM: LabelingReviewForm = {
  overallComment: '', rubric: {}, metrics: {}, idempotencyKey: '',
};

interface WorkspaceProps {
  item: LabelingCase;
  onQueuesChanged: () => Promise<void>;
}

function nextKey(): string {
  return crypto.randomUUID();
}

function problemCode(error: unknown): string | null {
  return error instanceof ApiError ? error.problem.code ?? null : null;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'No fue posible completar la operación.';
}

export function LabelingCaseWorkspace({ item, onQueuesChanged }: WorkspaceProps) {
  const [detail, setDetail] = useState<LabelingCaseDetail | null>(null);
  const [reviews, setReviews] = useState<LabelingReview[]>([]);
  const [currentReview, setCurrentReview] = useState<LabelingReview | null>(null);
  const [lease, setLease] = useState<LabelingLease | null>(null);
  const leaseRef = useRef<LabelingLease | null>(null);
  const renewingRef = useRef(false);
  const lastActivityRef = useRef(0);
  const [form, dispatch] = useReducer(labelingReviewReducer, EMPTY_FORM);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [readOnly, setReadOnly] = useState(true);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [now, setNow] = useState(0);

  const storeLease = (value: LabelingLease | null) => {
    leaseRef.current = value;
    setLease(value);
    if (value) {
      const currentTime = Date.now();
      setNow(currentTime);
      if (!lastActivityRef.current) lastActivityRef.current = currentTime;
    }
  };

  useEffect(() => {
    let ignore = false;
    const controller = new AbortController();

    async function load() {
      try {
        const [loadedDetail, loadedReviews] = await Promise.all([
          labelingService.getDetail(item.caseId, controller.signal),
          labelingService.listReviews(item.caseId, controller.signal),
        ]);
        if (ignore) return;
        const activeReview = loadedReviews.find(review => review.isCurrent) ?? null;
        setDetail(loadedDetail);
        setReviews(loadedReviews);
        setCurrentReview(activeReview);
        dispatch({ type: 'replace', form: createLabelingReviewForm(loadedDetail, activeReview, nextKey()) });
        if (loadedDetail.status === 'pending' && loadedDetail.sourceStatus !== 'ambiguous') {
          try {
            const claimed = await labelingService.acquireLease(item.caseId);
            if (!ignore) {
              storeLease(claimed);
              setReadOnly(false);
            }
          } catch (claimError) {
            if (!ignore) {
              setReadOnly(true);
              setOperationError(problemCode(claimError) === 'LEASE_CONFLICT'
                ? 'Otro experto está revisando este caso. Puedes consultarlo en modo lectura.'
                : message(claimError));
            }
          }
        } else {
          setReadOnly(true);
        }
      } catch (loadError) {
        if (!ignore) setOperationError(message(loadError));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    void load();
    return () => {
      ignore = true;
      controller.abort();
      const activeLease = leaseRef.current;
      leaseRef.current = null;
      if (activeLease) void labelingService.releaseLease(item.caseId, activeLease).catch(() => undefined);
    };
  }, [item.caseId]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const currentTime = Date.now();
      setNow(currentTime);
      const activeLease = leaseRef.current;
      const recentlyActive = currentTime - lastActivityRef.current < 5 * 60 * 1000;
      const nearExpiry = activeLease
        ? Date.parse(activeLease.expiresAt) - currentTime < 5 * 60 * 1000
        : false;
      if (!activeLease || document.visibilityState !== 'visible' || !recentlyActive || !nearExpiry || renewingRef.current) return;
      renewingRef.current = true;
      labelingService.renewLease(item.caseId, activeLease)
        .then(renewed => {
          storeLease(renewed);
          setOperationError(null);
        })
        .catch(renewError => {
          setReadOnly(true);
          setConflict(problemCode(renewError) ?? 'LEASE_RENEWAL_FAILED');
          setOperationError('La reserva expiró o fue reemplazada. Tus cambios se conservaron localmente.');
        })
        .finally(() => { renewingRef.current = false; });
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [item.caseId]);

  const markActivity = () => { lastActivityRef.current = Date.now(); };

  const change = (type: 'rubricValue' | 'rubricComment' | 'metricValue' | 'metricComment', key: string, value: string) => {
    dispatch({ type, key, value, nextIdempotencyKey: nextKey() });
    setErrors({});
    setNotice(null);
  };

  const beginNewReview = async () => {
    setOperationError(null);
    setConflict(null);
    try {
      const claimed = await labelingService.acquireLease(item.caseId);
      storeLease(claimed);
      setReadOnly(false);
      setNotice('Nueva revisión iniciada. La revisión confirmada permanece intacta hasta guardar.');
    } catch (claimError) {
      setReadOnly(true);
      setOperationError(problemCode(claimError) === 'LEASE_CONFLICT'
        ? 'Otro experto posee la reserva. El caso permanece en modo lectura.'
        : message(claimError));
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!detail || !lease || readOnly) return;
    const validation = validateLabelingReview(detail, form);
    setErrors(validation);
    if (Object.keys(validation).length) return;
    const request = buildLabelingReviewRequest(
      detail,
      form,
      lease,
      currentReview?.reviewId ?? null,
    );
    setSubmitting(true);
    setOperationError(null);
    setConflict(null);
    try {
      const saved = await labelingService.submitReview(item.caseId, request);
      storeLease(null);
      setCurrentReview(saved);
      setReviews(previous => [saved, ...previous.filter(review => review.reviewId !== saved.reviewId)]);
      setDetail(previous => previous ? {
        ...previous,
        status: 'reviewed',
        contentRevision: saved.contentRevision,
        currentReview: {
          reviewId: saved.reviewId,
          reviewNo: saved.reviewNo,
          reviewerCode: saved.reviewerCode,
          submittedAt: saved.submittedAt,
        },
      } : previous);
      dispatch({ type: 'replace', form: createLabelingReviewForm(detail, saved, nextKey()) });
      setReadOnly(true);
      setNotice(`Revisión #${saved.reviewNo} confirmada. El caso pasó a Revisadas.`);
      void onQueuesChanged();
    } catch (submitError) {
      const code = problemCode(submitError);
      if (submitError instanceof ApiError && submitError.problem.status === 409) {
        setConflict(code ?? 'CONFLICT');
        setOperationError('El caso cambió o la reserva dejó de ser válida. Tus cambios no se descartaron.');
      } else {
        setOperationError(message(submitError));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const copyDraft = async () => {
    if (!detail || !lease) return;
    const draft = {
      caseId: item.caseId,
      expectedContentRevision: lease.contentRevision,
      overallComment: form.overallComment,
      rubric: form.rubric,
      metrics: form.metrics,
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(draft, null, 2));
      setNotice('Borrador copiado al portapapeles. No incluye el token de reserva.');
    } catch {
      setOperationError('No fue posible copiar el borrador.');
    }
  };

  const discardAndReload = async () => {
    const oldLease = leaseRef.current;
    storeLease(null);
    if (oldLease) await labelingService.releaseLease(item.caseId, oldLease).catch(() => undefined);
    setLoading(true);
    setConflict(null);
    setOperationError(null);
    try {
      const [loadedDetail, loadedReviews] = await Promise.all([
        labelingService.getDetail(item.caseId),
        labelingService.listReviews(item.caseId),
      ]);
      const activeReview = loadedReviews.find(review => review.isCurrent) ?? null;
      setDetail(loadedDetail);
      setReviews(loadedReviews);
      setCurrentReview(activeReview);
      dispatch({ type: 'replace', form: createLabelingReviewForm(loadedDetail, activeReview, nextKey()) });
      setReadOnly(true);
      if (loadedDetail.status === 'pending') {
        const claimed = await labelingService.acquireLease(item.caseId);
        storeLease(claimed);
        setReadOnly(false);
      }
    } catch (reloadError) {
      setOperationError(message(reloadError));
    } finally {
      setLoading(false);
    }
  };

  if (loading || !detail) {
    return <div role="status" style={{ minHeight: '300px', display: 'grid', placeItems: 'center', color: 'var(--muted)' }}>Cargando caso…</div>;
  }

  const leaseSeconds = lease ? Math.max(0, Math.ceil((Date.parse(lease.expiresAt) - now) / 1000)) : 0;
  const minutes = Math.floor(leaseSeconds / 60);
  const seconds = leaseSeconds % 60;
  const groupedMetrics = detail.metricGroups.map(group => ({
    ...group,
    metrics: group.metrics.filter(metric => editableMetrics(detail).some(itemMetric => itemMetric.metricKey === metric.metricKey)),
  })).filter(group => group.metrics.length > 0);

  return (
    <div onPointerDownCapture={markActivity} onKeyDownCapture={markActivity} onInputCapture={markActivity}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', borderBottom: '1px solid var(--line)', paddingBottom: '12px' }}>
        <div>
          <div className="label" style={{ margin: 0, fontSize: '15px' }}>Caso #{detail.caseNumber} — Revisión de Calidad</div>
          <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '2px' }}>
            Escenario: <b>{detail.scenario.title}</b> · Duración: <b>{formatDuration(detail.session.durationSeconds)}</b>
          </div>
        </div>
        <span className="tagm" style={{ background: 'var(--soft)', color: 'var(--accent2)', fontWeight: 600 }}>{labelingReasonLabel(detail)}</span>
      </header>

      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', marginBottom: '12px', fontSize: '11px' }}>
        <span style={{ color: readOnly ? 'var(--muted)' : 'var(--accent)' }}>
          {readOnly ? 'Modo lectura' : `Reserva activa · ${minutes}:${String(seconds).padStart(2, '0')}`}
        </span>
        <span style={{ color: 'var(--muted)' }}>{formatCaseDateTime(detail.session.finishedAt)}</span>
      </div>

      {notice && <div role="status" className="box" style={{ padding: '10px', marginBottom: '12px', color: 'var(--accent)' }}>{notice}</div>}
      {operationError && <div role="alert" className="box" style={{ padding: '10px', marginBottom: '12px', color: 'var(--accent2)' }}>{operationError}</div>}
      {conflict && (
        <div className="box" style={{ padding: '10px', marginBottom: '12px' }}>
          <div style={{ fontSize: '11px', marginBottom: '8px' }}>Conflicto: {conflict}. Conserva una copia o descarta y recarga el estado vigente.</div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button type="button" className="btn ghost" onClick={() => void copyDraft()}>Copiar borrador</button>
            <button type="button" className="btn ghost" onClick={() => void discardAndReload()}>Descartar y recargar</button>
          </div>
        </div>
      )}

      <form onSubmit={submit}>
        <div className="grid2" style={{ marginBottom: '16px', gap: '16px', alignItems: 'start' }}>
          <LabelingRecordingPlayer
            caseId={detail.caseId}
            availability={detail.recording.availability}
            persistedDuration={detail.recording.durationSeconds}
          />
          <section style={{ background: 'var(--soft)', padding: '14px 16px', borderRadius: '8px', border: '1px solid var(--line)' }}>
            <div className="legend" style={{ fontWeight: 600, color: 'var(--ink)', marginBottom: '10px' }}>Rúbrica · IA vs calibración experta</div>
            {detail.rubric.areas.filter(area => area.editable).map(area => {
              const field = form.rubric[area.areaId];
              return (
                <ScoreField
                  key={area.areaId}
                  id={`rubric-${area.areaId}`}
                  label={area.label}
                  aiValue={area.aiValue}
                  value={field?.value ?? ''}
                  comment={field?.comment ?? ''}
                  disabled={readOnly}
                  error={errors[`rubric.${area.areaId}`]}
                  commentError={errors[`rubric.${area.areaId}.comment`]}
                  min={0}
                  max={100}
                  step={0.01}
                  onValue={value => change('rubricValue', area.areaId, value)}
                  onComment={value => change('rubricComment', area.areaId, value)}
                />
              );
            })}
          </section>
        </div>

        <div className="label">Métricas observadas</div>
        {groupedMetrics.length === 0 ? (
          <div className="box" style={{ padding: '12px', color: 'var(--muted)', marginBottom: '14px' }}>No hay métricas editables para este caso.</div>
        ) : groupedMetrics.map(group => (
          <section key={group.categoryKey} className="box" style={{ padding: '12px', marginBottom: '12px' }}>
            <div className="legend" style={{ fontWeight: 700, marginBottom: '8px' }}>{group.label}</div>
            <div className="grid2" style={{ gap: '12px' }}>
              {group.metrics.map(metric => (
                <MetricField
                  key={metric.metricKey}
                  metric={metric}
                  value={form.metrics[metric.metricKey]?.value ?? ''}
                  comment={form.metrics[metric.metricKey]?.comment ?? ''}
                  disabled={readOnly}
                  error={errors[`metric.${metric.metricKey}`]}
                  commentError={errors[`metric.${metric.metricKey}.comment`]}
                  onValue={value => change('metricValue', metric.metricKey, value)}
                  onComment={value => change('metricComment', metric.metricKey, value)}
                />
              ))}
            </div>
          </section>
        ))}

        <label className="label" htmlFor={`overall-${item.caseId}`}>Observaciones del experto para reentrenamiento</label>
        <textarea
          id={`overall-${item.caseId}`}
          className="area"
          value={form.overallComment}
          disabled={readOnly}
          onChange={event => dispatch({ type: 'overallComment', value: event.target.value, nextIdempotencyKey: nextKey() })}
          maxLength={4000}
          style={{ minHeight: '75px', marginBottom: '4px', lineHeight: 1.5 }}
        />
        {errors.overallComment && <div role="alert" style={{ color: 'crimson', fontSize: '11px', marginBottom: '10px' }}>{errors.overallComment}</div>}

        <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
          {!readOnly && (
            <button type="submit" className="btn pri" disabled={submitting || !lease}>
              {submitting ? 'Guardando…' : '✓ Confirmar / Guardar corrección'}
            </button>
          )}
          {readOnly && currentReview && !conflict && (
            <button type="button" className="btn pri" onClick={() => void beginNewReview()}>Nueva revisión</button>
          )}
        </div>
      </form>

      {reviews.length > 0 && (
        <section style={{ marginTop: '18px', borderTop: '1px solid var(--line)', paddingTop: '12px' }}>
          <div className="label">Historial inmutable</div>
          {reviews.map(review => (
            <div key={review.reviewId} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', padding: '5px 0' }}>
              <span>Revisión #{review.reviewNo} · {review.reviewerCode}{review.isCurrent ? ' · vigente' : ''}</span>
              <span style={{ color: 'var(--muted)' }}>{formatCaseDateTime(review.submittedAt)}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

interface ScoreFieldProps {
  id: string;
  label: string;
  aiValue: number | null;
  value: string;
  comment: string;
  disabled: boolean;
  error?: string;
  commentError?: string;
  min?: number;
  max?: number;
  step: number;
  onValue: (value: string) => void;
  onComment: (value: string) => void;
}

function ScoreField(props: ScoreFieldProps) {
  return (
    <div style={{ marginBottom: '10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
        <label htmlFor={props.id} style={{ fontSize: '12px', fontWeight: 600 }}>{props.label}</label>
        <span style={{ fontSize: '11px', color: 'var(--muted)' }}>IA: {props.aiValue ?? '—'} →</span>
        <input
          id={props.id}
          type="number"
          min={props.min}
          max={props.max}
          step={props.step}
          value={props.value}
          disabled={props.disabled}
          onChange={event => props.onValue(event.target.value)}
          aria-invalid={Boolean(props.error)}
          style={{ width: '70px', height: '30px', textAlign: 'center', border: '1px solid var(--line)', borderRadius: '6px' }}
        />
      </div>
      {props.error && <div role="alert" style={{ color: 'crimson', fontSize: '10px' }}>{props.error}</div>}
      <input
        aria-label={`Justificación para ${props.label}`}
        type="text"
        value={props.comment}
        disabled={props.disabled}
        onChange={event => props.onComment(event.target.value)}
        placeholder="Justificación del ajuste (obligatoria si cambia)"
        maxLength={2000}
        style={{ width: '100%', marginTop: '5px', padding: '6px', border: '1px solid var(--line)', borderRadius: '5px', fontSize: '11px' }}
      />
      {props.commentError && <div role="alert" style={{ color: 'crimson', fontSize: '10px' }}>{props.commentError}</div>}
    </div>
  );
}

function MetricField({ metric, ...props }: {
  metric: LabelingMetric;
  value: string;
  comment: string;
  disabled: boolean;
  error?: string;
  commentError?: string;
  onValue: (value: string) => void;
  onComment: (value: string) => void;
}) {
  return (
    <ScoreField
      {...props}
      id={`metric-${metric.metricKey.replace(/[^a-z0-9_-]/gi, '-')}`}
      label={`${metric.label} (${metric.unit})`}
      aiValue={metric.aiValue}
      min={metric.observation?.technicalMin ?? undefined}
      max={metric.observation?.technicalMax ?? undefined}
      step={metric.observation?.valueType === 'integer' ? 1 : 10 ** -metric.precision}
    />
  );
}
