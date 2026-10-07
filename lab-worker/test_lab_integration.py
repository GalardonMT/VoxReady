import os
import sys
import json
from pathlib import Path

# Cargar .env de lab-worker
BASE_DIR = Path(__file__).resolve().parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lstrip('\ufeff')
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip().lstrip('\ufeff')
                v = v.strip().strip('"').strip("'")
                os.environ[k] = v

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pyodbc
from openai import OpenAI
from core.narrative_generator import generate_visum_report

def get_compatible_sql_conn_str(conn_str: str) -> str:
    drivers = pyodbc.drivers()
    preferred = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server"
    ]
    chosen = None
    for p in preferred:
        if p in drivers:
            chosen = p
            break
    if chosen and "Driver={" in conn_str:
        import re
        conn_str = re.sub(r"Driver=\{[^}]+\}", f"Driver={{{chosen}}}", conn_str)
        # Si el driver es 'SQL Server' antiguo, remover TrustServerCertificate/Encrypt si causa incompatibilidad
        if chosen == "SQL Server":
            conn_str = re.sub(r";Encrypt=[^;]+", "", conn_str)
            conn_str = re.sub(r";TrustServerCertificate=[^;]+", "", conn_str)
    return conn_str

def test_azure_sql_connection():
    print("----------------------------------------------------------------")
    print("1. Probando conexión a Azure SQL Serverless (sqldb-voxready)...")
    sql_conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not sql_conn_str:
        print("[SKIP] SQL_CONNECTION_STRING no configurado.")
        return None, None, []

    adapted_conn_str = get_compatible_sql_conn_str(sql_conn_str)
    print(f"   [INFO] Drivers instalados: {pyodbc.drivers()}")
    conn = pyodbc.connect(adapted_conn_str)
    cur = conn.cursor()

    cur.execute("""
        SELECT TOP 1 s.id, s.title, t.context, t.optics, t.audience, s.topic_id
        FROM scenario s
        LEFT JOIN topic t ON s.topic_id = t.id
        WHERE s.status = 'active'
    """)
    scenario = cur.fetchone()
    print(f"   [OK] Escenario activo encontrado: ID={scenario.id if scenario else 'N/A'}")
    if scenario:
        print(f"        Título: {scenario.title}")
        print(f"        Contexto: {scenario.context}")
        print(f"        Óptica: {scenario.optics}")

    key_messages = []
    if scenario and scenario.topic_id:
        cur.execute("SELECT text FROM topic_key_message WHERE topic_id = ? ORDER BY sort_order", scenario.topic_id)
        key_messages = [r[0] for r in cur.fetchall()]
        print(f"   [OK] Mensajes clave ({len(key_messages)}): {key_messages}")

    cur.execute("SELECT TOP 1 id, status, version_label FROM rubric_version WHERE status = 'published'")
    rubric = cur.fetchone()
    print(f"   [OK] Versión de rúbrica activa: ID={rubric.id if rubric else 'N/A'} (Label: {rubric.version_label if rubric else 'N/A'})")

    cur.execute("SELECT area_key, name, weight FROM rubric_area WHERE rubric_version_id = ?", rubric.id if rubric else "")
    areas = cur.fetchall()
    print(f"   [OK] Áreas de evaluación ({len(areas)}):")
    for a in areas:
        print(f"        - {a.area_key} ({a.name}): {a.weight}%")

    conn.close()
    return scenario, rubric, areas, key_messages


def test_visum_with_live_scenario(scenario, key_messages=None):
    print("\n----------------------------------------------------------------")
    print("2. Probando generación narrativa VISUM con NVIDIA NIM...")
    nvidia_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    nvidia_base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip()
    model_name = os.environ.get("LLM_MODEL_NAME", "meta/llama-3.2-11b-vision-instruct")

    scenario_info = {
        "title": scenario.title if scenario else "Fuga de Gas en Planta Norte",
        "context": scenario.context if scenario and scenario.context else "Emergencia ambiental con corte de suministro.",
        "optics": scenario.optics if scenario and scenario.optics else "Institucional, empática y de resolución operativa",
        "key_messages": key_messages or [
            "La seguridad de los vecinos y colaboradores es la prioridad número uno.",
            "Equipos técnicos se encuentran en terreno controlando la situación.",
            "Canales de asistencia social y albergues habilitados."
        ],
        "red_lines": [
            "No atribuir causas antes de los peritajes oficiales.",
            "No comprometer plazos sin certificación técnica de seguridad."
        ]
    }

    mock_consolidated = {
        "score_global": 79.5,
        "transcripcion": (
            "Ante todo, queremos transmitir tranquilidad a la comunidad: nuestra prioridad absoluta es la seguridad de las familias. "
            "La fuga ha sido contenida por las cuadrillas de emergencia y estamos asistiendo a los evacuados. "
            "No descansaremos hasta que el último vecino regrese seguro a su hogar."
        ),
        "evaluacion_areas": {
            "expresion": {"score": 84.0, "contacto_visual_pct": 82.0, "postura_score": 88.0},
            "tono_voz": {"score": 75.0, "wpm": 128.0, "muletillas_count": 1},
            "contenido": {"score": 80.0, "adherencia_mensajes": 85.0},
            "empatia": {"score": 76.0, "bridging_detectado": True}
        }
    }

    client = OpenAI(base_url=nvidia_base_url, api_key=nvidia_key, timeout=120.0)
    report = generate_visum_report(client, model_name, scenario_info, mock_consolidated)

    assert "sintesis_ejecutiva" in report, "Falta sintesis_ejecutiva"
    assert "desempeno_observado" in report, "Falta desempeno_observado"
    assert len(report["desempeno_observado"]["fortalezas"]) >= 1, "Fortalezas vacías"
    assert "formula_practica_recomendada" in report["desempeno_observado"], "Falta fórmula práctica"

    print("   [OK] Reporte VISUM generado y validado:")
    print(f"        Diagnóstico: {report['sintesis_ejecutiva']['diagnostico_general'][:120]}...")
    print(f"        Fórmula: {report['desempeno_observado']['formula_practica_recomendada'][:120]}...")
    return report


def test_blob_storage_connection():
    print("\n----------------------------------------------------------------")
    print("3. Probando conexión a Azure Blob Storage...")
    storage_conn = os.environ.get("STORAGE_CONNECTION_STRING")
    if not storage_conn:
        print("[SKIP] STORAGE_CONNECTION_STRING no configurado.")
        return

    from azure.storage.blob import BlobServiceClient
    blob_service = BlobServiceClient.from_connection_string(storage_conn)
    containers = [c["name"] for c in blob_service.list_containers()]
    print(f"   [OK] Contenedores encontrados: {containers}")
    assert "recordings" in containers or "reports" in containers, "Contenedores requeridos no encontrados"


if __name__ == "__main__":
    print("================================================================")
    print("  TEST DE INTEGRACIÓN COMPLETO DE LAB-WORKER")
    print("================================================================")
    scen, rubric, areas, key_messages = test_azure_sql_connection()
    test_blob_storage_connection()
    test_visum_with_live_scenario(scen, key_messages)
    print("\n================================================================")
    print("  [EXITO] TODAS LAS VALIDACIONES DE LAB-WORKER PASARON.")
    print("================================================================")
