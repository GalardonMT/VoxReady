import os
import sys
import json
from pathlib import Path
from openai import OpenAI

# Asegurar path de imports
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# Cargar variables de entorno desde .env manualmente o vía dotenv
env_file = CURRENT_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lstrip('\ufeff')
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip().lstrip('\ufeff')
                v = v.strip().strip('"').strip("'")
                os.environ[k] = v

from core.narrative_generator import generate_visum_report

def run_test():
    nvidia_key = (os.environ.get("NVIDIA_API_KEY") or "").strip()
    nvidia_base_url = (os.environ.get("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1").strip()
    model_name = os.environ.get("LLM_MODEL_NAME") or "meta/llama-3.2-11b-vision-instruct"

    print("================================================================")
    print("  TEST: Generador de Informe Narrativo Ejecutivo VISUM (Lab)")
    print(f"  Modelo: {model_name}")
    print(f"  Endpoint: {nvidia_base_url}")
    print(f"  API Key presente: {bool(nvidia_key)}")
    print("================================================================\n")

    scenario_info = {
        "title": "Fuga de Gas y Evacuación Preventiva en Planta Norte",
        "context": "Se produjo un escape de gas odorizado en la línea de distribución secundaria. Se evacuaron 400 viviendas de forma preventiva sin víctimas fatales.",
        "optics": "Empática, institucional y de máxima transparencia operativa",
        "key_messages": [
            "La prioridad absoluta de la compañía es la seguridad de las familias del sector.",
            "Los equipos técnicos de emergencia ya aislaron el sector y el perímetro es seguro.",
            "Habilitamos canales directos de asistencia social y albergues temporales para los vecinos."
        ],
        "red_lines": [
            "No atribuir culpas a terceros ni especular sobre fallas de mantenimiento antes del peritaje.",
            "No comprometer horas exactas de restablecimiento del suministro hasta tener certificación técnica."
        ]
    }

    mock_consolidated = {
        "score_global": 79.5,
        "transcript": (
            "En primer lugar, quiero transmitir la total tranquilidad a todas las familias de la comunidad: "
            "nuestra prioridad número uno desde el primer minuto ha sido su seguridad e integridad. "
            "A esta hora podemos confirmar que la válvula afectada ya fue totalmente aislada y el perímetro "
            "se encuentra bajo estricto control de Bomberos y nuestros especialistas. Hemos habilitado el centro "
            "de asistencia comunitaria para apoyar a cada familia evacuada mientras se completan las pruebas de hermeticidad."
        ),
        "evaluacion_areas": {
            "expresion": {
                "score": 82.0,
                "contacto_visual_pct": 84.5,
                "postura_score": 92.0
            },
            "tono_voz": {
                "score": 76.0,
                "wpm": 132,
                "muletillas_count": 1,
                "pausas_silencio": 2
            },
            "contenido": {
                "score": 81.0,
                "adherencia_mensajes": 85,
                "control_crisis": 78
            },
            "empatia": {
                "score": 79.0,
                "bridging_detectado": True
            }
        }
    }

    client = OpenAI(base_url=nvidia_base_url, api_key=nvidia_key or "test-key", timeout=120.0)

    print("[1/3] Invocando generador VISUM con NVIDIA NIM...")
    reporte = generate_visum_report(
        client=client,
        model_name=model_name,
        scenario_info=scenario_info,
        consolidated_json=mock_consolidated
    )

    print("\n[2/3] Validando aserciones del esquema de respuesta VISUM...")
    assert "sintesis_ejecutiva" in reporte, "Falta 'sintesis_ejecutiva'"
    assert "diagnostico_general" in reporte["sintesis_ejecutiva"], "Falta 'diagnostico_general'"
    assert "fortaleza_principal" in reporte["sintesis_ejecutiva"], "Falta 'fortaleza_principal'"
    assert "foco_desarrollo" in reporte["sintesis_ejecutiva"], "Falta 'foco_desarrollo'"

    assert "desempeno_observado" in reporte, "Falta 'desempeno_observado'"
    assert len(reporte["desempeno_observado"]["fortalezas"]) >= 1, "Lista de fortalezas vacía"
    assert len(reporte["desempeno_observado"]["oportunidades_desarrollo"]) >= 1, "Lista de oportunidades vacía"
    assert "formula_practica_recomendada" in reporte["desempeno_observado"], "Falta 'formula_practica_recomendada'"

    assert "hallazgos_transversales" in reporte, "Falta 'hallazgos_transversales'"
    assert "recomendaciones_proximas_vocerias" in reporte, "Falta 'recomendaciones_proximas_vocerias'"
    assert "observacion_senal_cruzada" in reporte, "Falta 'observacion_senal_cruzada'"

    print("[OK] Todas las aserciones de esquema superadas con éxito.\n")

    print("[3/3] Resumen del Informe Ejecutivo VISUM Generado:")
    print("----------------------------------------------------------------")
    print(f"Diagnóstico General:\n  {reporte['sintesis_ejecutiva']['diagnostico_general']}\n")
    print(f"Piso de Competencias:\n  {reporte['sintesis_ejecutiva']['fortaleza_principal']}\n")
    print(f"Foco de Desarrollo:\n  {reporte['sintesis_ejecutiva']['foco_desarrollo']}\n")
    print(f"Fórmula Práctica Recomendada:\n  {reporte['desempeno_observado']['formula_practica_recomendada']}\n")
    print(f"Señal Cruzada (Congruencia):\n  {reporte.get('observacion_senal_cruzada', 'N/A')}\n")
    print("Reglas de Oro Recomendadas:")
    for r in reporte.get("recomendaciones_proximas_vocerias", []):
        print(f"  • {r}")
    print("----------------------------------------------------------------\n")

    # Guardar en archivo para inspección
    output_path = CURRENT_DIR / "outputs" / "sample_visum_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)
    print(f"[OK] Informe completo guardado en: {output_path}")

    return reporte

if __name__ == "__main__":
    run_test()
