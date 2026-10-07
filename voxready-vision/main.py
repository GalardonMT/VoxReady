from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
from core.analyzer import MultimodalVisionAnalyzer

app = FastAPI(
    title="ca-vision-service",
    description="Microservicio de visión para análisis de contacto visual, postura y gesticulación con MediaPipe (VISUM)",
    version="2.0.0"
)

analyzer = MultimodalVisionAnalyzer()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ca-vision-service",
        "version": "2.0.0",
        "runtime": "solutions" if analyzer.use_solutions else "tasks"
    }


@app.post("/analyze/batch")
async def analyze_batch(frames: List[UploadFile] = File(...)):
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

    results = []
    for frame_file in frames:
        content = await frame_file.read()
        frame_metrics = analyzer.process_frame(content)
        results.append(frame_metrics)

    aggregated = analyzer.aggregate_metrics(results)
    return {
        "status": "success",
        "summary": aggregated,
        "frame_details": results
    }


@app.post("/analyze-frame")
async def analyze_frame(file: UploadFile = File(...)):
    """
    Compatibilidad hacia atrás: analiza un frame individual (JPEG/PNG/WebP).
    """
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="El archivo recibido está vacío.")

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
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error procesando frame: {str(e)}", "valid": False}
        )
