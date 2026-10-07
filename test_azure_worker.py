import os
import sys
import json
import time
from datetime import datetime, timezone
import argparse
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.storage.blob import BlobServiceClient

# Connection strings de Azure dev (resueltos dinámicamente o por env vars)
SB_CONN = os.getenv("SERVICE_BUS_CONNECTION_STRING")
STORAGE_CONN = os.getenv("STORAGE_CONNECTION_STRING")
QUEUE_NAME = "analysis-queue"
CONTAINER_RECORDINGS = "recordings"
CONTAINER_REPORTS = "reports"

# Transcripción de prueba por defecto (basada en el discurso de media training)
DEFAULT_TRANSCRIPT = (
    "Buenas tardes. Entiendo perfectamente la inquietud que existe sobre este tema y es una pregunta muy legítima. "
    "Como organización, asumimos con total seriedad y transparencia el momento que estamos atravesando, "
    "porque nuestro primer compromiso siempre ha sido con la confianza de nuestros clientes y de la comunidad. "
    "Ahora bien, lo importante aquí es poner el foco en las soluciones concretas. Desde el primer minuto activamos "
    "un protocolo de respuesta inmediata y auditoría externa, lo que nos ha permitido aislar el incidente y "
    "garantizar que el noventa y cinco por ciento de nuestras operaciones continúe funcionando con absoluta normalidad. "
    "Si hay un mensaje central que quiero enfatizar hoy, es este: no nos estamos quedando en explicaciones, estamos actuando con hechos."
)

DEFAULT_KEY_MESSAGES = [
    "Nuestra prioridad es la seguridad y el restablecimiento del servicio.",
    "No nos estamos quedando en explicaciones, estamos actuando con hechos."
]


def resolve_service_bus_conn():
    global SB_CONN
    if SB_CONN:
        return SB_CONN
    import subprocess
    for ns in ["sb-voxready-st", "sb-voxready-dev"]:
        try:
            res = subprocess.run(
                f"az servicebus namespace authorization-rule keys list --resource-group rg-voxready-dev --namespace-name {ns} --name RootManageSharedAccessKey --query primaryConnectionString -o tsv",
                shell=True, capture_output=True, text=True, check=True
            )
            out = res.stdout.strip()
            if out:
                SB_CONN = out
                return SB_CONN
        except Exception:
            continue
    print("Aviso: No se pudo obtener SERVICE_BUS_CONNECTION_STRING vía Azure CLI.")
    return None


def resolve_storage_conn():
    global STORAGE_CONN
    if STORAGE_CONN:
        return STORAGE_CONN
    import subprocess
    for sa in ["stavoxreadyst", "stavoxreadydev"]:
        try:
            res = subprocess.run(
                f"az storage account show-connection-string --name {sa} --resource-group rg-voxready-dev --query connectionString -o tsv",
                shell=True, capture_output=True, text=True, check=True
            )
            out = res.stdout.strip()
            if out:
                STORAGE_CONN = out
                return STORAGE_CONN
        except Exception:
            continue
    print("Aviso: No se pudo obtener STORAGE_CONNECTION_STRING vía Azure CLI.")
    return None


def list_available_blobs(storage_conn):
    if not storage_conn:
        return []
    try:
        blob_service = BlobServiceClient.from_connection_string(storage_conn)
        container = blob_service.get_container_client(CONTAINER_RECORDINGS)
        blobs = [b.name for b in container.list_blobs() if b.name.endswith(".webm") or b.name.endswith(".mp4")]
        return blobs
    except Exception as e:
        print(f"Error listando blobs: {e}")
        return []


def send_test_message(session_id: str, video_blob_name: str, transcript: str):
    message_payload = {
        "session_id": session_id,
        "media": {
            "storage_container": CONTAINER_RECORDINGS,
            "video_blob_name": video_blob_name
        },
        "transcript": transcript,
        "question_text": "¿Cuál es la postura oficial y qué medidas urgentes se están adoptando?",
        "key_messages": DEFAULT_KEY_MESSAGES,
        "scenario_id": "crisis-prueba-azure",
        "scenario_description": "Incidente corporativo con afectación parcial del servicio y vocería institucional."
    }

    print(f"\n[1/3] Enviando mensaje a Service Bus ({QUEUE_NAME})...")
    print(f"       Sesión: {session_id}")
    print(f"       Video Blob: {video_blob_name}")
    
    sb_conn = resolve_service_bus_conn()
    if not sb_conn:
        print("Error: No se pudo obtener la cadena de conexión de Service Bus.")
        return

    with ServiceBusClient.from_connection_string(sb_conn) as client:
        with client.get_queue_sender(queue_name=QUEUE_NAME) as sender:
            msg = ServiceBusMessage(json.dumps(message_payload))
            sender.send_messages(msg)

    print("       Mensaje encolado con éxito.")


def wait_for_report(session_id: str, storage_conn: str, timeout_sec: int = 90):
    print(f"\n[2/3] Esperando que el worker procese el video y genere el reporte...")
    print(f"       Consultando Azure Blob Storage: {CONTAINER_REPORTS}/{session_id}_report.json")
    
    blob_service = BlobServiceClient.from_connection_string(storage_conn)
    container = blob_service.get_container_client(CONTAINER_REPORTS)
    report_name = f"{session_id}_report.json"
    blob_client = container.get_blob_client(report_name)

    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        try:
            if blob_client.exists():
                print(f"       ¡Reporte generado en {round(time.time() - start_time, 1)} segundos!")
                data = blob_client.download_blob().readall()
                return json.loads(data.decode("utf-8"))
        except Exception:
            pass
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(4)

    print("\nTiempo de espera agotado. El worker podría seguir procesando.")
    return None


def print_report_summary(report: dict):
    print("\n" + "=" * 70)
    print(" REPORTE CONSOLIDADO DE EVALUACIÓN (AZURE WORKER)")
    print("=" * 70)
    puntuacion = report.get("puntuacion_global", {})
    print(f" Score General:               {puntuacion.get('score_general')}/100")
    print(f" Comunicación No Verbal:      {puntuacion.get('score_comunicacion_no_verbal')}/100")
    print(f" Comunicación Verbal:         {puntuacion.get('score_comunicacion_verbal')}/100")
    print(f" Estrategia de Crisis (LLM):  {puntuacion.get('score_estrategia_crisis')}/100")

    metrics = report.get("metrics", {})
    vision = metrics.get("vision", {})
    print("\n--- VISIÓN (MediaPipe / Face Tracking) ---")
    print(f" Contacto visual: {vision.get('eye_contact_percentage')}%")
    print(f" Estabilidad postura: {vision.get('average_posture_score')}")
    print(f" Frames analizados: {vision.get('frames_analyzed')}")

    judge = metrics.get("judge", {})
    feedback = judge.get("feedback", {})
    print("\n--- JUEZ LLM (Visum Pedagogical Judge) ---")
    print(f" Fortaleza Principal:   {feedback.get('fortaleza_principal')}")
    print(f" Brecha Crítica:        {feedback.get('brecha_critica')}")
    print(f" Recomendación:         {feedback.get('recomendacion_accionable')}")

    # VISUM Executive Report
    visum = report.get("informe_ejecutivo_visum") or (report.get("narrative") or {}).get("visum")
    if visum:
        print("\n--- SÍNTESIS EJECUTIVA VISUM CONSULTING ---")
        sintesis = visum.get("sintesis_ejecutiva", {})
        print(f" Diagnóstico General:    {sintesis.get('diagnostico_general')}")
        print(f" Fortaleza Principal:    {sintesis.get('fortaleza_principal')}")
        print(f" Foco de Desarrollo:     {sintesis.get('foco_desarrollo')}")
        print(f" Continuidad:            {sintesis.get('continuidad_recomendada')}")

        desempeno = visum.get("desempeno_observado", {})
        print(f"\n Fórmula Práctica:       {desempeno.get('formula_practica_recomendada')}")
        print(f" Observación Cruzada:    {visum.get('observacion_senal_cruzada')}")

    area_scores = report.get("areaScores") or []
    if area_scores:
        print("\n--- SCORES POR ÁREA (RÚBRICA PONDERADA v0.4) ---")
        for a in area_scores:
            print(f"   * {a.get('area'):15}: {a.get('value')}%")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Probar el Worker alojado en Azure Container Apps.")
    parser.add_argument("--blob", help="Nombre del blob de video en el contenedor recordings", default=None)
    parser.add_argument("--session", help="ID de la sesión de prueba", default=None)
    args = parser.parse_args()

    storage_conn = resolve_storage_conn()
    if not storage_conn:
        print("Error: No se encontró la cadena de conexión de Blob Storage.")
        return

    available_blobs = list_available_blobs(storage_conn)
    print(f"Blobs disponibles en container 'recordings': {len(available_blobs)}")
    for b in available_blobs[:6]:
        print(f"  - {b}")

    target_blob = args.blob
    if not target_blob:
        # Usar session-crisis-1790373240648.webm si está disponible
        candidate = "recordings/session-crisis-1790373240648.webm"
        if candidate in available_blobs:
            target_blob = candidate
        elif available_blobs:
            target_blob = available_blobs[0]
        else:
            target_blob = "recordings/session-crisis-1790373240648.webm"

    session_id = args.session or f"test-azure-{int(time.time())}"

    # Enviar mensaje a Service Bus
    send_test_message(session_id, target_blob, DEFAULT_TRANSCRIPT)

    # Esperar reporte
    report = wait_for_report(session_id, storage_conn, timeout_sec=120)
    if report:
        print_report_summary(report)
        # Guardar copia local
        out_file = f"reporte_{session_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nReporte completo guardado localmente en: {out_file}")


if __name__ == "__main__":
    main()
