'use client';

import { useEffect, useState } from 'react';
import { labelingService } from '../../services/labelingService';
import {
  currentEvidence,
  formatDelta,
  governanceContext,
  metricComments,
  metricEvidence,
  qualityPeriodBounds,
  rubricComments,
  rubricEvidence,
  shortIdentity,
  type QualityPeriod,
  type ReviewedCaseEvidence,
} from '../../services/qualityReviewModel';
import type { LabelingQualitySummary } from '../../types/api';
import styles from './QualityReviewPanel.module.css';

interface QualityReviewPanelProps {
  mode: 'rubric' | 'metrics';
  metricLabels?: Record<string, string>;
  onOpenCase: (caseId: string) => void;
}

const areaLabels: Record<string, string> = {
  expression: 'Expresión',
  voice: 'Tono de voz',
  coherence: 'Coherencia',
  empathy: 'Nivel de empatía',
};

const categoryLabels: Record<string, string> = {
  voice: 'Voz', vision: 'Video', content: 'Contenido', empathy: 'Empatía',
};

function categoryForMetric(metricKey: string): string {
  return metricKey.split('.')[0] ?? 'other';
}

export function QualityReviewPanel({ mode, metricLabels = {}, onOpenCase }: QualityReviewPanelProps) {
  const [period, setPeriod] = useState<QualityPeriod>('30');
  const [summary, setSummary] = useState<LabelingQualitySummary | null>(null);
  const [evidence, setEvidence] = useState<ReviewedCaseEvidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const bounds = qualityPeriodBounds(period);

    async function loadEvidence() {
      setLoading(true);
      setError('');
      try {
        const [quality, reviewed] = await Promise.all([
          labelingService.getQualitySummary(bounds, controller.signal),
          labelingService.list('reviewed', controller.signal),
        ]);
        const reviewPairs = await Promise.all(reviewed.items.map(async item => [
          item.caseId,
          await labelingService.listReviews(item.caseId, controller.signal),
        ] as const));
        if (!active) return;
        setSummary(quality);
        setEvidence(currentEvidence(reviewed.items, new Map(reviewPairs), bounds));
      } catch (cause) {
        if (active && !controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : 'No se pudo cargar la evidencia de calidad.');
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadEvidence();
    return () => {
      active = false;
      controller.abort();
    };
  }, [period]);

  const governance = summary ? governanceContext(summary) : null;
  const rubricItems = summary ? rubricEvidence(summary) : [];
  const metricItems = summary ? metricEvidence(summary) : [];
  const categories = [...new Set(metricItems.map(item => categoryForMetric(item.metricKey)))];

  return (
    <section className={styles.panel} aria-labelledby={`quality-review-${mode}`}>
      <div className={styles.heading}>
        <div>
          <span className={styles.eyebrow}>EVIDENCIA · SOLO LECTURA</span>
          <h2 id={`quality-review-${mode}`}>Revisión de calidad</h2>
          <p>Contrasta la propuesta de IA con calibraciones expertas. Esta evidencia no modifica pesos, límites ni versiones publicadas.</p>
        </div>
        <label className={styles.period}>
          Período
          <select value={period} onChange={event => setPeriod(event.target.value as QualityPeriod)}>
            <option value="7">Últimos 7 días</option>
            <option value="30">Últimos 30 días</option>
            <option value="90">Últimos 90 días</option>
            <option value="all">Todo el historial</option>
          </select>
        </label>
      </div>

      {loading && <p className={styles.state} role="status">Cargando revisiones confirmadas…</p>}
      {error && <p className={styles.error} role="alert">{error}</p>}
      {!loading && !error && summary && (
        <>
          <div className={styles.summary}>
            <div><strong>{summary.reviewedCases}</strong><span>casos revisados</span></div>
            <div><strong>{mode === 'rubric' ? rubricItems.length : metricItems.length}</strong><span>{mode === 'rubric' ? 'áreas/versiones' : 'métricas/mapeos'}</span></div>
            <div><strong>{evidence.length}</strong><span>comentarios recientes consultables</span></div>
          </div>

          {mode === 'rubric' ? (
            <div className={styles.grid}>
              {rubricItems.map(item => (
                <EvidenceCard key={`${item.rubricVersionId}:${item.areaKey}`}
                  title={areaLabels[item.areaKey] ?? item.areaKey}
                  identity={`Rúbrica ${shortIdentity(item.rubricVersionId)}`}
                  sampleCount={item.sampleCount} meanDelta={item.meanDelta}
                  increased={item.increasedCount} decreased={item.decreasedCount} unchanged={item.unchangedCount}
                  comments={rubricComments(evidence, item.areaKey)} onOpenCase={onOpenCase} />
              ))}
            </div>
          ) : (
            <div className={styles.categoryList}>
              {categories.map(category => (
                <section key={category} className={styles.category}>
                  <h3>{categoryLabels[category] ?? category}</h3>
                  <div className={styles.grid}>
                    {metricItems.filter(item => categoryForMetric(item.metricKey) === category).map(item => (
                      <EvidenceCard key={`${item.metricKey}:${item.mappingVersion}:${item.unit}`}
                        title={metricLabels[item.metricKey] ?? item.metricKey}
                        identity={`Mapeo ${item.mappingVersion} · ${item.unit}`}
                        sampleCount={item.sampleCount} meanDelta={item.meanDelta} unit={item.unit}
                        increased={item.increasedCount} decreased={item.decreasedCount} unchanged={item.unchangedCount}
                        comments={metricComments(evidence, item.metricKey, item.unit)} onOpenCase={onOpenCase} />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}

          {mode === 'metrics' && governance && (
            <aside className={styles.governance}>
              <div><strong>Gobernanza: contexto de selección y acuerdo</strong><p>No se calibra desde este panel ni se mezcla con métricas observadas.</p></div>
              <span>{governance.reviewedMetricCount} observaciones · {governance.changedCount} variaciones registradas</span>
            </aside>
          )}

          {(mode === 'rubric' ? rubricItems : metricItems).length === 0 && (
            <p className={styles.state}>No hay calibraciones confirmadas para este período.</p>
          )}
        </>
      )}
    </section>
  );
}

function EvidenceCard({ title, identity, sampleCount, meanDelta, unit = 'pts', increased, decreased, unchanged, comments, onOpenCase }: {
  title: string;
  identity: string;
  sampleCount: number;
  meanDelta: number | null;
  unit?: string;
  increased: number;
  decreased: number;
  unchanged: number;
  comments: Array<ReviewedCaseEvidence & { comment: string }>;
  onOpenCase: (caseId: string) => void;
}) {
  return (
    <article className={styles.card}>
      <div className={styles.cardTitle}><div><h3>{title}</h3><span>{identity}</span></div><strong>{sampleCount} casos</strong></div>
      <div className={styles.delta}><span>Diferencia media</span><strong>{formatDelta(meanDelta, unit)}</strong></div>
      <div className={styles.distribution} aria-label={`Distribución: ${increased} al alza, ${decreased} a la baja y ${unchanged} sin cambio`}>
        <span className={styles.up}>↑ {increased}</span><span className={styles.down}>↓ {decreased}</span><span>＝ {unchanged}</span>
      </div>
      <div className={styles.comments}>
        <strong>Comentarios recientes</strong>
        {comments.length === 0 && <p>Sin comentarios específicos recientes.</p>}
        {comments.map(item => (
          <div key={`${item.review.reviewId}:${item.comment}`} className={styles.comment}>
            <p>{item.comment}</p>
            <button type="button" onClick={() => onOpenCase(item.caseId)}>Abrir {item.caseNumber}</button>
          </div>
        ))}
      </div>
    </article>
  );
}
