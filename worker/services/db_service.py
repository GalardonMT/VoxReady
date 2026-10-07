import os
import re
import time
import json
import uuid
import datetime
from typing import Optional, Dict, Any, Tuple, List
from utils.logger import get_logger
from services.keyvault_service import get_secret

logger = get_logger("services.db_service")


class DatabaseService:
    """
    Servicio de conexión resiliente para Azure SQL Serverless (sqldb-voxready).
    Implementa reintentos con retroceso exponencial (exponential backoff) para
    manejar el cold-start cuando la base de datos se encuentra auto-pausada.
    """

    DEFAULT_CLIENT_ID = "7D8C0575-196C-40D1-AD7C-08AA2843B4C3"
    DEFAULT_USER_ID = "4CC52B91-3A9C-5659-8363-4F069CC39F9B"

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

    def get_active_scenario_and_rubric(self) -> Dict[str, Any]:
        """
        Obtiene el escenario activo, los metadatos de su tópico (contexto, óptica),
        sus mensajes clave oficiales y la versión de rúbrica publicada activa.
        """
        with self._get_connection() as conn:
            cur = conn.cursor()

            # Escenario y tópico
            cur.execute("""
                SELECT TOP 1 s.id, s.title, t.context, t.optics, t.audience, s.topic_id
                FROM scenario s
                LEFT JOIN topic t ON s.topic_id = t.id
                WHERE s.status = 'active'
            """)
            scen_row = cur.fetchone()

            key_messages = []
            scenario_data = {}
            if scen_row:
                scenario_data = {
                    "scenario_id": str(scen_row.id),
                    "title": scen_row.title,
                    "context": scen_row.context or "Crisis institucional con impacto en la comunidad.",
                    "optics": scen_row.optics or "empathetic",
                    "audience": scen_row.audience or "Medios de comunicación y opinión pública",
                }
                if scen_row.topic_id:
                    cur.execute(
                        "SELECT text FROM topic_key_message WHERE topic_id = ? ORDER BY sort_order",
                        scen_row.topic_id,
                    )
                    key_messages = [r[0] for r in cur.fetchall()]

            scenario_data["key_messages"] = key_messages

            # Rúbrica publicada activa
            cur.execute("""
                SELECT TOP 1 id, version_label
                FROM rubric_version
                WHERE status = 'published'
            """)
            rubric_row = cur.fetchone()
            rubric_version_id = str(rubric_row.id) if rubric_row else None

            # Áreas de rúbrica
            areas = {}
            if rubric_version_id:
                cur.execute(
                    "SELECT id, area_key, weight FROM rubric_area WHERE rubric_version_id = ?",
                    rubric_version_id,
                )
                for r in cur.fetchall():
                    areas[r.area_key] = {"id": str(r.id), "weight": r.weight}

            return {
                "scenario": scenario_data,
                "rubric_version_id": rubric_version_id,
                "rubric_areas": areas,
            }

    def ensure_session_exists(
        self,
        session_id: str,
        scenario_id: Optional[str] = None,
        rubric_version_id: Optional[str] = None,
    ) -> bool:
        """
        Garantiza que la sesión exista en la tabla 'session' con clave foránea válida.
        Si no existe, la crea con estado 'processing'.
        """
        try:
            uuid_obj = uuid.UUID(session_id)
            valid_session_uuid = str(uuid_obj)
        except Exception:
            valid_session_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, session_id))

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM session WHERE id = ?", valid_session_uuid)
            row = cur.fetchone()
            if row:
                return True

            logger.info(f"Creando registro inicial en tabla 'session' para {valid_session_uuid}...")
            cur.execute("""
                INSERT INTO session (
                    id, client_id, user_id, scenario_id, rubric_version_id,
                    language, status, started_at, created_at, updated_at, is_deleted
                )
                VALUES (
                    ?, ?, ?, ?, ?,
                    'es', 'processing', SYSUTCDATETIME(), SYSUTCDATETIME(), SYSUTCDATETIME(), 0
                )
            """, (
                valid_session_uuid,
                self.DEFAULT_CLIENT_ID,
                self.DEFAULT_USER_ID,
                scenario_id,
                rubric_version_id,
            ))
            conn.commit()
            return True

    def finalize_session_analysis(
        self,
        session_id: str,
        overall_score: int,
        visum_report: Dict[str, Any],
        area_scores: Dict[str, int],
        rubric_version_id: str,
        rubric_areas: Dict[str, Any],
    ) -> str:
        """
        Persiste atómicamente el informe en 'report' y los 4 puntajes en 'area_score',
        y actualiza la sesión a 'completed'.
        """
        try:
            uuid_obj = uuid.UUID(session_id)
            valid_session_uuid = str(uuid_obj)
        except Exception:
            valid_session_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, session_id))

        report_id = str(uuid.uuid4())
        strengths_list = visum_report.get("desempeno_observado", {}).get("fortalezas", [])
        improvements_list = visum_report.get("desempeno_observado", {}).get("oportunidades_desarrollo", [])
        cross_signal = str(visum_report.get("observacion_senal_cruzada", ""))[:1000]

        strengths_json = json.dumps(strengths_list, ensure_ascii=False)
        improvements_json = json.dumps(improvements_list, ensure_ascii=False)

        conn = self._get_connection()
        try:
            cur = conn.cursor()

            # 1. Insertar en report
            cur.execute("""
                INSERT INTO report (
                    id, session_id, rubric_version_id, overall_score,
                    narrative_strengths, narrative_improvements, cross_signal_observation,
                    version_no, is_current, generated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, SYSUTCDATETIME())
            """, (
                report_id,
                valid_session_uuid,
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

            conn.commit()
            logger.info(f"Sesión {valid_session_uuid} finalizada y persistida con Report ID: {report_id}")
            return report_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error persistiendo informe en SQL para {valid_session_uuid}: {e}")
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

    save_analysis_report = finalize_session_analysis

    def update_session_status(
        self,
        session_id: str,
        status: str,
    ) -> bool:
        """
        Actualiza el estado de la sesión ('processing', 'completed', 'failed').
        """
        try:
            uuid_obj = uuid.UUID(session_id)
            valid_session_uuid = str(uuid_obj)
        except Exception:
            valid_session_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, session_id))

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE session
                SET status = ?, updated_at = SYSUTCDATETIME()
                WHERE id = ?
            """, (status, valid_session_uuid))
            conn.commit()
            return True
