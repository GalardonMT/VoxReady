import os
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from utils.logger import get_logger
from services.keyvault_service import get_secret

try:
    import httpx
except ImportError:
    httpx = None

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from concurrent.futures import ThreadPoolExecutor
except ImportError:
    requests = None

logger = get_logger("core.vision_client")


class VisionClient:
    """
    Cliente HTTP asíncrono para el microservicio `ca-vision-service`.
    Envía los fotogramas muestreados mediante multipart POST /analyze-frame
    con concurrencia controlada (semáforo de 5) para no saturar las instancias
    de Container Apps durante escalados o cold-starts.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        concurrency_limit: int = 5,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ):
        self.base_url = (
            base_url
            or get_secret("VISION_SERVICE_URL")
            or "https://ca-vision-service.internal.azurecontainerapps.io"
        ).rstrip("/")
        self.endpoint = f"{self.base_url}/analyze-frame"
        self.concurrency_limit = concurrency_limit
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def _send_frame_with_retry(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        frame_path: str,
    ) -> Optional[Dict[str, Any]]:
        """Envía un solo frame con control de semáforo y reintentos ante cold-starts."""
        path_obj = Path(frame_path)
        filename = path_obj.name

        async with semaphore:
            for attempt in range(1, self.max_retries + 1):
                try:
                    with open(path_obj, "rb") as f:
                        file_bytes = f.read()

                    files = {"file": (filename, file_bytes, "image/jpeg")}
                    response = await client.post(
                        self.endpoint,
                        files=files,
                        timeout=self.timeout_seconds,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        data["frame_name"] = filename
                        return data
                    elif response.status_code in [502, 503, 504] and attempt < self.max_retries:
                        await asyncio.sleep(2.0 * attempt)
                    else:
                        logger.warning(
                            f"Frame '{filename}' falló con HTTP {response.status_code}: {response.text[:150]}"
                        )
                except Exception as e:
                    if attempt < self.max_retries:
                        await asyncio.sleep(2.0 * attempt)
                    else:
                        logger.error(f"Error enviando frame '{filename}' a ca-vision-service: {e}")
            return None

    async def analyze_frames_async(
        self, frame_paths: List[str], fps: float = 0.5
    ) -> Dict[str, Any]:
        """
        Envía en paralelo controlado la lista de frames al microservicio
        y calcula las métricas agregadas solicitadas en la especificación.
        """
        total_frames = len(frame_paths)
        if total_frames == 0:
            return {
                "total_frames_analizados": 0,
                "contacto_visual_porcentaje": 0.0,
                "posture_stability_score": 0.0,
                "metricas_ejes": {},
                "frames_validos": 0,
                "eventos_detectados": [],
            }

        logger.info(
            f"Enviando {total_frames} frames a '{self.endpoint}' con semáforo={self.concurrency_limit}..."
        )

        semaphore = asyncio.Semaphore(self.concurrency_limit)
        limits = httpx.Limits(
            max_keepalive_connections=self.concurrency_limit,
            max_connections=self.concurrency_limit * 2,
        )

        async with httpx.AsyncClient(limits=limits, timeout=self.timeout_seconds) as client:
            tasks = [
                self._send_frame_with_retry(client, semaphore, fp)
                for fp in frame_paths
            ]
            results = await asyncio.gather(*tasks, return_exceptions=False)

    def _send_frame_requests(self, session: Any, frame_path: str) -> Optional[Dict[str, Any]]:
        """Envía un frame usando requests y connection pooling."""
        path_obj = Path(frame_path)
        filename = path_obj.name

        for attempt in range(1, self.max_retries + 1):
            try:
                with open(path_obj, "rb") as f:
                    file_bytes = f.read()

                files = {"file": (filename, file_bytes, "image/jpeg")}
                response = session.post(
                    self.endpoint,
                    files=files,
                    timeout=self.timeout_seconds,
                )

                if response.status_code == 200:
                    data = response.json()
                    data["frame_name"] = filename
                    return data
                elif response.status_code in [502, 503, 504] and attempt < self.max_retries:
                    time.sleep(2.0 * attempt)
                else:
                    logger.warning(
                        f"Frame '{filename}' falló con HTTP {response.status_code}: {response.text[:150]}"
                    )
            except Exception as e:
                if attempt < self.max_retries:
                    time.sleep(2.0 * attempt)
                else:
                    logger.error(f"Error enviando frame '{filename}' a ca-vision-service (requests): {e}")
        return None

    def analyze_frames_with_requests(self, frame_paths: List[str], fps: float = 0.5) -> Dict[str, Any]:
        """Envía los frames usando requests con pool de conexiones y ThreadPoolExecutor."""
        total_frames = len(frame_paths)
        if total_frames == 0:
            return {
                "total_frames_analizados": 0,
                "contacto_visual_porcentaje": 0.0,
                "posture_stability_score": 0.0,
                "metricas_ejes": {},
                "frames_validos": 0,
                "eventos_detectados": [],
            }

        session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=self.concurrency_limit,
            pool_maxsize=self.concurrency_limit * 2,
            max_retries=Retry(total=self.max_retries, backoff_factor=1.0),
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        with ThreadPoolExecutor(max_workers=self.concurrency_limit) as executor:
            futures = [executor.submit(self._send_frame_requests, session, fp) for fp in frame_paths]
            results = [f.result() for f in futures]

        valid_results = [r for r in results if r is not None]
        return self._consolidate_results(total_frames, valid_results)

    def _consolidate_results(self, total_frames: int, valid_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fusión matemática unificada de resultados de frames."""
        total_validos = len(valid_results)
        if total_validos == 0:
            logger.warning("No se recibieron respuestas válidas de ca-vision-service.")
            return {
                "total_frames_analizados": total_frames,
                "frames_validos": 0,
                "contacto_visual_porcentaje": 0.0,
                "posture_stability_score": 0.0,
                "error": "El microservicio de visión no respondió exitosamente para ningún frame.",
            }

        frames_con_contacto = sum(
            1 for r in valid_results if r.get("eye_contact") is True or r.get("mirada_directa") is True
        )
        eye_contact_pct = round((frames_con_contacto / total_validos) * 100.0, 1)

        posture_scores = [
            float(r.get("posture_stability_score", r.get("estabilidad_score", 100.0)))
            for r in valid_results
            if "posture_stability_score" in r or "estabilidad_score" in r
        ]
        avg_posture_stability = (
            round(sum(posture_scores) / len(posture_scores), 1)
            if posture_scores
            else 100.0
        )

        shoulder_angles = [
            float(r.get("shoulder_angle", r.get("angulo_hombros", 0.0)))
            for r in valid_results
            if "shoulder_angle" in r or "angulo_hombros" in r
        ]
        avg_shoulder_angle = (
            round(sum(shoulder_angles) / len(shoulder_angles), 1)
            if shoulder_angles
            else 0.0
        )

        head_roll_angles = [
            float(r.get("head_roll_angle", r.get("angulo_cabeza", 0.0)))
            for r in valid_results
            if "head_roll_angle" in r or "angulo_cabeza" in r
        ]
        avg_head_roll = (
            round(sum(head_roll_angles) / len(head_roll_angles), 1)
            if head_roll_angles
            else 0.0
        )

        tension_indices = [
            float(r.get("facial_tension_index", r.get("indice_tension", 0.0)))
            for r in valid_results
            if "facial_tension_index" in r or "indice_tension" in r
        ]
        avg_facial_tension = (
            round(sum(tension_indices) / len(tension_indices), 2)
            if tension_indices
            else 0.0
        )

        eventos = []
        for r in valid_results:
            fname = r.get("frame_name", "")
            if r.get("eye_contact") is False:
                eventos.append({"frame": fname, "tipo": "desvio_mirada", "detalle": r.get("gaze_detail", "desvio")})
            if r.get("shoulder_angle", 0.0) > 5.0:
                eventos.append({"frame": fname, "tipo": "inclinacion_hombros", "valor": r.get("shoulder_angle")})
            if r.get("head_roll_angle", 0.0) > 8.0:
                eventos.append({"frame": fname, "tipo": "ladeo_cabeza", "valor": r.get("head_roll_angle")})

        logger.info(
            f"Consolidación de visión: {total_validos}/{total_frames} frames válidos. "
            f"Contacto visual: {eye_contact_pct}%, Estabilidad: {avg_posture_stability}."
        )

        return {
            "total_frames_analizados": total_frames,
            "frames_validos": total_validos,
            "contacto_visual_porcentaje": eye_contact_pct,
            "posture_stability_score": avg_posture_stability,
            "metricas_ejes": {
                "contacto_visual_porcentaje": eye_contact_pct,
                "desvios_mirada_total": total_validos - frames_con_contacto,
                "alineacion_hombros_grados_promedio": avg_shoulder_angle,
                "ladeo_cabeza_grados_promedio": avg_head_roll,
                "indice_tension_facial": avg_facial_tension,
                "estabilidad_balanceo_score": avg_posture_stability,
            },
            "eventos_detectados": eventos[:30],
        }

    def analyze_frames(self, frame_paths: List[str], fps: float = 0.5) -> Dict[str, Any]:
        """
        Envía frames usando httpx asíncrono si está instalado,
        o requests con pool de conexiones en caso contrario.
        """
        if httpx is not None:
            return asyncio.run(self.analyze_frames_async(frame_paths, fps=fps))
        elif requests is not None:
            return self.analyze_frames_with_requests(frame_paths, fps=fps)
        else:
            raise RuntimeError("Se requiere instalar 'httpx' o 'requests' para vision_client.")
