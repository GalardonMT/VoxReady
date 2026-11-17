export type ClientScenarioCategory = 'health' | 'operational' | 'reputational';
export type ClientScenarioDifficulty = 'basic' | 'intermediate' | 'hard';
export type ClientScenarioAudience = 'leadership' | 'frontline' | 'technical';
export type ClientScenarioOptics = 'empathetic' | 'formal' | 'technical';

export interface ClientScenarioSummary {
  id: string;
  title: string;
  category: ClientScenarioCategory;
  difficulty: ClientScenarioDifficulty;
  estimatedMinutes: number;
  questionCount: number;
  audience: ClientScenarioAudience;
  optics: ClientScenarioOptics;
}

export interface ClientScenarioPage {
  items: ClientScenarioSummary[];
  page: number;
  pageSize: number;
  total: number;
}

export interface ClientScenarioQuestion {
  sequenceNo: number;
  text: string;
}

export interface ClientScenarioDetail extends ClientScenarioSummary {
  context: string;
  keyMessages: string[];
  redLines: string[];
  questions: ClientScenarioQuestion[];
}

export interface ClientScenarioListOptions {
  page?: number;
  pageSize?: number;
}

export const clientScenarioLabels = {
  category: {
    health: 'Sanitaria',
    operational: 'Operativa',
    reputational: 'Reputacional',
  },
  difficulty: {
    basic: 'Fácil',
    intermediate: 'Intermedio',
    hard: 'Difícil',
  },
  audience: {
    leadership: 'Dirección',
    frontline: 'Planta',
    technical: 'Técnicos',
  },
  optics: {
    empathetic: 'Empática',
    formal: 'Formal',
    technical: 'Técnica',
  },
} as const;
