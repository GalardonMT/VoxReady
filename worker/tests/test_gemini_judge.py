import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKER_DIR = Path(__file__).resolve().parent.parent
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from core.llm_judge import LLMJudgeService
from core.schemas import EvaluacionLLMResponse, DimensionScore, EvaluacionDimensiones, FeedbackPedagogico, TecnicasControlScore, MensajeClaveScore


class TestGeminiJudge(unittest.TestCase):
    def test_gemini_base_url_ends_with_slash(self):
        """Verifica la regla crítica de que GEMINI_OPENAI_BASE_URL siempre termine en '/'."""
        judge = LLMJudgeService(
            api_key="fake-key",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai"
        )
        self.assertTrue(judge.base_url.endswith("/"), f"La URL debe terminar con '/', recibido: {judge.base_url}")
        self.assertEqual(judge.base_url, "https://generativelanguage.googleapis.com/v1beta/openai/")

    def test_gemini_judge_structured_parse_success(self):
        """Valida que evaluate_response utilice Structured Outputs (beta.chat.completions.parse) con reasoning_effort."""
        judge = LLMJudgeService(api_key="fake-key", model="gemini-3.8-flash")

        mock_eval = EvaluacionLLMResponse(
            evaluacion_dimensiones=EvaluacionDimensiones(
                pertinencia_respuesta=DimensionScore(nivel=4, criterio="Responde adecuadamente", evidencia_textual="frase"),
                tecnicas_control=TecnicasControlScore(nivel=4, criterio="Usa bridging efectivo", evidencia_textual="puente"),
                alineacion_mensaje_clave=MensajeClaveScore(nivel=5, criterio="Excelente alineación", evidencia_textual="mensaje"),
                capacidad_sintesis=DimensionScore(nivel=4, criterio="Buena síntesis", evidencia_textual=""),
                claridad_mensaje=DimensionScore(nivel=4, criterio="Claro y directo", evidencia_textual=""),
                consistencia_institucional=DimensionScore(nivel=5, criterio="Consistente con políticas", evidencia_textual=""),
                asertividad_hostilidad=DimensionScore(nivel=4, criterio="Tranquilo y firme", evidencia_textual="")
            ),
            feedback_pedagogico=FeedbackPedagogico(
                fortaleza_principal="Mantuvo el control",
                brecha_critica="Puede acortar la introducción",
                recomendacion_accionable="Ir directo al grano"
            ),
            infraccion_linea_roja=False,
            evidencia_linea_roja=None,
            reconocimiento_afectados=DimensionScore(nivel=4, criterio="Priorizó afectados", evidencia_textual="")
        )

        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.parsed = mock_eval
        mock_completion.choices = [mock_choice]

        with patch.object(judge.client.beta.chat.completions, "parse", return_value=mock_completion) as mock_parse:
            reporte = judge.evaluate_response(
                pregunta_periodista="¿Por qué ocurrió el incidente?",
                mensajes_clave=["La seguridad es prioridad"],
                contexto_crisis="Falla eléctrica en planta",
                transcripcion_vocero="Estamos investigando el incidente con máxima prioridad en la seguridad."
            )

            self.assertIsNotNone(reporte)
            self.assertGreater(reporte.puntaje_global_100, 70.0)
            self.assertFalse(reporte.infraccion_linea_roja)
            mock_parse.assert_called_once()
            call_kwargs = mock_parse.call_args[1]
            self.assertEqual(call_kwargs.get("extra_body"), {"reasoning_effort": "medium"})

    def test_gemini_judge_fallback_on_503(self):
        """Verifica que ante un error 503 en el modelo primario, se intente con gemini-3.5-flash-lite."""
        judge = LLMJudgeService(
            api_key="fake-key",
            model="gemini-3.8-flash",
            fast_model="gemini-3.5-flash-lite"
        )

        mock_eval = EvaluacionLLMResponse(
            evaluacion_dimensiones=EvaluacionDimensiones(
                pertinencia_respuesta=DimensionScore(nivel=3, criterio="Regular", evidencia_textual=""),
                tecnicas_control=TecnicasControlScore(nivel=3, criterio="Regular", evidencia_textual=""),
                alineacion_mensaje_clave=MensajeClaveScore(nivel=3, criterio="Regular", evidencia_textual=""),
                capacidad_sintesis=DimensionScore(nivel=3, criterio="Regular", evidencia_textual=""),
                claridad_mensaje=DimensionScore(nivel=3, criterio="Regular", evidencia_textual=""),
                consistencia_institucional=DimensionScore(nivel=3, criterio="Regular", evidencia_textual=""),
                asertividad_hostilidad=DimensionScore(nivel=3, criterio="Regular", evidencia_textual="")
            ),
            feedback_pedagogico=FeedbackPedagogico(
                fortaleza_principal="Ninguna evidente",
                brecha_critica="Falta preparación",
                recomendacion_accionable="Entrenar vocería"
            ),
            infraccion_linea_roja=False,
            evidencia_linea_roja=None
        )

        mock_fast_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.parsed = mock_eval
        mock_fast_completion.choices = [mock_choice]

        # Simular fallo 503 en gemini-3.8-flash y éxito en gemini-3.5-flash-lite
        err_503 = Exception("503 Service Unavailable (high demand)")

        def side_effect(**kwargs):
            if kwargs.get("model") == "gemini-3.8-flash":
                raise err_503
            return mock_fast_completion

        with patch.object(judge.client.beta.chat.completions, "parse", side_effect=side_effect) as mock_parse:
            with patch("core.llm_judge.time.sleep", return_value=None):
                reporte = judge.evaluate_response(
                    pregunta_periodista="Pregunta de prueba",
                    mensajes_clave=["Mensaje clave"],
                    contexto_crisis="Contexto",
                    transcripcion_vocero="Respuesta del vocero"
                )

                self.assertIsNotNone(reporte)
                self.assertEqual(reporte.puntaje_global_100, 50.0)
                # Verificar que se llamó al modelo de respaldo con reasoning_effort='low'
                last_call_kwargs = mock_parse.call_args[1]
                self.assertEqual(last_call_kwargs.get("model"), "gemini-3.5-flash-lite")
                self.assertEqual(last_call_kwargs.get("extra_body"), {"reasoning_effort": "low"})


if __name__ == "__main__":
    unittest.main()

