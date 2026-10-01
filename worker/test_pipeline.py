import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Asegurar que el directorio voxready-worker esté en el sys.path
WORKER_ROOT = Path(__file__).resolve().parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from utils.logger import get_logger, setup_logging
from core.media_splitter import (
    get_ffmpeg_executable,
    extract_audio_pcm16,
    extract_sampled_frames,
    cleanup_temp_files,
    create_temp_workspace,
    get_temp_base_dir,
)
from core.audio_analyzer import AudioAnalyzer, MULETILLAS_TARGET
from core.vision_client import VisionClient
from core.llm_judge import LLMJudge
from core.report_builder import ReportBuilder
from services.blob_service import BlobService
from services.db_service import DatabaseService

setup_logging("INFO")
logger = get_logger("test_pipeline")


def create_synthetic_test_video(output_path: str, duration_sec: int = 3) -> str:
    """
    Genera un video sintético breve (.mp4 con audio test) usando FFmpeg
    para probar el pipeline localmente sin requerir archivos pesados.
    """
    ffmpeg_exe = get_ffmpeg_executable()
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # Genera video de color test con tono senoidal de 440Hz
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration_sec}:size=640x360:rate=10",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={duration_sec}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(out),
    ]

    import subprocess
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"No se pudo crear video de prueba sintético: {res.stderr}")
    return str(out)


class TestVoxReadyWorkerUnit(unittest.TestCase):
    """Suite de Pruebas Unitarias para los Módulos de VoxReady Worker."""

    def test_01_ffmpeg_executable_discovery(self):
        """Verifica que FFmpeg sea encontrado y ejecutable."""
        exe = get_ffmpeg_executable()
        self.assertTrue(os.path.exists(exe) or shutil.which(exe) is not None)
        logger.info(f"[TEST PASS] FFmpeg ejecutable detectado: {exe}")

    def test_02_media_splitter_extraction_and_cleanup(self):
        """Valida separación de audio PCM16, frames muestreados y limpieza estricta."""
        temp_dir = Path(tempfile.mkdtemp(prefix="test_voxready_media_"))
        try:
            test_video = temp_dir / "test_sample.mp4"
            create_synthetic_test_video(str(test_video), duration_sec=3)
            self.assertTrue(test_video.exists())

            out_audio = temp_dir / "test_audio.wav"
            frames_dir = temp_dir / "frames"

            # Extraer audio PCM16
            audio_ok = extract_audio_pcm16(str(test_video), str(out_audio))
            self.assertTrue(audio_ok)
            self.assertTrue(out_audio.exists())
            self.assertGreater(out_audio.stat().st_size, 0)

            # Extraer frames a 0.5 FPS (1 frame cada 2s -> 3s video = ~2 frames)
            frames = extract_sampled_frames(str(test_video), str(frames_dir), fps=0.5)
            self.assertGreaterEqual(len(frames), 1)
            for f in frames:
                self.assertTrue(os.path.exists(f))

            logger.info(
                f"[TEST PASS] Separación exitosa: audio ({out_audio.stat().st_size} bytes), frames ({len(frames)})"
            )
        finally:
            cleanup_temp_files(str(temp_dir))
            self.assertFalse(temp_dir.exists())
            logger.info("[TEST PASS] Limpieza estricta de directorio temporal verificada.")

    def test_03_audio_analyzer_acoustics_and_wpm(self):
        """Valida cálculo de RMS, VAD, pausas prolongadas y métricas de fluidez/WPM."""
        temp_dir = Path(tempfile.mkdtemp(prefix="test_voxready_audio_"))
        try:
            test_video = temp_dir / "test_sample.mp4"
            create_synthetic_test_video(str(test_video), duration_sec=3)
            out_audio = temp_dir / "test_audio.wav"
            extract_audio_pcm16(str(test_video), str(out_audio))

            analyzer = AudioAnalyzer()
            acustica = analyzer.calcular_acustica_rms(str(out_audio))
            self.assertIn("total_duration_sec", acustica)
            self.assertGreater(acustica["total_duration_sec"], 2.0)
            self.assertIn("speech_time_sec", acustica)

            # Simular salida de ASR Parakeet con muletillas y pausas
            mock_parakeet = {
                "transcript": "hola este es un mensaje de prueba o sea estamos verificando la seguridad",
                "words": [
                    {"word": "hola", "start": 0.1, "end": 0.4, "confidence": 0.98},
                    {"word": "este", "start": 0.5, "end": 0.8, "confidence": 0.95},  # Muletilla
                    {"word": "es", "start": 0.85, "end": 0.95, "confidence": 0.99},
                    {"word": "un", "start": 1.0, "end": 1.1, "confidence": 0.99},
                    {"word": "mensaje", "start": 1.15, "end": 1.6, "confidence": 0.97},
                    {"word": "de", "start": 1.65, "end": 1.75, "confidence": 0.99},
                    {"word": "prueba", "start": 1.8, "end": 2.2, "confidence": 0.98},
                    # Pausa prolongada de 1.6 segundos entre 2.2 y 3.8
                    {"word": "o sea", "start": 3.8, "end": 4.2, "confidence": 0.94},  # Muletilla
                    {"word": "estamos", "start": 4.3, "end": 4.7, "confidence": 0.96},
                    {"word": "verificando", "start": 4.8, "end": 5.4, "confidence": 0.97},
                    {"word": "la", "start": 5.5, "end": 5.6, "confidence": 0.99},
                    {"word": "seguridad", "start": 5.7, "end": 6.3, "confidence": 0.98},
                ],
            }
            acustica_sim = {"total_duration_sec": 6.5, "speech_time_sec": 4.8, "phonation_ratio": 0.74}
            metrics = analyzer.calcular_metricas_fluidez(mock_parakeet, acustica_sim)

            self.assertEqual(metrics["palabras_totales"], 12)
            self.assertGreater(metrics["wpm_global"], 0)
            self.assertGreaterEqual(metrics["pausas_prolongadas"], 1)
            self.assertIn("este", metrics["muletillas_detectadas"])
            self.assertGreater(metrics["densidad_muletillas_pct"], 0)
            self.assertTrue(0 <= metrics["score_fluidez"] <= 100)
            self.assertTrue(0 <= metrics["score_diccion"] <= 100)

            logger.info(
                f"[TEST PASS] Métricas de voz validadas: {metrics['wpm_global']} WPM, "
                f"Pausas prolongadas={metrics['pausas_prolongadas']}, "
                f"Muletillas={metrics['conteo_muletillas']}, "
                f"Score fluidez={metrics['score_fluidez']}"
            )
        finally:
            cleanup_temp_files(str(temp_dir))

    def test_04_vision_client_math_aggregation(self):
        """Valida el cálculo matemático de Eye Contact % y Posture Stability Score."""
        client = VisionClient(base_url="https://mock-vision.internal")

        # Mock de respuestas de frames
        mock_frame_results = [
            {"eye_contact": True, "posture_stability_score": 92.0, "shoulder_angle": 2.1, "head_roll_angle": 3.4},
            {"eye_contact": True, "posture_stability_score": 88.0, "shoulder_angle": 3.0, "head_roll_angle": 4.1},
            {"eye_contact": False, "posture_stability_score": 90.0, "shoulder_angle": 6.2, "head_roll_angle": 9.5},
            {"eye_contact": True, "posture_stability_score": 94.0, "shoulder_angle": 1.8, "head_roll_angle": 2.0},
        ]

        # Simular consolidación parcheando tanto el método de httpx como el de requests
        with patch.object(client, "_send_frame_with_retry") as mock_async, \
             patch.object(client, "_send_frame_requests") as mock_sync:
            mock_async.side_effect = mock_frame_results
            mock_sync.side_effect = mock_frame_results
            res = client.analyze_frames(["f1.jpg", "f2.jpg", "f3.jpg", "f4.jpg"])

            # 3 de 4 frames tienen eye_contact = True -> 75%
            self.assertEqual(res["contacto_visual_porcentaje"], 75.0)
            # Promedio de posture_stability_score: (92 + 88 + 90 + 94)/4 = 91.0
            self.assertEqual(res["posture_stability_score"], 91.0)
            self.assertEqual(res["frames_validos"], 4)
            logger.info(
                f"[TEST PASS] Consolidación de visión: Contacto={res['contacto_visual_porcentaje']}%, "
                f"Estabilidad={res['posture_stability_score']}"
            )

    def test_05_llm_judge_json_schema_validation(self):
        """Valida que el evaluador LLM produzca y valide el esquema JSON requerido."""
        judge = LLMJudge()
        transcript = (
            "Queremos transmitir absoluta tranquilidad a la ciudadanía. "
            "Nuestra máxima prioridad es la seguridad y estamos aplicando todos los protocolos."
        )

        res = judge.evaluate_transcript(
            transcript=transcript,
            crisis_context="Fuga de gas controlada en planta norte",
            key_messages=["La situación está controlada", "La prioridad es la seguridad"],
        )

        required_keys = [
            "key_message_adherence_score",
            "crisis_control_score",
            "bridging_detected",
            "strengths",
            "weaknesses",
            "executive_summary",
        ]
        for k in required_keys:
            self.assertIn(k, res)

        self.assertTrue(0 <= res["key_message_adherence_score"] <= 100)
        self.assertTrue(0 <= res["crisis_control_score"] <= 100)
        self.assertIsInstance(res["bridging_detected"], bool)
        self.assertIsInstance(res["strengths"], list)
        self.assertIsInstance(res["weaknesses"], list)
        self.assertIsInstance(res["executive_summary"], str)

        logger.info(f"[TEST PASS] Evaluación LLM Juez esquema validado: {json.dumps(res, ensure_ascii=False)}")

    def test_06_report_builder_fusion(self):
        """Valida la fusión matemática de métricas y la estructura del JSON final."""
        vision_res = {
            "total_frames_analizados": 10,
            "frames_validos": 10,
            "contacto_visual_porcentaje": 80.0,
            "posture_stability_score": 90.0,
            "metricas_ejes": {"indice_tension_facial": 0.15},
            "eventos_detectados": [],
        }
        audio_res = {
            "transcription": "Mensaje de prueba institucional",
            "words": [{"word": "mensaje", "start": 0.0, "end": 0.5}],
            "metrics": {
                "duracion_segundos": 10.0,
                "tiempo_voz_activa_segundos": 7.5,
                "palabras_totales": 20,
                "wpm_global": 120.0,
                "score_fluidez": 88.0,
                "score_diccion": 92.0,
                "pausas_prolongadas": 0,
                "densidad_muletillas_pct": 2.5,
                "muletillas_detectadas": ["este"],
            },
        }
        llm_res = {
            "key_message_adherence_score": 85,
            "crisis_control_score": 80,
            "bridging_detected": True,
            "strengths": ["Mantuvo la calma"],
            "weaknesses": ["Falta precisión"],
            "executive_summary": "Buen desempeño.",
        }

        report = ReportBuilder.build_consolidated_report(
            session_id="sess_12345",
            blob_name="recordings/crisis_01.webm",
            vision_result=vision_res,
            audio_result=audio_res,
            llm_result=llm_res,
            metadata={"environment": "test"},
        )

        self.assertEqual(report["session_id"], "sess_12345")
        self.assertIn("puntuacion_global", report)
        self.assertIn("score_general", report["puntuacion_global"])
        self.assertGreater(report["puntuacion_global"]["score_general"], 0)
        self.assertEqual(report["metricas_vision"]["contacto_visual_porcentaje"], 80.0)
        self.assertEqual(report["metricas_audio_voz"]["score_fluidez"], 88.0)
        self.assertEqual(report["evaluacion_llm_crisis"]["key_message_adherence_score"], 85)

        logger.info(
            f"[TEST PASS] Reporte consolidado construido: Score general={report['puntuacion_global']['score_general']}"
        )


class TestPipelineSimulation(unittest.TestCase):
    """Simulación de Ejecución End-to-End simulando un mensaje de Azure Service Bus."""

    def test_full_pipeline_simulation(self):
        logger.info("==================================================")
        logger.info("  INICIANDO SIMULACIÓN DE TRIGGER DE SERVICE BUS")
        logger.info("==================================================")

        # 1. Crear un video de prueba
        temp_test_dir = Path(tempfile.mkdtemp(prefix="test_sim_source_"))
        source_video = temp_test_dir / "simulacion_crisis.mp4"
        create_synthetic_test_video(str(source_video), duration_sec=3)

        session_id = f"test_sess_{int(time.time())}"
        blob_name = "crisis_sample_video.mp4"

        # 2. Mock de Azure Service Bus Message
        class MockServiceBusMessage:
            def __init__(self, payload: dict):
                self._body = json.dumps(payload).encode("utf-8")

            def get_body(self) -> bytes:
                return self._body

        mock_msg = MockServiceBusMessage({
            "session_id": session_id,
            "blob_name": blob_name,
            "container_name": "recordings",
            "crisis_context": "Simulación de evacuación preventiva",
            "key_messages": ["Evacuación completada", "Sin víctimas"],
        })

        # 3. Patching de servicios de red externos para simulación offline
        with patch.object(BlobService, "download_recording") as mock_dl, \
             patch.object(BlobService, "upload_report") as mock_ul, \
             patch.object(DatabaseService, "update_session_status") as mock_db_status, \
             patch.object(DatabaseService, "save_analysis_report") as mock_db_save, \
             patch.object(VisionClient, "analyze_frames") as mock_vision:

            # Copiar video local en lugar de descargar de Azure Blob
            def mock_download(blob_name, destination_path, **kwargs):
                shutil.copyfile(str(source_video), destination_path)
                return destination_path

            mock_dl.side_effect = mock_download
            mock_ul.return_value = f"https://mockblob.core.windows.net/reports/{session_id}.json"
            mock_db_status.return_value = True
            mock_db_save.return_value = True
            mock_vision.return_value = {
                "total_frames_analizados": 2,
                "frames_validos": 2,
                "contacto_visual_porcentaje": 100.0,
                "posture_stability_score": 95.0,
                "metricas_ejes": {"indice_tension_facial": 0.1},
                "eventos_detectados": [],
            }

            from function_app import process_crisis_session

            # Ejecutar el trigger
            process_crisis_session(mock_msg)

            # Verificaciones
            self.assertTrue(mock_dl.called)
            self.assertTrue(mock_db_status.called)
            self.assertTrue(mock_db_save.called)

            # Verificar que los datos guardados en BD tengan el schema correcto
            call_args = mock_db_save.call_args[0]
            saved_session_id = call_args[0]
            saved_report = call_args[1]

            self.assertEqual(saved_session_id, session_id)
            self.assertEqual(saved_report["session_id"], session_id)
            self.assertIn("puntuacion_global", saved_report)

            # Verificar que los archivos temporales se hayan eliminado
            session_tmp_dir = get_temp_base_dir() / f"voxready_{session_id}"
            self.assertFalse(session_tmp_dir.exists())

            logger.info("==================================================")
            logger.info("  SIMULACIÓN COMPLETADA CON ÉXITO")
            logger.info(f"  Sesión: {session_id}")
            logger.info(f"  Score Global obtenido: {saved_report['puntuacion_global']['score_general']}")
            logger.info(f"  Limpieza de /tmp verificada: {not session_tmp_dir.exists()}")
            logger.info("==================================================")

        cleanup_temp_files(str(temp_test_dir))


def run_tests():
    suite = unittest.TestSuite()
    suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestVoxReadyWorkerUnit))
    suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestPipelineSimulation))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
