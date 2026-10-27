'use client';

import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../../services/apiClient';
import { changedThresholds, formatPublishedDate, thresholdFields, updateThreshold, validateMetricThresholds } from '../../services/metricsModel';
import type { MetricDefinition, MetricsVersion } from '../../services/metricsModel';
import { metricsService } from '../../services/metricsService';
import styles from './MetricsEditorView.module.css';

const categories = [
  { key: 'voice', title: 'Voz', icon: '◉', detail: 'Ritmo, pausas y dicción · Español' },
  { key: 'vision', title: 'Video', icon: '▣', detail: 'Mirada, postura y movimiento' },
  { key: 'content', title: 'Contenido', icon: '▤', detail: 'Líneas rojas y techo de puntaje' },
  { key: 'empathy', title: 'Empatía', icon: '♡', detail: 'Reconocimiento del afectado' },
  { key: 'governance', title: 'Gobernanza', icon: '◇', detail: 'Auditoría, acuerdo y muestreo' },
] as const;

const fieldNames: Record<string, string> = {
  warningLow: 'Inicio aceptable', optimalLow: 'Inicio óptimo', optimalHigh: 'Fin óptimo',
  warningHigh: 'Fin aceptable', optimalMax: 'Fin óptimo', warningMax: 'Fin aceptable',
  criticalBelow: 'Fin crítico', warningLevel: 'Inicio aceptable', optimalLevel: 'Inicio óptimo',
  normalBelow: 'Fin normal', auditAt: 'Inicio auditoría', halfWidth: 'Amplitud ±',
  cap: 'Techo de puntaje', rate: 'Tasa de muestreo',
};

const patterns: Record<string, string[]> = {
  'voice.wpm': ['bad', 'caution', 'good', 'caution', 'bad'],
  'voice.phonation_ratio': ['bad', 'caution', 'good', 'caution'],
  'voice.filler_density': ['good', 'caution', 'bad'],
  'voice.prolonged_pause': ['good', 'caution', 'bad'],
  'voice.hesitation_pause': ['good', 'caution', 'bad'],
  'vision.sway_tolerance': ['good', 'caution', 'bad'],
  'gov.disparity_delta': ['good', 'caution', 'bad'],
};

const colors: Record<string, string> = {
  good: '#8ac6aa', caution: '#f0cf87', bad: '#e8a19a',
};

function bandBackground(metric: MetricDefinition): string {
  const fields = thresholdFields(metric);
  const stops = [metric.min, ...fields.map(field => metric.thresholds[field]), metric.max];
  const pattern = patterns[metric.key] ?? ['bad', 'caution', 'good'];
  const parts = pattern.flatMap((zone, index) => {
    if (index >= stops.length - 1) return [];
    const start = ((stops[index] - metric.min) / (metric.max - metric.min)) * 100;
    const end = ((stops[index + 1] - metric.min) / (metric.max - metric.min)) * 100;
    return [`${colors[zone]} ${start}%`, `${colors[zone]} ${end}%`];
  });
  return `linear-gradient(90deg, ${parts.join(', ')})`;
}

function numberText(value: number, unit: string): string {
  return `${new Intl.NumberFormat('es-CL', { maximumFractionDigits: 3 }).format(value)}${unit ? ` ${unit}` : ''}`;
}

function MetricCard({ metric, editable, onChange }: {
  metric: MetricDefinition;
  editable: boolean;
  onChange: (field: string, value: number) => void;
}) {
  const bandRef = useRef<HTMLDivElement>(null);
  const fields = thresholdFields(metric);
  const errors = validateMetricThresholds(metric);
  const numberOnly = metric.control === 'number' || metric.key === 'gov.borderline_delta';
  const allowedRange = (field: string) => {
    const index = fields.indexOf(field);
    return {
      lower: index === 0 ? metric.min : metric.thresholds[fields[index - 1]] + metric.step,
      upper: index === fields.length - 1 ? metric.max : metric.thresholds[fields[index + 1]] - metric.step,
    };
  };
  const moveBoundary = (field: string, approximate: number) => {
    const { lower, upper } = allowedRange(field);
    const snapped = metric.min + Math.round((approximate - metric.min) / metric.step) * metric.step;
    const value = Math.min(upper, Math.max(lower, Number(snapped.toFixed(6))));
    if (Number.isFinite(value)) onChange(field, value);
  };
  const moveFromPointer = (field: string, clientX: number) => {
    const rect = bandRef.current?.getBoundingClientRect();
    if (rect && rect.width > 0) {
      moveBoundary(field, metric.min + Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)) * (metric.max - metric.min));
    }
  };
  return (
    <article className={styles.metricCard}>
      <div className={styles.metricIntro}>
        <div>
          <h4>{metric.label}</h4>
          <p>{metric.description}</p>
        </div>
        <span className={styles.unit}>{metric.unit || 'Escala'}</span>
      </div>
      {!numberOnly && (
        <div className={styles.bandWrap}>
          <div className={styles.band} ref={bandRef} style={{ background: bandBackground(metric) }}>
            {fields.map(field => (
              <button key={field} type="button" role="slider" className={styles.marker}
                style={{ left: `${((metric.thresholds[field] - metric.min) / (metric.max - metric.min)) * 100}%` }}
                disabled={!editable} aria-label={`${metric.label}: ${fieldNames[field] ?? field}`}
                aria-valuemin={allowedRange(field).lower} aria-valuemax={allowedRange(field).upper}
                aria-valuenow={Number.isFinite(metric.thresholds[field]) ? metric.thresholds[field] : undefined}
                aria-valuetext={numberText(metric.thresholds[field], metric.unit)}
                onPointerDown={event => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); moveFromPointer(field, event.clientX); }}
                onPointerMove={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) moveFromPointer(field, event.clientX); }}
                onKeyDown={event => {
                  if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') { event.preventDefault(); moveBoundary(field, metric.thresholds[field] - metric.step); }
                  if (event.key === 'ArrowRight' || event.key === 'ArrowUp') { event.preventDefault(); moveBoundary(field, metric.thresholds[field] + metric.step); }
                  if (event.key === 'Home') { event.preventDefault(); moveBoundary(field, metric.min); }
                  if (event.key === 'End') { event.preventDefault(); moveBoundary(field, metric.max); }
                }} />
            ))}
          </div>
          <div className={styles.scale}><span>{numberText(metric.min, metric.unit)}</span><span>{numberText(metric.max, metric.unit)}</span></div>
          <div className={styles.legend}><span><i className={styles.bad} />Crítico / auditoría</span><span><i className={styles.caution} />Aceptable / observación</span><span><i className={styles.good} />Óptimo / normal</span></div>
        </div>
      )}
      {metric.key === 'gov.borderline_delta' && <p className={styles.hint}>Auditoría entre {50 - metric.thresholds.halfWidth} y {50 + metric.thresholds.halfWidth} puntos; observación hasta 3 puntos fuera de esa ventana.</p>}
      <div className={styles.thresholdGrid}>
        {fields.map(field => {
          const value = metric.thresholds[field];
          const id = `metric-${metric.key.replaceAll('.', '-')}-${field}`;
          return (
            <div className={styles.threshold} key={field}>
              <label htmlFor={id}>{fieldNames[field] ?? field}</label>
              <div className={styles.numberWrap}>
                <input id={id} type="number" min={metric.min} max={metric.max} step={metric.step}
                  value={Number.isFinite(value) ? value : ''} disabled={!editable}
                  onChange={event => onChange(field, event.target.value === '' ? NaN : Number(event.target.value))} />
                <span>{metric.unit}</span>
              </div>
            </div>
          );
        })}
      </div>
      {errors.length > 0 && <p className={styles.error} role="alert">{errors[0]}</p>}
    </article>
  );
}

export function MetricsEditorView() {
  const [published, setPublished] = useState<MetricsVersion | null>(null);
  const [draft, setDraft] = useState<MetricsVersion | null>(null);
  const [metrics, setMetrics] = useState<MetricDefinition[]>([]);
  const [openCategory, setOpenCategory] = useState<string | null>('voice');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    metricsService.getWorkspace().then(workspace => {
      if (!active) return;
      setPublished(workspace.published);
      setDraft(workspace.draft);
      setMetrics(workspace.draft?.metrics ?? workspace.published?.metrics ?? []);
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : 'No se pudieron cargar las métricas.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const savedMetrics = draft?.metrics ?? published?.metrics ?? [];
  const unsaved = changedThresholds(savedMetrics, metrics).length > 0;
  const publishedChanges = changedThresholds(published?.metrics ?? [], metrics);
  const savedChanges = changedThresholds(published?.metrics ?? [], draft?.metrics ?? []);
  const validationErrors = metrics.flatMap(validateMetricThresholds);

  const changeValue = (key: string, field: string, value: number) => {
    setMetrics(current => current.map(metric => metric.key === key ? updateThreshold(metric, field, value) : metric));
    setReviewing(false);
    setConfirmDiscard(false);
    setMessage('');
  };

  const handleConflict = async (cause: unknown) => {
    if (cause instanceof ApiError && cause.problem.status === 409) {
      try {
        const workspace = await metricsService.getWorkspace();
        setPublished(workspace.published);
        setDraft(workspace.draft);
        setMetrics(workspace.draft?.metrics ?? workspace.published?.metrics ?? []);
        setReviewing(false);
        setConfirmDiscard(false);
        setError('Otra persona modificó esta versión. Se cargaron los valores más recientes; revisa tus cambios antes de continuar.');
      } catch (refreshError) {
        setError(refreshError instanceof Error ? refreshError.message : 'No se pudieron recuperar los valores más recientes.');
      }
    } else {
      setError(cause instanceof Error ? cause.message : 'No se pudo completar la acción.');
    }
  };

  const createDraft = async () => {
    setBusy(true); setError(''); setMessage('');
    try {
      const next = await metricsService.createDraft();
      setDraft(next); setMetrics(next.metrics); setOpenCategory('voice');
      setMessage(`Borrador ${next.versionLabel} creado. Puedes ajustar sus límites.`);
    } catch (cause) { await handleConflict(cause); }
    finally { setBusy(false); }
  };

  const saveDraft = async () => {
    if (!draft || validationErrors.length) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const saved = await metricsService.saveDraft(draft, metrics);
      setDraft(saved); setMetrics(saved.metrics);
      setMessage(`Borrador ${saved.versionLabel} guardado.`);
    } catch (cause) { await handleConflict(cause); }
    finally { setBusy(false); }
  };

  const publishDraft = async () => {
    if (!draft || unsaved || validationErrors.length) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const next = await metricsService.publishDraft(draft);
      setPublished(next); setDraft(null); setMetrics(next.metrics); setReviewing(false);
      setMessage(`Versión ${next.versionLabel} publicada. Las versiones anteriores se conservan.`);
    } catch (cause) { await handleConflict(cause); }
    finally { setBusy(false); }
  };

  const discardDraft = async () => {
    if (!draft) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await metricsService.discardDraft(draft);
      setDraft(null);
      setMetrics(published?.metrics ?? []);
      setConfirmDiscard(false);
      setReviewing(false);
      setMessage('Borrador descartado. Se muestran los límites de la versión publicada.');
    } catch (cause) { await handleConflict(cause); }
    finally { setBusy(false); }
  };

  if (loading) return <div className={styles.page} role="status">Cargando métricas desde la base de datos…</div>;
  if (!published && !draft) return <div className={styles.page}><h2>Editor de métricas</h2><p className={styles.error} role="alert">{error || 'No hay una versión publicada disponible.'}</p><button type="button" className="btn ghost" onClick={() => window.location.reload()}>Reintentar</button></div>;

  return (
    <div className={styles.page}>
      <div className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>CONFIGURACIÓN MAESTRA · VISUM</span>
          <h2>Editor de métricas</h2>
          <p>Ajusta los intervalos por categoría y publica una nueva versión para su integración posterior.</p>
        </div>
        <div className={styles.versionBox}>
          <span>Versión publicada</span>
          <strong>{published ? `${formatPublishedDate(published.publishedAt)} · Versión ${published.versionNumber}` : 'Sin versión'}</strong>
          {published && <small className={styles.versionId}>ID: {published.versionLabel}</small>}
          <small>{draft ? `Borrador ${draft.versionLabel} en edición` : 'Sin borrador activo'}</small>
        </div>
      </div>

      {error && <div className={styles.errorBanner} role="alert">{error}</div>}
      {message && <div className={styles.successBanner} role="status">{message}</div>}

      <div className={styles.toolbar}>
        <div><strong>{metrics.length} métricas</strong><span> · {categories.length} categorías · Voz en español</span></div>
        <div className={styles.actions}>
          {!draft && <button type="button" className="btn pri" disabled={busy || !published} onClick={createDraft}>Crear borrador</button>}
          {draft && <>
            <button type="button" className="btn ghost" disabled={busy || !unsaved || validationErrors.length > 0} onClick={saveDraft}>Guardar borrador</button>
            <button type="button" className="btn pri" disabled={busy || unsaved || validationErrors.length > 0 || savedChanges.length === 0} onClick={() => setReviewing(true)}>Revisar y publicar</button>
            <button type="button" className="btn ghost" disabled={busy} onClick={() => { setReviewing(false); setConfirmDiscard(true); }}>Descartar borrador</button>
          </>}
        </div>
      </div>
      {draft && <p className={styles.saveState}>{unsaved ? 'Hay cambios sin guardar. Guarda el borrador antes de publicar.' : 'Todos los cambios del borrador están guardados.'}</p>}

      <div className={styles.categories}>
        {categories.map(category => {
          const items = metrics.filter(metric => metric.category === category.key);
          const expanded = openCategory === category.key;
          const changeCount = publishedChanges.filter(change => items.some(item => item.key === change.key)).length;
          return (
            <section key={category.key} className={`${styles.category} ${expanded ? styles.expanded : ''}`}>
              <h3>
                <button type="button" className={styles.categoryButton} aria-expanded={expanded} aria-controls={`metrics-${category.key}`}
                  onClick={() => setOpenCategory(expanded ? null : category.key)}>
                  <span className={styles.categoryIcon} aria-hidden="true">{category.icon}</span>
                  <span className={styles.categoryTitle}><strong>{category.title}</strong><small>{category.detail}</small></span>
                  <span className={styles.count}>{items.length} {items.length === 1 ? 'métrica' : 'métricas'}</span>
                  {changeCount > 0 && <span className={styles.changed}>{changeCount} {changeCount === 1 ? 'cambio' : 'cambios'}</span>}
                  <span className={styles.chevron} aria-hidden="true">⌄</span>
                </button>
              </h3>
              {expanded && <div id={`metrics-${category.key}`} className={styles.categoryBody}>
                {items.map(metric => <MetricCard key={metric.key} metric={metric} editable={Boolean(draft) && !busy}
                  onChange={(field, value) => changeValue(metric.key, field, value)} />)}
              </div>}
            </section>
          );
        })}
      </div>

      {confirmDiscard && draft && <section className={styles.discardConfirm} aria-labelledby="discard-title">
        <h3 id="discard-title">¿Descartar el borrador {draft.versionLabel}?</h3>
        <p role="alert">Se perderán los cambios guardados en este borrador y cualquier cambio sin guardar. La versión publicada seguirá disponible.</p>
        <div className={styles.reviewActions}>
          <button type="button" className="btn ghost" disabled={busy} onClick={() => setConfirmDiscard(false)}>Conservar borrador</button>
          <button type="button" className="btn pri" disabled={busy} onClick={discardDraft}>{busy ? 'Descartando…' : 'Confirmar descarte'}</button>
        </div>
      </section>}

      {reviewing && draft && !unsaved && <section className={styles.review} aria-labelledby="review-title">
        <div className={styles.reviewHeading}><div><span className={styles.eyebrow}>REVISIÓN FINAL</span><h3 id="review-title">Cambios de {published?.versionLabel} a {draft.versionLabel}</h3></div><button type="button" className={styles.close} onClick={() => setReviewing(false)} aria-label="Cerrar revisión">×</button></div>
        <p>La nueva versión quedará publicada. Las sesiones anteriores conservarán su versión de rúbrica.</p>
        <ul>{savedChanges.map(change => <li key={`${change.key}-${change.field}`}><strong>{change.label}</strong><span>{fieldNames[change.field] ?? change.field}</span><span>{numberText(change.before, change.unit)} → {numberText(change.after, change.unit)}</span></li>)}</ul>
        <div className={styles.reviewActions}><button type="button" className="btn ghost" onClick={() => setReviewing(false)}>Volver a editar</button><button type="button" className="btn pri" disabled={busy} onClick={publishDraft}>{busy ? 'Publicando…' : 'Confirmar publicación'}</button></div>
      </section>}
    </div>
  );
}
