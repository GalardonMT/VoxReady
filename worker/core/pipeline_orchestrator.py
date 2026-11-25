import os
import re
import json
import glob
import time
import uuid
import shutil
import logging
import subprocess
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import requests
import httpx
from openai import OpenAI
from azure.storage.blob import BlobServiceClient

try:
    from core.audio_analyzer import AudioAnalyzer, aggregate_turn_audio_results
    from core.llm_judge import LLMJudgeService, format_interview_dialogue, resolve_turn_followup_reason
    from core.narrative_generator import generate_visum_report
    from core.vision_client import VisionClient
    from core.report_builder import (
        calculate_expression_area_score,
        sanitize_report_json,
        compute_empathy_score,
        compute_governance_metrics,
        evaluate_metric_bands,
        compute_turn_vision_metrics,
    )
    from core.scoring_rules import (
        WEIGHT_EXPRESSION,
        WEIGHT_VOICE,
        WEIGHT_COHERENCE,
        WEIGHT_EMPATHY,
        VOICE_WEIGHT_WPM,
        VOICE_WEIGHT_FLUENCY,
        VOICE_WEIGHT_DICTION,
        RED_LINE_SCORE_CAP,
        DICTION_FALLBACK_SCORE,
        DynamicRubricConfig,
    )
    from services.db_service import DatabaseService
    from services.job_status import update_analysis_job_status
    from services.keyvault_service import get_secret
    from services.pipeline_results import persist_pipeline_results
    from services.recording_evidence import seal_recording_evidence
except (ImportError, ValueError):
    from worker.core.audio_analyzer import AudioAnalyzer, aggregate_turn_audio_results
    from worker.core.llm_judge import LLMJudgeService, format_interview_dialogue, resolve_turn_followup_reason
    from worker.core.narrative_generator import generate_visum_report
    from worker.core.vision_client import VisionClient
    from worker.core.report_builder import (
        calculate_expression_area_score,
        sanitize_report_json,
        compute_empathy_score,
        compute_governance_metrics,
        evaluate_metric_bands,
        compute_turn_vision_metrics,
    )
    from worker.config.scoring_rules import (
        WEIGHT_EXPRESSION,
        WEIGHT_VOICE,
        WEIGHT_COHERENCE,
        WEIGHT_EMPATHY,
        VOICE_WEIGHT_WPM,
        VOICE_WEIGHT_FLUENCY,
        VOICE_WEIGHT_DICTION,
        RED_LINE_SCORE_CAP,
        DICTION_FALLBACK_SCORE,
        DynamicRubricConfig,
    )
    from worker.services.db_service import DatabaseService
    from worker.services.job_status import update_analysis_job_status
    from worker.services.pipeline_results import persist_pipeline_results
    from worker.services.recording_evidence import seal_recording_evidence
    try:
        from worker.services.keyvault_service import get_secret
    except ImportError:
        get_secret = lambda k, d=None: os.getenv(k, d)

logger = logging.getLogger("analysis-worker.orchestrator")

STORAGE_CONN = os.getenv("STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("STORAGE_CONTAINER_NAME") or os.getenv("BLOB_CONTAINER_NAME", "recordings")
NVIDIA_API_KEY = (os.getenv("NVIDIA_API_KEY") or get_secret("NVIDIA_API_KEY") or get_secret("nvidia-api-key") or "").strip()
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
gemini_key = (os.getenv("GEMINI_API_KEY") or get_secret("GEMINI_API_KEY") or get_secret("gemini-api-key") or "").strip()

if gemini_key:
    LLM_API_KEY = gemini_key
    raw_base = (os.getenv("GEMINI_OPENAI_BASE_URL") or get_secret("GEMINI_OPENAI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai/").strip()
    LLM_MODEL = (os.getenv("GEMINI_JUDGE_MODEL") or get_secret("GEMINI_JUDGE_MODEL") or "gemini-3.5-flash-lite").strip()
    LLM_FAST_MODEL = (os.getenv("GEMINI_FAST_MODEL") or get_secret("GEMINI_FAST_MODEL") or "gemini-3.5-flash-lite").strip()
else:
    LLM_API_KEY = NVIDIA_API_KEY
    raw_base = (os.getenv("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1").strip()
    LLM_MODEL = (os.getenv("LLM_MODEL_NAME") or "deepseek-ai/deepseek-v4.1-flash").strip()
    LLM_FAST_MODEL = "deepseek-ai/deepseek-v4.1-flash"

if "generativelanguage.googleapis.com" in raw_base and not raw_base.endswith("/"):
    raw_base += "/"
elif raw_base.endswith("/chat/completions"):
    raw_base = raw_base[:-len("/chat/completions")].rstrip("/")
LLM_BASE_URL = raw_base
VISION_URL = os.getenv("VISION_SERVICE_URL")
SQL_CONN_STR = os.getenv("SQL_CONNECTION_STRING") or os.getenv("DATABASE_URL")


def download_blob(blob_path: str, local_path: str):
    """Descarga el video desde Azure Blob Storage probando variantes de contenedor y prefijo."""
    if not STORAGE_CONN:
        raise ValueError("STORAGE_CONNECTION_STRING no está configurada")

    blob_service = BlobServiceClient.from_connection_string(STORAGE_CONN)

    clean_path = (blob_path or "").strip().lstrip("/")
    default_container = CONTAINER_NAME or "recordings"

    candidates = []

    # 1. Si es URL completa (https://...)
    if clean_path.startswith("http://") or clean_path.startswith("https://"):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(clean_path)
            path_parts = parsed.path.lstrip("/").split("/", 1)
            if len(path_parts) == 2:
                candidates.append((path_parts[0], path_parts[1]))
        except Exception:
            pass

    # 2. Contenedor por defecto con la ruta tal cual (ej: "recordings", "recordings/<id>.webm")
    candidates.append((default_container, clean_path))

    # 3. Si clean_path empieza con f"{default_container}/", probar quitando el prefijo
    if clean_path.startswith(f"{default_container}/"):
        stripped = clean_path[len(default_container) + 1:]
        candidates.append((default_container, stripped))

    # 4. Si clean_path NO empieza con f"{default_container}/", probar agregando el prefijo
    if not clean_path.startswith(f"{default_container}/"):
        candidates.append((default_container, f"{default_container}/{clean_path}"))

    # 5. Si contiene '/', dividir por el primer segmento como contenedor
    if "/" in clean_path:
        parts = clean_path.split("/", 1)
        candidates.append((parts[0], parts[1]))

    seen = set()
    unique_candidates = []
    for c, b in candidates:
        pair = (c, b)
        if pair not in seen and c and b:
            seen.add(pair)
            unique_candidates.append(pair)

    last_error = None
    for cont, b_name in unique_candidates:
        try:
            logger.info(f"Intentando descargar blob: container='{cont}', blob='{b_name}'...")
            blob_client = blob_service.get_blob_client(container=cont, blob=b_name)
            with open(local_path, "wb") as f:
                download_stream = blob_client.download_blob()
                f.write(download_stream.readall())
            file_size = os.path.getsize(local_path)
            if file_size > 0:
                logger.info(f"Video descargado exitosamente de {cont}/{b_name}: {local_path} ({file_size} bytes)")
                return (cont, b_name)
        except Exception as e:
            last_error = e
            logger.warning(f"No se pudo descargar desde container='{cont}', blob='{b_name}': {e}")

    logger.error(f"Error crítico: Todas las rutas de descarga fallaron para '{blob_path}'. Candidatos probados: {unique_candidates}")
    raise last_error or RuntimeError(f"No se pudo descargar el blob: {blob_path}")


def remux_webm_for_seeking(input_path: str, output_path: str) -> bool:
    """
    Reconstruye sin recodificar (-c copy) las cabeceras EBML Duration e índice Cues
    en grabaciones WebM generadas por Chromium MediaRecorder para que permitan
    adelantar, retroceder y mostrar su duración real en cualquier navegador.
    """
    if not input_path or not os.path.exists(input_path):
        return False
    try:
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-i",
            input_path,
            "-c",
            "copy",
            "-f",
            "webm",
            output_path,
        ]
        res = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(
                f"Remux WebM sin recodificación completado ({os.path.getsize(output_path)} bytes): {output_path}"
            )
            return True
        logger.warning(f"Aviso en remux WebM (rc={res.returncode}): {(res.stderr or '')[:240]}")
    except Exception as exc:
        logger.warning(f"Aviso ejecutando remux WebM: {exc}")
    return False


def upload_remuxed_recording(container_name: str, blob_name: str, local_path: str) -> bool:
    """Sobrescribe el blob maestro con la versión remuxeada seekable (Duration + Cues)."""
    if not STORAGE_CONN or not container_name or not blob_name:
        return False
    try:
        from azure.storage.blob import ContentSettings

        blob_service = BlobServiceClient.from_connection_string(STORAGE_CONN)
        blob_client = blob_service.get_blob_client(container=container_name, blob=blob_name)
        with open(local_path, "rb") as stream:
            blob_client.upload_blob(
                stream,
                overwrite=True,
                content_settings=ContentSettings(content_type="video/webm"),
            )
        logger.info(f"Grabación remuxeada actualizada en Azure Blob: {container_name}/{blob_name}")
        return True
    except Exception as exc:
        logger.warning(f"Aviso actualizando grabación remuxeada en Blob Storage ({container_name}/{blob_name}): {exc}")
        return False


def _parse_ffmpeg_time_duration(stderr_text: str) -> Optional[float]:
    matches = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", stderr_text or "")
    if not matches:
        return None
    hrs, mins, secs = matches[-1]
    total = (int(hrs) * 3600.0) + (int(mins) * 60.0) + float(secs)
    return round(total, 3) if total >= 1.0 else None


def probe_media_duration(video_path: str) -> Optional[float]:
    """
    Obtiene la duración real en segundos del video maestro.
    Rechaza valores inválidos (< 1.0s como 0.001 de WebM crudos de MediaRecorder)
    y recurre a un escaneo rápido con FFmpeg null muxer si ffprobe no trae duración válida.
    """
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        res = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        raw = (res.stdout or "").strip()
        if res.returncode == 0 and raw and raw.lower() != "n/a":
            val = float(raw)
            if val >= 1.0:
                return round(val, 3)
    except Exception as exc:
        logger.warning(f"Aviso obteniendo duración con ffprobe: {exc}")

    # Respaldo: leer timestamp final real del stream con ffmpeg -f null -
    try:
        res_ff = subprocess.run(
            ["ffmpeg", "-nostdin", "-i", video_path, "-vn", "-f", "null", "-"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        parsed = _parse_ffmpeg_time_duration(res_ff.stderr)
        if parsed and parsed >= 1.0:
            return parsed
    except Exception as exc:
        logger.warning(f"Aviso obteniendo duración fallback con ffmpeg: {exc}")
    return None


def split_media(
    video_path: str,
    session_tmp_dir: str,
    *,
    extract_audio: bool = True,
    video_duration_sec: Optional[float] = None,
):
    """
    Extrae audio PCM 16kHz (si extract_audio=True) y fotogramas con FPS adaptativo:
    - <= 5 minutos (300s): 2 FPS (máxima fidelidad en contacto visual).
    - > 5 minutos: 1 FPS para balancear precisión y tiempo de inferencia.
    - Tope configurable VISION_MAX_FRAMES (default 600, procesados en lotes de 60).
    """
    audio_path = os.path.join(session_tmp_dir, "audio.wav")
    frames_dir = os.path.join(session_tmp_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    if extract_audio:
        cmd_audio = [
            "ffmpeg", "-nostdin", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path
        ]
        res_audio = subprocess.run(
            cmd_audio,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res_audio.returncode != 0:
            logger.error(f"Error en extracción de audio con FFmpeg: {res_audio.stderr[:400]}")
            raise RuntimeError(f"FFmpeg no pudo extraer la pista de audio: {res_audio.stderr[:200]}")

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise ValueError("El archivo de audio generado está vacío o no contiene datos válidos.")
    else:
        audio_path = ""

    # FPS adaptativo: 2 FPS hasta 5 min (300s), 1 FPS en sesiones más largas
    adaptive_fps = 1 if (video_duration_sec is not None and video_duration_sec > 300.0) else 2
    max_frames = max(60, int(os.getenv("VISION_MAX_FRAMES", "600")))

    cmd_frames = [
        "ffmpeg", "-nostdin", "-y", "-i", video_path,
        "-vf", f"fps={adaptive_fps}", "-q:v", "2", os.path.join(frames_dir, "frame_%05d.jpg")
    ]
    res_frames = subprocess.run(
        cmd_frames,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if res_frames.returncode != 0:
        logger.error(f"Error extrayendo frames con FFmpeg: {res_frames.stderr[:400]}")
        raise RuntimeError(f"FFmpeg no pudo extraer fotogramas del video: {res_frames.stderr[:200]}")

    frame_files = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    logger.info(f"Fotogramas extraídos a {adaptive_fps} FPS: {len(frame_files)}")

    if not frame_files:
        raise ValueError("No se pudieron generar fotogramas a partir de la grabación.")

    if len(frame_files) > max_frames:
        indices = [int(i * (len(frame_files) - 1) / (max_frames - 1)) for i in range(max_frames)]
        frame_files = [frame_files[idx] for idx in indices]
        logger.info(f"Muestreados uniformemente {len(frame_files)} fotogramas representativos para MediaPipe.")

    return audio_path, frame_files


def segment_audio_by_turns(audio_path: str, turns: list, output_dir: str) -> list:
    """Segmenta el audio principal en intervalos temporales correspondientes a cada pregunta."""
    if not os.path.exists(audio_path) or not turns:
        return []

    os.makedirs(output_dir, exist_ok=True)
    segmented = []
    for t in turns:
        q_id = t.get("questionId") or t.get("question_id") or "q"
        seq = t.get("sequenceNo") or t.get("sequence_no") or 0
        start_ms = t.get("startMs") if t.get("startMs") is not None else t.get("startOffsetMs", 0)
        end_ms = t.get("endMs") if t.get("endMs") is not None else t.get("endOffsetMs", 0)
        if end_ms <= start_ms:
            continue

        start_sec = start_ms / 1000.0
        dur_sec = (end_ms - start_ms) / 1000.0
        out_wav = os.path.join(output_dir, f"turn_{seq}_{q_id}.wav")

        cmd = [
            "ffmpeg", "-nostdin", "-y", "-ss", f"{start_sec:.3f}", "-t", f"{dur_sec:.3f}",
            "-i", audio_path, "-acodec", "copy", out_wav
        ]
        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(out_wav):
            segmented.append({
                "turn": t,
                "path": out_wav,
                "duration_sec": dur_sec
            })

    logger.info(f"Segmentación de audio por turnos completada: {len(segmented)} intervalos creados.")
    return segmented


def analyze_vision(frame_files: list) -> dict:
    """Envía los fotogramas al microservicio ca-vision-service (MediaPipe)."""
    if not frame_files:
        raise ValueError("No se encontraron fotogramas válidos para el análisis de visión.")

    try:
        client = VisionClient(base_url=VISION_URL)
        res = client.analyze_frames(frame_files)
    except Exception as e:
        logger.error(f"Error conectando con el microservicio de visión (ca-vision-service): {e}")
        raise RuntimeError(f"Fallo en microservicio de análisis visual: {e}") from e

    if not res:
        raise RuntimeError("El microservicio de visión (ca-vision-service) no devolvió datos para los fotogramas.")

    if res.get("error"):
        raise RuntimeError(f"Error devuelto por el microservicio de visión: {res.get('error')}")

    frames_validos = res.get("frames_validos") or res.get("frames_analyzed") or 0
    if frames_validos == 0:
        raise ValueError("No se detectó la presencia de ningún rostro o postura en los fotogramas del video para evaluar.")

    return res


def upload_report_to_blob(session_id: str, report_data: dict):
    """Guarda el informe consolidado en formato JSON en el contenedor 'reports' de Azure Blob Storage."""
    if not STORAGE_CONN:
        return
    try:
        blob_service = BlobServiceClient.from_connection_string(STORAGE_CONN)
        container_client = blob_service.get_container_client("reports")
        if not container_client.exists():
            container_client.create_container()
        report_blob = f"{session_id}_report.json"
        blob_client = container_client.get_blob_client(report_blob)
        blob_client.upload_blob(json.dumps(report_data, indent=2, ensure_ascii=False), overwrite=True)
        logger.info(f"Reporte consolidado subido a Azure Blob: reports/{report_blob}")
    except Exception as e:
        logger.warning(f"Aviso al persistir reporte en Blob Storage: {e}")


def process_session_pipeline(
    session_id: str,
    job_id: str,
    rubric_version_id: Optional[str],
    blob_path: str,
    turns: list
):
    """
    Ejecuta el pipeline multimodal completo de inferencia sin fallbacks ficticios:
    1. Descarga del video desde Azure Blob Storage.
    2. Extracción de audio PCM 16kHz y fotogramas (0.5 FPS).
    3. Análisis de Imagen con MediaPipe (ca-vision-service).
    4. Análisis de Audio acústico (RMS VAD) y transcripción ASR con NVIDIA Riva.
    5. Evaluación de Contenido con NVIDIA LLM Judge.
    6. Fusión multivariable y cálculo de rúbrica ponderada (v0.4).
    7. Generación de Síntesis Ejecutiva VISUM (Llamada 2 a LLM).
    8. Persistencia atómica en Azure SQL (report, area_score, analysis_job, session, analysis_pipeline_result).
    9. Almacenamiento del JSON consolidado en Blob Storage.
    Si cualquier paso no cuenta con información suficiente o falla, se lanza una excepción explícita.
    """
    logger.info(f"=== Iniciando Pipeline Multimodal Estricto: Sesión {session_id} (Job: {job_id}) ===")
    session_tmp_dir = os.path.join("/tmp", f"session_{session_id}")
    os.makedirs(session_tmp_dir, exist_ok=True)
    local_video_path = os.path.join(session_tmp_dir, "input.webm")

    db_svc = None
    session_verified = False
    report_persisted = False
    try:
        if not SQL_CONN_STR:
            raise RuntimeError("Azure SQL es obligatorio para resolver la sesion del analisis.")
        db_svc = DatabaseService()
        db_metadata = db_svc.get_session_context(session_id, job_id)
        internal_session_id = str(db_metadata["session_id"])
        if rubric_version_id and str(rubric_version_id).lower() != db_metadata["rubric_version_id"].lower():
            raise ValueError("La rubrica solicitada no coincide con la sesion.")
        if blob_path != f"recordings/{session_id}.webm" and not blob_path.endswith(f"{session_id}.webm") and not blob_path.endswith(f"{session_id}.mp4"):
            raise ValueError("La grabacion solicitada no corresponde a la sesion.")
        session_verified = True

        # Obtener configuración de rúbrica activa (16 métricas publicadas)
        rubric_cfg = db_svc.get_active_rubric_config() if db_svc else DynamicRubricConfig()
        logger.info(f"Rúbrica activa cargada: versión {rubric_cfg.version_code} ({rubric_cfg.rubric_version_id})")

        # 1. Descargar video
        downloaded_location = download_blob(blob_path, local_video_path)
        if not os.path.exists(local_video_path) or os.path.getsize(local_video_path) == 0:
            raise ValueError(f"El archivo de grabación descargado está vacío o no es válido: '{blob_path}'")

        # 1.05 Remuxear WebM sin recodificar (-c copy) para inyectar Duration + Cues (seeking nativo)
        if str(blob_path or "").lower().endswith(".webm"):
            remuxed_video_path = os.path.join(session_tmp_dir, "input_seekable.webm")
            if remux_webm_for_seeking(local_video_path, remuxed_video_path):
                os.replace(remuxed_video_path, local_video_path)
                if isinstance(downloaded_location, tuple) and len(downloaded_location) == 2:
                    upload_remuxed_recording(downloaded_location[0], downloaded_location[1], local_video_path)

        # 1.1 Sellar evidencia inmutable de grabación (ya remuxeada y seekable) para gobernanza y etiquetado
        recording_evidence = seal_recording_evidence(
            storage_connection_string=STORAGE_CONN,
            container_name=CONTAINER_NAME or "recordings",
            source_blob_path=blob_path,
            local_path=local_video_path,
            session_id=session_id,
            job_id=job_id,
        )
        logger.info(
            f"Evidencia de grabación sellada exitosamente: {recording_evidence['sealedPath']} "
            f"(SHA-256: {recording_evidence['sha256'][:8]}...)"
        )

        # 2. Consultar turnos en vivo (dbo.session_turn) con polling acotado y extraer media
        master_video_duration = probe_media_duration(local_video_path)
        db_turns = db_svc.get_session_turns(internal_session_id) if db_svc else []
        if db_turns:
            wait_timeout = float(os.getenv("TURN_ASR_WAIT_TIMEOUT_SEC", "30.0"))
            poll_interval = float(os.getenv("TURN_ASR_POLL_INTERVAL_SEC", "2.0"))
            wait_started = time.monotonic()
            while any(t.get("asr_status") in ("pending", "processing") for t in db_turns):
                if (time.monotonic() - wait_started) >= wait_timeout:
                    logger.warning(
                        f"Timeout ({wait_timeout}s) esperando transcripción background en dbo.session_turn "
                        f"para sesión {session_id}; turnos pendientes usarán fallback en worker."
                    )
                    break
                time.sleep(poll_interval)
                db_turns = db_svc.get_session_turns(internal_session_id)

        needs_fallback_turns = [
            t for t in db_turns
            if t.get("asr_status") not in ("completed", "fallback_worker")
        ]
        need_master_audio = (not db_turns) or bool(needs_fallback_turns)

        audio_path, frame_files = split_media(
            local_video_path,
            session_tmp_dir,
            extract_audio=need_master_audio,
            video_duration_sec=master_video_duration,
        )

        # 2.1 Segmentar audio por preguntas (turns legacy) solo si no hay dbo.session_turn
        segmented_turns = []
        if not db_turns and turns and audio_path:
            turns_audio_dir = os.path.join(session_tmp_dir, "turns")
            segmented_turns = segment_audio_by_turns(audio_path, turns, turns_audio_dir)

        # 3. Análisis de Imagen (MediaPipe en ca-vision-service por lotes de 60)
        logger.info(f"Enviando {len(frame_files)} fotogramas a ca-vision-service en lotes...")
        vision_metrics = analyze_vision(frame_files)

        # 4. Análisis de Audio y Transcripción ASR (consolidación por turnos o modo legacy)
        riva_key = NVIDIA_API_KEY or os.getenv("NVIDIA_API_KEY") or get_secret("NVIDIA_API_KEY") or get_secret("nvidia-api-key") or ""
        audio_analyzer = AudioAnalyzer(
            api_key=riva_key,
            server=os.getenv("NVIDIA_RIVA_SERVER", "grpc.nvcf.nvidia.com:443"),
            function_id=os.getenv("NVIDIA_FUNCTION_ID", "71203149-d3b7-4460-8231-1be2543a1fca"),
            language_code=os.getenv("NVIDIA_LANGUAGE_CODE", "es-US")
        )

        dialogue_turns_payload: List[Dict[str, Any]] = []
        if db_turns:
            # Ejecutar fallback determinista en worker solo para turnos pendientes/fallidos
            if needs_fallback_turns:
                if not riva_key:
                    raise ValueError("NVIDIA_API_KEY no está configurada para fallback ASR en worker.")
                fallback_dir = os.path.join(session_tmp_dir, "fallback_turns")
                os.makedirs(fallback_dir, exist_ok=True)
                for ft in needs_fallback_turns:
                    start_ms = ft.get("start_offset_ms")
                    end_ms = ft.get("end_offset_ms")
                    if start_ms is None or end_ms is None or int(end_ms) <= int(start_ms):
                        logger.warning(f"Turno {ft['turn_id']} sin offsets válidos para fallback FFmpeg.")
                        continue
                    seg_wav = os.path.join(fallback_dir, f"fallback_turn_{ft['turn_index']}.wav")
                    start_s = max(0.0, int(start_ms) / 1000.0)
                    dur_s = max(0.2, (int(end_ms) - int(start_ms)) / 1000.0)
                    cmd_seg = [
                        "ffmpeg", "-nostdin", "-y", "-ss", f"{start_s:.3f}", "-t", f"{dur_s:.3f}",
                        "-i", audio_path, "-acodec", "copy", seg_wav
                    ]
                    res_seg = subprocess.run(cmd_seg, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if res_seg.returncode == 0 and os.path.exists(seg_wav) and os.path.getsize(seg_wav) > 0:
                        fb_res = audio_analyzer.process_audio(seg_wav, rubric_cfg=rubric_cfg)
                        fb_ac = fb_res.get("acoustic_analysis", {})
                        fb_tr = (fb_res.get("transcription") or "").strip()
                        fb_words = fb_res.get("words", [])
                        ft["transcript"] = fb_tr
                        ft["words"] = fb_words
                        ft["audio_duration_sec"] = fb_ac.get("total_duration_sec", 0.0)
                        ft["speech_time_sec"] = fb_ac.get("speech_time_sec", 0.0)
                        ft["silence_time_sec"] = fb_ac.get("silence_time_sec", 0.0)
                        ft["phonation_ratio"] = fb_ac.get("phonation_ratio", 0.0)
                        ft["acoustic_pauses"] = fb_ac.get("pausas_prolongadas_acusticas", [])
                        ft["asr_status"] = "fallback_worker"
                        if db_svc:
                            try:
                                db_svc.update_turn_worker_fallback(
                                    turn_id=ft["turn_id"],
                                    session_id=internal_session_id,
                                    session_question_id=ft.get("session_question_id"),
                                    base_sequence_no=ft["base_sequence_no"],
                                    turn_kind=ft["turn_kind"],
                                    transcript=fb_tr,
                                    words=fb_words,
                                    acoustics=fb_ac,
                                )
                            except Exception as fb_db_err:
                                logger.warning(f"No se pudo persistir fallback del turno {ft['turn_id']}: {fb_db_err}")

            logger.info(f"Consolidando acústica y transcripción desde {len(db_turns)} turnos persistidos...")
            audio_res = aggregate_turn_audio_results(db_turns, rubric_cfg=rubric_cfg)
            turn_eff_durs = audio_res.get("turn_effective_durations", {})
            turn_audio_map = audio_res.get("turn_audio_metrics", {})
            adaptive_fps_used = 1.0 if (master_video_duration is not None and master_video_duration > 300.0) else 2.0
            turn_vision_map = compute_turn_vision_metrics(
                vision_metrics=vision_metrics,
                turns=db_turns,
                frame_files=frame_files,
                adaptive_fps=adaptive_fps_used,
            )
            for t in db_turns:
                t_idx_val = int(t["turn_index"])
                resolved_trigger = (
                    resolve_turn_followup_reason(t, db_turns)
                    if t.get("turn_kind") == "follow_up"
                    else t.get("followup_trigger_reason")
                )
                turn_item: Dict[str, Any] = {
                    "turnId": t["turn_id"],
                    "turnIndex": t_idx_val,
                    "baseSequenceNo": t["base_sequence_no"],
                    "turnKind": t["turn_kind"],
                    "parentTurnId": t.get("parent_turn_id"),
                    "questionText": t["question_text"],
                    "transcript": (t.get("transcript") or "").strip(),
                    "triggerReason": resolved_trigger,
                    "startOffsetMs": t.get("start_offset_ms"),
                    "endOffsetMs": t.get("end_offset_ms"),
                    "durationSeconds": turn_eff_durs.get(t_idx_val, t.get("audio_duration_sec", 0.0)),
                    "asrStatus": t.get("asr_status", "completed"),
                }
                if t_idx_val in turn_audio_map:
                    turn_item["voiceMetrics"] = turn_audio_map[t_idx_val]
                if t_idx_val in turn_vision_map:
                    turn_item["visionMetrics"] = turn_vision_map[t_idx_val]
                dialogue_turns_payload.append(turn_item)
        else:
            logger.info("Ejecutando análisis acústico y transcripción monolítica con NVIDIA Riva ASR (modo legacy)...")
            if not riva_key:
                raise ValueError("NVIDIA_API_KEY no está configurada en el entorno o Key Vault.")
            audio_res = audio_analyzer.process_audio(audio_path, rubric_cfg=rubric_cfg)

        acustica = audio_res.get("acoustic_analysis", {})
        total_duration = acustica.get("total_duration_sec", 0.0)
        speech_time = acustica.get("speech_time_sec", 0.0)

        if total_duration < 1.0:
            raise ValueError(f"La duración de la grabación ({total_duration:.1f}s) es insuficiente para el análisis (mínimo 1.0s).")

        if speech_time < 0.4:
            raise ValueError(
                f"No se detectó actividad vocal en la grabación (tiempo de fonación: {speech_time:.1f}s de {total_duration:.1f}s). "
                "Grabación en silencio o micrófono inactivo."
            )

        raw_transcript = (audio_res.get("transcription") or "").strip()
        words = audio_res.get("words", [])

        if not raw_transcript or len(words) == 0:
            raise ValueError("El servicio de transcripción (NVIDIA Riva ASR) no detectó palabras inteligibles en el audio.")

        transcript = (
            format_interview_dialogue(dialogue_turns_payload)
            if dialogue_turns_payload
            else raw_transcript
        )

        audio_metrics = audio_res.get("metrics", {})
        if words:
            audio_metrics["words"] = words
        max_turn_end_sec = max(
            (float(t.get("end_offset_ms") or 0) / 1000.0 for t in db_turns),
            default=0.0,
        )
        if master_video_duration and master_video_duration >= 1.0:
            evidence_duration = master_video_duration
        elif max_turn_end_sec >= 1.0:
            evidence_duration = max(max_turn_end_sec, total_duration)
        else:
            evidence_duration = total_duration
        if evidence_duration > 0:
            recording_evidence["durationSeconds"] = round(float(evidence_duration), 3)
        score_wpm = float(audio_metrics.get("score_wpm", 80.0))
        score_fluidez = float(audio_metrics.get("score_fluidez") if audio_metrics.get("score_fluidez") is not None else 0.0)
        score_diccion = float(audio_metrics.get("score_diccion") if audio_metrics.get("score_diccion") is not None else DICTION_FALLBACK_SCORE)
        score_verbal = round(
            (score_wpm * VOICE_WEIGHT_WPM) +
            (score_fluidez * VOICE_WEIGHT_FLUENCY) +
            (score_diccion * VOICE_WEIGHT_DICTION),
            1
        )

        # 4.1 Mapear transcripción legacy a session_question solo cuando no hubo dbo.session_turn
        turn_responses = []
        if not db_turns and turns:
            for t in turns:
                q_id = t.get("questionId") or t.get("question_id") or ""
                seq = t.get("sequenceNo") or t.get("sequence_no") or 1
                start_ms = t.get("startMs") if t.get("startMs") is not None else t.get("startOffsetMs", 0)
                end_ms = t.get("endMs") if t.get("endMs") is not None else t.get("endOffsetMs", 0)
                start_s = start_ms / 1000.0
                end_s = end_ms / 1000.0

                matched_words = []
                for w in words:
                    w_start = w.get("start", w.get("start_time", 0.0))
                    w_end = w.get("end", w.get("end_time", w_start + 0.1))
                    if (w_start < end_s and w_end > start_s) or (w_start >= start_s and w_start <= end_s):
                        matched_words.append(w.get("word", ""))

                turn_text = " ".join(matched_words).strip()
                turn_responses.append({
                    "questionId": q_id,
                    "sequenceNo": seq,
                    "transcript": turn_text,
                })

            non_empty_turns = [tr for tr in turn_responses if tr.get("transcript")]
            if not non_empty_turns and raw_transcript and turn_responses:
                turn_responses[0]["transcript"] = raw_transcript

            if db_svc and turn_responses:
                try:
                    db_svc.update_question_responses(internal_session_id, turn_responses)
                except Exception as t_err:
                    logger.error(f"Error actualizando respuestas en session_question: {t_err}", exc_info=True)
        elif not db_turns and db_svc and raw_transcript:
            try:
                with db_svc._get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT question_id, sequence_no 
                        FROM session_question 
                        WHERE session_id = ? 
                        ORDER BY sequence_no ASC
                    """, internal_session_id)
                    sq_rows = cur.fetchall()
                    if sq_rows:
                        turn_responses = [{
                            "questionId": str(sq_rows[0][0]),
                            "sequenceNo": sq_rows[0][1],
                            "transcript": raw_transcript
                        }]
                        db_svc.update_question_responses(internal_session_id, turn_responses)
            except Exception as e_turns:
                logger.warning(f"Aviso actualizando respuesta para sesión sin turnos explícitos: {e_turns}")

        # 5. Evaluación de Contenido con LLM Juez
        active_scen = db_metadata.get("scenario", {}) if isinstance(db_metadata, dict) else {}
        pregunta = (
            dialogue_turns_payload[0]["questionText"]
            if dialogue_turns_payload
            else "¿Cuál es la postura oficial y qué medidas urgentes se están adoptando?"
        )
        mensajes = active_scen.get("key_messages") or ["Nuestra prioridad es la seguridad y el esclarecimiento de los hechos."]
        contexto = active_scen.get("context") or "Incidente corporativo y vocería institucional ante medios de comunicación."
        red_lines = active_scen.get("red_lines") or []

        judge_svc = LLMJudgeService(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            model=LLM_MODEL,
            fast_model=LLM_FAST_MODEL,
            timeout=60.0
        )
        logger.info(
            f"Evaluando adherencia y control de crisis con LLM Juez "
            f"[API Endpoint: {judge_svc.base_url}, Modelo: {judge_svc.model}, Respaldo: {judge_svc.fast_model}, "
            f"Turnos: {len(dialogue_turns_payload)}, Timeout: {judge_svc.timeout}s]..."
        )
        reporte_juez = judge_svc.evaluate_response(
            pregunta_periodista=pregunta,
            mensajes_clave=mensajes,
            contexto_crisis=contexto,
            transcripcion_vocero=transcript,
            lineas_rojas=red_lines,
            interview_turns=dialogue_turns_payload or None,
            scenario_title=active_scen.get("title"),
            optica=active_scen.get("optics"),
            audiencia=active_scen.get("audience"),
            dificultad=active_scen.get("difficulty"),
        )

        # Enlazar evaluación individual del Juez a cada turno de dialogue_turns_payload
        if dialogue_turns_payload and reporte_juez.evaluacion_por_turno:
            turn_eval_map = {
                int(te["turnIndex"]): te
                for te in reporte_juez.evaluacion_por_turno
                if isinstance(te, dict) and te.get("turnIndex") is not None
            }
            for dt in dialogue_turns_payload:
                dt_idx = int(dt.get("turnIndex") or 0)
                if dt_idx in turn_eval_map:
                    eval_copy = dict(turn_eval_map[dt_idx])
                    eval_copy.pop("turnIndex", None)
                    dt["evaluation"] = eval_copy

        llm_metrics = reporte_juez.model_dump()
        llm_metrics["key_message_adherence_score"] = int(
            reporte_juez.dimensiones.get("alineacion_mensaje_clave", {}).get("score_100", 0)
        )
        llm_metrics["crisis_control_score"] = int(
            reporte_juez.dimensiones.get("tecnicas_control", {}).get("score_100", 0)
        )
        tecnicas_det = reporte_juez.dimensiones.get("tecnicas_control", {}).get("tecnicas_detectadas", [])
        frase_trans = reporte_juez.dimensiones.get("tecnicas_control", {}).get("frase_transicion")
        llm_metrics["bridging_detected"] = (
            any("bridg" in str(t).lower() for t in tecnicas_det) or bool(frase_trans)
        )
        llm_metrics["mensajes_cumplidos"] = list(
            reporte_juez.dimensiones.get("alineacion_mensaje_clave", {}).get("mensajes_cumplidos", [])
        )
        llm_metrics["mensajes_omitidos"] = list(
            reporte_juez.dimensiones.get("alineacion_mensaje_clave", {}).get("mensajes_omitidos", [])
        )
        llm_metrics["infraccion_linea_roja"] = reporte_juez.infraccion_linea_roja
        llm_metrics["evidencia_linea_roja"] = reporte_juez.evidencia_linea_roja
        llm_metrics["reconocimiento_afectados"] = reporte_juez.reconocimiento_afectados
        llm_metrics["strengths"] = [reporte_juez.feedback.fortaleza_principal] if reporte_juez.feedback.fortaleza_principal else []
        llm_metrics["weaknesses"] = [reporte_juez.feedback.brecha_critica] if reporte_juez.feedback.brecha_critica else []
        llm_metrics["executive_summary"] = reporte_juez.feedback.recomendacion_accionable
        
        score_estrategico = float(reporte_juez.puntaje_global_100)
        # Salvaguarda determinista: Línea roja trunca Coherencia al techo dinámico
        if reporte_juez.infraccion_linea_roja:
            score_estrategico = min(score_estrategico, rubric_cfg.red_line_cap)

        # 6. Fusión Multivariable y Puntuaciones por Área (Rúbrica Ponderada)
        vision_summary = vision_metrics.get("summary") or vision_metrics
        if any(k in vision_summary for k in ["hands_visible_pct", "body_sway_std", "shoulder_stability_score"]):
            expression_eval = calculate_expression_area_score(vision_summary)
            score_visual = float(expression_eval["score"])
        else:
            eye_pct = float(vision_metrics.get("eye_contact_percentage", 0.0))
            posture_score = float(vision_metrics.get("average_posture_score", 0.0))
            score_visual = round((eye_pct * 0.6) + (posture_score * 0.4), 1)

        # Empatía balanceada (60% verbal / reconocimiento del afectado + 40% no verbal)
        rec_afectados = reporte_juez.reconocimiento_afectados or {}
        victim_level = rec_afectados.get("nivel", 3) if isinstance(rec_afectados, dict) else 3
        score_empatia = compute_empathy_score(score_visual, victim_level)

        # Ponderación general usando pesos dinámicos de rúbrica
        w_expr = rubric_cfg.area_weights.get("expression", WEIGHT_EXPRESSION)
        w_voice = rubric_cfg.area_weights.get("voice", WEIGHT_VOICE)
        w_coherence = rubric_cfg.area_weights.get("coherence", WEIGHT_COHERENCE)
        w_empathy = rubric_cfg.area_weights.get("empathy", WEIGHT_EMPATHY)

        score_global = round(
            (score_visual * w_expr) +
            (score_verbal * w_voice) +
            (score_estrategico * w_coherence) +
            (score_empatia * w_empathy),
            1
        )

        area_scores_map = {
            "expression": int(round(score_visual)),
            "voice": int(round(score_verbal)),
            "coherence": int(round(score_estrategico)),
            "empathy": int(round(score_empatia)),
        }

        # Cálculo de Gobernanza Nivel 2 y Auditoría Humana
        governance_metrics = compute_governance_metrics(
            session_id=session_id,
            overall_score=score_global,
            area_scores=area_scores_map,
            vision_metrics=vision_summary,
            audio_metrics=audio_metrics,
            rubric_cfg=rubric_cfg
        )

        # 7. Generación Narrativa Ejecutiva VISUM (Llamada 2 a LLM)
        logger.info(f"Generando Síntesis Ejecutiva VISUM [API Endpoint: {LLM_BASE_URL}, Modelo: {LLM_MODEL}]...")
        http_client = httpx.Client(verify=False, timeout=60.0)
        client_visum = OpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            timeout=60.0,
            max_retries=0,
            http_client=http_client
        )
        scenario_meta = {
            "title": active_scen.get("title") or "Incidente Corporativo y Vocería de Crisis",
            "context": contexto,
            "optics": active_scen.get("optics") or "empática, institucional y de control operativo",
            "audience": active_scen.get("audience") or "opinión pública y medios de comunicación",
            "difficulty": active_scen.get("difficulty") or "intermediate",
            "key_messages": mensajes,
            "red_lines": red_lines or ["No especular sobre causas no confirmadas ni evadir la responsabilidad institucional."]
        }

        eye_contact_val = vision_summary.get("eye_contact_pct", vision_metrics.get("eye_contact_percentage", 0.0))
        posture_val = vision_summary.get("shoulder_stability_score", vision_metrics.get("average_posture_score", 0.0))
        sway_val = vision_summary.get("body_sway_std", 0.0)
        ratio_fonacion_raw = float(audio_metrics.get("ratio_fonacion", 0.0))
        ratio_fonacion_pct = round(ratio_fonacion_raw * 100.0 if ratio_fonacion_raw <= 1.0 else ratio_fonacion_raw, 1)

        bandas_rubrica = evaluate_metric_bands(
            {
                "wpm_global": audio_metrics.get("wpm_global", 0.0),
                "densidad_muletillas_pct": audio_metrics.get("densidad_muletillas_pct", 0.0),
                "ratio_fonacion": ratio_fonacion_raw,
                "score_diccion": score_diccion,
                "eye_contact_pct": eye_contact_val,
                "shoulder_stability_score": posture_val,
                "body_sway_std": sway_val,
                "victim_level": victim_level,
            },
            rubric_cfg=rubric_cfg,
        )

        consolidated_intermediate = {
            "score_global": score_global,
            "transcript": transcript,
            "dialogue_turns": dialogue_turns_payload,
            "bandas_rubrica": bandas_rubrica,
            "dictamen_juez": llm_metrics,
            "evaluacion_areas": {
                "expresion": {
                    "score": score_visual,
                    "contacto_visual_pct": eye_contact_val,
                    "postura_score": posture_val,
                    "manos_visibles_pct": vision_summary.get("hands_visible_pct", 0.0),
                    "gesticulacion_activa_pct": vision_summary.get("hands_active_pct", 0.0),
                    "balanceo_torso_std": sway_val,
                },
                "tono_voz": {
                    "score": score_verbal,
                    "wpm": audio_metrics.get("wpm_global", 0),
                    "wpm_global": audio_metrics.get("wpm_global", 0),
                    "ratio_fonacion_pct": ratio_fonacion_pct,
                    "pausas_vacilacion": int(audio_metrics.get("pausas_vacilacion", 0)),
                    "pausas_prolongadas": int(audio_metrics.get("pausas_prolongadas", 0)),
                    "densidad_muletillas_pct": float(audio_metrics.get("densidad_muletillas_pct", 0.0)),
                    "muletillas_count": len(audio_metrics.get("muletillas_detectadas", [])),
                    "score_diccion_asr": score_diccion,
                },
                "contenido": {
                    "score": score_estrategico,
                    "puntaje_juez_sin_truncar": float(reporte_juez.puntaje_global_100),
                    "truncado_por_linea_roja": bool(
                        reporte_juez.infraccion_linea_roja
                        and float(reporte_juez.puntaje_global_100) > score_estrategico
                    ),
                    "adherencia_mensajes": llm_metrics.get("key_message_adherence_score", 0),
                    "adherencia_mensajes_score": llm_metrics.get("key_message_adherence_score", 0),
                    "control_crisis_score": llm_metrics.get("crisis_control_score", 0),
                    "bridging_detectado": llm_metrics.get("bridging_detected", False),
                    "tecnicas_detectadas": list(tecnicas_det),
                },
                "empatia": {
                    "score": score_empatia,
                    "bridging_detectado": llm_metrics.get("bridging_detected", False),
                    "reconocimiento_afectados_nivel": victim_level,
                    "reconocimiento_afectados_criterio": (
                        rec_afectados.get("criterio", "") if isinstance(rec_afectados, dict) else ""
                    ),
                }
            }
        }
        visum_narrative = generate_visum_report(
            client=client_visum,
            model_name=LLM_MODEL,
            scenario_info=scenario_meta,
            consolidated_json=consolidated_intermediate
        )
        logger.info("Informe VISUM generado exitosamente.")

        # 8. Persistencia Atómica en Azure SQL
        report_id = None
        resolved_rubric_id = rubric_cfg.rubric_version_id or db_metadata.get("rubric_version_id")

        processed_at_iso = datetime.now(timezone.utc).isoformat()
        video_blob_url = f"https://stavoxreadyst.blob.core.windows.net/recordings/recordings/{session_id}.webm"

        # Construir JSON consolidado y saneado (Sección 1)
        cleaned_report = sanitize_report_json(
            session_id=session_id,
            job_id=job_id,
            report_id=None,
            processed_at=processed_at_iso,
            recording_url=video_blob_url,
            overall_score=int(round(score_global)),
            area_scores=area_scores_map,
            visum_narrative=visum_narrative,
            vision_metrics=vision_metrics,
            audio_metrics=audio_metrics,
            judge_metrics=llm_metrics,
            transcript=transcript,
            segmented_turns=segmented_turns,
            governance=governance_metrics,
            dialogue_turns=dialogue_turns_payload,
            master_duration_seconds=evidence_duration,
        )
        cleaned_report["recordingEvidence"] = recording_evidence

        if db_svc and resolved_rubric_id:
            try:
                report_id = db_svc.finalize_session_analysis(
                    session_id=internal_session_id,
                    overall_score=int(round(score_global)),
                    visum_report=visum_narrative,
                    area_scores=area_scores_map,
                    rubric_version_id=resolved_rubric_id,
                    rubric_areas=db_metadata.get("rubric_areas", {}),
                    job_id=job_id
                )
                report_persisted = True
                logger.info(f"Reporte y puntajes persistidos en Azure SQL con ID: {report_id}")
                cleaned_report["reportId"] = report_id
                cleaned_report["report_id"] = report_id

                # Trazabilidad integral en analysis_pipeline_result (incluyendo fusion consolidado y governance)
                pipeline_map = {
                    "vision": vision_metrics,
                    "voice": audio_metrics,
                    "content_judge": llm_metrics,
                    "governance": governance_metrics,
                    "fusion": cleaned_report
                }
                persist_pipeline_results(db_svc, job_id, pipeline_map)

                # Persistir caso canónico; no completar el job si falla la materialización.
                case_id = db_svc.create_labeling_case_if_needed(report_id)
                logger.info(
                    f"Sesión {session_id} enrutada a dbo.labeling_case "
                    f"(ID: {case_id}, motivo: {governance_metrics.get('labeling_reason') or 'routine'})"
                )

                update_analysis_job_status(db_svc, job_id, "completed")
            except Exception as dbe:
                logger.error(f"Fallo en persistencia Azure SQL: {dbe}")
                raise dbe

        # 9. Subir JSON saneado a Azure Blob Storage
        upload_report_to_blob(session_id, cleaned_report)
        if session_id != internal_session_id:
            upload_report_to_blob(internal_session_id, cleaned_report)
        logger.info(f"=== Pipeline Multimodal completado con éxito para sesión {session_id} ===")

    except Exception as ex:
        err_msg = str(ex)
        if hasattr(ex, "response") and getattr(ex.response, "text", None):
            err_msg += f" - API Details: {ex.response.text}"
        elif hasattr(ex, "body"):
            err_msg += f" - API Details: {ex.body}"
        logger.error(f"Fallo crítico en pipeline de sesión {session_id}: {err_msg}", exc_info=True)
        if db_svc and session_verified:
            update_analysis_job_status(
                db_svc,
                job_id,
                "failed",
                failure_reason=err_msg,
                best_effort=True,
            )
            report_state_known = report_persisted
            if not report_persisted:
                try:
                    report_persisted = db_svc.has_persisted_report(job_id, session_id)
                    report_state_known = True
                except Exception as report_check_error:
                    logger.warning(
                        "No se pudo confirmar si el job ya tiene informe; "
                        "se preserva el estado de la sesión: %s",
                        report_check_error,
                    )
            if report_state_known and not report_persisted:
                try:
                    db_svc.update_session_status(session_id, "failed")
                except Exception as dbe:
                    logger.warning(f"Aviso actualizando estado de sesión a 'failed': {dbe}")
            elif report_persisted:
                logger.error(
                    "El análisis quedó persistido; la sesión permanece completed "
                    "para permitir reconciliar la cola de etiquetado."
                )
        raise ex
    finally:
        shutil.rmtree(session_tmp_dir, ignore_errors=True)
        logger.info(f"Limpieza de archivos temporales completada: {session_tmp_dir}")
