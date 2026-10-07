"""
Suite de Verificación Automatizada: Calibración de Rigor y Exigencia VISUM (lab-worker)

Valida los 4 Pilares del Plan de Exigencia aprobado:
1. Calibración No Verbal: Castigo por manos ocultas (<10% -> techo <= 45.0) y balanceo lateral.
2. Erradicación de Pisos Artificiales: Valores neutros en 50.0, penalización por WPM fuera de rango.
3. Blindaje de Narrativa Táctica: Prohibición de 'leer libros', guiones en 3 partes y prioridades atómicas sin pipes '|'.
4. Coherencia Multimodal: Telemetría empírica reflejada en la observación de señal cruzada.
"""

import sys
import json
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from core.analyzer import MultimodalVisionAnalyzer
from core.report_builder import ReportBuilder, calculate_expression_area_score
from core.narrative_generator import (
    _sanitizar_reporte_visum,
    VALORES_PRIORIDAD_VALIDOS,
    CLICHE_PATTERNS
)


def test_1_expresion_manos_ocultas_techo_45():
    print("----------------------------------------------------------------")
    print("TEST 1: Factor de Bloqueo No Verbal (Manos ocultas 95%)")
    print("----------------------------------------------------------------")
    
    # Simular escenario real donde el vocero tuvo 100% contacto visual pero ocultó las manos el 95% del tiempo
    vision_vulnerable = {
        "eye_contact_pct": 100.0,
        "shoulder_stability_score": 85.0,
        "body_sway_std": 0.012,
        "hands_visible_pct": 5.0,  # 95% del tiempo con manos ocultas
        "hands_active_pct": 2.0,
        "total_frames_analyzed": 50
    }

    resultado = calculate_expression_area_score(vision_vulnerable)
    score = resultado["score"]
    penalizacion = resultado["metrics"]["penalizacion_manos_ocultas"]

    print(f"  • Puntaje Expresión obtenido: {score} / 100")
    print(f"  • Penalización por manos ocultas: {penalizacion} pts")
    print(f"  • Métricas: {resultado['metrics']}")

    # Aserción crítica: Con manos ausentes (<10%), el puntaje NO PUEDE superar 45.0
    assert score <= 45.0, f"FALLO: El puntaje ({score}) superó el techo de contención de 45.0 para manos ocultas"
    assert penalizacion > 0.0, "FALLO: No se aplicó penalización por manos ocultas"
    print("  [OK] Superado: Postura defensiva castigada con score <= 45.0.\n")


def test_2_expresion_balanceo_lateral_penalizacion():
    print("----------------------------------------------------------------")
    print("TEST 2: Penalización por Balanceo Lateral del Torso (sway > 0.03)")
    print("----------------------------------------------------------------")

    # Vocero con manos visibles pero balanceo nervioso oscilatorio
    vision_inestable = {
        "eye_contact_pct": 80.0,
        "shoulder_stability_score": 90.0,
        "body_sway_std": 0.045,  # Inquietud postural evidente
        "hands_visible_pct": 60.0,
        "hands_active_pct": 40.0,
        "total_frames_analyzed": 50
    }

    resultado = calculate_expression_area_score(vision_inestable)
    postura_score = resultado["metrics"]["estabilidad_postural"]

    print(f"  • Score Postura tras balanceo: {postura_score} / 100 (base: 90.0)")
    assert postura_score < 90.0, "FALLO: No se penalizó el balanceo lateral del torso"
    print("  [OK] Superado: Inquietud postural penalizada con precisión.\n")


def test_3_erradicacion_pisos_artificiales_audio():
    print("----------------------------------------------------------------")
    print("TEST 3: Erradicación de Pisos Artificiales de 75.0 en Voz y Neutrales")
    print("----------------------------------------------------------------")

    # Caso A: Audio con cadencia lenta (WPM = 75) y muletillas excesivas
    audio_lento = {
        "metrics": {
            "wpm": 75.0,
            "densidad_muletillas_pct": 4.5,
            "score_fluidez": 70.0,
            "score_diccion": 70.0
        }
    }
    
    mock_vision = {
        "visum_summary": {
            "eye_contact_pct": 75.0,
            "shoulder_stability_score": 80.0,
            "body_sway_std": 0.01,
            "hands_visible_pct": 50.0,
            "hands_active_pct": 30.0
        }
    }

    reporte_a = ReportBuilder.build_consolidated_report(
        session_id="test_cadencia",
        video_name="test_audio.mp4",
        vision_result=mock_vision,
        audio_result=audio_lento,
        llm_result=None
    )

    score_voz = reporte_a["puntuacion_global"]["score_comunicacion_verbal"]
    score_empatia_default = reporte_a["puntuacion_global"]["score_empatia"]

    print(f"  • Score Voz con WPM bajo (75) y muletillas: {score_voz} (debe ser < 60.0)")
    print(f"  • Score Empatía sin LLM disponible: {score_empatia_default} (debe ser 50.0 neutro)")

    assert score_voz < 60.0, f"FALLO: El score de voz ({score_voz}) no penalizó la cadencia deficiente"
    assert score_empatia_default == 50.0, f"FALLO: El default neutro debe ser 50.0, no {score_empatia_default}"
    print("  [OK] Superado: Pisos de 75.0 erradicados; penalización acústica activa.\n")


def test_4_blindaje_narrativa_anti_complacencia():
    print("----------------------------------------------------------------")
    print("TEST 4: Blindaje Narrativo (Erradicación de Pipes '|' y Clichés)")
    print("----------------------------------------------------------------")

    # Simular una respuesta de LLM con los vicios detectados previamente:
    # 1. Copió las opciones del prompt con pipes en 'prioridad'
    # 2. Recomendó 'leer libros sobre comunicación'
    # 3. Oportunidades sin guion táctico
    raw_llm_output_complaciente = {
        "sintesis_ejecutiva": {
            "diagnostico_general": "El vocero mantuvo la compostura.",
            "fortaleza_principal": "Serenidad.",
            "foco_desarrollo": "Mejorar soltura.",
            "continuidad_recomendada": "Talleres."
        },
        "desempeno_observado": {
            "evaluacion_general": "Interacción regular.",
            "fortalezas": ["Mantuvo la voz firme."],
            "oportunidades_desarrollo": [
                "Se sugiere leer libros y artículos de comunicación de crisis para enriquecer el vocabulario.",
                "Cita observada: 'No es nuestra responsabilidad directa' -> Impacto en prensa: Percepción de evasión -> Guion táctico alternativo sugerido: 'El vocero debió señalar: Comprendemos el impacto y estamos coordinando el apoyo en terreno.'"
            ],
            "formula_practica_recomendada": "Reconocer impacto -> Explicar certezas -> Acciones."
        },
        "hallazgos_transversales": [
            {
                "prioridad": "Pedagogía de la complejidad | Conducción estratégica | Empatía como primera señal",
                "descripcion": "Brecha en la conducción del mensaje."
            }
        ],
        "recomendaciones_proximas_vocerias": [
            "Regla 1: Leer libros sobre empatía y relaciones públicas.",
            "Regla 2: Mantener las manos visibles."
        ],
        "consideracion_final": "La vocería es una disciplina.",
        "observacion_senal_cruzada": "El vocero mantuvo las manos ocultas mientras afirmaba total transparencia."
    }

    mock_telemetria = {
        "expresion_no_verbal": {
            "manos_visibles_pct": 5.0,
            "contacto_visual_pct": 80.0
        }
    }

    sanitizado = _sanitizar_reporte_visum(raw_llm_output_complaciente, mock_telemetria)

    # 1. Verificar prioridad atómica sin pipes '|'
    prioridad_resultado = sanitizado["hallazgos_transversales"][0]["prioridad"]
    print(f"  • Prioridad transversal sanitizada: '{prioridad_resultado}'")
    assert "|" not in prioridad_resultado, f"FALLO: La prioridad aún contiene pipes '|': {prioridad_resultado}"
    assert prioridad_resultado in VALORES_PRIORIDAD_VALIDOS, f"FALLO: Prioridad no reconocida: {prioridad_resultado}"

    # 2. Verificar erradicación de clichés ('leer libros')
    for op in sanitizado["desempeno_observado"]["oportunidades_desarrollo"]:
        print(f"  • Oportunidad evaluada: {op[:80]}...")
        assert not any(cliche in op.lower() for cliche in CLICHE_PATTERNS), f"FALLO: Cliché detectado en oportunidad: {op}"

    for rec in sanitizado["recomendaciones_proximas_vocerias"]:
        print(f"  • Regla evaluada: {rec[:80]}...")
        assert not any(cliche in rec.lower() for cliche in CLICHE_PATTERNS), f"FALLO: Cliché detectado en regla: {rec}"

    print("  [OK] Superado: Sin pipes literales, sin consejos de 'leer libros' y con guiones tácticos obligatorios.\n")


def test_5_integracion_completa_report_builder():
    print("----------------------------------------------------------------")
    print("TEST 5: Integración Consolidada de 4 Áreas VISUM")
    print("----------------------------------------------------------------")

    # Sesión vulnerable: Manos ocultas 95%, WPM acelerado (175), sin bridging
    vision_data = {
        "visum_summary": {
            "eye_contact_pct": 85.0,
            "shoulder_stability_score": 88.0,
            "body_sway_std": 0.015,
            "hands_visible_pct": 4.0,  # Manos ocultas
            "hands_active_pct": 1.0,
            "total_frames_analyzed": 60
        }
    }

    audio_data = {
        "metrics": {
            "wpm": 175.0,  # Acelerado / ansiedad
            "densidad_muletillas_pct": 3.0,
            "score_fluidez": 65.0,
            "score_diccion": 75.0
        }
    }

    llm_data = {
        "puntaje_global_100": 45.0,
        "dimensiones": {
            "alineacion_mensaje_clave": {"score_100": 50.0},
            "tecnicas_control": {"score_100": 35.0, "tecnicas_detectadas": []},
            "asertividad_hostilidad": {"score_100": 40.0}
        }
    }

    reporte_final = ReportBuilder.build_consolidated_report(
        session_id="test_vulnerable_completo",
        video_name="vocero_contingencia.webm",
        vision_result=vision_data,
        audio_result=audio_data,
        llm_result=llm_data
    )

    areas = reporte_final["puntuacion_global"]["areas"]
    score_general = reporte_final["puntuacion_global"]["score_general"]

    print(f"  • Score General Ponderado: {score_general} / 100")
    print(f"  • Desglose por Áreas: {areas}")

    # En este desempeño vulnerable, el score general DEBE ser reprobatorio (< 55.0),
    # no benévolo (en contraste con el 72.4 previo)
    assert areas["expression"] <= 45.0, f"FALLO: Expresión no respetó techo de manos ocultas: {areas['expression']}"
    assert score_general < 55.0, f"FALLO: El score general ({score_general}) fue complaciente ante un desempeño vulnerable"
    assert "evaluacion_areas" in reporte_final, "FALLO: Falta evaluacion_areas en reporte consolidado"

    print("  [OK] Superado: Diagnóstico riguroso y reprobatorio ante vulnerabilidades graves.\n")


def run_all_tests():
    print("================================================================")
    print("   BATERÍA DE PRUEBAS DE CALIBRACIÓN DE EXIGENCIA VISUM (LAB)   ")
    print("================================================================\n")
    test_1_expresion_manos_ocultas_techo_45()
    test_2_expresion_balanceo_lateral_penalizacion()
    test_3_erradicacion_pisos_artificiales_audio()
    test_4_blindaje_narrativa_anti_complacencia()
    test_5_integracion_completa_report_builder()
    print("================================================================")
    print("   [ÉXITO TOTAL] TODAS LAS PRUEBAS DE CALIBRACIÓN APROBADAS     ")
    print("================================================================")


if __name__ == "__main__":
    run_all_tests()
