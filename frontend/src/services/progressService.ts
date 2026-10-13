import { apiFetch } from './apiClient';

export interface ProgressSessionPoint {
  sessionId: string;
  label: string;
  scenarioTitle: string;
  completedAt: string;
  overallScore: number | null;
}

export interface ProgressArea {
  areaKey: string;
  current: number | null;
  change: number | null;
  values: Array<number | null>;
}

export interface RecentProgressSession {
  sessionId: string;
  scenarioTitle: string;
  startedAt: string;
  completedAt: string;
  reportGeneratedAt: string;
  overallScore: number | null;
  areas: Array<{ areaKey: string; score: number | null }>;
}

export interface ProgressResponse {
  lastN: number;
  sessionsCount: number;
  trendSessions: ProgressSessionPoint[];
  areas: ProgressArea[];
  recentSessions: RecentProgressSession[];
}

export interface ScheduledScenario {
  id: string;
  title: string;
  status: string;
  available: boolean;
}

export interface ScheduleItem {
  id: string;
  date: string;
  status: 'scheduled' | 'completed';
  scenario: ScheduledScenario | null;
  sessionId: string | null;
  createdAt?: string;
  updatedAt?: string;
}

export interface CompletedCalendarSession {
  sessionId: string;
  date: string;
  completedAt: string;
  scenario: { id: string; title: string };
  report: {
    id: string;
    overallScore: number | null;
    generatedAt: string;
    areas: Array<{ key: string; value: number | null }>;
  };
}

export interface CalendarResponse {
  dateFrom: string;
  dateTo: string;
  schedules: ScheduleItem[];
  sessions: CompletedCalendarSession[];
}

export interface StartedSchedule {
  sessionId: string;
  scenarioId: string;
  status: string;
  questionCount: number;
  scheduleId: string;
}

export const progressService = {
  getProgress(lastN = 5) {
    return apiFetch<ProgressResponse>(`/me/progress?lastN=${lastN}`);
  },
  getCalendar(fromDate: string, toDate: string) {
    const query = new URLSearchParams({ fromDate, toDate });
    return apiFetch<CalendarResponse>(`/me/schedule?${query}`);
  },
  createSchedule(date: string, scenarioId: string) {
    return apiFetch<ScheduleItem>('/me/schedule', {
      method: 'POST',
      body: JSON.stringify({ date, scenarioId })
    });
  },
  updateSchedule(id: string, date: string, scenarioId: string) {
    return apiFetch<ScheduleItem>(`/me/schedule/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ date, scenarioId })
    });
  },
  cancelSchedule(id: string) {
    return apiFetch<{ id: string; status: 'cancelled' }>(
      `/me/schedule/${encodeURIComponent(id)}/cancel`,
      { method: 'POST' }
    );
  },
  startSchedule(id: string) {
    return apiFetch<StartedSchedule>(`/me/schedule/${encodeURIComponent(id)}/start`, {
      method: 'POST'
    });
  }
};
