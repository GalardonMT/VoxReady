import os
from pathlib import Path
from typing import Optional
from utils.logger import get_logger
from services.keyvault_service import get_secret

logger = get_logger("services.blob_service")


class BlobService:
    """
    Servicio de integración con Azure Blob Storage para descargar grabaciones
    y persistir reportes o evidencias de análisis.
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        default_container: str = "recordings",
    ):
        self.connection_string = connection_string or get_secret("STORAGE_CONNECTION_STRING")
        self.default_container = default_container
        self._blob_service_client = None

    def _get_client(self):
        if self._blob_service_client is None:
            if not self.connection_string:
                raise ValueError(
                    "No se encontró STORAGE_CONNECTION_STRING para conectar con Azure Blob Storage."
                )
            try:
                from azure.storage.blob import BlobServiceClient
                self._blob_service_client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
            except Exception as e:
                logger.error(f"Error inicializando BlobServiceClient: {e}")
                raise
        return self._blob_service_client

    def download_recording(
        self,
        blob_name: str,
        destination_path: str,
        container_name: Optional[str] = None,
        max_chunk_size: int = 4 * 1024 * 1024,
    ) -> str:
        """
        Descarga una grabación de video desde Blob Storage escribiendo por bloques
        directamente al disco local (/tmp) para evitar saturar la memoria RAM.
        """
        container = container_name or self.default_container
        destination = Path(destination_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Descargando blob '{blob_name}' desde contenedor '{container}' hacia '{destination}'..."
        )

        client = self._get_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)

        if not blob_client.exists():
            raise FileNotFoundError(
                f"El blob '{blob_name}' no existe en el contenedor '{container}' de Azure Storage."
            )

        with open(destination, "wb") as file_handle:
            stream = blob_client.download_blob(max_concurrency=4)
            # Descargar en bloques para streaming seguro
            for chunk in stream.chunks():
                file_handle.write(chunk)

        file_size_mb = destination.stat().st_size / (1024 * 1024)
        logger.info(
            f"Descarga exitosa de '{blob_name}': {file_size_mb:.2f} MB guardados en '{destination}'."
        )
        return str(destination)

    def upload_report(
        self,
        blob_name: str,
        content: str,
        container_name: str = "reports",
        content_type: str = "application/json",
    ) -> str:
        """
        Sube el JSON del reporte consolidado al contenedor de reportes de Azure Blob Storage.
        """
        client = self._get_client()
        container_client = client.get_container_client(container_name)

        # Crear contenedor si no existe
        if not container_client.exists():
            try:
                container_client.create_container()
            except Exception:
                pass

        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings={"content_type": content_type} if hasattr(content, "content_type") else None,
        )
        logger.info(f"Reporte subido exitosamente a '{container_name}/{blob_name}'.")
        return blob_client.url
