import {
  DemoMicrolesson,
  MasterRubric,
  CoachReport
} from '../types/api';

export const INITIAL_MICROLESSONS: Record<string, DemoMicrolesson> = {
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
