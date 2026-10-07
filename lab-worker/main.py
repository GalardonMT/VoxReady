import os
import sys
import json
import datetime
import importlib.util
from pathlib import Path
from typing import Dict, Optional, Union

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUTS_DIR = BASE_DIR / "outputs"

# Cargar automáticamente variables de entorno desde .env si existe
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


def _cargar_modulo(nombre: str, ruta_relativa: str):
    ruta = BASE_DIR / ruta_relativa
    spec = importlib.util.spec_from_file_location(nombre, str(ruta))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# Cargar módulos dinámicamente
modulo_separar = _cargar_modulo("separar_audio_video_mod", "separar-audio-video/main.py")
modulo_video = _cargar_modulo("video_mod", "video/main.py")
try:
    modulo_voice = _cargar_modulo("voice_mod", "voice/voice.py")
except Exception:
    modulo_voice = None

separar_audio_video = modulo_separar.separar_audio_video
procesar_metricas_video = modulo_video.procesar_metricas_video


def preparar_directorio_salida(
    video_path: Union[str, Path],
    base_output_dir: Optional[Union[str, Path]] = None,
    con_timestamp: bool = False,
) -> Dict[str, Path]:
    """
    Crea y organiza la estructura de carpetas de salida por video:
    outputs/
      └── <nombre_video>/
          ├── audio.wav
          ├── frames/
          │   ├── frame_0001.jpg
          │   └── ...
          ├── metricas_video.json
          ├── metricas_voz.json
          └── resultado_consolidado.json
    """
    video_path = Path(video_path).resolve()
    base_dir = Path(base_output_dir).resolve() if base_output_dir else DEFAULT_OUTPUTS_DIR

    # Nombre de la subcarpeta para el video
    nombre_carpeta = video_path.stem
    if con_timestamp:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_carpeta = f"{nombre_carpeta}_{ts}"

    video_output_dir = base_dir / nombre_carpeta
    frames_dir = video_output_dir / "frames"

    # Crear directorios
    video_output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    return {
        "output_dir": video_output_dir,
        "audio_path": video_output_dir / "audio.wav",
        "frames_dir": frames_dir,
        "consolidated_json_path": video_output_dir / "resultado_consolidado.json",
        "video_metrics_json_path": video_output_dir / "metricas_video.json",
        "voice_metrics_json_path": video_output_dir / "metricas_voz.json",
        "judge_metrics_json_path": video_output_dir / "metricas_juez.json",
        "visum_report_json_path": video_output_dir / "informe_visum.json",
    }


def procesar_video_completo(
    video_path: Union[str, Path],
    output_base_dir: Optional[Union[str, Path]] = None,
    fps: float = 0.5,
    evaluar_audio: bool = True,
    evaluar_juez_llm: bool = True,
    pregunta_periodista: Optional[str] = None,
    mensajes_clave: Optional[list] = None,
    contexto_crisis: Optional[str] = None,
    con_timestamp: bool = False,
) -> Dict:
    """
    Pipeline integral con persistencia organizada de outputs:
    1. Prepara la carpeta de salida en outputs/<nombre_video>/
    2. Separa el video en audio.wav y carpeta frames/ con fotogramas a 0.5 fps.
    3. Evalúa las métricas de video con MediaPipe (4 Ejes + Tuplas de eventos).
    4. Guarda metricas_video.json.
    5. Evalúa el audio con NVIDIA Riva (ASR, fluidez, dicción, muletillas).
    6. Guarda metricas_voz.json.
    7. Evalúa la respuesta transcrita con el LLM Juez Visum (NVIDIA Build API).
    8. Guarda metricas_juez.json.
    9. Genera y guarda resultado_consolidado.json.
    
    :param video_path: Ruta del video (WebM o MP4).
    :param output_base_dir: Carpeta base para outputs (por defecto lab-worker/outputs/).
    :param fps: Frecuencia de muestreo de fotogramas (por defecto 0.5 fps = 1 foto cada 2s).
    :param evaluar_audio: Si True, ejecuta la transcripción y evaluación de voz con NVIDIA Riva.
    :param evaluar_juez_llm: Si True, ejecuta la evaluación estructurada con LLMJudgeService.
    :param pregunta_periodista: Pregunta del periodista para el análisis de pertinencia.
    :param mensajes_clave: Lista de mensajes clave obligatorios.
    :param contexto_crisis: Contexto del escenario de crisis.
    :param con_timestamp: Si True, agrega sufijo de fecha/hora al nombre de la carpeta.
    :return: Diccionario consolidado con métricas completas y rutas de los archivos generados.
    """
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"No existe el archivo de video: {video_path}")

    # Paso 0: Preparar estructura de directorios
    rutas = preparar_directorio_salida(
        video_path=video_path,
        base_output_dir=output_base_dir,
        con_timestamp=con_timestamp
    )

    print("==================================================")
    print(f"  Iniciando analisis integral: {video_path.name}")
    print(f"  Carpeta de salida: {rutas['output_dir']}")
    print("==================================================\n")

    # Paso 1: Separar Audio y Video dentro de la carpeta de outputs
    resultado_separacion = separar_audio_video(
        video_path=video_path,
        output_audio_path=rutas["audio_path"],
        output_frames_dir=rutas["frames_dir"],
        fps=fps,
    )

    # Paso 2: Evaluar fotogramas de video con MediaPipe
    resultado_video = procesar_metricas_video(
        frames_path=rutas["frames_dir"],
        fps=fps
    )

    # Guardar JSON de métricas de video
    with open(rutas["video_metrics_json_path"], "w", encoding="utf-8") as f:
        json.dump(resultado_video, f, indent=2, ensure_ascii=False)
    print(f"[OK] Metricas de video guardadas en: {rutas['video_metrics_json_path'].name}")

    # Paso 3: Evaluar audio con NVIDIA Riva
    resultado_audio = None
    if evaluar_audio and modulo_voice and hasattr(modulo_voice, "transcribe_and_evaluate"):
        try:
            resultado_audio = modulo_voice.transcribe_and_evaluate(audio_path=str(rutas["audio_path"]))
            if resultado_audio:
                # Guardar JSON de métricas de voz
                with open(rutas["voice_metrics_json_path"], "w", encoding="utf-8") as f:
                    json.dump(resultado_audio, f, indent=2, ensure_ascii=False)
                print(f"[OK] Metricas de voz guardadas en: {rutas['voice_metrics_json_path'].name}")
        except Exception as e:
            print(f"[AVISO] No se pudo procesar el audio con NVIDIA Riva: {e}")

    # Paso 4: Evaluar con LLM Juez Visum (NVIDIA Build API)
    resultado_juez = None
    transcripcion = (resultado_audio.get("transcription") or "").strip() if resultado_audio else ""
    
    if evaluar_juez_llm and transcripcion:
        try:
            from core.llm_judge import LLMJudgeService
            judge_service = LLMJudgeService()
            print("[INFO] Evaluando respuesta con LLM Juez Visum (NVIDIA NIM)...")
            reporte_juez = judge_service.evaluate_response(
                pregunta_periodista=pregunta_periodista or "¿Cuál es la postura oficial y qué medidas urgentes se están adoptando?",
                mensajes_clave=mensajes_clave or ["Nuestra máxima prioridad es la seguridad y el restablecimiento del servicio."],
                contexto_crisis=contexto_crisis or "Crisis institucional y operacional con impacto en la comunidad.",
                transcripcion_vocero=transcripcion
            )
            resultado_juez = reporte_juez.model_dump()
            with open(rutas["judge_metrics_json_path"], "w", encoding="utf-8") as f:
                json.dump(resultado_juez, f, indent=2, ensure_ascii=False)
            print(f"[OK] Metricas del Juez LLM Visum guardadas en: {rutas['judge_metrics_json_path'].name}")
            print(f"     Puntaje Global LLM: {resultado_juez['puntaje_global_100']}/100")
        except Exception as e:
            print(f"[AVISO] No se pudo procesar la evaluacion del LLM Juez ({type(e).__name__}): {e}")

    # Paso 5: Generar Informe Narrativo Ejecutivo VISUM (Llamada 2 a NVIDIA NIM)
    resultado_visum = None
    if evaluar_juez_llm:
        try:
            from core.narrative_generator import generate_visum_report
            from openai import OpenAI
            print("[INFO] Generando Informe Ejecutivo Narrativo VISUM con NVIDIA NIM...")
            nvidia_key = (os.environ.get("NVIDIA_API_KEY") or (modulo_voice.API_KEY if modulo_voice and hasattr(modulo_voice, "API_KEY") else "") or "").strip()
            nvidia_base_url = (os.environ.get("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1").strip()
            model_name = os.environ.get("LLM_MODEL_NAME") or "meta/llama-3.2-11b-vision-instruct"

            client_visum = OpenAI(base_url=nvidia_base_url, api_key=nvidia_key or "test-key", timeout=120.0)

            scenario_meta = {
                "title": contexto_crisis or "Simulación de Vocería en Crisis",
                "context": contexto_crisis or "Incidente corporativo y vocería de crisis.",
                "optics": "empática, institucional y de control operativo",
                "key_messages": mensajes_clave or ["Nuestra máxima prioridad es la seguridad y el restablecimiento del servicio."],
                "red_lines": ["No especular sobre causas no confirmadas ni desviar la responsabilidad institucional."]
            }

            # Extracción precisa de métricas multimodales de video y audio (sin pisos artificiales de 75/80)
            score_expresion = float(resultado_video.get("score_area_expresion", 50.0))
            metricas_ejes = resultado_video.get("metricas_ejes", {})
            contacto_visual_val = float(metricas_ejes.get("contacto_visual_porcentaje", 0.0))
            postura_val = float(metricas_ejes.get("shoulder_stability_score", metricas_ejes.get("estabilidad_balanceo_score", 50.0)))
            manos_visibles_val = float(metricas_ejes.get("manos_visibles_pct", 0.0))
            gesticulacion_activa_val = float(metricas_ejes.get("gesticulacion_activa_pct", 0.0))
            sway_torso_val = float(metricas_ejes.get("body_sway_std", 0.0))

            audio_metrics = resultado_audio.get("metrics", {}) if resultado_audio else {}
            score_voz = float(audio_metrics.get("score_fluidez", 50.0))
            wpm_val = float(audio_metrics.get("wpm_global", audio_metrics.get("wpm", 130.0)))
            muletillas_cnt = len(audio_metrics.get("muletillas_detectadas", [])) if "muletillas_detectadas" in audio_metrics else int(audio_metrics.get("cantidad_muletillas", 0))

            score_contenido = float(resultado_juez.get("puntaje_global_100", 50.0)) if resultado_juez else 50.0
            dimensiones_juez = resultado_juez.get("dimensiones", {}) if resultado_juez else {}
            adherencia_val = float(dimensiones_juez.get("alineacion_mensaje_clave", {}).get("score_100", 50.0)) if dimensiones_juez else 50.0
            score_empatia = float(dimensiones_juez.get("asertividad_hostilidad", {}).get("score_100", 50.0)) if "asertividad_hostilidad" in dimensiones_juez else 50.0
            tecnicas_ctrl = dimensiones_juez.get("tecnicas_control", {}).get("tecnicas_detectadas", []) if dimensiones_juez else []
            bridging_val = len(tecnicas_ctrl) > 0

            # Ponderación oficial de 4 áreas (Expresión 25%, Voz 25%, Coherencia/Contenido 35%, Empatía 15%)
            score_global_calculado = round(
                (0.25 * score_expresion) +
                (0.25 * score_voz) +
                (0.35 * score_contenido) +
                (0.15 * score_empatia),
                1
            )

            consolidado_intermedio = {
                "score_global": score_global_calculado,
                "transcripcion": transcripcion,
                "evaluacion_areas": {
                    "expresion": {
                        "score": score_expresion,
                        "contacto_visual_pct": contacto_visual_val,
                        "estabilidad_postural": postura_val,
                        "manos_visibles_pct": manos_visibles_val,
                        "gesticulacion_activa_pct": gesticulacion_activa_val,
                        "balanceo_torso_std": sway_torso_val
                    },
                    "tono_voz": {
                        "score": score_voz,
                        "wpm": wpm_val,
                        "muletillas_count": muletillas_cnt
                    },
                    "contenido": {
                        "score": score_contenido,
                        "adherencia_mensajes": adherencia_val
                    },
                    "empatia": {
                        "score": score_empatia,
                        "bridging_detectado": bridging_val
                    }
                }
            }

            resultado_visum = generate_visum_report(
                client=client_visum,
                model_name=model_name,
                scenario_info=scenario_meta,
                consolidated_json=consolidado_intermedio
            )

            with open(rutas["visum_report_json_path"], "w", encoding="utf-8") as f:
                json.dump(resultado_visum, f, indent=2, ensure_ascii=False)
            print(f"[OK] Informe Ejecutivo Narrativo VISUM guardado en: {rutas['visum_report_json_path'].name}")
        except Exception as e:
            print(f"[AVISO] No se pudo generar el informe narrativo VISUM ({type(e).__name__}): {e}")

    # Paso 6: Construir Payload Consolidado Final
    puntuacion_final = {
        "score_global": score_global_calculado if 'score_global_calculado' in locals() else (resultado_juez.get("puntaje_global_100") if resultado_juez else resultado_video.get("score_area_expresion", 75.0)),
        "areas": {
            "expresion": score_expresion if 'score_expresion' in locals() else resultado_video.get("score_area_expresion", 0.0),
            "voz": score_voz if 'score_voz' in locals() else (resultado_audio.get("metrics", {}).get("score_fluidez") if resultado_audio else None),
            "contenido": score_contenido if 'score_contenido' in locals() else (resultado_juez.get("puntaje_global_100") if resultado_juez else None),
            "empatia": score_empatia if 'score_empatia' in locals() else None,
        }
    }

    payload_consolidado = {
        "video_origen": str(video_path),
        "fecha_procesamiento": datetime.datetime.now().isoformat(),
        "archivos_generados": {
            "carpeta_output": str(rutas["output_dir"]),
            "audio_wav": str(rutas["audio_path"]),
            "carpeta_frames": str(rutas["frames_dir"]),
            "json_metricas_video": str(rutas["video_metrics_json_path"]),
            "json_metricas_voz": str(rutas["voice_metrics_json_path"]) if resultado_audio else None,
            "json_metricas_juez": str(rutas["judge_metrics_json_path"]) if resultado_juez else None,
            "json_informe_visum": str(rutas["visum_report_json_path"]) if resultado_visum else None,
            "json_consolidado": str(rutas["consolidated_json_path"])
        },
        "puntuacion_global": puntuacion_final,
        "resumen_ejecutivo": {
            "score_global": puntuacion_final["score_global"],
            "score_expresion_video": puntuacion_final["areas"]["expresion"],
            "contacto_visual_pct": float(resultado_video.get("visum_summary", {}).get("eye_contact_pct", 0.0)),
            "manos_visibles_pct": float(resultado_video.get("visum_summary", {}).get("hands_visible_pct", 0.0)),
            "gesticulacion_activa_pct": float(resultado_video.get("visum_summary", {}).get("hands_active_pct", 0.0)),
            "estabilidad_postural_score": float(resultado_video.get("visum_summary", {}).get("shoulder_stability_score", 0.0)),
            "balanceo_torso_std": float(resultado_video.get("visum_summary", {}).get("body_sway_std", 0.0)),
            "score_fluidez_voz": puntuacion_final["areas"]["voz"],
            "score_diccion_voz": resultado_audio.get("metrics", {}).get("score_diccion") if resultado_audio else None,
            "score_contenido_juez": puntuacion_final["areas"]["contenido"],
            "score_empatia": puntuacion_final["areas"]["empatia"],
            "diagnostico_visum": resultado_visum.get("sintesis_ejecutiva", {}).get("diagnostico_general") if resultado_visum else None,
            "formula_visum": resultado_visum.get("desempeno_observado", {}).get("formula_practica_recomendada") if resultado_visum else None,
        },
        "metricas_video": resultado_video,
        "metricas_audio": resultado_audio.get("metrics") if resultado_audio else None,
        "metricas_juez": resultado_juez,
        "informe_ejecutivo_visum": resultado_visum,
        "transcripcion": transcripcion or None
    }

    # Guardar JSON consolidado final
    with open(rutas["consolidated_json_path"], "w", encoding="utf-8") as f:
        json.dump(payload_consolidado, f, indent=2, ensure_ascii=False)
    print(f"[OK] Payload consolidado guardado en: {rutas['consolidated_json_path'].name}\n")

    return payload_consolidado


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python main.py <ruta_del_video_webm_o_mp4> [fps] [carpeta_salida] [escenario_json]")
        print("Ejemplo: python main.py grabacion.webm 0.5")
        sys.exit(1)

    video_input = sys.argv[1]
    fps_input = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    output_dir_arg = sys.argv[3] if len(sys.argv) > 3 else None
    
    pregunta_arg = None
    mensajes_arg = None
    contexto_arg = None
    if len(sys.argv) > 4:
        # Permite pasar un archivo JSON con la metadata del escenario
        escenario_file = Path(sys.argv[4])
        if escenario_file.exists():
            with open(escenario_file, "r", encoding="utf-8") as f:
                escenario_data = json.load(f)
                pregunta_arg = escenario_data.get("pregunta_periodista") or escenario_data.get("question_text")
                mensajes_arg = escenario_data.get("mensajes_clave") or escenario_data.get("key_messages")
                contexto_arg = escenario_data.get("contexto_crisis") or escenario_data.get("scenario_description")

    resultado = procesar_video_completo(
        video_path=video_input,
        output_base_dir=output_dir_arg,
        fps=fps_input,
        pregunta_periodista=pregunta_arg,
        mensajes_clave=mensajes_arg,
        contexto_crisis=contexto_arg
    )
    print("=== PROCESAMIENTO COMPLETADO ===")
    print(f"Carpeta de salida: {resultado['archivos_generados']['carpeta_output']}")
    print(f"JSON consolidado: {resultado['archivos_generados']['json_consolidado']}")
    if resultado.get("resumen_ejecutivo", {}).get("score_global_juez_llm") is not None:
        print(f"Score Global Juez Visum: {resultado['resumen_ejecutivo']['score_global_juez_llm']}/100")

