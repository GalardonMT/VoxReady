import os
import sys
import io
import cv2
import json
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.analyzer import MultimodalVisionAnalyzer
from core.report_builder import ReportBuilder, calculate_expression_area_score
from video.main import EvaluadorExpresionVideo, procesar_metricas_video


def test_poc_sintetico():
    print("==================================================================")
    print("  PRUEBA 1: SUITE DE VERIFICACIÓN SINTÉTICA (VISUM SMOKE TEST)")
    print("==================================================================")

    analyzer = MultimodalVisionAnalyzer()

    # 1. Crear fotograma sintético con dimensiones estándar (640x480)
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    dummy_img[:] = (200, 200, 200) # Fondo neutro
    cv2.circle(dummy_img, (320, 180), 60, (150, 120, 100), -1) # Rostro simulado

    _, buffer = cv2.imencode('.jpg', dummy_img)
    img_bytes = buffer.tobytes()

    # Probar process_frame tanto con bytes como con numpy array
    res_bytes = analyzer.process_frame(img_bytes)
    res_np = analyzer.process_frame(dummy_img)

    assert res_bytes.get("valid") is True, "El frame no fue reconocido como válido"
    assert "eye_contact" in res_bytes, "Falta clave 'eye_contact'"
    assert "hands_visible" in res_bytes, "Falta clave 'hands_visible'"
    assert "hands_active" in res_bytes, "Falta clave 'hands_active'"
    assert "shoulder_slope" in res_bytes, "Falta clave 'shoulder_slope'"
    assert "torso_center_x" in res_bytes, "Falta clave 'torso_center_x'"
    print("  [OK] process_frame() retorna todas las variables operacionales.")

    # 2. Agregar métricas de una secuencia sintética
    batch_results = [
        # Frame 1: buen contacto, postura recta, manos visibles y activas
        {
            "valid": True,
            "eye_contact": True,
            "pose_detected": True,
            "shoulder_slope": 0.015,
            "torso_center_x": 0.50,
            "hands_visible": True,
            "hands_active": True
        },
        # Frame 2: contacto directo, ligera inclinación, manos visibles pero inactivas
        {
            "valid": True,
            "eye_contact": True,
            "pose_detected": True,
            "shoulder_slope": 0.025,
            "torso_center_x": 0.51,
            "hands_visible": True,
            "hands_active": False
        },
        # Frame 3: desvío mirada, manos ocultas bajo la mesa
        {
            "valid": True,
            "eye_contact": False,
            "pose_detected": True,
            "shoulder_slope": 0.020,
            "torso_center_x": 0.49,
            "hands_visible": False,
            "hands_active": False
        },
        # Frame 4: contacto directo, manos activas
        {
            "valid": True,
            "eye_contact": True,
            "pose_detected": True,
            "shoulder_slope": 0.018,
            "torso_center_x": 0.50,
            "hands_visible": True,
            "hands_active": True
        }
    ]

    summary = analyzer.aggregate_metrics(batch_results)
    print("\n  Summary agregado de la secuencia sintética:")
    print(json.dumps(summary, indent=4))

    # 3. Aserciones oficiales requeridas por el Playbook VISUM (Fase 5)
    assert 'hands_visible_pct' in summary, "Falta hands_visible_pct"
    assert 'hands_active_pct' in summary, "Falta hands_active_pct"
    assert 'shoulder_stability_score' in summary, "Falta shoulder_stability_score"
    assert 'body_sway_std' in summary, "Falta body_sway_std"
    assert 'eye_contact_pct' in summary, "Falta eye_contact_pct"
    assert summary["total_frames_analyzed"] == 4, "total_frames_analyzed incorrecto"

    assert summary["eye_contact_pct"] == 75.0, f"eye_contact_pct esperado 75.0, obtenido {summary['eye_contact_pct']}"
    assert summary["hands_visible_pct"] == 75.0, f"hands_visible_pct esperado 75.0, obtenido {summary['hands_visible_pct']}"
    assert summary["hands_active_pct"] == 50.0, f"hands_active_pct esperado 50.0, obtenido {summary['hands_active_pct']}"
    print("  [OK] Aserciones de agregación VISUM superadas exitosamente.")

    # 4. Ponderación oficial de Expresión (Fase 3: 40% contacto, 30% postura/estabilidad, 30% gesticulación)
    calc_expression = calculate_expression_area_score(summary)
    print("\n  Cálculo de Área 'expression' (VISUM 40/30/30):")
    print(json.dumps(calc_expression, indent=4))

    assert "score" in calc_expression, "Falta score en cálculo de expresión"
    assert "metrics" in calc_expression, "Falta metrics en cálculo de expresión"
    assert calc_expression["score"] > 0, "El score debe ser mayor a 0"
    print("  [OK] calculate_expression_area_score() validado exitosamente.\n")


def test_poc_video_real():
    print("==================================================================")
    print("  PRUEBA 2: EVALUACIÓN DE VIDEO REAL CON MEDIAPIPE (POC VISUM)")
    print("==================================================================")

    video_path = BASE_DIR / "grabaciones" / "session-crisis-1790373240648.webm"
    if not video_path.exists():
        print(f"  [SKIP] No se encontró el video en {video_path}")
        return

    print(f"  Video encontrado: {video_path.name}")
    temp_frames_dir = BASE_DIR / "outputs" / "poc_temp_frames"
    temp_frames_dir.mkdir(parents=True, exist_ok=True)

    # Extraer fotogramas a 0.5 FPS (1 fotograma cada 2 segundos) para probar
    cap = cv2.VideoCapture(str(video_path))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    intervalo_frames = int(video_fps * 2.0) # cada 2 segundos

    saved_frames = []
    frame_idx = 0
    saved_count = 0
    max_test_frames = 10 # Limitar a 10 fotogramas para prueba de concepto ágil

    while True:
        ret, frame = cap.read()
        if not ret or saved_count >= max_test_frames:
            break
        if frame_idx % intervalo_frames == 0:
            frame_filename = temp_frames_dir / f"poc_frame_{saved_count:04d}.jpg"
            cv2.imwrite(str(frame_filename), frame)
            saved_frames.append(str(frame_filename))
            saved_count += 1
        frame_idx += 1
    cap.release()

    print(f"  [OK] {len(saved_frames)} fotogramas extraídos a 0.5 FPS.")

    # Ejecutar el procesador completo de video actualizado
    evaluador = EvaluadorExpresionVideo()
    resultado = evaluador.procesar_frames(frames_input=saved_frames, fps=0.5)

    print("\n  --- Resultados Cuantitativos VISUM ---")
    print(f"  Total frames evaluados: {resultado['total_frames_analizados']}")
    print(f"  Score Expresión VISUM:  {resultado['score_area_expresion']}/100")
    
    visum_summary = resultado.get("visum_summary", {})
    print(f"  - Contacto Visual:       {visum_summary.get('eye_contact_pct')}%")
    print(f"  - Manos Visibles:        {visum_summary.get('hands_visible_pct')}%")
    print(f"  - Gesticulación Activa:  {visum_summary.get('hands_active_pct')}%")
    print(f"  - Estabilidad Postural:  {visum_summary.get('shoulder_stability_score')}/100")
    print(f"  - Balanceo Torso (Std):  {visum_summary.get('body_sway_std')}")

    print(f"\n  Total de tuplas de eventos detectadas: {len(resultado['tuplas_eventos_detectados'])}")
    tuplas_gest = resultado["desglose_tuplas_por_eje"].get("gesticulacion", [])
    print(f"  Eventos de gesticulación ({len(tuplas_gest)}):")
    for tg in tuplas_gest[:5]:
        print(f"    • {tg}")

    # Validar aserciones estructurales
    assert "visum_summary" in resultado, "Falta visum_summary en el resultado"
    assert "evaluacion_expresion_visum" in resultado, "Falta evaluacion_expresion_visum"
    assert "gesticulacion" in resultado["desglose_tuplas_por_eje"], "Falta eje gesticulacion en desglose"
    print("\n  [OK] Evaluación de video real con MediaPipe completada con éxito.")

    # Limpiar frames temporales
    for f in temp_frames_dir.glob("poc_frame_*.jpg"):
        try:
            f.unlink()
        except Exception:
            pass


def test_poc_consolidacion_report_builder():
    print("\n==================================================================")
    print("  PRUEBA 3: INTEGRACIÓN DE FUSIÓN CON ReportBuilder (VISUM)")
    print("==================================================================")

    mock_vision = {
        "score_area_expresion": 78.5,
        "visum_summary": {
            "eye_contact_pct": 82.0,
            "hands_visible_pct": 70.0,
            "hands_active_pct": 60.0,
            "shoulder_stability_score": 92.0,
            "body_sway_std": 0.021,
            "total_frames_analyzed": 10
        }
    }

    mock_audio = {
        "metrics": {
            "score_fluidez": 80.0,
            "score_diccion": 95.0,
            "wpm": 135
        }
    }

    mock_llm = {
        "puntaje_global_100": 85.0,
        "dimensiones": {
            "alineacion_mensaje_clave": {"score_100": 88.0},
            "tecnicas_control": {"score_100": 82.0},
            "asertividad_hostilidad": {"score_100": 80.0}
        }
    }

    consolidated = ReportBuilder.build_consolidated_report(
        session_id="session-poc-visum-123",
        video_name="session-crisis-poc.webm",
        vision_result=mock_vision,
        audio_result=mock_audio,
        llm_result=mock_llm
    )

    print("  Reporte Consolidado generado:")
    print(f"  - Score General: {consolidated['puntuacion_global']['score_general']}/100")
    print(f"  - Desglose Áreas: {consolidated['puntuacion_global']['areas']}")
    print(f"  - Expresión VISUM: {consolidated['evaluacion_expresion_visum']}")

    areas = consolidated["puntuacion_global"]["areas"]
    assert "expression" in areas, "Falta área expression"
    assert "voice" in areas, "Falta área voice"
    assert "coherence" in areas, "Falta área coherence"
    assert "empathy" in areas, "Falta área empathy"

    print("  [OK] Fusión multi-área con ReportBuilder validada exitosamente.\n")


if __name__ == "__main__":
    test_poc_sintetico()
    test_poc_video_real()
    test_poc_consolidacion_report_builder()
    print("==================================================================")
    print("  ¡TODAS LAS PRUEBAS DE CONCEPTO MEDIAPIPE VISUM FUERON SUPERADAS!")
    print("==================================================================")
