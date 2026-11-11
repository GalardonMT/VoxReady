import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.ai_inference import AiInferenceService, FollowUpInput, FollowUpResponse


class TestAiInference(unittest.TestCase):
    def test_gemini_base_url_ends_with_slash(self):
        """Verifica la regla crítica de que GEMINI_OPENAI_BASE_URL siempre termine en '/'."""
        service = AiInferenceService(
            api_key="fake-key",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai"
        )
        self.assertTrue(service.base_url.endswith("/"), f"La URL debe terminar con '/', recibido: {service.base_url}")
        self.assertEqual(service.base_url, "https://generativelanguage.googleapis.com/v1beta/openai/")

    def test_follow_up_input_validation(self):
        """Valida que los campos mínimos requeridos sean obligatorios."""
        with self.assertRaises(ValidationError):
            # userAnswerTranscript debe tener al menos 10 caracteres
            FollowUpInput(
                currentQuestion="¿Qué medidas tomará?",
                userAnswerTranscript="Hola",
                topicContext="Crisis de ciberataque"
            )

        valid_input = FollowUpInput(
            currentQuestion="¿Por qué se demoró la respuesta?",
            userAnswerTranscript="Se demoró debido a que estábamos recopilando antecedentes con el equipo de TI.",
            topicContext="Crisis operativa por filtración de datos"
        )
        self.assertEqual(len(valid_input.topicRedLines), 0)
        self.assertEqual(len(valid_input.keyMessages), 0)

    def test_generate_dynamic_follow_up_success(self):
        """Valida la llamada con Structured Outputs y reasoning_effort='low'."""
        service = AiInferenceService(api_key="fake-key")

        mock_response = FollowUpResponse(
            followUpQuestion="¿Por qué no alertaron a los usuarios de inmediato?",
            rationale="Presionar sobre el retraso en la comunicación",
            targetRisk="Evasión de responsabilidad"
        )

        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.parsed = mock_response
        mock_completion.choices = [mock_choice]

        with patch.object(service.client.beta.chat.completions, "parse", return_value=mock_completion) as mock_parse:
            payload = FollowUpInput(
                currentQuestion="¿Cuándo se enteraron del problema?",
                userAnswerTranscript="Tomamos conocimiento a primera hora de hoy y activamos el protocolo de seguridad.",
                topicContext="Falla crítica en servidores de pago",
                topicRedLines=["No responsabilizar al proveedor externo"],
                keyMessages=["La plataforma ya está operando con normalidad"]
            )
            result = service.generate_dynamic_follow_up(payload)

            self.assertEqual(result.followUpQuestion, "¿Por qué no alertaron a los usuarios de inmediato?")
            mock_parse.assert_called_once()
            call_kwargs = mock_parse.call_args[1]
            self.assertEqual(call_kwargs.get("extra_body"), {"reasoning_effort": "low"})
            self.assertEqual(call_kwargs.get("model"), "gemini-3.5-flash-lite")

    def test_generate_dynamic_follow_up_fallback_on_api_error(self):
        """Valida que ante fallo de API se retorne la pregunta de fallback determinista."""
        service = AiInferenceService(api_key="fake-key")

        with patch.object(service.client.beta.chat.completions, "parse", side_effect=Exception("API Error")):
            with patch("time.sleep", return_value=None):
                payload = FollowUpInput(
                    currentQuestion="¿Cuál es el balance de los daños?",
                    userAnswerTranscript="Estamos evaluando aún el alcance total de los daños en la planta.",
                    topicContext="Incendio en bodega central"
                )
                result = service.generate_dynamic_follow_up(payload)

                self.assertIsNotNone(result)
                self.assertIn("garantías operativas inmediatas", result.followUpQuestion)


if __name__ == "__main__":
    unittest.main()

