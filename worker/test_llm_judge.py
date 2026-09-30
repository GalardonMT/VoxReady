import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(BASE_DIR))

from core.llm_judge import LLMJudgeService

def test_judge():
    judge = LLMJudgeService()

    contexto = "Crisis por rotura de matriz de agua servida en zona residencial con afectacion a 500 viviendas."
    pregunta = "¿Es verdad que el departamento tecnico ignoro tres alertas tempranas la semana pasada sobre esta misma tuberia?"
    mensajes = [
        "Nuestra prioridad es la sanitizacion del area y el restablecimiento del servicio.",
        "Estamos desplegando camiones aljibe y asistencia directa a las familias afectadas."
    ]

    # Caso 1: Evasion directa con bridging cinico (debe castigar pertinencia a nivel 1 o 2)
    transcripcion_evasiva = (
        "Mire, entiendo perfectamente la situacion, pero lo verdaderamente importante aqui "
        "es que nuestra prioridad es la sanitizacion del area y el restablecimiento del servicio. "
        "Ya tenemos los camiones aljibe trabajando con las familias."
    )

    print("\n" + "="*56)
    print("  EJECUTANDO PRUEBA 1: RESPUESTA EVASIVA (ANTI-EVASION)")
    print("="*56)
    resultado_evasivo = judge.evaluate_response(
        pregunta_periodista=pregunta,
        mensajes_clave=mensajes,
        contexto_crisis=contexto,
        transcripcion_vocero=transcripcion_evasiva
    )

    nivel_pert_1 = resultado_evasivo.dimensiones["pertinencia_respuesta"]["nivel_visum"]
    print(f"Puntaje Global: {resultado_evasivo.puntaje_global_100}/100")
    print(f"Nivel Pertinencia: {nivel_pert_1} (Esperado: <= 2)")
    print(f"Brecha Critica: {resultado_evasivo.feedback.brecha_critica}")
    print(f"Recomendacion: {resultado_evasivo.feedback.recomendacion_accionable}")

    assert nivel_pert_1 <= 2, f"Fallo: No penalizo la evasion directa (obtenido nivel {nivel_pert_1})"
    print("\n>>> PRUEBA 1 SUPERADA EXITOSAMENTE: Evasion castigada segun metodologia Visum.")

    # Caso 2: Bridging efectivo (responde / delimita primero y luego transiciona al mensaje clave)
    transcripcion_efectiva = (
        "Respecto a los reportes previos, se ha instruido una auditoria tecnica inmediata para esclarecer que ocurrio con esas alertas. "
        "Sin embargo, lo prioritario en este momento de emergencia es que estamos volcados en la sanitizacion del area y en el restablecimiento urgente del servicio, "
        "con camiones aljibe y asistencia directa a cada una de las 500 familias afectadas."
    )

    print("\n" + "="*56)
    print("  EJECUTANDO PRUEBA 2: RESPUESTA CON BRIDGING EFECTIVO")
    print("="*56)
    resultado_efectivo = judge.evaluate_response(
        pregunta_periodista=pregunta,
        mensajes_clave=mensajes,
        contexto_crisis=contexto,
        transcripcion_vocero=transcripcion_efectiva
    )

    nivel_pert_2 = resultado_efectivo.dimensiones["pertinencia_respuesta"]["nivel_visum"]
    print(f"Puntaje Global: {resultado_efectivo.puntaje_global_100}/100")
    print(f"Nivel Pertinencia: {nivel_pert_2} (Esperado: >= 3)")
    print(f"Fortaleza Principal: {resultado_efectivo.feedback.fortaleza_principal}")
    print(f"Recomendacion: {resultado_efectivo.feedback.recomendacion_accionable}")

    assert nivel_pert_2 >= 3, f"Fallo: No reconocio la pertinencia adecuada (obtenido nivel {nivel_pert_2})"
    print("\n>>> PRUEBA 2 SUPERADA EXITOSAMENTE: Bridging efectivo evaluado con nivel alto.")

    print("\n" + "="*56)
    print("  TODAS LAS PRUEBAS DEL LLM JUEZ VISUM SUPERADAS (OK)")
    print("="*56)

if __name__ == "__main__":
    test_judge()
