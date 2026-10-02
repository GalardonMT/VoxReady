import os
import time
import json
import datetime
from typing import Optional, Dict, Any
from utils.logger import get_logger
from services.keyvault_service import get_secret

logger = get_logger("services.db_service")


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
            or get_secret("SQL_CONNECTION_STRING")
            or get_secret("DATABASE_URL")
        )
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def _normalize_connection_string(self, conn_str: str) -> str:
        """
        Asegura que la cadena de conexión tenga el driver y opciones seguras para Azure SQL.
        """
        if "DRIVER=" not in conn_str.upper():
            # Si se pasa un URI estilo mssql+pyodbc o formato estándar
            conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};{conn_str}"

        # Parámetros recomendados para Azure SQL
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
                # Códigos típicos de cold start o timeout de conexión inicial: 40613, HYT00, 08001
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

    def update_session_status(
        self,
        session_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Actualiza el estado de la sesión ('processing', 'completed', 'failed').
        Si el estado es 'failed', registra también el mensaje de error.
        """
        logger.info(f"Actualizando estado de sesión '{session_id}' a '{status}'...")
        query = """
            UPDATE crisis_sessions
            SET status = ?,
                updated_at = ?,
                error_message = ?
            WHERE session_id = ?
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (status, now, error_message, session_id))
                conn.commit()
            logger.info(f"Estado de sesión '{session_id}' actualizado a '{status}'.")
            return True
        except Exception as e:
            logger.error(
                f"Error al actualizar estado de sesión '{session_id}' en BD: {e}"
            )
            # Reintentar o permitir que la excepción se capture en el llamador
            raise

    def save_analysis_report(
        self,
        session_id: str,
        report_data: Dict[str, Any],
    ) -> bool:
        """
        Persiste el JSON consolidado en la tabla de reportes y actualiza
        el estado de la sesión a 'completed' con su marca completed_at.
        """
        logger.info(f"Guardando reporte consolidado para sesión '{session_id}'...")
        now = datetime.datetime.now(datetime.timezone.utc)
        json_str = json.dumps(report_data, ensure_ascii=False)

        # Inserción o actualización del reporte
        upsert_report_query = """
            MERGE INTO session_reports AS target
            USING (SELECT ? AS session_id) AS source
            ON target.session_id = source.session_id
            WHEN MATCHED THEN
                UPDATE SET report_json = ?, updated_at = ?
            WHEN NOT MATCHED THEN
                INSERT (session_id, report_json, created_at, updated_at)
                VALUES (?, ?, ?, ?);
        """

        update_session_query = """
            UPDATE crisis_sessions
            SET status = 'completed',
                completed_at = ?,
                updated_at = ?
            WHERE session_id = ?
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 1. Upsert reporte
                cursor.execute(
                    upsert_report_query,
                    (session_id, json_str, now, session_id, json_str, now, now),
                )
                # 2. Actualizar sesión a completada
                cursor.execute(update_session_query, (now, now, session_id))
                conn.commit()

            logger.info(
                f"Reporte y sesión '{session_id}' guardados exitosamente en Azure SQL."
            )
            return True
        except Exception as e:
            logger.error(f"Error al persistir reporte para sesión '{session_id}': {e}")
            raise
