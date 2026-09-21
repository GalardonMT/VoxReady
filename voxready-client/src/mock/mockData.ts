import {
  UserSession,
  Scenario,
  Microlesson,
  TopicConfig,
  RetentionSettings,
  MasterRubric,
  LabelingCase,
  CoachReport
} from '../types/api';

export const TEST_USERS: UserSession[] = [
  {
    userId: 'usr-spokesperson-01',
    email: 'ana@visum.com',
    displayName: 'Ana Torres',
    role: 'spokesperson',
    clientId: 'tenant-visum',
    clientName: 'Visum Corp',
    clientLogo: '/Visum_logo.png',
    initials: 'AT',
    preferredLanguage: 'es'
  },
  {
    userId: 'usr-admin-01',
    email: 'carlos@visum.com',
    displayName: 'Carlos Ruiz',
    role: 'client_admin',
    clientId: 'tenant-visum',
    clientName: 'Visum Corp',
    clientLogo: '/Visum_logo.png',
    initials: 'CR',
    preferredLanguage: 'es'
  },
  {
    userId: 'usr-master-01',
    email: 'marta@voxready.io',
    displayName: 'Marta Vidal',
    role: 'master_config',
    clientId: 'tenant-voxready-central',
    clientName: 'VoxReady Central / Visum',
    clientLogo: '/VoxReady_logo.png',
    initials: 'MV',
    preferredLanguage: 'es'
  }
];

export const INITIAL_SCENARIOS: Scenario[] = [
  {
    id: 'scen-01',
    name: 'Retiro de producto',
    category: 'Sanitaria',
    context: 'Eres el vocero ante la prensa tras detectar un defecto grave en un lote de producción farmacéutica. Entrevista de 8 preguntas.',
    audience: 'Dirección',
    difficulty: 'Intermedio',
    estimatedMinutes: 6,
    questionsCount: 8,
    languages: ['es', 'en'],
    imageUrl: ''
  },
  {
    id: 'scen-02',
    name: 'Incidente de seguridad',
    category: 'Operativa',
    context: 'Filtración masiva de datos y registros confidenciales de clientes. Debes informar a la comunidad con serenidad sin detonar alarma desproporcionada.',
    audience: 'Planta',
    difficulty: 'Difícil',
    estimatedMinutes: 5,
    questionsCount: 6,
    languages: ['es'],
    imageUrl: ''
  },
  {
    id: 'scen-03',
    name: 'Crisis reputacional en redes',
    category: 'Reputacional',
    context: 'Campaña viral en redes sociales acusando a la empresa de prácticas laborales cuestionables. Respuesta rápida frente a medios digitales.',
    audience: 'Dirección',
    difficulty: 'Intermedio',
    estimatedMinutes: 7,
    questionsCount: 8,
    languages: ['es', 'en', 'pt'],
    imageUrl: ''
  },
  {
    id: 'scen-04',
    name: 'Accidente en línea de envasado',
    category: 'Operativa',
    context: 'Paralización de faenas por falla mecánica con heridos leves. Declaración formal ante autoridades y sindicatos.',
    audience: 'Planta',
    difficulty: 'Fácil',
    estimatedMinutes: 4,
    questionsCount: 5,
    languages: ['es'],
    imageUrl: ''
  },
  {
    id: 'scen-05',
    name: 'Falla crítica de infraestructura cloud',
    category: 'Operativa',
    context: 'Caída de servicios que impacta transacciones bancarias de millones de usuarios. Vocería técnica pero con empatía hacia el usuario final.',
    audience: 'Técnicos',
    difficulty: 'Difícil',
    estimatedMinutes: 6,
    questionsCount: 7,
    languages: ['es', 'en'],
    imageUrl: ''
  },
  {
    id: 'scen-06',
    name: 'Contaminación microbiológica de lotes',
    category: 'Sanitaria',
    context: 'Retiro preventivo en cadenas de supermercados. Manejo riguroso de evidencia científica y medidas correctivas.',
    audience: 'Dirección',
    difficulty: 'Intermedio',
    estimatedMinutes: 6,
    questionsCount: 8,
    languages: ['es', 'en', 'pt'],
    imageUrl: ''
  }
];

export const INITIAL_MICROLESSONS: Record<string, Microlesson> = {
  bridging: {
    id: 'bridging',
    title: 'Mensajes puente (Bridging)',
    durationMinutes: 4,
    objective: 'Aprenderás a redirigir preguntas hostiles o trampas de periodistas hacia tus mensajes clave institucionales sin evadir ni parecer a la defensiva.',
    videoPlaceholder: 'Video instructivo: Técnica de 3 pasos (Reconocer -> Transición -> Mensaje Clave)',
    exampleAnalysis: 'Periodista: "¿Reconocen ustedes que mintieron al ocultar este error?"\nVocero (puente): "Lo más sustancial en esta contingencia es verificar la trazabilidad de cada producto; y con esa convicción, hemos ordenado una auditoría externa independiente..."',
    relatedScenarioId: 'scen-01'
  },
  hostile: {
    id: 'hostile',
    title: 'Preguntas hostiles y trampas',
    durationMinutes: 5,
    objective: 'Reconoce y neutraliza falacias, dicotomías forzadas y ataques personales en conferencias de prensa de alta presión.',
    videoPlaceholder: 'Video instructivo: Control de la reactividad y pausas asertivas',
    exampleAnalysis: 'Periodista: "¿Van a renunciar o van a seguir cobrando su sueldo ignorando el daño?"\nVocero: "Nuestra obligación moral e institucional hoy es solucionar la situación técnica de inmediato..."',
    relatedScenarioId: 'scen-02'
  },
  nonverbal: {
    id: 'nonverbal',
    title: 'Lenguaje no verbal y microexpresiones',
    durationMinutes: 4,
    objective: 'Domina el contacto visual constante con la lente de la cámara, la posición de los hombros y la congruencia gestual en momentos críticos.',
    videoPlaceholder: 'Video ilustrativo: Contacto visual y triangulación de mirada en cámara',
    exampleAnalysis: 'Análisis: Bajar la mirada al pedir perdón produce en la audiencia una percepción de culpa encubierta o falta de convicción.',
    relatedScenarioId: 'scen-03'
  }
};

export const INITIAL_REPORT: CoachReport = {
  sessionId: 'sess-8842',
  scenarioName: 'Retiro de producto',
  date: '24 jun 2026',
  globalScore: 74,
  goodAspects: [
    'Mantuviste serenidad y control de la postura en las primeras tres preguntas.',
    'Utilizaste la técnica de mensaje puente al ser consultado sobre responsabilidades financieras.'
  ],
  improveAspects: [
    'Evitaste el contacto visual al abordar las disculpas hacia los afectados directos.',
    'Se detectaron 14 muletillas ("eh", "este") que restan contundencia al mensaje de calma.'
  ],
  crossSignalQuote: '“Sonaste firme al dar los datos, pero al hablar del cliente afectado evitaste la mirada — eso restó empatía percibida.” (observación de señal cruzada)',
  areas: [
    { name: 'Expresión', channel: 'Imagen / no verbal', score: 70, criteria: 'Contacto visual, postura y gestos' },
    { name: 'Tono de voz', channel: 'Voz / prosodia', score: 81, criteria: 'Ritmo, pausas, muletillas y firmeza' },
    { name: 'Coherencia', channel: 'Contenido', score: 79, criteria: 'Mensajes puente y líneas clave' },
    { name: 'Nivel de empatía', channel: 'Señal cruzada', score: 58, criteria: 'Congruencia, calidez y reconocimiento' }
  ]
};

export const INITIAL_PROGRESS = {
  sessions: ['S1', 'S2', 'S3', 'S4', 'S5'],
  chartData: [
    [55, 60, 64, 67, 70], // Expresión
    [62, 68, 73, 78, 81], // Tono de voz
    [60, 66, 70, 75, 79], // Coherencia
    [40, 46, 50, 54, 58]  // Empatía
  ],
  chartColors: ['#17354F', '#DB6427', '#2f9c83', '#8a8a8a']
};

export const INITIAL_TOPICS: TopicConfig[] = [
  {
    id: 'top-01',
    name: 'Retiro de producto',
    context: 'Detección de defecto en lote cosmético y farmacéutico. Gestión de retiro voluntario preventivo.',
    optics: 'Empática',
    audience: 'Dirección',
    languages: ['ES', 'EN'],
    retention: '90 días',
    keyMessages: [
      'La salud y seguridad de nuestros usuarios es la prioridad intransable.',
      'Hemos habilitado canales de canje y devolución inmediata sin costo.'
    ],
    redLines: [
      'No admitir culpa civil antes del peritaje técnico concluyente.',
      'No descalificar las quejas de los usuarios en redes sociales.'
    ]
  },
  {
    id: 'top-02',
    name: 'Incidente de seguridad informática',
    context: 'Acceso no autorizado a base de datos de auditoría interna. Posible filtración de credenciales.',
    optics: 'Técnica',
    audience: 'Planta',
    languages: ['ES'],
    retention: 'Solo métricas',
    keyMessages: [
      'Los sistemas perimetrales contuvieron el 98% del tráfico anómalo.',
      'Se activó el protocolo SOC nivel 3 con restablecimiento de claves forzado.'
    ],
    redLines: [
      'No especular sobre el origen geográfico del ciberataque.',
      'No prometer plazos que no dependan del equipo de ciberseguridad.'
    ]
  },
  {
    id: 'top-03',
    name: 'Crisis reputacional',
    context: 'Reportaje televisivo sobre impacto ambiental en cuenca hídrica.',
    optics: 'Formal',
    audience: 'Dirección',
    languages: ['ES', 'EN', 'PT'],
    retention: '30 días',
    keyMessages: [
      'Cumplimos el 100% de la norma ambiental vigente con certificaciones al día.',
      'Iniciaremos mesas de diálogo abiertas con las comunidades ribereñas.'
    ],
    redLines: [
      'No atacar la credibilidad de los periodistas o medios de comunicación.'
    ]
  }
];

export const INITIAL_RETENTION_SETTINGS: RetentionSettings = {
  keep: 'full_recording',
  termDays: 90,
  deletionRequests: [
    {
      id: 'del-01',
      userId: 'usr-spokesperson-01',
      userLabel: 'Vocero #14 (Ana Torres)',
      requestedAt: '22 jun 2026',
      status: 'pending'
    }
  ]
};

export const INITIAL_MASTER_RUBRIC: MasterRubric = {
  version: 'v0.4',
  effectiveDate: 'Vigente desde el 15 de junio de 2026',
  areas: [
    { area: 'Expresión', channel: 'Imagen / no verbal', criteria: 'Contacto visual, postura, gestos y presencia', weight: 25 },
    { area: 'Tono de voz', channel: 'Voz / prosodia', criteria: 'Ritmo, pausas, muletillas, variación y firmeza', weight: 25 },
    { area: 'Coherencia', channel: 'Contenido', criteria: 'Mensajes puente, sostener líneas clave, evitar trampas', weight: 30 },
    { area: 'Nivel de empatía', channel: 'Señal cruzada', criteria: 'Congruencia, calidez y reconocimiento del afectado', weight: 20 }
  ],
  levelDescriptors: 'Nivel Alto: Reconocimiento sincero del afectado con contacto visual constante y voz cálida.\nNivel Medio: Mención de empatía pero con microexpresión neutra o mirada esquiva.\nNivel Bajo: Indiferencia o disonancia marcada entre mensaje y expresión facial.',
  supportedLanguages: ['ES', 'EN', 'PT']
};

export const INITIAL_LABELING_QUEUE: LabelingCase[] = [
  {
    id: 'case-8842',
    caseNumber: '#8842',
    reason: 'low_confidence',
    reasonLabel: 'Confianza baja · Empatía',
    scenarioName: 'Retiro de producto',
    videoDuration: '03:12',
    aiScores: { expression: 70, tone: 81, coherence: 79, empathy: 58 },
    expertScores: { expression: 70, tone: 81, coherence: 79, empathy: 62 },
    expertComment: 'Empatía penalizada por la IA al desviar la mirada, pero hubo modulación cálida sincera en turnos 3 y 4.'
  },
  {
    id: 'case-8843',
    caseNumber: '#8843',
    reason: 'borderline',
    reasonLabel: 'Puntaje límite (69 pts)',
    scenarioName: 'Incidente de seguridad',
    videoDuration: '02:45',
    aiScores: { expression: 68, tone: 72, coherence: 69, empathy: 66 },
    expertScores: { expression: 68, tone: 72, coherence: 69, empathy: 66 }
  },
  {
    id: 'case-8844',
    caseNumber: '#8844',
    reason: 'random',
    reasonLabel: 'Muestreo aleatorio de control',
    scenarioName: 'Crisis reputacional',
    videoDuration: '04:10',
    aiScores: { expression: 85, tone: 80, coherence: 82, empathy: 84 },
    expertScores: { expression: 85, tone: 80, coherence: 82, empathy: 84 }
  }
];
