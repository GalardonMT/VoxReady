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

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, Any

# --- Catálogo Fallback de las 16 Métricas (Compatible con v0.4 y metrics_catalog.py) ---
DEFAULT_METRIC_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "voice.wpm": {"warningLow": 100.0, "optimalLow": 120.0, "optimalHigh": 150.0, "warningHigh": 170.0},
    "voice.filler_density": {"optimalMax": 1.5, "warningMax": 3.0},
    "voice.prolonged_pause": {"optimalMax": 1.0, "warningMax": 3.0},
    "voice.hesitation_pause": {"optimalMax": 2.0, "warningMax": 5.0},
    "voice.phonation_ratio": {"criticalBelow": 45.0, "optimalLow": 60.0, "optimalHigh": 85.0},
    "voice.asr_confidence": {"warningLow": 70.0, "optimalLow": 85.0},
    "vision.eye_contact": {"warningLow": 50.0, "optimalLow": 75.0},
    "vision.posture": {"warningLow": 50.0, "optimalLow": 75.0},
    "vision.sway_tolerance": {"optimalMax": 0.015, "warningMax": 0.035},
    "content.red_line_cap": {"cap": 20.0},
    "empathy.victim_recog": {"warningLevel": 3.0, "optimalLevel": 4.0},
    "gov.confidence_min": {"warningLow": 70.0, "optimalLow": 85.0},
    "gov.borderline_delta": {"halfWidth": 2.0},
    "gov.disparity_delta": {"normalBelow": 35.0, "auditAt": 50.0},
    "gov.random_sample": {"rate": 10.0},
    "gov.agreement_target": {"warningLow": 0.70, "optimalLow": 0.85},
}


@dataclass
class DynamicRubricConfig:
    """Contenedor de versión, pesos de área y los 16 intervalos publicados."""
    rubric_version_id: str = "B8AB7DE6-C3A8-4F0F-A9CF-5D3C33484134"  # Fallback v0.4
    version_code: str = "v0.4"
    area_weights: Dict[str, float] = field(default_factory=lambda: {
        "expression": WEIGHT_EXPRESSION,
        "voice": WEIGHT_VOICE,
        "coherence": WEIGHT_COHERENCE,
        "empathy": WEIGHT_EMPATHY,
    })
    thresholds: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: deepcopy(DEFAULT_METRIC_THRESHOLDS)
    )

    def get_metric(self, key: str) -> Dict[str, float]:
        return self.thresholds.get(key, DEFAULT_METRIC_THRESHOLDS.get(key, {}))

    @property
    def wpm_ideal(self) -> float:
        m = self.get_metric("voice.wpm")
        return (float(m.get("optimalLow", 120.0)) + float(m.get("optimalHigh", 150.0))) / 2.0

    @property
    def filler_penalty_per_pct(self) -> float:
        w_max = float(self.get_metric("voice.filler_density").get("warningMax", 3.0))
        return 15.0 / w_max if w_max > 0 else 5.0

    @property
    def prolonged_pause_allowance(self) -> int:
        return int(self.get_metric("voice.prolonged_pause").get("optimalMax", 1))

    @property
    def hesitation_pause_allowance(self) -> int:
        return int(self.get_metric("voice.hesitation_pause").get("optimalMax", 2))

    @property
    def red_line_cap(self) -> float:
        return float(self.get_metric("content.red_line_cap").get("cap", RED_LINE_SCORE_CAP))

