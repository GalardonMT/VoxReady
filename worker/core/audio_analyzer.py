import os
import sys
import wave
import string
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from utils.logger import get_logger
from services.keyvault_service import get_secret

logger = get_logger("core.audio_analyzer")

# Lista de muletillas frecuentes en español corporativo / crisis
MULETILLAS_TARGET = {
    "eh",
    "ehh",
    "em",
    "este",
    "o sea",
    "bueno",
    "digamos",
    "verdad",
    "ya",
    "entonces",
}


class AudioAnalyzer:
    """
    Analizador acústico y de voz que combina transcripción ASR con marcas
    de tiempo a nivel de palabra (NVIDIA Parakeet/Riva) y métricas acústicas locales
    (VAD por RMS, pausas prolongadas > 1.5s, WPM y muletillas corporativas).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        server: Optional[str] = None,
        function_id: Optional[str] = None,
        language_code: Optional[str] = None,
    ):
        self.api_key = api_key or get_secret("NVIDIA_API_KEY")
        self.server = server or get_secret("NVIDIA_RIVA_SERVER", "grpc.nvcf.nvidia.com:443")
        self.function_id = function_id or get_secret(
            "NVIDIA_FUNCTION_ID", "71203149-d3b7-4460-8231-1be2543a1fca"
        )
        self.language_code = language_code or get_secret("NVIDIA_LANGUAGE_CODE", "es-US")

    def calcular_acustica_rms(
        self, audio_path: str, frame_duration_ms: int = 30
    ) -> Dict[str, Any]:
        """
        Calcula la duración total, el tiempo real de fonación (VAD por energía RMS)
        y detecta silencios prolongados directamente sobre el archivo WAV PCM 16-bit
        sin saturar la memoria RAM.
        """
        audio_file = Path(audio_path).resolve()
        if not audio_file.exists():
            raise FileNotFoundError(f"Archivo de audio no encontrado: {audio_file}")

        with wave.open(str(audio_file), "rb") as wf:
            sample_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            n_frames = wf.getnframes()
            total_duration = n_frames / float(sample_rate) if sample_rate > 0 else 0.0

            if n_frames == 0 or total_duration == 0:
                return {
                    "total_duration_sec": 0.0,
                    "speech_time_sec": 0.0,
                    "silence_time_sec": 0.0,
                    "phonation_ratio": 0.0,
                    "pausas_prolongadas_acusticas": [],
                }

            # Leer en chunks de tamaño frame_size para no mantener todo el audio en RAM
            frame_size = int(sample_rate * (frame_duration_ms / 1000.0))
            frame_bytes = frame_size * n_channels * 2  # 2 bytes por muestra (16-bit)

            # Paso 1: Estimación adaptativa de umbral de silencio
            # Muestrear los primeros 100 bloques para estimar nivel de ruido de fondo
            rms_samples = []
            sample_chunks = min(100, n_frames // frame_size)
            for _ in range(sample_chunks):
                raw = wf.readframes(frame_size)
                if not raw:
                    break
                data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(data ** 2)) if len(data) > 0 else 0.0
                rms_samples.append(rms)

            wf.rewind()

            max_rms = max(rms_samples) if rms_samples else 1.0
            threshold = max(300.0, max_rms * 0.08)

            speech_frames = 0
            silent_frames_consecutivos = 0
            pausas_prolongadas = []
            frames_1_5s = int(1.5 / (frame_duration_ms / 1000.0))

            current_frame_idx = 0
            while True:
                raw = wf.readframes(frame_size)
                if not raw:
                    break
                data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(data ** 2)) if len(data) > 0 else 0.0

                if rms > threshold:
                    if silent_frames_consecutivos >= frames_1_5s:
                        silence_dur = round(silent_frames_consecutivos * (frame_duration_ms / 1000.0), 2)
                        start_time = round((current_frame_idx - silent_frames_consecutivos) * (frame_duration_ms / 1000.0), 2)
                        pausas_prolongadas.append({
                            "inicio_segundo": start_time,
                            "duracion_segundos": silence_dur
                        })
                    silent_frames_consecutivos = 0
                    speech_frames += 1
                else:
                    silent_frames_consecutivos += 1

                current_frame_idx += 1

            # Revisar si termina en silencio prolongado
            if silent_frames_consecutivos >= frames_1_5s:
                silence_dur = round(silent_frames_consecutivos * (frame_duration_ms / 1000.0), 2)
                start_time = round((current_frame_idx - silent_frames_consecutivos) * (frame_duration_ms / 1000.0), 2)
                pausas_prolongadas.append({
                    "inicio_segundo": start_time,
                    "duracion_segundos": silence_dur
                })

            tiempo_fonacion_real = speech_frames * (frame_duration_ms / 1000.0)
            tiempo_silencio = max(0.0, total_duration - tiempo_fonacion_real)
            phonation_ratio = min(1.0, tiempo_fonacion_real / total_duration) if total_duration > 0 else 0.0

            return {
                "total_duration_sec": round(total_duration, 2),
                "speech_time_sec": round(tiempo_fonacion_real, 2),
                "silence_time_sec": round(tiempo_silencio, 2),
                "phonation_ratio": round(phonation_ratio, 2),
                "pausas_prolongadas_acusticas": pausas_prolongadas,
            }

    def _transcribir_con_riva(self, audio_path: str) -> Dict[str, Any]:
        """
        Ejecuta la transcripción vía NVIDIA Riva ASR Streaming en bloques de 1600 bytes
        obteniendo word-level timestamps sin saturar la memoria RAM serverless.
        """
        try:
            import riva.client
        except ImportError:
            logger.warning("riva.client no está instalado. Omitiendo llamada gRPC a Riva.")
            return {"transcript": "", "words": []}

        if not self.api_key:
            logger.warning("NVIDIA_API_KEY no configurada. Omitiendo transcripción ASR en vivo.")
            return {"transcript": "", "words": []}

        auth = riva.client.Auth(
            use_ssl=True,
            uri=self.server,
            metadata_args=[
                ["function-id", self.function_id],
                ["authorization", f"Bearer {self.api_key}"],
            ],
        )
        asr_service = riva.client.ASRService(auth)

        config = riva.client.StreamingRecognitionConfig(
            config=riva.client.RecognitionConfig(
                language_code=self.language_code,
                max_alternatives=1,
                enable_automatic_punctuation=True,
                enable_word_time_offsets=True,
            ),
            interim_results=False,
        )

        words = []
        full_text = []

        # Usar AudioChunkFileIterator con bloques de 1600 bytes (100 ms) para streaming de bajo consumo
        with riva.client.AudioChunkFileIterator(audio_path, 1600) as audio_chunk_iterator:
            responses = asr_service.streaming_response_generator(
                audio_chunks=audio_chunk_iterator,
                streaming_config=config,
            )
            for response in responses:
                for result in response.results:
                    if not result.is_final:
                        continue
                    for alt in result.alternatives:
                        full_text.append(alt.transcript)
                        for w in alt.words:
                            cleaned_word = w.word.strip(string.punctuation).lower()
                            if cleaned_word:
                                words.append({
                                    "word": cleaned_word,
                                    "start": round(w.start_time / 1000.0, 3),
                                    "end": round(w.end_time / 1000.0, 3),
                                    "confidence": float(w.confidence if w.confidence > 0 else (alt.confidence or 1.0)),
                                })

        return {
            "transcript": " ".join(full_text).strip(),
            "words": words,
        }

    def calcular_metricas_fluidez(
        self,
        parakeet_output: Dict[str, Any],
        acustica: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calcula las métricas de fluidez, dicción, pausas (naturales, vacilaciones,
        prolongadas > 1.5s), WPM y muletillas corporativas.
        """
        words = parakeet_output.get("words", [])
        total_words = len(words)
        total_duration = acustica.get("total_duration_sec", 0.0)
        speech_time_real = acustica.get("speech_time_sec", 0.0)

        # Si no hay palabras reconocidas (o modo offline), usar duración acústica
        if total_words == 0:
            return {
                "palabras_totales": 0,
                "duracion_segundos": total_duration,
                "tiempo_voz_activa_segundos": speech_time_real,
                "wpm_global": 0.0,
                "wpm_articulacion_neta": 0.0,
                "ratio_fonacion": acustica.get("phonation_ratio", 0.0),
                "pausas_naturales": 0,
                "pausas_vacilacion": 0,
                "pausas_prolongadas": len(acustica.get("pausas_prolongadas_acusticas", [])),
                "detalle_pausas_prolongadas": acustica.get("pausas_prolongadas_acusticas", []),
                "densidad_muletillas_pct": 0.0,
                "muletillas_detectadas": [],
                "conteo_muletillas": {},
                "score_fluidez": 0.0,
                "score_diccion": 0.0,
            }

        # 1. Análisis de pausas entre palabras sucesivas
        pausas_naturales = []
        pausas_vacilacion = []
        pausas_prolongadas = []

        for i in range(total_words - 1):
            gap = max(0.0, words[i + 1]["start"] - words[i]["end"])
            if gap >= 1.50:
                pausas_prolongadas.append({
                    "inicio_segundo": words[i]["end"],
                    "duracion_segundos": round(gap, 2),
                    "entre_palabras": f"{words[i]['word']} -> {words[i + 1]['word']}",
                })
            elif gap >= 0.70:
                pausas_vacilacion.append(gap)
            elif gap >= 0.25:
                pausas_naturales.append(gap)

        # Si ASR no detectó pausas prolongadas pero el análisis acústico sí, combinar
        if not pausas_prolongadas and acustica.get("pausas_prolongadas_acusticas"):
            pausas_prolongadas = acustica.get("pausas_prolongadas_acusticas")

        # 2. Palabras Por Minuto (WPM)
        # Fórmula: WPM = Total de palabras / (Duración audible en segundos / 60)
        duracion_minutos_global = max(0.01, total_duration / 60.0)
        duracion_minutos_audible = max(0.01, speech_time_real / 60.0)

        wpm_global = total_words / duracion_minutos_global
        wpm_articulacion = total_words / duracion_minutos_audible

        # 3. Muletillas corporativas
        muletillas_encontradas: List[str] = []
        conteo_muletillas: Dict[str, int] = {}
        for w in words:
            word_str = w["word"].lower()
            if word_str in MULETILLAS_TARGET:
                muletillas_encontradas.append(word_str)
                conteo_muletillas[word_str] = conteo_muletillas.get(word_str, 0) + 1

        densidad_muletillas = (len(muletillas_encontradas) / total_words) * 100.0

        # 4. Rúbrica de fluidez y dicción
        # Penalizaciones: WPM fuera del rango ideal corporativo (120 - 150 WPM), vacilaciones y muletillas
        penalizacion_wpm = abs(135.0 - wpm_global) * 0.6
        penalizacion_vacilacion = len(pausas_vacilacion) * 3.5
        penalizacion_prolongadas = len(pausas_prolongadas) * 6.0
        penalizacion_muletillas = densidad_muletillas * 5.0

        score_fluidez = max(
            0.0,
            min(
                100.0,
                100.0
                - penalizacion_wpm
                - penalizacion_vacilacion
                - penalizacion_prolongadas
                - penalizacion_muletillas,
            ),
        )

        avg_confidence = sum(w.get("confidence", 1.0) for w in words) / total_words
        score_diccion = max(0.0, min(100.0, avg_confidence * 100.0))

        return {
            "palabras_totales": total_words,
            "duracion_segundos": round(total_duration, 2),
            "tiempo_voz_activa_segundos": round(speech_time_real, 2),
            "wpm_global": round(wpm_global, 1),
            "wpm_articulacion_neta": round(wpm_articulacion, 1),
            "ratio_fonacion": acustica.get("phonation_ratio", 0.0),
            "pausas_naturales": len(pausas_naturales),
            "pausas_vacilacion": len(pausas_vacilacion),
            "pausas_prolongadas": len(pausas_prolongadas),
            "detalle_pausas_prolongadas": pausas_prolongadas[:15],
            "densidad_muletillas_pct": round(densidad_muletillas, 2),
            "muletillas_detectadas": muletillas_encontradas[:20],
            "conteo_muletillas": conteo_muletillas,
            "score_fluidez": round(score_fluidez, 1),
            "score_diccion": round(score_diccion, 1),
        }

    def process_audio(self, audio_path: str) -> Dict[str, Any]:
        """
        Método de orquestación principal para el audio:
        1. Métricas acústicas locales (VAD RMS, pausas > 1.5s).
        2. Transcripción ASR por streaming (NVIDIA Parakeet/Riva).
        3. Fusión de métricas de fluidez, WPM y muletillas.
        """
        logger.info(f"Iniciando análisis acústico y de voz sobre '{audio_path}'...")

        # 1. Acústica local
        acustica = self.calcular_acustica_rms(audio_path)
        logger.info(
            f"Acústica completada: {acustica['total_duration_sec']}s total, "
            f"{acustica['speech_time_sec']}s fonación ({acustica['phonation_ratio']*100:.1f}%), "
            f"{len(acustica['pausas_prolongadas_acusticas'])} pausas prolongadas (>1.5s)."
        )

        # 2. ASR Streaming
        asr_res = self._transcribir_con_riva(audio_path)
        if asr_res.get("transcript"):
            logger.info(
                f"Transcripción ASR obtenida: {len(asr_res['words'])} palabras reconocidas."
            )
        else:
            logger.info("No se obtuvo transcripción ASR en vivo (se mantendrán métricas acústicas).")

        # 3. Consolidación de métricas de voz
        metricas_voz = self.calcular_metricas_fluidez(asr_res, acustica)

        return {
            "transcription": asr_res.get("transcript", ""),
            "words": asr_res.get("words", []),
            "acoustic_analysis": acustica,
            "metrics": metricas_voz,
        }
