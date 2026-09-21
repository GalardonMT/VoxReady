export type Role = 'spokesperson' | 'client_admin' | 'master_config';

export interface UserSession {
  userId: string;
  email: string;
  displayName: string;
  role: Role;
  clientId: string;
  clientName: string;
  clientLogo?: string;
  initials: string;
  preferredLanguage: 'es' | 'en' | 'pt';
}

export type ScenarioCategory = 'Todos' | 'Sanitaria' | 'Reputacional' | 'Operativa';
export type InternalAudience = 'Dirección' | 'Planta' | 'Técnicos';
export type InstitutionalOptics = 'Empática' | 'Formal' | 'Técnica';

export interface Scenario {
  id: string;
  name: string;
  category: 'Sanitaria' | 'Reputacional' | 'Operativa';
  context: string;
  audience: InternalAudience;
  difficulty: 'Fácil' | 'Intermedio' | 'Difícil';
  estimatedMinutes: number;
  questionsCount: number;
  languages: string[];
  imageUrl?: string;
}

export interface Microlesson {
  id: string;
  title: string;
  durationMinutes: number;
  objective: string;
  videoPlaceholder: string;
  exampleAnalysis: string;
  relatedScenarioId?: string;
}

export interface PracticeSessionState {
  id: string;
  scenarioId: string;
  scenarioName: string;
  currentQuestionIndex: number;
  totalQuestions: number;
  currentQuestionText: string;
  isPaused: boolean;
  elapsedSeconds: number;
}

export interface MultimodalAnalysisStep {
  id: 'content' | 'voice' | 'image' | 'fusion';
  label: string;
  status: 'done' | 'running' | 'pending';
}

export interface AreaScore {
  name: string;
  channel: string;
  score: number;
  criteria?: string;
  weight?: string;
}

export interface CoachReport {
  sessionId: string;
  scenarioName: string;
  date: string;
  globalScore: number;
  goodAspects: string[];
  improveAspects: string[];
  crossSignalQuote: string;
  areas: AreaScore[];
}

export interface ProgressTrend {
  sessions: string[]; // e.g. ['S1', 'S2', 'S3', 'S4', 'S5']
  expression: number[];
  tone: number[];
  coherence: number[];
  empathy: number[];
}

export interface ActionableRecommendation {
  id: string;
  title: string;
  description: string;
  lessonId: string;
  lessonTitle: string;
}

export interface TopicConfig {
  id: string;
  name: string;
  context: string;
  optics: InstitutionalOptics;
  audience: InternalAudience;
  languages: string[];
  retention: string;
  keyMessages: string[];
  redLines: string[];
}

export interface DeletionRequest {
  id: string;
  userId: string;
  userLabel: string;
  requestedAt: string;
  status: 'pending' | 'processed';
}

export interface RetentionSettings {
  keep: 'full_recording' | 'metrics_only';
  termDays: number; // 30, 90, 180, etc.
  deletionRequests: DeletionRequest[];
}

export interface MasterRubricArea {
  area: string;
  channel: string;
  criteria: string;
  weight: number; // percentage, e.g. 25
}

export interface MasterRubric {
  version: string;
  effectiveDate: string;
  areas: MasterRubricArea[];
  levelDescriptors: string;
  supportedLanguages: string[];
}

export interface LabelingCase {
  id: string;
  caseNumber: string;
  reason: 'low_confidence' | 'borderline' | 'random';
  reasonLabel: string;
  scenarioName: string;
  aiScores: {
    expression: number;
    tone: number;
    coherence: number;
    empathy: number;
  };
  expertScores?: {
    expression: number;
    tone: number;
    coherence: number;
    empathy: number;
  };
  expertComment?: string;
  videoDuration: string;
}
