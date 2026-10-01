import os
import json
import time
from typing import Any

try:
    import azure.functions as func
except ImportError:
    class _MockFunc:
        class FunctionApp:
            def service_bus_queue_trigger(self, *args, **kwargs):
                def decorator(fn):
                    return fn
                return decorator

        class ServiceBusMessage:
            def __init__(self, body: bytes = b""):
                self._body = body

            def get_body(self) -> bytes:
                return self._body

    func = _MockFunc()

from utils.logger import get_logger, log_event
from services.blob_service import BlobService
from services.db_service import DatabaseService
from core.media_splitter import (
    create_temp_workspace,
    extract_audio_pcm16,
    extract_sampled_frames,
    cleanup_temp_files,
)
from core.audio_analyzer import AudioAnalyzer
from core.vision_client import VisionClient
from core.llm_judge import LLMJudge
from core.report_builder import ReportBuilder

logger = get_logger("function_app")

# Inicializar la aplicación bajo el modelo Azure Functions Python v2
app = func.FunctionApp()


@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="analysis-queue",
    connection="SERVICE_BUS_CONNECTION_STRING",
)
def process_crisis_session(msg: func.ServiceBusMessage) -> None:
    """
    Entrypoint principal activado por eventos en Azure Service Bus (analysis-queue).
    Orquesta el pipeline completo de análisis multimedia:
      1. Parseo del mensaje y cambio de estado a 'processing'.
      2. Descarga del video desde Azure Blob Storage a /tmp.
      3. Separación de audio WAV (16kHz PCM) y frames (0.5 FPS) vía FFmpeg.
      4. Análisis acústico y transcripción (NVIDIA Parakeet/Riva).
      5. Evaluación de presencia y contacto visual (ca-vision-service).
      6. Calificación de crisis con LLM Juez (NVIDIA Build API / Llama 3.2 90B).
      7. Fusión matemática, persistencia en Azure SQL y Blob Storage.
      8. Limpieza estricta de archivos temporales en /tmp.
      9. Manejo de reintentos y Dead-Letter Queue ante fallos críticos.
    """
    start_time = time.time()
    session_id = "unknown"
    step = "init"
    temp_paths = None

    # Inicializar servicios
    blob_service = BlobService()
    db_service = DatabaseService()
    audio_analyzer = AudioAnalyzer()
    vision_client = VisionClient()
    llm_judge = LLMJudge()

    try:
        # 1. Parseo del payload JSON recibido desde Service Bus
        step = "parse_message"
        body_str = msg.get_body().decode("utf-8")
        payload = json.loads(body_str)

        session_id = str(payload.get("session_id", "")).strip()
        blob_name = str(payload.get("blob_name", "")).strip()
        container_name = payload.get("container_name", "recordings")
        crisis_context = payload.get("crisis_context")
        key_messages = payload.get("key_messages")

        if not session_id or not blob_name:
            raise ValueError(
                f"Mensaje inválido: 'session_id' y 'blob_name' son obligatorios. Payload: {body_str}"
            )

        log_event(
            logger,
            "INFO",
            f"Iniciando procesamiento de sesión '{session_id}' para blob '{blob_name}'...",
            session_id=session_id,
            step=step,
        )

        # 2. Actualizar estado a 'processing' en Azure SQL
        step = "update_status_processing"
        try:
            db_service.update_session_status(session_id, "processing")
        except Exception as db_err:
            logger.warning(
                f"Aviso: no se pudo actualizar estado a 'processing' en BD ({db_err}). Continuando..."
            )

        # 3. Crear espacio temporal en /tmp
        step = "create_workspace"
        temp_paths = create_temp_workspace(session_id)
        video_local_path = str(temp_paths["video_path"])
        audio_local_path = str(temp_paths["audio_path"])
        frames_dir = str(temp_paths["frames_dir"])

        # 4. Descargar video desde Azure Blob Storage
        step = "download_blob"
        t0 = time.time()
        blob_service.download_recording(
            blob_name=blob_name,
            destination_path=video_local_path,
            container_name=container_name,
        )
        log_event(
            logger,
            "INFO",
            f"Descarga de blob completada",
            session_id=session_id,
            step=step,
            latency_ms=round((time.time() - t0) * 1000, 2),
        )

        # 5. Separación multimedia con FFmpeg
        step = "ffmpeg_media_split"
        t0 = time.time()
        # 5a. Extraer Audio PCM16 16kHz
        extract_audio_pcm16(
            input_video_path=video_local_path,
            output_wav_path=audio_local_path,
        )
        # 5b. Extraer frames muestreados a 0.5 FPS
        frame_files = extract_sampled_frames(
            input_video_path=video_local_path,
            output_dir=frames_dir,
            fps=0.5,
        )
        log_event(
            logger,
            "INFO",
            f"Separación FFmpeg completada: {len(frame_files)} frames extraídos",
            session_id=session_id,
            step=step,
            latency_ms=round((time.time() - t0) * 1000, 2),
        )

        # 6. Análisis de Audio y Voz (NVIDIA Parakeet + Métricas Acústicas Locales)
        step = "audio_analysis"
        t0 = time.time()
        audio_result = audio_analyzer.process_audio(audio_local_path)
        log_event(
            logger,
            "INFO",
            f"Análisis de audio completado: {audio_result.get('metrics', {}).get('wpm_global')} WPM, "
            f"fluidez={audio_result.get('metrics', {}).get('score_fluidez')}",
            session_id=session_id,
            step=step,
            latency_ms=round((time.time() - t0) * 1000, 2),
        )

        # 7. Análisis de Visión (ca-vision-service)
        step = "vision_analysis"
        t0 = time.time()
        vision_result = vision_client.analyze_frames(frame_files, fps=0.5)
        log_event(
            logger,
            "INFO",
            f"Análisis de visión completado: contacto={vision_result.get('contacto_visual_porcentaje')}%, "
            f"estabilidad={vision_result.get('posture_stability_score')}",
            session_id=session_id,
            step=step,
            latency_ms=round((time.time() - t0) * 1000, 2),
        )

        # 8. Evaluación con LLM Juez (NVIDIA Build API / Llama 3.2 90B)
        step = "llm_judge"
        t0 = time.time()
        transcript_text = audio_result.get("transcription", "")
        llm_result = llm_judge.evaluate_transcript(
            transcript=transcript_text,
            crisis_context=crisis_context,
            key_messages=key_messages,
        )
        log_event(
            logger,
            "INFO",
            f"Evaluación de LLM Juez completada: apego={llm_result.get('key_message_adherence_score')}, "
            f"crisis={llm_result.get('crisis_control_score')}",
            session_id=session_id,
            step=step,
            latency_ms=round((time.time() - t0) * 1000, 2),
        )

        # 9. Fusión Matemática y Construcción del Reporte Consolidado
        step = "build_report"
        consolidated_report = ReportBuilder.build_consolidated_report(
            session_id=session_id,
            blob_name=blob_name,
            vision_result=vision_result,
            audio_result=audio_result,
            llm_result=llm_result,
            metadata=payload.get("metadata"),
        )

        # 10. Persistencia en Azure SQL y Azure Blob Storage
        step = "persist_report"
        # Guardar en Azure SQL Serverless
        db_service.save_analysis_report(session_id, consolidated_report)

        # Subir copia JSON a contenedor reports/ en Blob Storage
        try:
            report_blob_name = f"{session_id}/reporte_consolidado.json"
            blob_service.upload_report(
                blob_name=report_blob_name,
                content=json.dumps(consolidated_report, ensure_ascii=False, indent=2),
            )
        except Exception as upload_err:
            logger.warning(
                f"No se pudo respaldar el JSON del reporte en Blob Storage ({upload_err})."
            )

        total_duration = round((time.time() - start_time), 2)
        log_event(
            logger,
            "INFO",
            f"Pipeline finalizado exitosamente para sesión '{session_id}' en {total_duration}s. "
            f"Score global={consolidated_report['puntuacion_global']['score_general']}.",
            session_id=session_id,
            step="completed",
            latency_ms=round(total_duration * 1000, 2),
            status="completed",
        )

    except Exception as exc:
        total_duration = round((time.time() - start_time), 2)
        log_event(
            logger,
            "ERROR",
            f"Fallo crítico en paso '{step}' para sesión '{session_id}': {exc}",
            session_id=session_id,
            step=step,
            status="failed",
            latency_ms=round(total_duration * 1000, 2),
        )

        # Marcar la sesión como failed en la base de datos
        try:
            db_service.update_session_status(
                session_id=session_id,
                status="failed",
                error_message=f"Fallo en paso [{step}]: {str(exc)}",
            )
        except Exception as db_fail_err:
            logger.error(
                f"No se pudo registrar estado 'failed' en BD para sesión '{session_id}': {db_fail_err}"
            )

        # Al propagar la excepción, Azure Functions no completa el mensaje de Service Bus.
        # Esto permite que el runtime aplique los reintentos automáticos configurados
        # y tras 3 intentos mueva el mensaje a la Dead-Letter Queue (DLQ).
        raise exc

    finally:
        # 11. Limpieza estricta de archivos temporales en /tmp
        if temp_paths and "session_dir" in temp_paths:
            logger.info(f"Ejecutando limpieza estricta de /tmp para sesión '{session_id}'...")
            cleanup_temp_files(str(temp_paths["session_dir"]))
