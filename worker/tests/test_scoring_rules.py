"""
Pruebas Unitarias para las Métricas de Nivel 1 y Reglas de Scoring VISUM.
Cubre los Criterios de Aceptación (DoD) de Indicaciones.txt:
1. Dicción ASR variable vs Fallback
2. Desacople de WPM y Fluidez neta
3. Truncamiento determinista por vulneración de Línea Roja (cap <= 20 pts)
4. Empatía balanceada (40% no verbal + 60% reconocimiento del afectado)
5. Estructura y sanitización de reporte en camelCase
"""

import sys
import unittest
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parent.parent
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from core.audio_analyzer import compute_diction_score, AudioAnalyzer
from core.report_builder import ReportBuilder, compute_empathy_score, sanitize_report_json
from config.scoring_rules import (
    WEIGHT_EXPRESSION,
    WEIGHT_VOICE,
    WEIGHT_COHERENCE,
    WEIGHT_EMPATHY,
    VOICE_WEIGHT_WPM,
    VOICE_WEIGHT_FLUENCY,
    VOICE_WEIGHT_DICTION,
    RED_LINE_SCORE_CAP,
    DICTION_FALLBACK_SCORE,
)


class TestScoringRules(unittest.TestCase):

    def test_diction_score_calculation(self):
        # Caso 1: Salida de palabras con confianzas acústicas variables
        words_sample = [
            {"word": "buenos", "confidence": 0.95},
            {"word": "días", "confidence": 0.85},
            {"word": "a", "confidence": 0.90},
            {"word": "todos", "confidence": 0.80},
        ]
        score = compute_diction_score(words_sample)
        # (0.95 + 0.85 + 0.90 + 0.80) / 4 = 0.875 -> 87.5
        self.assertEqual(score, 87.5)

        # Caso 2: Sin palabras inteligibles -> debe retornar DICTION_FALLBACK_SCORE (70.0)
        empty_words = []
        self.assertEqual(compute_diction_score(empty_words), DICTION_FALLBACK_SCORE)

        # Caso 3: Palabras vacías o sin campo de confianza
        dirty_words = [{"word": "  "}, {"word": ""}]
        self.assertEqual(compute_diction_score(dirty_words), DICTION_FALLBACK_SCORE)

    def test_decoupled_wpm_and_fluency(self):
        analyzer = AudioAnalyzer()
        # Simular audio con 135 WPM (óptimo VISUM) y sin vacilaciones ni muletillas
        # 135 palabras en 60 segundos
        words = [{"word": f"palabra{i}", "start": i * 0.4, "end": i * 0.4 + 0.3, "confidence": 0.9} for i in range(135)]
        acustica = {
            "total_duration_sec": 60.0,
            "speech_time_sec": 50.0,
            "phonation_ratio": 0.83,
            "pausas_prolongadas_acusticas": [],
        }
        metrics = analyzer.calcular_metricas_fluidez({"words": words}, acustica)
        
        # WPM óptimo (135) debe arrojar score_wpm = 100.0
        self.assertEqual(metrics["score_wpm"], 100.0)
        # Sin muletillas ni pausas prolongadas -> score_fluidez = 100.0
        self.assertEqual(metrics["score_fluidez"], 100.0)
        self.assertEqual(metrics["score_diccion"], 90.0)

        # Simular WPM lento (ej: 60 WPM en 60 segundos)
        slow_words = [{"word": f"lento{i}", "start": i * 0.9, "end": i * 0.9 + 0.5, "confidence": 0.9} for i in range(60)]
        slow_metrics = analyzer.calcular_metricas_fluidez({"words": slow_words}, acustica)
        # score_wpm = 100 - |135 - 60| * 1.2 = 100 - 75 * 1.2 = 10.0
        self.assertEqual(slow_metrics["score_wpm"], 10.0)
        # score_fluidez no debe haber sido castigado por el ritmo lento, sino por pausas/muletillas
        self.assertEqual(slow_metrics["score_fluidez"], 100.0)

    def test_red_line_infraction_cap(self):
        # Si hubo vulneración de línea roja, Coherencia debe quedar truncada a <= RED_LINE_SCORE_CAP (20 pts)
        llm_result_violation = {
            "puntaje_global_100": 85.0,  # Nota alta original
            "infraccion_linea_roja": True,
            "evidencia_linea_roja": "El vocero admitió culpabilidad sin peritaje previo.",
            "reconocimiento_afectados": {"nivel": 4, "score_100": 75.0, "criterio": "Mencionó afectados."},
            "dimensiones": {
                "alineacion_mensaje_clave": {"score_100": 80.0},
                "tecnicas_control": {"score_100": 70.0, "tecnicas_detectadas": ["bridging"]},
            },
            "feedback": {"fortaleza_principal": "Voz clara", "brecha_critica": "Vulneró línea roja", "recomendacion_accionable": "No admitir culpa"}
        }
        
        vision_result = {"summary": {"eye_contact_pct": 80.0, "shoulder_stability_score": 85.0, "hands_visible_pct": 40.0, "hands_active_pct": 30.0, "body_sway_std": 0.01}}
        audio_result = {"metrics": {"score_wpm": 85.0, "score_fluidez": 80.0, "score_diccion": 90.0}}

        report = ReportBuilder.build_consolidated_report(
            session_id="test-session",
            blob_name="test.webm",
            vision_result=vision_result,
            audio_result=audio_result,
            llm_result=llm_result_violation,
        )

        # Coherencia / Estrategia debe quedar truncada a 20.0
        self.assertLessEqual(report["puntuacion_global"]["score_estrategia_crisis"], RED_LINE_SCORE_CAP)
        self.assertLessEqual(report["puntuacion_global"]["areas"]["coherence"], RED_LINE_SCORE_CAP)

        # Al sanitizar el reporte, debe inyectarse la advertencia prioritaria en improvements
        sanitized = sanitize_report_json(
            session_id="test-session",
            job_id="job-1",
            report_id="rep-1",
            processed_at="2026-10-20T12:00:00Z",
            recording_url="https://blob/test.webm",
            overall_score=report["puntuacion_global"]["score_general"],
            area_scores=report["puntuacion_global"]["areas"],
            visum_narrative={"desempeno_observado": {"fortalezas": ["Aplomo"], "oportunidades_desarrollo": ["Articulación"]}},
            vision_metrics=vision_result,
            audio_metrics=audio_result["metrics"],
            judge_metrics=report["evaluacion_llm_crisis"],
            transcript="Texto de prueba",
        )

        improvements = sanitized["narrative"]["improvements"]
        self.assertGreater(len(improvements), 0)
        self.assertIn("ALERTA CRÍTICA: Vulneraste una línea roja del escenario", improvements[0])
        self.assertTrue(sanitized["metrics"]["judge"]["infraccionLineaRoja"])

    def test_balanced_empathy_calculation(self):
        # Criterio DoD: Video perfecto (100% no verbal) pero omisión total de afectados (Nivel 1 = 0 verbal)
        # Resultado esperado: 100 * 0.40 + 0 * 0.60 = 40.0 pts
        score_no_verbal = 100.0
        victim_level_omission = 1
        empathy_score = compute_empathy_score(score_no_verbal, victim_level_omission)
        self.assertEqual(empathy_score, 40.0)

        # Reconocimiento adecuado (Nivel 3 = 50.0 verbal)
        # 100 * 0.40 + 50 * 0.60 = 40.0 + 30.0 = 70.0 pts
        self.assertEqual(compute_empathy_score(100.0, 3), 70.0)

        # Reconocimiento sobresaliente (Nivel 5 = 100.0 verbal) con video bajo (50.0 no verbal)
        # 50 * 0.40 + 100 * 0.60 = 20.0 + 60.0 = 80.0 pts
        self.assertEqual(compute_empathy_score(50.0, 5), 80.0)

    def test_macro_weights_overall_score(self):
        # Expresión 25%, Voz 25%, Coherencia 35%, Empatía 15%
        vision_result = {"summary": {"eye_contact_pct": 100.0, "shoulder_stability_score": 100.0, "hands_visible_pct": 100.0, "hands_active_pct": 100.0, "body_sway_std": 0.0}}
        audio_result = {"metrics": {"score_wpm": 100.0, "score_fluidez": 100.0, "score_diccion": 100.0}}
        llm_result = {
            "puntaje_global_100": 100.0,
            "infraccion_linea_roja": False,
            "reconocimiento_afectados": {"nivel": 5, "score_100": 100.0},
            "dimensiones": {},
            "feedback": {},
        }

        report = ReportBuilder.build_consolidated_report(
            session_id="test-perfect",
            blob_name="perfect.webm",
            vision_result=vision_result,
            audio_result=audio_result,
            llm_result=llm_result,
        )

        self.assertEqual(report["puntuacion_global"]["areas"]["expression"], 100.0)
        self.assertEqual(report["puntuacion_global"]["areas"]["voice"], 100.0)
        self.assertEqual(report["puntuacion_global"]["areas"]["coherence"], 100.0)
        self.assertEqual(report["puntuacion_global"]["areas"]["empathy"], 100.0)
        self.assertEqual(report["puntuacion_global"]["score_general"], 100.0)


if __name__ == "__main__":
    unittest.main()
