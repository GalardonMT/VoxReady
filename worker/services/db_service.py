import os
import re
import time
import json
import uuid
import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple, List
try:
    from utils.logger import get_logger
    from services.keyvault_service import get_secret
    from config.scoring_rules import DynamicRubricConfig, DEFAULT_METRIC_THRESHOLDS
except (ImportError, ValueError):
    try:
        from worker.utils.logger import get_logger
        from worker.services.keyvault_service import get_secret
        from worker.config.scoring_rules import DynamicRubricConfig, DEFAULT_METRIC_THRESHOLDS
    except (ImportError, ValueError):
        from core.scoring_rules import DynamicRubricConfig, DEFAULT_METRIC_THRESHOLDS

logger = get_logger("services.db_service")



USER_AREA_PROGRESS_REFRESH_DML = """
;WITH target_actor AS (
    SELECT user_id,client_id
    FROM dbo.session
    WHERE id=? AND is_deleted=0
),
current_reports AS (
    SELECT r.id,r.session_id,
           ROW_NUMBER() OVER (
               PARTITION BY r.session_id
               ORDER BY r.generated_at DESC,r.id DESC
           ) AS report_position
    FROM dbo.report r
    JOIN dbo.session s ON s.id=r.session_id
    JOIN target_actor actor
      ON actor.user_id=s.user_id AND actor.client_id=s.client_id
    WHERE r.is_current=1 AND s.status='completed' AND s.is_deleted=0
),
ranked_area_scores AS (
    SELECT a.report_id,a.rubric_area_id,ra.area_key,a.value,
           ROW_NUMBER() OVER (
               PARTITION BY a.report_id,ra.area_key
               ORDER BY a.id DESC
           ) AS score_position
    FROM dbo.area_score a
    JOIN dbo.rubric_area ra ON ra.id=a.rubric_area_id
),
scored_sessions AS (
    SELECT s.user_id,a.rubric_area_id,a.area_key,a.value,
           COALESCE(s.finished_at,s.updated_at,s.created_at) AS session_at,
           ROW_NUMBER() OVER (
               PARTITION BY s.user_id,a.area_key
               ORDER BY COALESCE(s.finished_at,s.updated_at,s.created_at) DESC,s.id DESC
           ) AS area_position,
           LEAD(a.value) OVER (
               PARTITION BY s.user_id,a.area_key
               ORDER BY COALESCE(s.finished_at,s.updated_at,s.created_at) DESC,s.id DESC
           ) AS previous_value
    FROM dbo.session s
    JOIN target_actor actor
      ON actor.user_id=s.user_id AND actor.client_id=s.client_id
    JOIN current_reports r ON r.session_id=s.id AND r.report_position=1
    JOIN ranked_area_scores a ON a.report_id=r.id AND a.score_position=1
    WHERE s.status='completed' AND s.is_deleted=0
),
session_totals AS (
    SELECT s.user_id,COUNT_BIG(DISTINCT s.id) AS sessions_count,
           MAX(COALESCE(s.finished_at,s.updated_at,s.created_at)) AS last_session_at
    FROM dbo.session s
    JOIN target_actor actor
      ON actor.user_id=s.user_id AND actor.client_id=s.client_id
    WHERE s.status='completed' AND s.is_deleted=0
      AND EXISTS (
          SELECT 1 FROM current_reports r
          WHERE r.session_id=s.id AND r.report_position=1
      )
    GROUP BY s.user_id
),
latest AS (
    SELECT scored.user_id,scored.rubric_area_id,scored.value AS current_value,
           CASE WHEN scored.previous_value IS NULL THEN NULL
                ELSE scored.value-scored.previous_value END AS delta_value,
           CONVERT(INT,totals.sessions_count) AS sessions_count,
           totals.last_session_at
    FROM scored_sessions scored
    JOIN session_totals totals ON totals.user_id=scored.user_id
    WHERE scored.area_position=1
)
MERGE dbo.user_area_progress WITH (HOLDLOCK) AS target
USING latest AS source
   ON target.user_id=source.user_id
  AND target.rubric_area_id=source.rubric_area_id
WHEN MATCHED THEN UPDATE SET
    current_value=source.current_value,
    [delta]=source.delta_value,
    sessions_count=source.sessions_count,
    last_session_at=source.last_session_at,
    updated_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT (
    id,user_id,rubric_area_id,current_value,[delta],sessions_count,
    last_session_at,created_at,updated_at
) VALUES (
    NEWID(),source.user_id,source.rubric_area_id,source.current_value,
    source.delta_value,source.sessions_count,source.last_session_at,
    SYSUTCDATETIME(),SYSUTCDATETIME()
);
"""

LINKED_SCHEDULE_COMPLETE_DML = """
UPDATE sch
SET sch.status = 'completed', sch.updated_at = SYSUTCDATETIME()
FROM dbo.schedule sch
JOIN dbo.session s ON s.id = sch.session_id
WHERE sch.session_id = ?
  AND sch.user_id = s.user_id AND sch.client_id = s.client_id
  AND sch.status = 'scheduled'
"""


class DatabaseService:
    """
    Servicio de conexión resiliente para Azure SQL Serverless (sqldb-voxready).
    Implementa reintentos con retroceso exponencial (exponential backoff) para
    manejar el cold-start cuando la base de datos se encuentra auto-pausada.
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 15.0,
    ):
        self.connection_string = (
            connection_string
            or os.getenv("SQL_CONNECTION_STRING")
            or get_secret("SQL_CONNECTION_STRING")
            or os.getenv("DATABASE_URL")
            or get_secret("DATABASE_URL")
        )
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def _normalize_connection_string(self, conn_str: str) -> str:
        """
        Asegura que la cadena de conexión tenga el driver instalado compatible
        (ODBC Driver 18 en Linux / Docker, o fallback en Windows) y opciones seguras.
        """
        import pyodbc

        installed_drivers = pyodbc.drivers()
        preferred_drivers = [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server",
        ]
        chosen_driver = None
        for d in preferred_drivers:
            if d in installed_drivers:
                chosen_driver = d
                break

        if chosen_driver and "Driver={" in conn_str:
            conn_str = re.sub(r"Driver=\{[^}]+\}", f"Driver={{{chosen_driver}}}", conn_str, flags=re.IGNORECASE)
            if chosen_driver == "SQL Server":
                conn_str = re.sub(r";Encrypt=[^;]+", "", conn_str, flags=re.IGNORECASE)
                conn_str = re.sub(r";TrustServerCertificate=[^;]+", "", conn_str, flags=re.IGNORECASE)
        elif chosen_driver and "DRIVER=" not in conn_str.upper():
            conn_str = f"DRIVER={{{chosen_driver}}};{conn_str}"

        # Parámetros recomendados para Azure SQL si es Driver 18 o 17
        if chosen_driver != "SQL Server":
            if "Encrypt=" not in conn_str and "ENCRYPT=" not in conn_str:
                conn_str += ";Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"

        return conn_str

    def _get_connection(self):
        """
        Intenta conectar a Azure SQL con reintentos para tolerar el tiempo de
        despertar de Azure SQL Serverless (Auto-paused resume time: ~15 a 45s).
        """
        if not self.connection_string:
            raise ValueError(
                "No se encontró la cadena de conexión SQL_CONNECTION_STRING ni DATABASE_URL para Azure SQL."
            )

        try:
            import pyodbc
        except ImportError:
            raise ImportError(
                "El paquete 'pyodbc' es requerido para conectar a Azure SQL Serverless. "
                "Instálelo con 'pip install pyodbc'."
            )

        conn_str = self._normalize_connection_string(self.connection_string)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"Conectando a Azure SQL Serverless (intento {attempt}/{self.max_retries})..."
                )
                conn = pyodbc.connect(conn_str, timeout=30)
                logger.info("Conexión exitosa a Azure SQL Database.")
                return conn
            except pyodbc.Error as e:
                last_error = e
                error_msg = str(e)
                logger.warning(
                    f"Error al conectar con Azure SQL (intento {attempt}/{self.max_retries}): {error_msg}"
                )

                if attempt < self.max_retries:
                    sleep_time = self.retry_delay_seconds * (1.5 ** (attempt - 1))
                    logger.info(
                        f"Esperando {sleep_time:.1f}s para que Azure SQL despierte del estado Auto-paused..."
                    )
                    time.sleep(sleep_time)

        logger.error(
            f"No se pudo establecer conexión con Azure SQL tras {self.max_retries} intentos: {last_error}"
        )
        raise last_error

    def get_connection(self):
        """Alias público de _get_connection compatible con gestor de contexto with."""
        return self._get_connection()

    def get_session_context(self, session_id: str, job_id: str) -> Dict[str, Any]:
        """Carga solo la sesion y el job persistidos, con su escenario y rubrica."""
        if not session_id or not job_id:
            raise ValueError("La sesion y el job son obligatorios.")
        try:
            internal_id = str(uuid.UUID(str(session_id)))
        except (TypeError, ValueError, AttributeError):
            internal_id = None

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT s.id, s.client_id, s.user_id, s.scenario_id,
                       s.rubric_version_id, sc.title, t.context, t.optics,
                       t.audience, t.id, j.rubric_version_id, s.external_session_id
                FROM dbo.analysis_job j
                JOIN dbo.session s ON s.id = j.session_id
                JOIN dbo.app_user u ON u.id = s.user_id
                                   AND u.client_id = s.client_id
                                   AND (u.is_deleted IS NULL OR u.is_deleted = 0)
                JOIN dbo.scenario sc ON sc.id = s.scenario_id
                                     AND sc.client_id = s.client_id
                JOIN dbo.topic t ON t.id = sc.topic_id
                                AND (t.client_id IS NULL OR t.client_id = s.client_id)
                WHERE j.id = ? AND (s.external_session_id = ? OR s.id = ?)
                  AND s.is_deleted = 0 AND sc.is_deleted = 0 AND t.is_deleted = 0
            """, job_id, str(session_id), internal_id)
            row = cur.fetchone()
            if row is None:
                raise LookupError("Job o sesion no encontrada para este cliente.")
            if any(row[index] is None for index in (1, 2, 3, 4)):
                raise ValueError("La sesion carece de cliente, usuario, escenario o rubrica.")
            if row[10] is not None and str(row[10]).lower() != str(row[4]).lower():
                raise ValueError("La rubrica del job no coincide con la sesion.")

            cur.execute("""
                SELECT text FROM dbo.topic_key_message
                WHERE topic_id = ? AND status = 'active' ORDER BY sort_order
            """, row[9])
            key_messages = [message[0] for message in cur.fetchall()]

            red_lines = []
            try:
                cur.execute("""
                    SELECT text FROM dbo.topic_red_line
                    WHERE topic_id = ? AND (status IS NULL OR status = 'active')
                    ORDER BY sort_order ASC
                """, row[9])
                red_lines = [rl[0] for rl in cur.fetchall()]
            except Exception as ex_rl:
                logger.warning(f"Aviso al consultar dbo.topic_red_line, intentando fallback dbo.red_line: {ex_rl}")
                try:
                    cur.execute("""
                        SELECT text FROM dbo.red_line
                        WHERE topic_id = ? ORDER BY sort_order ASC
                    """, row[9])
                    red_lines = [rl[0] for rl in cur.fetchall()]
                except Exception:
                    red_lines = []

            cur.execute("""
                SELECT id, area_key, weight FROM dbo.rubric_area
                WHERE rubric_version_id = ?
            """, row[4])
            areas = {area[1]: {"id": str(area[0]), "weight": area[2]}
                     for area in cur.fetchall()}
            return {
                "session_id": str(row[0]),
                "external_session_id": row[11],
                "client_id": str(row[1]),
                "user_id": str(row[2]),
                "scenario": {
                    "scenario_id": str(row[3]),
                    "title": row[5],
                    "context": row[6],
                    "optics": row[7],
                    "audience": row[8],
                    "key_messages": key_messages,
                    "red_lines": red_lines,
                },
                "rubric_version_id": str(row[4]),
                "rubric_areas": areas,
            }

    def _resolve_session_id(self, cur, session_id: str) -> str:
        """Resuelve una sesion existente; nunca fabrica un identificador."""
        cur.execute("SELECT id FROM dbo.session WHERE external_session_id=? AND is_deleted=0", str(session_id))
        row = cur.fetchone()
        if row:
            return str(row[0])
        try:
            internal_id = str(uuid.UUID(str(session_id)))
        except (TypeError, ValueError, AttributeError):
            raise LookupError("Sesion no encontrada.") from None
        cur.execute("SELECT id FROM dbo.session WHERE id=? AND is_deleted=0", internal_id)
        row = cur.fetchone()
        if row:
            return str(row[0])
        raise LookupError("Sesion no encontrada.")

    def finalize_session_analysis(
        self,
        session_id: str,
        overall_score: int,
        visum_report: Dict[str, Any],
        area_scores: Dict[str, int],
        rubric_version_id: str,
        rubric_areas: Dict[str, Any],
        job_id: Optional[str] = None,
    ) -> str:
        """
        Persiste atómicamente el informe y sus áreas, completa la sesión,
        refresca ``user_area_progress`` y completa su agenda vinculada.
        """
        valid_job_uuid = None
        if job_id:
            try:
                valid_job_uuid = str(uuid.UUID(str(job_id)))
            except Exception:
                valid_job_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(job_id)))
        report_id = str(uuid.uuid4())
        strengths_list = visum_report.get("desempeno_observado", {}).get("fortalezas", [])
        improvements_list = visum_report.get("desempeno_observado", {}).get("oportunidades_desarrollo", [])
        cross_signal = str(visum_report.get("observacion_senal_cruzada", ""))[:1000]

        strengths_json = json.dumps(strengths_list, ensure_ascii=False)
        improvements_json = json.dumps(improvements_list, ensure_ascii=False)

        conn = self._get_connection()
        valid_session_uuid = session_id
        try:
            cur = conn.cursor()
            valid_session_uuid = self._resolve_session_id(cur, session_id)

            # 1. Insertar en report con analysis_job_id
            cur.execute("""
                INSERT INTO report (
                    id, session_id, analysis_job_id, rubric_version_id, overall_score,
                    narrative_strengths, narrative_improvements, cross_signal_observation,
                    version_no, is_current, generated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, SYSUTCDATETIME())
            """, (
                report_id,
                valid_session_uuid,
                valid_job_uuid,
                rubric_version_id,
                int(round(overall_score)),
                strengths_json,
                improvements_json,
                cross_signal,
            ))

            # 2. Insertar los 4 puntajes por área en area_score
            for area_key, score_val in area_scores.items():
                area_meta = rubric_areas.get(area_key)
                if area_meta and "id" in area_meta:
                    rubric_area_id = area_meta["id"]
                    cur.execute("""
                        INSERT INTO area_score (id, report_id, rubric_area_id, value)
                        VALUES (NEWID(), ?, ?, ?)
                    """, (
                        report_id,
                        rubric_area_id,
                        int(round(score_val)),
                    ))

            # 3. Actualizar session a completed
            cur.execute("""
                UPDATE session
                SET status = 'completed', finished_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
                WHERE id = ?
            """, valid_session_uuid)

            # 4. Refrescar el resumen de progreso del mismo vocero/cliente.
            cur.execute(USER_AREA_PROGRESS_REFRESH_DML, valid_session_uuid)

            # 5. Completar únicamente la cita desde la que nació esta sesión.
            cur.execute(LINKED_SCHEDULE_COMPLETE_DML, valid_session_uuid)

            conn.commit()
            logger.info(f"Sesión {valid_session_uuid} finalizada y persistida con Report ID: {report_id} (Job: {valid_job_uuid})")
            return report_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error persistiendo informe en SQL para {session_id} ({valid_session_uuid}): {e}")
            try:
                cur.execute("""
                    UPDATE session
                    SET status = 'failed', updated_at = SYSUTCDATETIME()
                    WHERE id = ?
                """, valid_session_uuid)
                conn.commit()
            except Exception:
                pass
            raise e
        finally:
            conn.close()

    def update_question_responses(
        self,
        session_id: str,
        turn_responses: List[Dict[str, Any]]
    ):
        """
        Actualiza el texto transcrito de la respuesta (response_text) para cada pregunta
        en la tabla session_question.
        """
        if not turn_responses:
            return

        with self._get_connection() as conn:
            cur = conn.cursor()
            valid_session_uuid = self._resolve_session_id(cur, session_id)
            for tr in turn_responses:
                q_id = tr.get("questionId") or tr.get("question_id") or ""
                seq = tr.get("sequenceNo") or tr.get("sequence_no") or 1
                resp_text = (tr.get("transcript") or tr.get("response_text") or "").strip()
                q_text = tr.get("questionText") or tr.get("question_text")

                try:
                    q_uuid = str(uuid.UUID(str(q_id)))
                except Exception:
                    q_uuid = None

                # 1. Intentar actualizar response_text en fila existente
                if q_uuid:
                    cur.execute("""
                        UPDATE session_question
                        SET response_text = ?, updated_at = SYSUTCDATETIME()
                        WHERE session_id = ? AND (question_id = ? OR sequence_no = ?)
                    """, (resp_text, valid_session_uuid, q_uuid, seq))
                else:
                    cur.execute("""
                        UPDATE session_question
                        SET response_text = ?, updated_at = SYSUTCDATETIME()
                        WHERE session_id = ? AND sequence_no = ?
                    """, (resp_text, valid_session_uuid, seq))

                # 2. Si no existía la fila, resolver question_id válido y crearla (sin question_text)
                if cur.rowcount == 0:
                    real_q_uuid = q_uuid
                    if real_q_uuid:
                        cur.execute("SELECT id FROM question WHERE id = ?", real_q_uuid)
                        if not cur.fetchone():
                            real_q_uuid = None

                    if not real_q_uuid:
                        cur.execute("""
                            SELECT sq.question_id 
                            FROM scenario_question sq
                            JOIN session s ON s.scenario_id = sq.scenario_id
                            WHERE s.id = ? AND sq.sequence_no = ?
                        """, (valid_session_uuid, seq))
                        sq_row = cur.fetchone()
                        if sq_row:
                            real_q_uuid = str(sq_row[0])

                    if not real_q_uuid:
                        cur.execute("SELECT TOP 1 id FROM question")
                        any_q = cur.fetchone()
                        real_q_uuid = str(any_q[0]) if any_q else None

                    if real_q_uuid:
                        cur.execute("""
                            INSERT INTO session_question (
                                id, session_id, question_id, sequence_no, asked_at, response_text, created_at, updated_at
                            )
                            VALUES (NEWID(), ?, ?, ?, SYSUTCDATETIME(), ?, SYSUTCDATETIME(), SYSUTCDATETIME())
                        """, (
                            valid_session_uuid,
                            real_q_uuid,
                            seq,
                            resp_text
                        ))
            conn.commit()
            logger.info(f"Respuestas transcritas de {len(turn_responses)} preguntas actualizadas en session_question para sesión {valid_session_uuid}")

    save_analysis_report = finalize_session_analysis

    def update_session_status(
        self,
        session_id: str,
        status: str,
    ) -> bool:
        """
        Actualiza el estado de la sesión ('processing', 'completed', 'failed').
        """
        with self._get_connection() as conn:
            cur = conn.cursor()
            valid_session_uuid = self._resolve_session_id(cur, session_id)
            cur.execute("""
                UPDATE session
                SET status = ?, updated_at = SYSUTCDATETIME()
                WHERE id = ?
            """, (status, valid_session_uuid))
            conn.commit()
            return True

    def get_active_rubric_config(self) -> DynamicRubricConfig:
        """
        Lee la última versión publicada en dbo.rubric_version y sus 16 límites desde dbo.rubric_metric_value.
        Si falla o es una versión histórica sin filas (ej. v0.4), opera con el fallback estático.
        """
        cfg = DynamicRubricConfig()
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # 1. Obtener la última versión publicada (priorizando la que tenga métricas cargadas)
                try:
                    cursor.execute("""
                        SELECT TOP 1 rv.id, rv.version_label
                        FROM dbo.rubric_version rv
                        WHERE rv.status = 'published'
                        ORDER BY 
                            CASE WHEN EXISTS (
                                SELECT 1 FROM dbo.rubric_metric_value rmv WHERE rmv.rubric_version_id = rv.id
                            ) THEN 0 ELSE 1 END,
                            rv.created_at DESC
                    """)
                    row = cursor.fetchone()
                except Exception:
                    cursor.execute("""
                        SELECT TOP 1 rv.id, rv.version_code
                        FROM dbo.rubric_version rv
                        WHERE rv.status = 'published'
                        ORDER BY 
                            CASE WHEN EXISTS (
                                SELECT 1 FROM dbo.rubric_metric_value rmv WHERE rmv.rubric_version_id = rv.id
                            ) THEN 0 ELSE 1 END,
                            rv.created_at DESC
                    """)
                    row = cursor.fetchone()

                if not row:
                    return cfg

                cfg.rubric_version_id = str(row[0])
                cfg.version_code = str(row[1]) if row[1] else "published"

                # 2. Cargar pesos de dbo.rubric_area para esta versión
                try:
                    cursor.execute("""
                        SELECT area_key, weight
                        FROM dbo.rubric_area
                        WHERE rubric_version_id = ?
                    """, (cfg.rubric_version_id,))
                    area_rows = cursor.fetchall()
                except Exception:
                    cursor.execute("""
                        SELECT code, weight
                        FROM dbo.rubric_area
                        WHERE rubric_version_id = ?
                    """, (cfg.rubric_version_id,))
                    area_rows = cursor.fetchall()

                for area_code, weight_val in area_rows:
                    key = str(area_code).lower().strip()
                    if key in cfg.area_weights and weight_val is not None:
                        w = float(weight_val)
                        cfg.area_weights[key] = w / 100.0 if w > 1.0 else w

                # 3. Cargar los 16 límites desde dbo.rubric_metric_value
                cursor.execute("""
                    SELECT metric_key, thresholds_json
                    FROM dbo.rubric_metric_value
                    WHERE rubric_version_id = ?
                """, (cfg.rubric_version_id,))
                for metric_key, thresholds_raw in cursor.fetchall():
                    if metric_key and thresholds_raw:
                        parsed = json.loads(thresholds_raw) if isinstance(thresholds_raw, str) else thresholds_raw
                        if isinstance(parsed, dict):
                            base = cfg.thresholds.get(metric_key, {}).copy()
                            base.update({k: float(v) for k, v in parsed.items() if v is not None})
                            cfg.thresholds[metric_key] = base
        except Exception as exc:
            logger.warning(f"Usando DynamicRubricConfig por defecto tras excepción SQL: {exc}")
        return cfg

    def create_labeling_case_if_needed(
        self,
        session_id: str,
        rubric_version_id: Optional[str] = None,
        reason: Optional[str] = None,
        report_id: Optional[str] = None,
        job_id: Optional[str] = None,
        governance_metrics: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Inserta un caso pendiente en dbo.labeling_case cuando la sesión requiere auditoría o se completa.
        Utiliza el pipeline canónico de labeling_runtime si es posible, con fallback seguro que cumple
        el esquema estricto de dbo.labeling_case (queue_reason, reason_detail_json, ai_snapshot_json, etc.).
        """
        # 1. Intentar creación canónica usando ensure_labeling_case_for_report si hay report_id
        if report_id:
            try:
                try:
                    from worker.services.labeling_runtime import (
                        ensure_labeling_case_for_report,
                        runtime_enabled,
                    )
                except ImportError:
                    from services.labeling_runtime import (
                        ensure_labeling_case_for_report,
                        runtime_enabled,
                    )

                if runtime_enabled():
                    with self.get_connection() as conn:
                        cursor = conn.cursor()
                        result = ensure_labeling_case_for_report(cursor, str(report_id), materialize=True)
                        conn.commit()
                        if result and result.get("caseId"):
                            logger.info(f"Caso de etiquetado canónico creado/asegurado: {result['caseId']}")
                            return str(result["caseId"])
            except Exception as e_canonical:
                logger.warning(
                    f"Aviso en ensure_labeling_case_for_report para report {report_id}: {e_canonical}. "
                    "Intentando fallback directo conforme al esquema de dbo.labeling_case..."
                )

        # 2. Fallback resiliente que respeta el esquema formal de dbo.labeling_case
        case_id = str(uuid.uuid4())
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                valid_session_uuid = self._resolve_session_id(cursor, session_id)

                resolved_report_id = str(report_id) if report_id else None
                resolved_job_id = str(job_id) if job_id else None
                resolved_rubric_id = str(rubric_version_id) if rubric_version_id else None
                client_id = None
                finished_at = None

                if resolved_report_id:
                    cursor.execute("""
                        SELECT r.id, r.analysis_job_id, r.rubric_version_id, s.client_id,
                               COALESCE(s.finished_at, s.updated_at, s.created_at, SYSUTCDATETIME())
                        FROM dbo.report r
                        JOIN dbo.[session] s ON s.id = r.session_id
                        WHERE r.id = ?
                    """, resolved_report_id)
                    row = cursor.fetchone()
                    if row:
                        resolved_report_id = str(row[0])
                        resolved_job_id = resolved_job_id or str(row[1])
                        resolved_rubric_id = resolved_rubric_id or str(row[2])
                        client_id = str(row[3])
                        finished_at = row[4]

                if not client_id:
                    cursor.execute("""
                        SELECT s.client_id, s.rubric_version_id,
                               COALESCE(s.finished_at, s.updated_at, s.created_at, SYSUTCDATETIME())
                        FROM dbo.[session] s
                        WHERE s.id = ?
                    """, valid_session_uuid)
                    s_row = cursor.fetchone()
                    if s_row:
                        client_id = str(s_row[0])
                        resolved_rubric_id = resolved_rubric_id or str(s_row[1])
                        finished_at = finished_at or s_row[2]

                if not resolved_report_id:
                    cursor.execute("""
                        SELECT TOP 1 r.id, r.analysis_job_id
                        FROM dbo.report r
                        WHERE r.session_id = ?
                        ORDER BY r.generated_at DESC, r.version_no DESC
                    """, valid_session_uuid)
                    r_row = cursor.fetchone()
                    if r_row:
                        resolved_report_id = str(r_row[0])
                        resolved_job_id = resolved_job_id or str(r_row[1])

                if not resolved_job_id:
                    cursor.execute("""
                        SELECT TOP 1 j.id
                        FROM dbo.analysis_job j
                        WHERE j.session_id = ?
                        ORDER BY j.created_at DESC
                    """, valid_session_uuid)
                    j_row = cursor.fetchone()
                    if j_row:
                        resolved_job_id = str(j_row[0])

                if not client_id or not resolved_report_id or not resolved_job_id or not resolved_rubric_id:
                    logger.warning(
                        f"No se pudo resolver la identidad relacional para dbo.labeling_case "
                        f"(client: {client_id}, report: {resolved_report_id}, job: {resolved_job_id}, rubric: {resolved_rubric_id})"
                    )
                    return None

                # Evitar duplicados por report_id (UQ_labeling_case_report)
                cursor.execute("SELECT id FROM dbo.labeling_case WHERE report_id = ?", resolved_report_id)
                existing = cursor.fetchone()
                if existing:
                    return str(existing[0])

                clean_reason = str(reason or "").strip().lower()
                if clean_reason in ("critical", "borderline", "disparity", "routine"):
                    queue_reason = clean_reason
                elif clean_reason in ("low_confidence", "red_line", "audit", "human_review"):
                    queue_reason = "critical"
                else:
                    queue_reason = "routine"

                reason_detail = {
                    "kind": queue_reason,
                    "originalReason": str(reason or ""),
                    "governance": governance_metrics or {}
                }
                reason_detail_json = json.dumps(reason_detail, ensure_ascii=False)

                is_complete_evidence = False
                rec_path = None
                rec_version = None
                rec_sha = None
                rec_etag = None
                rec_type = None
                rec_dur = None

                if isinstance(evidence, dict) and evidence.get("sealedPath") and evidence.get("sha256"):
                    sha_str = str(evidence.get("sha256", "")).strip().lower()
                    if len(sha_str) == 64:
                        try:
                            rec_sha = bytes.fromhex(sha_str)
                            rec_path = str(evidence.get("sealedPath"))
                            rec_version = str(evidence["versionId"]) if evidence.get("versionId") else None
                            rec_etag = str(evidence.get("etag") or "sealed")
                            rec_type = str(evidence.get("contentType") or "video/webm")
                            dur_val = evidence.get("durationSeconds")
                            rec_dur = Decimal(str(round(dur_val, 3))) if dur_val is not None else None
                            is_complete_evidence = True
                        except Exception:
                            is_complete_evidence = False

                source_status = "complete" if is_complete_evidence else "partial"

                ai_snapshot = {
                    "schemaVersion": 1,
                    "identity": {
                        "clientId": client_id,
                        "sessionId": valid_session_uuid,
                        "reportId": resolved_report_id,
                        "analysisJobId": resolved_job_id,
                        "rubricVersionId": resolved_rubric_id,
                    },
                    "sourceStatus": source_status,
                    "queueReason": queue_reason,
                }
                ai_snapshot_json = json.dumps(ai_snapshot, ensure_ascii=False)

                cursor.execute("""
                    INSERT INTO dbo.labeling_case (
                        id, client_id, session_id, report_id, analysis_job_id, rubric_version_id,
                        session_finished_at, queue_reason, reason_detail_json, ai_snapshot_json,
                        snapshot_schema_version, source_status, recording_evidence_path,
                        recording_version_id, recording_sha256, recording_etag,
                        recording_content_type, recording_duration_seconds, status,
                        created_at, updated_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?,
                        COALESCE(?, SYSUTCDATETIME()), ?, ?, ?,
                        1, ?, ?,
                        ?, ?, ?,
                        ?, ?, 'pending',
                        SYSUTCDATETIME(), SYSUTCDATETIME()
                    )
                """, (
                    case_id, client_id, valid_session_uuid, resolved_report_id, resolved_job_id, resolved_rubric_id,
                    finished_at, queue_reason, reason_detail_json, ai_snapshot_json,
                    source_status, rec_path,
                    rec_version, rec_sha, rec_etag,
                    rec_type, rec_dur
                ))
                conn.commit()
                logger.info(f"Caso de etiquetado insertado exitosamente en dbo.labeling_case (ID: {case_id}, motivo: {queue_reason})")
                return case_id
        except Exception as exc:
            logger.error(f"No se pudo insertar en dbo.labeling_case para sesión {session_id}: {exc}", exc_info=True)
            return None

