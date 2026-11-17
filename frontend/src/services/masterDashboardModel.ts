import type { MasterDashboardResponse } from '../types/api';

export function dashboardBars(distribution: MasterDashboardResponse['scoreDistribution']) {
  const maximum = Math.max(0, ...distribution.bins.map(bin => bin.count));
  return distribution.bins.map((bin, index) => ({
    ...bin,
    x: 30 + index * 45,
    height: maximum ? bin.count / maximum * 96 : 0,
    modal: maximum > 0 && bin.count === maximum,
  }));
}

export function dashboardNumber(value: number | null | undefined, language: string, signed = false): string {
  if (value == null) return '—';
  return new Intl.NumberFormat(language, {
    maximumFractionDigits: 2,
    ...(signed ? { signDisplay: 'exceptZero' as const } : {}),
  }).format(value);
}
