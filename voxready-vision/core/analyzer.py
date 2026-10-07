import os
import cv2
import numpy as np
import mediapipe as mp
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

FACE_LANDMARKER_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
POSE_LANDMARKER_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"


def _garantizar_modelo(ruta_modelo: Path, url: str) -> str:
    """Descarga el modelo si no existe localmente."""
    ruta_modelo = Path(ruta_modelo).resolve()
    if not ruta_modelo.exists():
        ruta_modelo.parent.mkdir(parents=True, exist_ok=True)
        import urllib.request
        print(f"--> Descargando modelo MediaPipe desde: {url}...")
        urllib.request.urlretrieve(url, str(ruta_modelo))
        print(f"[OK] Modelo guardado en: {ruta_modelo}")
    return str(ruta_modelo)


class MultimodalVisionAnalyzer:
    """
    Motor de análisis multimodal de visión computacional para lenguaje corporal y presencia (VISUM).
    Audita variables operacionales:
      1. Contacto visual (vector de mirada e iris respecto a centro nasal).
      2. Simetría e inclinación de hombros (shoulder_slope).
      3. Gesticulación (visibilidad de muñecas y zona de gesticulación ilustrativa sobre cadera).
      4. Estabilidad corporal (centro gravitacional del torso y balanceo lateral body_sway_std).
    """

    def __init__(self, models_dir: Optional[Union[str, Path]] = None):
        self.use_solutions = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")

        if self.use_solutions:
            # Runtime clásico (MediaPipe 0.10.x / Linux standard)
            self.mp_face_mesh = mp.solutions.face_mesh
            self.mp_pose = mp.solutions.pose

            self.face_mesh = self.mp_face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5
            )
            self.pose = self.mp_pose.Pose(
                static_image_mode=True,
                model_complexity=1,
                enable_segmentation=False,
                min_detection_confidence=0.5
            )
        else:
            # Runtime alternativo moderno (MediaPipe Tasks)
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            if models_dir is None:
                models_dir = Path(__file__).resolve().parent.parent / "models"
            self.models_dir = Path(models_dir)

            face_model_path = _garantizar_modelo(
                self.models_dir / "face_landmarker.task",
                FACE_LANDMARKER_URL
            )
            pose_model_path = _garantizar_modelo(
                self.models_dir / "pose_landmarker.task",
                POSE_LANDMARKER_URL
            )

            face_opts = vision.FaceLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=face_model_path),
                num_faces=1
            )
            pose_opts = vision.PoseLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=pose_model_path),
                num_poses=1
            )
            self.face_landmarker = vision.FaceLandmarker.create_from_options(face_opts)
            self.pose_landmarker = vision.PoseLandmarker.create_from_options(pose_opts)

    def process_frame(self, image_input: Union[bytes, np.ndarray]) -> Dict[str, Any]:
        """
        Procesa un único fotograma en memoria y extrae métricas de rostro, postura y manos.
        Acepta bytes (JPEG/PNG/WebP) o ndarray.
        """
        if isinstance(image_input, bytes):
            nparr = np.frombuffer(image_input, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        elif isinstance(image_input, np.ndarray):
            frame = image_input
        else:
            return {"valid": False}

        if frame is None or frame.size == 0:
            return {"valid": False}

        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        eye_contact = False
        pose_detected = False
        shoulder_slope = 0.0
        torso_center_x = 0.5
        hands_visible = False
        hands_active = False

        if self.use_solutions:
            # 1. Contacto Visual (Face Mesh)
            face_results = self.face_mesh.process(rgb_frame)
            if face_results.multi_face_landmarks:
                landmarks = face_results.multi_face_landmarks[0].landmark
                left_iris = landmarks[468]
                right_iris = landmarks[473]
                nose_tip = landmarks[1]

                # Desviación relativa horizontal del iris respecto al centro nasal
                gaze_offset_x = abs(((left_iris.x + right_iris.x) / 2.0) - nose_tip.x)
                eye_contact = bool(gaze_offset_x < 0.04)

            # 2. Análisis Corporal y Gesticulación (Pose Landmarks)
            pose_results = self.pose.process(rgb_frame)
            if pose_results.pose_landmarks:
                pose_detected = True
                pl = pose_results.pose_landmarks.landmark

                # 11: hombro izquierdo, 12: hombro derecho
                # 15: muñeca izquierda, 16: muñeca derecha
                # 23: cadera izquierda, 24: cadera derecha
                l_shoulder = pl[11]
                r_shoulder = pl[12]
                l_wrist = pl[15]
                r_wrist = pl[16]
                l_hip = pl[23]
                r_hip = pl[24]

                shoulder_slope = abs(l_shoulder.y - r_shoulder.y)
                torso_center_x = (l_shoulder.x + r_shoulder.x) / 2.0

                l_visible = l_wrist.visibility > 0.5
                r_visible = r_wrist.visibility > 0.5
                hands_visible = bool(l_visible or r_visible)

                hip_avg_y = (l_hip.y + r_hip.y) / 2.0
                l_active = l_visible and (l_wrist.y < hip_avg_y)
                r_active = r_visible and (r_wrist.y < hip_avg_y)
                hands_active = bool(l_active or r_active)

        else:
            # Runtime mediapipe.tasks
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            face_results = self.face_landmarker.detect(mp_image)
            if face_results.face_landmarks:
                landmarks = face_results.face_landmarks[0]
                left_iris = landmarks[468]
                right_iris = landmarks[473]
                nose_tip = landmarks[1]

                gaze_offset_x = abs(((left_iris.x + right_iris.x) / 2.0) - nose_tip.x)
                eye_contact = bool(gaze_offset_x < 0.04)

            pose_results = self.pose_landmarker.detect(mp_image)
            if pose_results.pose_landmarks:
                pose_detected = True
                pl = pose_results.pose_landmarks[0]

                l_shoulder = pl[11]
                r_shoulder = pl[12]
                l_wrist = pl[15]
                r_wrist = pl[16]
                l_hip = pl[23]
                r_hip = pl[24]

                shoulder_slope = abs(l_shoulder.y - r_shoulder.y)
                torso_center_x = (l_shoulder.x + r_shoulder.x) / 2.0

                l_vis = getattr(l_wrist, "visibility", 0.0) or 0.0
                r_vis = getattr(r_wrist, "visibility", 0.0) or 0.0
                l_visible = l_vis > 0.5
                r_visible = r_vis > 0.5
                hands_visible = bool(l_visible or r_visible)

                hip_avg_y = (l_hip.y + r_hip.y) / 2.0
                l_active = l_visible and (l_wrist.y < hip_avg_y)
                r_active = r_visible and (r_wrist.y < hip_avg_y)
                hands_active = bool(l_active or r_active)

        return {
            "valid": True,
            "eye_contact": bool(eye_contact),
            "pose_detected": bool(pose_detected),
            "shoulder_slope": float(shoulder_slope),
            "torso_center_x": float(torso_center_x),
            "hands_visible": bool(hands_visible),
            "hands_active": bool(hands_active)
        }

    def aggregate_metrics(self, frame_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Agrega la serie temporal de fotogramas en las variables operacionales de VISUM.
        """
        valid_frames = [f for f in frame_results if f.get("valid")]
        total_frames = len(valid_frames)
        if total_frames == 0:
            return {
                "eye_contact_pct": 0.0,
                "hands_visible_pct": 0.0,
                "hands_active_pct": 0.0,
                "shoulder_stability_score": 0.0,
                "body_sway_std": 0.0,
                "total_frames_analyzed": 0
            }

        eye_contact_count = sum(1 for f in valid_frames if f.get("eye_contact"))
        hands_visible_count = sum(1 for f in valid_frames if f.get("hands_visible"))
        hands_active_count = sum(1 for f in valid_frames if f.get("hands_active"))

        # Cálculo de estabilidad postural (inclinación media de hombros)
        slopes = [f["shoulder_slope"] for f in valid_frames if f.get("pose_detected")]
        avg_shoulder_slope = float(np.mean(slopes)) if slopes else 0.0
        # Mapeo a score: pendientes menores a 0.03 representan postura balanceada (100)
        shoulder_stability = max(0.0, 100.0 - (avg_shoulder_slope * 1500.0))

        # Balanceo lateral del torso (desviación estándar del centro X)
        torso_x_series = [f["torso_center_x"] for f in valid_frames if f.get("pose_detected")]
        body_sway_std = float(np.std(torso_x_series)) if len(torso_x_series) > 1 else 0.0

        return {
            "eye_contact_pct": round((eye_contact_count / total_frames) * 100.0, 2),
            "hands_visible_pct": round((hands_visible_count / total_frames) * 100.0, 2),
            "hands_active_pct": round((hands_active_count / total_frames) * 100.0, 2),
            "shoulder_stability_score": round(shoulder_stability, 2),
            "body_sway_std": round(body_sway_std, 4),
            "total_frames_analyzed": total_frames
        }

    @staticmethod
    def calculate_expression_area_score(vision_summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calcula el puntaje de 0 a 100 para el área 'expression' según los criterios de VISUM:
        - Contacto visual: 40%
        - Estabilidad corporal y postura: 30%
        - Gesticulación (visibilidad y actividad de manos): 30%
        """
        eye_pct = float(vision_summary.get("eye_contact_pct", vision_summary.get("contacto_visual_porcentaje", 0.0)))
        shoulder_score = float(vision_summary.get("shoulder_stability_score", vision_summary.get("posture_stability_score", 100.0)))
        sway_std = float(vision_summary.get("body_sway_std", 0.0))
        hands_vis_pct = float(vision_summary.get("hands_visible_pct", 0.0))
        hands_act_pct = float(vision_summary.get("hands_active_pct", 0.0))

        # 1. Puntuación de postura y estabilidad (penaliza balanceo lateral > 0.04)
        sway_penalty = min(40.0, sway_std * 800.0)
        body_stability_final = max(0.0, shoulder_score - sway_penalty)

        # 2. Puntuación de gesticulación
        # Premia que las manos sean visibles y se usen activamente sin exceso estático
        gesticulation_score = (hands_vis_pct * 0.5) + (hands_act_pct * 0.5)

        # 3. Ponderación interna del área
        final_expression_score = (
            (eye_pct * 0.40) +
            (body_stability_final * 0.30) +
            (gesticulation_score * 0.30)
        )

        return {
            "score": round(max(0.0, min(100.0, final_expression_score)), 2),
            "metrics": {
                "contacto_visual_pct": eye_pct,
                "estabilidad_postural": round(body_stability_final, 2),
                "manos_visibles_pct": hands_vis_pct,
                "gesticulacion_activa_pct": hands_act_pct,
                "balanceo_torso_std": sway_std
            }
        }
