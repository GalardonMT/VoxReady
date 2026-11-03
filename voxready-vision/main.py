import logging
import os
import secrets

from fastapi import Depends, FastAPI, UploadFile, File, Header, HTTPException
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
from core.analyzer import MultimodalVisionAnalyzer

app = FastAPI(
    title="ca-vision-service",
    description="Microservicio de visión para análisis de contacto visual, postura y gesticulación con MediaPipe (VISUM)",
    version="2.0.0"
)

analyzer = MultimodalVisionAnalyzer()
logger = logging.getLogger("voxready-vision")
VISION_SERVICE_TOKEN = os.getenv("VISION_SERVICE_TOKEN", "").strip()
VISION_MAX_FRAME_BYTES = int(os.getenv("VISION_MAX_FRAME_BYTES", str(5 * 1024 * 1024)))
VISION_MAX_BATCH_FRAMES = int(os.getenv("VISION_MAX_BATCH_FRAMES", "20"))
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def verify_internal_service(
    service_token: str | None = Header(default=None, alias="X-VoxReady-Service-Token"),
) -> None:
    if len(VISION_SERVICE_TOKEN) < 32:
        raise HTTPException(status_code=503, detail="Autenticación interna no configurada.")
    if not service_token or not secrets.compare_digest(service_token, VISION_SERVICE_TOKEN):
        raise HTTPException(status_code=401, detail="Credencial interna inválida.")


async def read_validated_image(upload: UploadFile) -> bytes:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Tipo de imagen no permitido.")
    content = await upload.read(VISION_MAX_FRAME_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="El archivo recibido está vacío.")
    if len(content) > VISION_MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="La imagen excede el tamaño permitido.")
    return content


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ca-vision-service",
        "version": "2.0.0",
        "runtime": "solutions" if analyzer.use_solutions else "tasks"
    }


@app.post("/analyze/batch")
async def analyze_batch(
    frames: List[UploadFile] = File(...),
    _: None = Depends(verify_internal_service),
):
    """
    Recibe un lote de fotogramas JPEG/PNG muestreados a 0.5 FPS y retorna el agregado multivariable.
    Variables operacionales VISUM:
      - eye_contact_pct
      - hands_visible_pct
      - hands_active_pct
      - shoulder_stability_score
      - body_sway_std
      - total_frames_analyzed
    """
    if not frames:
        raise HTTPException(status_code=400, detail="No se recibieron fotogramas para análisis.")
    if len(frames) > VISION_MAX_BATCH_FRAMES:
        raise HTTPException(status_code=413, detail="El lote excede el máximo de fotogramas permitido.")

    results = []
    for frame_file in frames:
        content = await read_validated_image(frame_file)
        frame_metrics = analyzer.process_frame(content)
        if not frame_metrics.get("valid"):
            raise HTTPException(status_code=400, detail="Una imagen del lote no pudo decodificarse.")
        results.append(frame_metrics)

    aggregated = analyzer.aggregate_metrics(results)
    return {
        "status": "success",
        "summary": aggregated,
        "frame_details": results
    }


@app.post("/analyze-frame")
async def analyze_frame(
    file: UploadFile = File(...),
    _: None = Depends(verify_internal_service),
):
    """
    Compatibilidad hacia atrás: analiza un frame individual (JPEG/PNG/WebP).
    """
    try:
        content = await read_validated_image(file)

        res = analyzer.process_frame(content)
        if not res.get("valid"):
            return JSONResponse(
                status_code=400,
                content={"error": "No se pudo decodificar la imagen.", "valid": False}
            )

        posture_stability = max(0.0, 100.0 - (res.get("shoulder_slope", 0.0) * 1500.0))
        return {
            "valid": True,
            "face_detected": res.get("valid"),
            "pose_detected": res.get("pose_detected"),
            "eye_contact": res.get("eye_contact"),
            "mirada_directa": res.get("eye_contact"),
            "hands_visible": res.get("hands_visible"),
            "hands_active": res.get("hands_active"),
            "shoulder_slope": res.get("shoulder_slope"),
            "posture_stability_score": round(posture_stability, 2),
            "estabilidad_score": round(posture_stability, 2),
            "torso_center_x": res.get("torso_center_x")
        }
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Error al procesar un fotograma: %s", type(error).__name__)
        return JSONResponse(
            status_code=500,
            content={"error": "Error interno al procesar el fotograma.", "valid": False}
        )
