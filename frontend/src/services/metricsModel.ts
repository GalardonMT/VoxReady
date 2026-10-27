export interface MetricDefinition {
  key: string;
  category: string;
  label: string;
  description: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  control: string;
  thresholdKeys: string[];
  thresholds: Record<string, number>;
}

export interface MetricsVersion {
  id: string;
  versionLabel: string;
  versionNumber: number | null;
  status: 'draft' | 'published';
  revision: number;
  createdAt: string;
  publishedAt: string | null;
  metrics: MetricDefinition[];
}

export function formatPublishedDate(publishedAt: string | null): string {
  const date = publishedAt?.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return date ? `${date[3]}/${date[2]}/${date[1]}` : 'Fecha no disponible';
}

export interface ThresholdChange {
  key: string;
  label: string;
  field: string;
  before: number;
  after: number;
  unit: string;
}

export function thresholdFields(metric: MetricDefinition): string[] {
  return metric.thresholdKeys;
}

export function validateMetricThresholds(metric: MetricDefinition): string[] {
  const fields = thresholdFields(metric);
  const errors: string[] = [];
  const actualFields = Object.keys(metric.thresholds);
  if (actualFields.length !== fields.length || fields.some(field => !actualFields.includes(field))) {
    errors.push(`${metric.label}: la configuración de límites está incompleta.`);
  }
  for (const field of fields) {
    const value = metric.thresholds[field];
    if (!Number.isFinite(value) || value < metric.min || value > metric.max) {
      errors.push(`${metric.label}: ${field} debe estar entre ${metric.min} y ${metric.max}.`);
    } else if (!Number.isFinite(metric.step) || metric.step <= 0 ||
      Math.abs((value - metric.min) / metric.step - Math.round((value - metric.min) / metric.step)) > 1e-6) {
      errors.push(`${metric.label}: ${field} debe avanzar en pasos de ${metric.step}.`);
    }
  }
  for (let index = 1; index < fields.length; index += 1) {
    if (metric.thresholds[fields[index - 1]] >= metric.thresholds[fields[index]]) {
      errors.push(`${metric.label}: los límites deben estar en orden ascendente.`);
      break;
    }
  }
  return errors;
}

export function updateThreshold(metric: MetricDefinition, field: string, value: number): MetricDefinition {
  return { ...metric, thresholds: { ...metric.thresholds, [field]: value } };
}

export function changedThresholds(published: MetricDefinition[], current: MetricDefinition[]): ThresholdChange[] {
  const originals = new Map(published.map(metric => [metric.key, metric]));
  return current.flatMap(metric => {
    const original = originals.get(metric.key);
    if (!original) return [];
    return thresholdFields(metric).flatMap(field => {
      const before = original.thresholds[field];
      const after = metric.thresholds[field];
      return before === after ? [] : [{ key: metric.key, label: metric.label, field, before, after, unit: metric.unit }];
    });
  });
}
