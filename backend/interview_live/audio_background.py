"""Decoupled background task: FFmpeg PCM conversion + intra-turn RMS VAD + NVIDIA Parakeet ASR."""

from __future__ import annotations

import asyncio
import logging
import os
import string
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

from . import store
from .config import InterviewLiveSettings

logger = logging.getLogger("interview_live.audio_background")

# Strong references to active background tasks so Python GC never cancels them early
_ACTIVE_BG_TASKS: set[asyncio.Task] = set()
_SEMAPHORES: dict[int, asyncio.Semaphore] = {}


def _get_loop_semaphore(limit: int) -> asyncio.Semaphore:
    loop_id = id(asyncio.get_running_loop())
    sem = _SEMAPHORES.get(loop_id)
    if sem is None:
        sem = asyncio.Semaphore(max(1, limit))
        _SEMAPHORES[loop_id] = sem
    return sem


def convert_to_pcm16_wav(input_path: Path, output_wav_path: Path) -> int:
    """Transcode turn audio blob (WebM/MP4/OGG) to 16kHz mono PCM WAV via FFmpeg."""
    t0 = time.perf_counter()
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_wav_path),
    ]
    res = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=45,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if res.returncode != 0 or not output_wav_path.exists() or output_wav_path.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg fallo ({res.returncode}): {(res.stderr or '')[:240]}")
    return elapsed_ms


def compute_turn_rms_acoustics(wav_path: Path, frame_duration_ms: int = 30) -> dict[str, Any]:
    """Compute intra-turn VAD RMS duration, active speech time, and pauses >= 1.5s."""
    with wave.open(str(wav_path), "rb") as wf:
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        total_duration = n_frames / float(sample_rate) if sample_rate > 0 else 0.0

        if n_frames == 0 or total_duration <= 0:
            return {
                "total_duration_sec": 0.0,
                "speech_time_sec": 0.0,
                "silence_time_sec": 0.0,
                "phonation_ratio": 0.0,
                "pausas_prolongadas_acusticas": [],
            }

        frame_size = max(1, int(sample_rate * (frame_duration_ms / 1000.0)))
        rms_samples: list[float] = []
        sample_chunks = min(100, max(1, n_frames // frame_size))
        for _ in range(sample_chunks):
            raw = wf.readframes(frame_size)
            if not raw:
                break
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            rms_samples.append(float(np.sqrt(np.mean(data ** 2))) if len(data) > 0 else 0.0)

        wf.rewind()
        max_rms = max(rms_samples) if rms_samples else 1.0
        threshold = max(300.0, max_rms * 0.08)

        speech_frames = 0
        silent_consecutive = 0
        prolonged_pauses: list[dict[str, Any]] = []
        frames_1_5s = int(1.5 / (frame_duration_ms / 1000.0))

        frame_idx = 0
        while True:
            raw = wf.readframes(frame_size)
            if not raw:
                break
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(data ** 2))) if len(data) > 0 else 0.0

            if rms > threshold:
                if silent_consecutive >= frames_1_5s:
                    silence_dur = round(silent_consecutive * (frame_duration_ms / 1000.0), 2)
                    start_time = round(
                        (frame_idx - silent_consecutive) * (frame_duration_ms / 1000.0), 2
                    )
                    prolonged_pauses.append(
                        {"inicio_segundo": start_time, "duracion_segundos": silence_dur}
                    )
                silent_consecutive = 0
                speech_frames += 1
            else:
                silent_consecutive += 1
            frame_idx += 1

        if silent_consecutive >= frames_1_5s:
            silence_dur = round(silent_consecutive * (frame_duration_ms / 1000.0), 2)
            start_time = round((frame_idx - silent_consecutive) * (frame_duration_ms / 1000.0), 2)
            prolonged_pauses.append(
                {"inicio_segundo": start_time, "duracion_segundos": silence_dur}
            )

        speech_time = speech_frames * (frame_duration_ms / 1000.0)
        silence_time = max(0.0, total_duration - speech_time)
        phonation_ratio = min(1.0, speech_time / total_duration) if total_duration > 0 else 0.0

        return {
            "total_duration_sec": round(total_duration, 3),
            "speech_time_sec": round(speech_time, 3),
            "silence_time_sec": round(silence_time, 3),
            "phonation_ratio": round(phonation_ratio, 4),
            "pausas_prolongadas_acusticas": prolonged_pauses,
        }


def transcribe_wav_with_parakeet(
    wav_path: Path, settings: InterviewLiveSettings
) -> tuple[str, list[dict[str, Any]], int]:
    """Run NVIDIA Riva Parakeet ASR streaming on a 16kHz mono PCM WAV turn."""
    t0 = time.perf_counter()
    if not settings.nvidia_api_key:
        raise ValueError("NVIDIA_API_KEY no configurada en backend para Parakeet ASR.")

    import riva.client

    auth = riva.client.Auth(
        use_ssl=True,
        uri=settings.nvidia_riva_server,
        metadata_args=[
            ["function-id", settings.nvidia_function_id],
            ["authorization", f"Bearer {settings.nvidia_api_key}"],
        ],
    )
    asr_service = riva.client.ASRService(auth)
    config = riva.client.StreamingRecognitionConfig(
        config=riva.client.RecognitionConfig(
            language_code=settings.nvidia_language_code,
            max_alternatives=1,
            enable_automatic_punctuation=True,
            enable_word_time_offsets=True,
        ),
        interim_results=False,
    )

    words: list[dict[str, Any]] = []
    full_text: list[str] = []

    with riva.client.AudioChunkFileIterator(str(wav_path), 1600) as chunk_iter:
        responses = asr_service.streaming_response_generator(
            audio_chunks=chunk_iter,
            streaming_config=config,
        )
        for response in responses:
            for result in response.results:
                if not result.is_final:
                    continue
                for alt in result.alternatives:
                    if alt.transcript:
                        full_text.append(alt.transcript)
                    for w in alt.words:
                        cleaned = w.word.strip(string.punctuation).lower()
                        if cleaned:
                            conf = float(w.confidence if w.confidence > 0 else (alt.confidence or 1.0))
                            conf = max(0.0, min(1.0, conf))
                            words.append(
                                {
                                    "word": cleaned,
                                    "start": round(w.start_time / 1000.0, 3),
                                    "end": round(w.end_time / 1000.0, 3),
                                    "confidence": conf,
                                }
                            )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return " ".join(full_text).strip(), words, elapsed_ms


def _extension_from_mime(mime_type: str | None) -> str:
    base = (mime_type or "audio/webm").split(";", 1)[0].strip().lower()
    if "mp4" in base:
        return ".mp4"
    if "ogg" in base:
        return ".ogg"
    if "wav" in base:
        return ".wav"
    return ".webm"


async def process_turn_audio_background(
    *,
    conn_str: str,
    settings: InterviewLiveSettings,
    turn_id: str,
    session_id: str,
    session_question_id: str | None,
    base_sequence_no: int,
    turn_kind: str,
    audio_bytes: bytes,
    audio_mime_type: str | None,
) -> None:
    """Execute FFmpeg + RMS VAD + Parakeet ASR in background guarded by Semaphore."""
    sem = _get_loop_semaphore(settings.bg_concurrency)
    input_path: Path | None = None
    wav_path: Path | None = None
    ffmpeg_ms: int | None = None
    parakeet_ms: int | None = None

    async with sem:
        try:
            await asyncio.to_thread(store.mark_turn_asr_processing, conn_str, turn_id)

            settings.tmp_dir.mkdir(parents=True, exist_ok=True)
            ext = _extension_from_mime(audio_mime_type)
            input_path = settings.tmp_dir / f"{session_id}_{turn_id}{ext}"
            wav_path = settings.tmp_dir / f"{session_id}_{turn_id}.wav"

            await asyncio.to_thread(input_path.write_bytes, audio_bytes)
            ffmpeg_ms = await asyncio.to_thread(convert_to_pcm16_wav, input_path, wav_path)
            acoustics = await asyncio.to_thread(compute_turn_rms_acoustics, wav_path)
            transcript, words, parakeet_ms = await asyncio.to_thread(
                transcribe_wav_with_parakeet, wav_path, settings
            )

            await asyncio.to_thread(
                store.update_turn_asr_completed,
                conn_str,
                turn_id=turn_id,
                session_id=session_id,
                session_question_id=session_question_id,
                base_sequence_no=base_sequence_no,
                turn_kind=turn_kind,
                transcript=transcript,
                words=words,
                acoustic_metrics=acoustics,
                ffmpeg_latency_ms=ffmpeg_ms,
                parakeet_latency_ms=parakeet_ms,
            )
            logger.info(
                "Turno %s (session=%s) transcrito OK: %d palabras, dur=%.2fs, ffmpeg=%dms, parakeet=%dms",
                turn_id,
                session_id,
                len(words),
                acoustics.get("total_duration_sec", 0.0),
                ffmpeg_ms,
                parakeet_ms,
            )
        except Exception as exc:
            logger.warning(
                "Fallo ASR background para turno %s (session=%s): %s. Worker aplicará fallback.",
                turn_id,
                session_id,
                exc,
            )
            try:
                await asyncio.to_thread(
                    store.update_turn_asr_failed,
                    conn_str,
                    turn_id=turn_id,
                    error_message=f"{type(exc).__name__}: {exc}",
                    ffmpeg_latency_ms=ffmpeg_ms,
                    parakeet_latency_ms=parakeet_ms,
                )
            except Exception as db_err:
                logger.error("No se pudo persistir fallo ASR del turno %s: %s", turn_id, db_err)
        finally:
            for p in (input_path, wav_path):
                if p is not None:
                    try:
                        if p.exists():
                            os.remove(p)
                    except OSError:
                        pass


def schedule_turn_audio_background(**kwargs) -> asyncio.Task:
    """Spawn background ASR task with strong reference retention until completion."""
    task = asyncio.create_task(process_turn_audio_background(**kwargs))
    _ACTIVE_BG_TASKS.add(task)
    task.add_done_callback(_ACTIVE_BG_TASKS.discard)
    return task
