"""Approved fixed metadata and initial thresholds for the Spanish metrics editor."""

METRICS = [
    # key, category, label, description, unit, min, max, step, control, thresholds
    ("voice.wpm", "voice", "Ritmo de habla", "Palabras pronunciadas por minuto.", "WPM", 60, 220, 1, "range", {"warningLow": 100, "optimalLow": 120, "optimalHigh": 150, "warningHigh": 170}),
    ("voice.filler_density", "voice", "Densidad de muletillas", "Proporción de muletillas en el discurso.", "%", 0, 10, 0.1, "range", {"optimalMax": 1.5, "warningMax": 3}),
    ("voice.prolonged_pause", "voice", "Pausas prolongadas", "Silencios de más de 1,5 segundos.", "pausas", 0, 10, 1, "stepper", {"optimalMax": 1, "warningMax": 3}),
    ("voice.hesitation_pause", "voice", "Pausas de vacilación", "Titubeos de 0,7 a 1,5 segundos.", "pausas", 0, 15, 1, "stepper", {"optimalMax": 2, "warningMax": 5}),
    ("voice.phonation_ratio", "voice", "Ratio de fonación", "Tiempo de voz activa respecto del total.", "%", 20, 100, 1, "range", {"criticalBelow": 45, "optimalLow": 60, "optimalHigh": 85}),
    ("voice.asr_confidence", "voice", "Confianza de dicción", "Confianza fonética promedio del reconocimiento de voz.", "%", 50, 100, 1, "range", {"warningLow": 70, "optimalLow": 85}),
    ("vision.eye_contact", "vision", "Contacto visual", "Tiempo de mirada hacia la cámara.", "%", 0, 100, 1, "range", {"warningLow": 50, "optimalLow": 75}),
    ("vision.posture", "vision", "Estabilidad de hombros", "Estabilidad de la postura de hombros.", "%", 0, 100, 1, "range", {"warningLow": 50, "optimalLow": 75}),
    ("vision.sway_tolerance", "vision", "Balanceo del torso", "Variación lateral del torso.", "std", 0.005, 0.080, 0.001, "range", {"optimalMax": 0.015, "warningMax": 0.035}),
    ("content.red_line_cap", "content", "Techo por línea roja", "Puntaje máximo de contenido ante infracción confirmada.", "pts", 0, 50, 5, "number", {"cap": 20}),
    ("empathy.victim_recog", "empathy", "Reconocimiento del afectado", "Nivel de prioridad del impacto en las personas.", "nivel", 1, 5, 1, "levels", {"warningLevel": 3, "optimalLevel": 4}),
    ("gov.confidence_min", "governance", "Confianza para auditoría", "Corte de confianza técnica para revisión.", "%", 50, 95, 1, "range", {"warningLow": 70, "optimalLow": 85}),
    ("gov.borderline_delta", "governance", "Ventana de puntaje límite", "Semiamplitud alrededor de 50; observación se extiende 3 puntos más.", "pts", 1, 10, 1, "stepper", {"halfWidth": 2}),
    ("gov.disparity_delta", "governance", "Disparidad entre canales", "Diferencia de puntaje entre áreas.", "pts", 20, 70, 5, "stepper", {"normalBelow": 35, "auditAt": 50}),
    ("gov.random_sample", "governance", "Muestreo aleatorio", "Porcentaje de sesiones ordinarias para calibración.", "%", 0, 30, 1, "number", {"rate": 10}),
    ("gov.agreement_target", "governance", "Acuerdo IA–humano", "Concordancia de puntuaciones para recalibración.", "ratio", 0.50, 0.99, 0.01, "range", {"warningLow": 0.70, "optimalLow": 0.85}),
]
