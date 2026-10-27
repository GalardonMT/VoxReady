"""
Configuraciones y constantes numéricas de la Rúbrica Maestro VoxReady (Metodología VISUM).
Single Source of Truth (SSOT) para ponderaciones, tolerancias y reglas deterministas de scoring.
"""

# Ponderaciones macro de la Rúbrica VoxReady (Fijas para MVP)
WEIGHT_EXPRESSION = 0.25
WEIGHT_VOICE = 0.25
WEIGHT_COHERENCE = 0.35
WEIGHT_EMPATHY = 0.15

# Canal Voz: Ponderación interna de submétricas (WPM, Fluidez neta, Dicción ASR)
VOICE_WEIGHT_WPM = 0.40
VOICE_WEIGHT_FLUENCY = 0.35
VOICE_WEIGHT_DICTION = 0.25

# Canal Coherencia: Castigo estricto por vulneración de Línea Roja
RED_LINE_SCORE_CAP = 20.0  # Si se vulnera una línea roja, Coherencia no puede superar este valor

# Canal Empatía: Proporción verbal / no verbal
EMPATHY_WEIGHT_VERBAL = 0.60     # Reconocimiento del afectado vía LLM Juez
EMPATHY_WEIGHT_NONVERBAL = 0.40  # Contacto visual + estabilidad física (Expresión no verbal)

# Umbrales fijos de Dicción (Confianza acústica Parakeet/Riva)
DICTION_FALLBACK_SCORE = 70.0    # Valor asignado si no hay palabras computables
