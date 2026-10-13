import os
import re
import json
import glob
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
    from core.audio_analyzer import AudioAnalyzer
    from core.llm_judge import LLMJudgeService
    from core.narrative_generator import generate_visum_report
    from core.vision_client import VisionClient
    from core.report_builder import calculate_expression_area_score, sanitize_report_json
    from services.db_service import DatabaseService
except (ImportError, ValueError):
    from worker.core.audio_analyzer import AudioAnalyzer
    from worker.core.llm_judge import LLMJudgeService
    from worker.core.narrative_generator import generate_visum_report
    from worker.core.vision_client import VisionClient
    from worker.core.report_builder import calculate_expression_area_score, sanitize_report_json
    from worker.services.db_service import DatabaseService

logger = logging.getLogger("analysis-worker.orchestrator")

STORAGE_CONN = os.getenv("STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("STORAGE_CONTAINER_NAME") or os.getenv("BLOB_CONTAINER_NAME", "recordings")
NVIDIA_API_KEY = (os.getenv("NVIDIA_API_KEY") or "").strip()
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL_NAME", "meta/llama-3.2-11b-vision-instruct")
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
                return
        except Exception as e:
            last_error = e
            logger.warning(f"No se pudo descargar desde container='{cont}', blob='{b_name}': {e}")

    logger.error(f"Error crítico: Todas las rutas de descarga fallaron para '{blob_path}'. Candidatos probados: {unique_candidates}")
    raise last_error or RuntimeError(f"No se pudo descargar el blob: {blob_path}")


def split_media(video_path: str, session_tmp_dir: str):
    """Extrae audio PCM 16kHz y fotogramas muestreados a 0.5 FPS."""
    audio_path = os.path.join(session_tmp_dir, "audio.wav")
    frames_dir = os.path.join(session_tmp_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    # Extraer audio PCM 16kHz Mono
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

    # Extraer frames a 2 FPS (1 fotograma cada 500 ms según especificación técnica)
    cmd_frames = [
        "ffmpeg", "-nostdin", "-y", "-i", video_path,
        "-vf", "fps=2", "-q:v", "2", os.path.join(frames_dir, "frame_%04d.jpg")
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
    logger.info(f"Fotogramas extraídos a 2 FPS: {len(frame_files)}")

    if not frame_files:
        raise ValueError("No se pudieron generar fotogramas a partir de la grabación.")

    # Muestrear si la grabación es excesivamente larga para proteger tiempo de inferencia (< 60s)
    if len(frame_files) > 120:
        step = len(frame_files) // 120
        frame_files = frame_files[::step][:120]
        logger.info(f"Muestreados {len(frame_files)} fotogramas representativos para MediaPipe.")

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


def persist_pipeline_results(db_svc: DatabaseService, job_id: str, results_map: Dict[str, Any]):
    """Registra trazabilidad por pipeline en la tabla analysis_pipeline_result."""
    try:
        with db_svc._get_connection() as conn:
            cur = conn.cursor()
            for pipeline_name, result_data in results_map.items():
                cur.execute("""
                    INSERT INTO analysis_pipeline_result (
                        id, analysis_job_id, pipeline, status, summary_json, created_at, updated_at
                    )
                    VALUES (NEWID(), ?, ?, 'completed', ?, SYSUTCDATETIME(), SYSUTCDATETIME())
                """, (job_id, pipeline_name, json.dumps(result_data, ensure_ascii=False)))
            conn.commit()
            logger.info(f"Trazabilidad de pipelines persistida en analysis_pipeline_result para job {job_id}")
    except Exception as e:
        logger.warning(f"Aviso al guardar analysis_pipeline_result: {e}")


def update_analysis_job_status(db_svc: DatabaseService, job_id: str, status: str, failure_reason: Optional[str] = None):
    """Actualiza el estado de analysis_job a 'completed' o 'failed'."""
    try:
        with db_svc._get_connection() as conn:
            cur = conn.cursor()
            if status == "completed":
                cur.execute("""
                    UPDATE analysis_job
                    SET status = 'completed', completed_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
                    WHERE id = ?
                """, job_id)
            else:
                cur.execute("""
                    UPDATE analysis_job
                    SET status = 'failed', failure_reason = ?, updated_at = SYSUTCDATETIME()
                    WHERE id = ?
                """, (str(failure_reason)[:500] if failure_reason else None, job_id))
            conn.commit()
    except Exception as e:
        logger.warning(f"Aviso al actualizar analysis_job ({job_id}): {e}")


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
    try:
        if not SQL_CONN_STR:
            raise RuntimeError("Azure SQL es obligatorio para resolver la sesion del analisis.")
        db_svc = DatabaseService()
        db_metadata = db_svc.get_session_context(session_id, job_id)
        if rubric_version_id and str(rubric_version_id).lower() != db_metadata["rubric_version_id"].lower():
            raise ValueError("La rubrica solicitada no coincide con la sesion.")
        if blob_path != f"recordings/{session_id}.webm" and not blob_path.endswith(f"{session_id}.webm") and not blob_path.endswith(f"{session_id}.mp4"):
            raise ValueError("La grabacion solicitada no corresponde a la sesion.")
        session_verified = True

        # 1. Descargar video
        download_blob(blob_path, local_video_path)
        if not os.path.exists(local_video_path) or os.path.getsize(local_video_path) == 0:
            raise ValueError(f"El archivo de grabación descargado está vacío o no es válido: '{blob_path}'")

        # 2. Extraer audio y fotogramas
        audio_path, frame_files = split_media(local_video_path, session_tmp_dir)

        # 2.1 Segmentar audio por preguntas (turns) si fueron provistos
        segmented_turns = []
        if turns:
            turns_audio_dir = os.path.join(session_tmp_dir, "turns")
            segmented_turns = segment_audio_by_turns(audio_path, turns, turns_audio_dir)

        # 3. Análisis de Imagen (MediaPipe en ca-vision-service)
        logger.info("Enviando fotogramas a ca-vision-service...")
        vision_metrics = analyze_vision(frame_files)

        # 4. Análisis de Audio y Transcripción ASR (NVIDIA Riva + VAD RMS)
        logger.info("Ejecutando análisis acústico y transcripción de voz con NVIDIA Riva ASR...")
        if not NVIDIA_API_KEY:
            raise ValueError("NVIDIA_API_KEY no está configurada en el entorno.")

        audio_analyzer = AudioAnalyzer(
            api_key=NVIDIA_API_KEY,
            server=os.getenv("NVIDIA_RIVA_SERVER", "grpc.nvcf.nvidia.com:443"),
            function_id=os.getenv("NVIDIA_FUNCTION_ID", "71203149-d3b7-4460-8231-1be2543a1fca"),
            language_code=os.getenv("NVIDIA_LANGUAGE_CODE", "es-US")
        )
        audio_res = audio_analyzer.process_audio(audio_path)

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

        transcript = (audio_res.get("transcription") or "").strip()
        words = audio_res.get("words", [])

        if not transcript or len(words) == 0:
            raise ValueError("El servicio de transcripción (NVIDIA Riva ASR) no detectó palabras inteligibles en el audio.")

        audio_metrics = audio_res.get("metrics", {})
        score_fluidez = float(audio_metrics.get("score_fluidez") if audio_metrics.get("score_fluidez") is not None else 0.0)
        score_diccion = float(audio_metrics.get("score_diccion") if audio_metrics.get("score_diccion") is not None else 100.0)
        score_verbal = round((score_fluidez * 0.6) + (score_diccion * 0.4), 1)

        # 4.1 Mapear transcripción a cada turno/pregunta y persistir respuesta en session_question
        turn_responses = []
        if turns:
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

            # Si ningún turno capturó texto individual (o sólo hay 1 turno) pero hay transcripción global:
            non_empty_turns = [tr for tr in turn_responses if tr.get("transcript")]
            if not non_empty_turns and transcript and turn_responses:
                turn_responses[0]["transcript"] = transcript

            if db_svc and turn_responses:
                try:
                    db_svc.update_question_responses(session_id, turn_responses)
                except Exception as t_err:
                    logger.error(f"Error actualizando respuestas en session_question: {t_err}", exc_info=True)
        elif db_svc and transcript:
            try:
                with db_svc._get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT question_id, sequence_no 
                        FROM session_question 
                        WHERE session_id = ? 
                        ORDER BY sequence_no ASC
                    """, valid_session_uuid)
                    sq_rows = cur.fetchall()
                    if sq_rows:
                        turn_responses = [{
                            "questionId": str(sq_rows[0][0]),
                            "sequenceNo": sq_rows[0][1],
                            "transcript": transcript
                        }]
                        db_svc.update_question_responses(session_id, turn_responses)
            except Exception as e_turns:
                logger.warning(f"Aviso actualizando respuesta para sesión sin turnos explícitos: {e_turns}")

        # 5. Evaluación de Contenido con LLM Juez
        logger.info("Evaluando adherencia y control de crisis con LLM Juez (NVIDIA NIM)...")
        active_scen = db_metadata.get("scenario", {}) if isinstance(db_metadata, dict) else {}
        pregunta = "¿Cuál es la postura oficial y qué medidas urgentes se están adoptando?"
        mensajes = active_scen.get("key_messages") or ["Nuestra prioridad es la seguridad y el esclarecimiento de los hechos."]
        contexto = active_scen.get("context") or "Incidente corporativo y vocería institucional ante medios de comunicación."

        judge_svc = LLMJudgeService(
            api_key=NVIDIA_API_KEY,
            base_url=NVIDIA_BASE_URL,
            model=LLM_MODEL,
            timeout=120.0
        )
        reporte_juez = judge_svc.evaluate_response(
            pregunta_periodista=pregunta,
            mensajes_clave=mensajes,
            contexto_crisis=contexto,
            transcripcion_vocero=transcript
        )

        llm_metrics = reporte_juez.model_dump()
        llm_metrics["key_message_adherence_score"] = int(
            reporte_juez.dimensiones.get("alineacion_mensaje_clave", {}).get("score_100", 0)
        )
        llm_metrics["crisis_control_score"] = int(
            reporte_juez.dimensiones.get("tecnicas_control", {}).get("score_100", 0)
        )
        llm_metrics["bridging_detected"] = len(
            reporte_juez.dimensiones.get("tecnicas_control", {}).get("tecnicas_detectadas", [])
        ) > 0
        llm_metrics["strengths"] = [reporte_juez.feedback.fortaleza_principal] if reporte_juez.feedback.fortaleza_principal else []
        llm_metrics["weaknesses"] = [reporte_juez.feedback.brecha_critica] if reporte_juez.feedback.brecha_critica else []
        llm_metrics["executive_summary"] = reporte_juez.feedback.recomendacion_accionable
        score_estrategico = float(reporte_juez.puntaje_global_100)
        score_empatia = float(reporte_juez.dimensiones.get("asertividad_hostilidad", {}).get("score_100", 0.0))

        # 6. Fusión Multivariable y Puntuaciones por Área (Rúbrica Ponderada v0.4)
        vision_summary = vision_metrics.get("summary") or vision_metrics
        if any(k in vision_summary for k in ["hands_visible_pct", "body_sway_std", "shoulder_stability_score"]):
            expression_eval = calculate_expression_area_score(vision_summary)
            score_visual = float(expression_eval["score"])
        else:
            eye_pct = float(vision_metrics.get("eye_contact_percentage", 0.0))
            posture_score = float(vision_metrics.get("average_posture_score", 0.0))
            score_visual = round((eye_pct * 0.6) + (posture_score * 0.4), 1)

        # Ponderación general: Expresión 25%, Voz 25%, Coherencia/Contenido 35%, Empatía 15%
        score_global = round(
            (score_visual * 0.25) +
            (score_verbal * 0.25) +
            (score_estrategico * 0.35) +
            (score_empatia * 0.15),
            1
        )

        area_scores_map = {
            "expression": int(round(score_visual)),
            "voice": int(round(score_verbal)),
            "coherence": int(round(score_estrategico)),
            "empathy": int(round(score_empatia)),
        }

        # 7. Generación Narrativa Ejecutiva VISUM (Llamada 2 a LLM)
        logger.info("Generando Síntesis Ejecutiva VISUM con NVIDIA NIM...")
        http_client = httpx.Client(verify=False, timeout=120.0)
        client_visum = OpenAI(
            base_url=NVIDIA_BASE_URL.rstrip("/").rstrip("/chat/completions"),
            api_key=NVIDIA_API_KEY,
            timeout=120.0,
            http_client=http_client
        )
        scenario_meta = {
            "title": active_scen.get("title") or "Incidente Corporativo y Vocería de Crisis",
            "context": contexto,
            "optics": active_scen.get("optics") or "empática, institucional y de control operativo",
            "key_messages": mensajes,
            "red_lines": ["No especular sobre causas no confirmadas ni evadir la responsabilidad institucional."]
        }
        consolidated_intermediate = {
            "score_global": score_global,
            "transcript": transcript,
            "evaluacion_areas": {
                "expresion": {
                    "score": score_visual,
                    "contacto_visual_pct": vision_summary.get("eye_contact_pct", vision_metrics.get("eye_contact_percentage", 0.0)),
                    "postura_score": vision_summary.get("shoulder_stability_score", vision_metrics.get("average_posture_score", 0.0)),
                    "manos_visibles_pct": vision_summary.get("hands_visible_pct", 0.0),
                    "gesticulacion_activa_pct": vision_summary.get("hands_active_pct", 0.0),
                    "balanceo_torso_std": vision_summary.get("body_sway_std", 0.0),
                },
                "tono_voz": {
                    "score": score_verbal,
                    "wpm": audio_metrics.get("wpm_global", 0),
                    "muletillas_count": len(audio_metrics.get("muletillas_detectadas", []))
                },
                "contenido": {
                    "score": score_estrategico,
                    "adherencia_mensajes": llm_metrics.get("key_message_adherence_score", 0)
                },
                "empatia": {
                    "score": score_empatia,
                    "bridging_detectado": llm_metrics.get("bridging_detected", False)
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
        resolved_rubric_id = db_metadata["rubric_version_id"]

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
            segmented_turns=segmented_turns
        )

        if db_svc and resolved_rubric_id:
            try:
                report_id = db_svc.finalize_session_analysis(
                    session_id=session_id,
                    overall_score=int(round(score_global)),
                    visum_report=visum_narrative,
                    area_scores=area_scores_map,
                    rubric_version_id=resolved_rubric_id,
                    rubric_areas=db_metadata.get("rubric_areas", {}),
                    job_id=job_id
                )
                logger.info(f"Reporte y puntajes persistidos en Azure SQL con ID: {report_id}")
                cleaned_report["reportId"] = report_id
                cleaned_report["report_id"] = report_id

                # Trazabilidad integral en analysis_pipeline_result (incluyendo fusion consolidado)
                pipeline_map = {
                    "vision": vision_metrics,
                    "voice": audio_metrics,
                    "content_judge": llm_metrics,
                    "fusion": cleaned_report
                }
                persist_pipeline_results(db_svc, job_id, pipeline_map)
                update_analysis_job_status(db_svc, job_id, "completed")
            except Exception as dbe:
                logger.error(f"Fallo en persistencia Azure SQL: {dbe}")
                raise dbe

        # 9. Subir JSON saneado a Azure Blob Storage
        upload_report_to_blob(session_id, cleaned_report)
        logger.info(f"=== Pipeline Multimodal completado con éxito para sesión {session_id} ===")

    except Exception as ex:
        logger.error(f"Fallo crítico en pipeline de sesión {session_id}: {ex}", exc_info=True)
        if db_svc and session_verified:
            update_analysis_job_status(db_svc, job_id, "failed", failure_reason=str(ex))
            try:
                db_svc.update_session_status(session_id, "failed")
            except Exception as dbe:
                logger.warning(f"Aviso actualizando estado de sesión a 'failed': {dbe}")
        raise ex
    finally:
        shutil.rmtree(session_tmp_dir, ignore_errors=True)
        logger.info(f"Limpieza de archivos temporales completada: {session_tmp_dir}")
