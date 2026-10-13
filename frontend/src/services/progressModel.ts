const AREA_LABELS: Record<string, string> = {
  expression: 'Expresión',
  expresion: 'Expresión',
  voice: 'Tono de voz',
  tone: 'Tono de voz',
  voice_tone: 'Tono de voz',
  coherence: 'Coherencia',
  coherencia: 'Coherencia',
  empathy: 'Empatía',
  empatia: 'Empatía'
};

export function areaLabel(key: string): string {
  const normalized = key.trim().toLowerCase().replace(/[ -]+/g, '_');
  if (AREA_LABELS[normalized]) return AREA_LABELS[normalized];
  const readable = normalized.replace(/_/g, ' ');
  return readable ? readable[0].toUpperCase() + readable.slice(1) : 'Área';
}

export function localDateKey(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function calendarRange(year: number, month: number): { fromDate: string; toDate: string } {
  return {
    fromDate: localDateKey(new Date(year, month, 0)),
    toDate: localDateKey(new Date(year, month + 1, 2))
  };
}

export function calendarDateKey(isoValue: string): string {
  return localDateKey(new Date(isoValue));
}

export function isSchedulableDate(date: string, today: Date): boolean {
  const first = localDateKey(today);
  const last = localDateKey(new Date(today.getFullYear(), today.getMonth() + 12, today.getDate()));
  return date >= first && date <= last;
}
