import os
import math
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

app = FastAPI(
    title="VoxReady Vision Service",
    description="Microservicio de visión para análisis de contacto visual, postura y microexpresiones con MediaPipe",
    version="1.0.0"
)

# URLs de respaldo para descarga de modelos MediaPipe
FACE_LANDMARKER_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
POSE_LANDMARKER_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"

# Constantes de puntos clave (Landmarks)
IRIS_LEFT_CENTER = 468
IRIS_RIGHT_CENTER = 473
EYE_LEFT_OUTER = 33
EYE_LEFT_INNER = 133
EYE_RIGHT_INNER = 362
EYE_RIGHT_OUTER = 263
NOSE_TIP = 1
CHIN = 152
SHOULDER_LEFT = 11
SHOULDER_RIGHT = 12

MODELS_DIR = Path(__file__).resolve().parent / "models"


def _obtener_modelo(ruta_modelo: Path, url: str) -> str:
    """Retorna la ruta del modelo, descargándolo si no existe en disco."""
    ruta_modelo = Path(ruta_modelo).resolve()
    if not ruta_modelo.exists():
        ruta_modelo.parent.mkdir(parents=True, exist_ok=True)
        print(f"Descargando modelo MediaPipe desde: {url}...")
        urllib.request.urlretrieve(url, str(ruta_modelo))
        print(f"[OK] Modelo guardado en: {ruta_modelo}")
    return str(ruta_modelo)


# Inicialización de modelos en memoria (Singleton en el runtime)
face_model_path = _obtener_modelo(MODELS_DIR / "face_landmarker.task", FACE_LANDMARKER_URL)
pose_model_path = _obtener_modelo(MODELS_DIR / "pose_landmarker.task", POSE_LANDMARKER_URL)

face_options = vision.FaceLandmarkerOptions(
    base_options=python.BaseOptions(model_asset_path=face_model_path),
    output_face_blendshapes=True,
    output_facial_transformation_matrixes=True,
    num_faces=1,
)
face_landmarker = vision.FaceLandmarker.create_from_options(face_options)

pose_options = vision.PoseLandmarkerOptions(
    base_options=python.BaseOptions(model_asset_path=pose_model_path),
    num_poses=1,
)
pose_landmarker = vision.PoseLandmarker.create_from_options(pose_options)


def _extraer_blendshapes(blendshapes_list) -> Dict[str, float]:
    if not blendshapes_list or len(blendshapes_list) == 0:
        return {}
    return {cat.category_name: cat.score for cat in blendshapes_list[0]}


@app.get("/health")
def health_check():
    """Endpoint de verificación de salud para Azure Container Apps."""
    return {"status": "healthy", "service": "ca-vision-service", "models_loaded": True}


@app.post("/analyze-frame")
async def analyze_frame(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Analiza un frame individual (JPEG/PNG/WebP) y calcula métricas de contacto visual,
    alineación postural, ladeo de cabeza y tensión facial.
    """
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="El archivo recibido está vacío.")

        np_arr = np.frombuffer(file_bytes, np.uint8)
        img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise HTTPException(status_code=400, detail="No se pudo decodificar la imagen.")

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)

        # Inferencia MediaPipe
        face_res = face_landmarker.detect(mp_image)
        pose_res = pose_landmarker.detect(mp_image)

        face_landmarks = face_res.face_landmarks[0] if face_res.face_landmarks else None
        blendshapes = _extraer_blendshapes(face_res.face_blendshapes)
        pose_landmarks = pose_res.pose_landmarks[0] if pose_res.pose_landmarks else None

        # Valores por defecto cuando no se detecta rostro
        face_detected = face_landmarks is not None
        pose_detected = pose_landmarks is not None

        eye_contact = False
        gaze_detail = "no_face_detected" if not face_detected else "desvio_mirada"
        rx_l, rx_r = 0.5, 0.5

        if face_detected:
            # 1. Contacto Visual (Gaze Tracking)
            x_iris_l = face_landmarks[IRIS_LEFT_CENTER].x
            x_inner_l = face_landmarks[EYE_LEFT_INNER].x
            x_outer_l = face_landmarks[EYE_LEFT_OUTER].x
            span_l = max(x_inner_l, x_outer_l) - min(x_inner_l, x_outer_l)
            rx_l = (x_iris_l - min(x_inner_l, x_outer_l)) / (span_l + 1e-6)

            x_iris_r = face_landmarks[IRIS_RIGHT_CENTER].x
            x_inner_r = face_landmarks[EYE_RIGHT_INNER].x
            x_outer_r = face_landmarks[EYE_RIGHT_OUTER].x
            span_r = max(x_inner_r, x_outer_r) - min(x_inner_r, x_outer_r)
            rx_r = (x_iris_r - min(x_inner_r, x_outer_r)) / (span_r + 1e-6)

            blink_left = blendshapes.get("eyeBlinkLeft", 0.0)
            blink_right = blendshapes.get("eyeBlinkRight", 0.0)
            ojos_abiertos = blink_left < 0.60 and blink_right < 0.60

            eye_contact = bool(
                ojos_abiertos and (0.40 <= rx_l <= 0.60) and (0.40 <= rx_r <= 0.60)
            )

            if not ojos_abiertos:
                gaze_detail = "ojos_cerrados"
            elif rx_l < 0.40 or rx_r < 0.40:
                gaze_detail = "mirada_hacia_lado_izquierdo"
            elif rx_l > 0.60 or rx_r > 0.60:
                gaze_detail = "mirada_hacia_lado_derecho"
            else:
                gaze_detail = "mirada_directa"

        # 2. Alineación de hombros (Pose)
        shoulder_angle = 0.0
        if pose_detected and len(pose_landmarks) > max(SHOULDER_LEFT, SHOULDER_RIGHT):
            y11, x11 = pose_landmarks[SHOULDER_LEFT].y, pose_landmarks[SHOULDER_LEFT].x
            y12, x12 = pose_landmarks[SHOULDER_RIGHT].y, pose_landmarks[SHOULDER_RIGHT].x
            dx = abs(x12 - x11)
            dy = abs(y12 - y11)
            if dx > 1e-5:
                shoulder_angle = round(math.degrees(math.atan2(dy, dx)), 2)

        # 3. Ladeo de cabeza (FaceMesh)
        head_roll_angle = 0.0
        if face_detected:
            p_nariz = face_landmarks[NOSE_TIP]
            p_menton = face_landmarks[CHIN]
            dx_cabeza = p_menton.x - p_nariz.x
            dy_cabeza = p_menton.y - p_nariz.y
            head_roll_angle = round(abs(math.degrees(math.atan2(dx_cabeza, dy_cabeza))), 2)

        # 4. Tensión facial (AU4 Brow Down + AU24 Mouth Press)
        brow_down = (blendshapes.get("browDownLeft", 0.0) + blendshapes.get("browDownRight", 0.0)) / 2.0
        mouth_press = (blendshapes.get("mouthPressLeft", 0.0) + blendshapes.get("mouthPressRight", 0.0)) / 2.0
        facial_tension_index = round((brow_down + mouth_press) / 2.0, 3)

        # 5. Score de estabilidad postural
        penalizacion_hombros = max(0.0, shoulder_angle - 5.0) * 3.0
        penalizacion_cabeza = max(0.0, head_roll_angle - 8.0) * 3.0
        posture_stability_score = round(max(0.0, min(100.0, 100.0 - penalizacion_hombros - penalizacion_cabeza)), 1)

        return {
            "face_detected": face_detected,
            "pose_detected": pose_detected,
            "eye_contact": eye_contact,
            "mirada_directa": eye_contact,
            "gaze_detail": gaze_detail,
            "shoulder_angle": shoulder_angle,
            "angulo_hombros": shoulder_angle,
            "head_roll_angle": head_roll_angle,
            "angulo_cabeza": head_roll_angle,
            "facial_tension_index": facial_tension_index,
            "indice_tension": facial_tension_index,
            "posture_stability_score": posture_stability_score,
            "estabilidad_score": posture_stability_score,
            "rx_left": round(rx_l, 2),
            "rx_right": round(rx_r, 2),
        }

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error procesando frame: {str(e)}", "face_detected": False}
        )
