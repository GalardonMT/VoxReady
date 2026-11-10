export type Role = 'spokesperson' | 'client_admin' | 'master_config';

export type LifecycleStatus = 'active' | 'archived';
export type MasterOptics = 'empathetic' | 'formal' | 'technical';
export type MasterAudience = 'leadership' | 'frontline' | 'technical';
export type MasterCategory = 'health' | 'operational' | 'reputational';
export type MasterDifficulty = 'basic' | 'intermediate' | 'hard';

export interface ClientInfo {
  id: string;
  name: string;
  status?: LifecycleStatus;
}

export interface MasterQuestion {
  id: string;
  text: string;
  sortOrder?: number;
  sequenceNo?: number;
  status: LifecycleStatus;
}

export interface MasterScenarioInput {
  title: string;
  category: MasterCategory;
  difficulty: MasterDifficulty;
  estimatedMinutes: number;
  clientId: string;
  questionIds: string[];
}

export interface MasterScenarioFull extends MasterScenarioInput {
  id: string;
  clientName: string;
  questionCount: number;
  status: LifecycleStatus;
  questions: MasterQuestion[];
}

export interface MasterTopicInput {
  name: string;
  context: string;
  optics: MasterOptics;
  audience: MasterAudience;
  keyMessages: string[];
  redLines: string[];
  questions: (string | { id?: string; text: string })[];
}

export interface MasterTopicListItem {
  id: string;
  name: string;
  context: string;
  optics: MasterOptics;
  audience: MasterAudience;
  status: LifecycleStatus;
  questionCount: number;
  scenarioCount: number;
  clients: ClientInfo[];
}

export interface MasterTopicFull extends Omit<MasterTopicInput, 'questions'> {
  id: string;
  status: LifecycleStatus;
  questions: MasterQuestion[];
  scenarios: MasterScenarioFull[];
}

export interface UserSession {
  userId: string;
  email: string;
  displayName: string;
  role: Role;
  clientId: string | null;
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

export interface DemoMicrolesson {
  id: string;
  title: string;
  durationMinutes: number;
  objective: string;
  videoPlaceholder: string;
  exampleAnalysis: string;
  relatedScenarioId?: string;
}

export interface MicrolessonInput {
  clientId: string;
  scenarioId: string;
  title: string;
  topicTag: string | null;
  durationMinutes: number | null;
  learningObjective: string;
  theoryContent: string;
  exampleContent: string | null;
  status: LifecycleStatus;
}

export interface Microlesson extends MicrolessonInput {
  id: string;
  clientName: string;
  scenarioTitle: string;
  hasVideo: boolean;
  videoFileName?: string | null;
  videoContentType?: string | null;
  videoSizeBytes?: number | null;
  createdAt?: string;
  updatedAt?: string;
}

export type MicrolessonAssignmentStatus = 'assigned' | 'in_progress' | 'completed' | 'revoked';

export interface SpokespersonMicrolesson {
  id: string;
  clientId: string;
  clientName: string;
  scenarioId: string;
  scenarioTitle: string;
  title: string;
  topicTag: string | null;
  durationMinutes: number | null;
  learningObjective: string;
  hasVideo: boolean;
  status: LifecycleStatus;
  createdAt?: string;
  updatedAt?: string;
  assignmentId: string | null;
  assignmentStatus: MicrolessonAssignmentStatus | null;
  canOpen: boolean;
  canPractice: boolean;
  sortOrder: number | null;
  assignedAt?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  revokedAt?: string | null;
}

export interface SpokespersonMicrolessonDetail extends SpokespersonMicrolesson {
  theoryContent: string;
  exampleContent: string | null;
}

export interface MicrolessonCatalog {
  items: SpokespersonMicrolesson[];
  history: SpokespersonMicrolesson[];
  total: number;
}

export interface MicrolessonRecommendations {
  items: SpokespersonMicrolesson[];
  total: number;
}

export interface MicrolessonAssignment {
  id: string;
  clientId: string;
  microlessonId: string;
  userId: string;
  userDisplayName: string;
  userEmail: string;
  status: MicrolessonAssignmentStatus;
  sortOrder: number;
  assignedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  revokedAt: string | null;
}

export interface MicrolessonSpokesperson {
  id: string;
  displayName: string;
  email: string;
}

export interface MicrolessonScenario {
  id: string;
  title: string;
  status: LifecycleStatus;
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

export interface CreateSessionResponse {
  sessionId: string;
  status: string;
  scenarioId: string;
  createdAt: string;
}

export interface RecordingUrlResponse {
  uploadUrl: string;
  blobPath: string;
  expiresAt: string;
  maxSizeBytes: number;
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
  metrics?: Record<string, unknown>;
  recordingUrl?: string;
  durationSeconds?: number;
}

export interface VisumExecutive {
  sintesisEjecutiva?: {
    diagnosticoGeneral?: string;
    fortalezaPrincipal?: string;
    focoDesarrollo?: string;
    continuidadRecomendada?: string;
  };
  formulaRecomendada?: string;
  hallazgosTransversales?: string;
  recomendacionesProximasVocerias?: string[];
  consideracionFinal?: string;
}

export interface MetricsSummary {
  eyeContactPct?: number;
  shoulderStabilityScore?: number;
  wpm?: number;
  fillerWordsCount?: number;
  fillerWordsDensityPct?: number;
  durationSeconds?: number;
}

export interface FullVisumReport {
  sessionId: string;
  status: string;
  overallScore: number;
  scenarioTitle?: string;
  generatedAt?: string;
  recordingUrl?: string;
  durationSeconds?: number;
  narrative: {
    strengths: string[];
    improvements: string[];
    crossSignal: string;
    visum?: VisumExecutive;
  };
  areaScores: { area: string; value: number }[];
  visumExecutive?: VisumExecutive;
  metricsSummary?: MetricsSummary;
  metrics?: {
    vision?: {
      eyeContactPct?: number;
      shoulderStabilityScore?: number;
      bodySwayStd?: number;
      handsVisiblePct?: number;
      totalFramesAnalyzed?: number;
      frames_analyzed?: number;
    };
    audio?: {
      palabrasTotales?: number;
      duracionSegundos?: number;
      tiempoVozActivaSegundos?: number;
      wpmGlobal?: number;
      ratioFonacion?: number;
      pausasVacilacion?: number;
      pausasProlongadas?: number;
      densidadMuletillasPct?: number;
      muletillasDetectadas?: string[];
      scoreFluidez?: number;
      scoreDiccion?: number;
    };
    judge?: {
      puntajeGlobal100?: number;
      dimensiones?: Record<string, { nivel: number; score: number; criterio: string }>;
      feedback?: Record<string, unknown>;
    };
  };
  transcript?: string;
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

export type LabelingCaseStatus = 'pending' | 'reviewed';
export type LabelingQueueReason = 'critical' | 'borderline' | 'disparity' | 'routine';
export type LabelingLeaseState = 'available' | 'owned' | 'locked_by_other' | 'expired' | 'not_claimable';

export interface LabelingClientSummary {
  code: string;
  displayName: string;
}

export interface LabelingReviewSummary {
  reviewId: string;
  reviewNo: number;
  reviewerCode: string;
  submittedAt: string;
}

export interface LabelingCase {
  caseId: string;
  caseNumber: string;
  status: LabelingCaseStatus;
  queueReason: LabelingQueueReason;
  reasonDetail: Record<string, unknown>;
  client: LabelingClientSummary;
  speakerCode: string;
  scenario: {
    title: string;
  };
  session: {
    startedAt: string | null;
    finishedAt: string | null;
    durationSeconds: number | null;
  };
  report: {
    reportId: string;
    generatedAt: string;
    overallScore: number | null;
  };
  criticalAreas: Array<{
    areaKey: string;
    label: string;
    value: number;
  }>;
  lease: {
    state: LabelingLeaseState;
    ownerCode: string | null;
    expiresAt: string | null;
  };
  latestReview: LabelingReviewSummary | null;
}

export interface LabelingCaseListResponse {
  items: LabelingCase[];
  total: number;
  limit: number;
}

export interface LabelingRubricArea {
  areaId: string;
  areaKey: 'expression' | 'voice' | 'coherence' | 'empathy';
  label: string;
  aiValue: number | null;
  editable: boolean;
}

export interface LabelingMetricObservation {
  valueType: 'decimal' | 'integer';
  canonicalUnit: string;
  conversion: string;
  technicalMin: number | null;
  technicalMax: number | null;
}

export interface LabelingMetric {
  metricKey: string;
  categoryKey: string;
  metricKind: 'observation' | 'configuration' | 'aggregate_target';
  label: string;
  availability: 'available' | 'unknown' | 'not_emitted';
  aiValue: number | null;
  unit: string;
  precision: number;
  mappingVersion: number;
  observation: LabelingMetricObservation | null;
  editable: boolean;
  unavailableReason: string | null;
  publishedThresholds: Record<string, number>;
}

export interface LabelingCaseDetail extends LabelingCase {
  contentRevision: number;
  sourceStatus: 'complete' | 'partial' | 'ambiguous';
  sourceIssues: string[];
  snapshotSchemaVersion: number;
  rubric: {
    rubricVersionId: string;
    areas: LabelingRubricArea[];
  };
  metricGroups: Array<{
    categoryKey: string;
    label: string;
    metrics: LabelingMetric[];
  }>;
  recording: {
    availability: 'available' | 'unavailable';
    durationSeconds: number | null;
  };
  currentReview: LabelingReviewSummary | null;
}

export interface LabelingLease {
  caseId: string;
  leaseToken: string;
  leaseGeneration: number;
  contentRevision: number;
  expiresAt: string;
  serverTime: string;
  readOnly: boolean;
}

export interface LabelingRecordingTicket {
  url: string;
  expiresAt: string;
  contentType: string;
  durationSeconds: number | null;
  etag: string;
  blobVersionId: string | null;
}

export interface LabelingRubricCorrectionRequest {
  areaId: string;
  correctedValue: number;
  comment: string | null;
}

export interface LabelingMetricCorrectionRequest {
  metricKey: string;
  correctedValue: number;
  comment: string | null;
}

export interface LabelingReviewRequest {
  leaseToken: string;
  leaseGeneration: number;
  expectedContentRevision: number;
  idempotencyKey: string;
  supersedesReviewId: string | null;
  overallComment: string;
  rubricCorrections: LabelingRubricCorrectionRequest[];
  metricCorrections: LabelingMetricCorrectionRequest[];
}

export interface LabelingReview {
  reviewId: string;
  caseId: string;
  reviewNo: number;
  reviewerCode: string;
  isCurrent: boolean;
  supersedesReviewId: string | null;
  submittedAt: string;
  contentRevision: number;
  overallComment: string;
  rubricCorrections: Array<{
    areaKey: string;
    aiValue: number;
    correctedValue: number;
    comment: string | null;
  }>;
  metricCorrections: Array<{
    metricKey: string;
    aiValue: number;
    correctedValue: number;
    unit: string;
    comment: string | null;
  }>;
}

export interface LabelingReviewListResponse {
  items: LabelingReview[];
  total: number;
}

export interface LabelingQualityAggregate {
  sampleCount: number;
  meanAiValue: number | null;
  meanCorrectedValue: number | null;
  meanDelta: number | null;
  meanAbsoluteError: number | null;
  changedCount: number;
  increasedCount: number;
  decreasedCount: number;
  unchangedCount: number;
}

export interface LabelingRubricQualityAggregate extends LabelingQualityAggregate {
  rubricVersionId: string;
  areaKey: string;
}

export interface LabelingMetricQualityAggregate extends LabelingQualityAggregate {
  metricKey: string;
  mappingVersion: number;
  unit: string;
}

export interface LabelingQualitySummary {
  period: { from: string | null; to: string | null };
  currentReviewsOnly: boolean;
  reviewedCases: number;
  rubricAreas: LabelingRubricQualityAggregate[];
  metrics: LabelingMetricQualityAggregate[];
  categories: Array<{
    categoryKey: string;
    reviewedMetricCount: number;
    changedCount: number;
  }>;
}

export interface TurnInterval {
  questionId: string;
  sequenceNo: number;
  startOffsetMs: number;
  endOffsetMs: number;
  questionText?: string;
}

export interface SessionHistoryItem {
  sessionId: string;
  scenarioId: string;
  scenarioTitle: string;
  createdAt: string;
  status: string;
  overallScore: number;
  hasReport: boolean;
}
