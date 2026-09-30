import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import List, Optional, Dict
from utils.logger import get_logger

logger = get_logger("core.media_splitter")

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


def get_temp_base_dir() -> Path:
    """
    Retorna el directorio base para archivos volátiles.
    En Linux serverless (Azure Functions/Container Apps) es `/tmp`.
    En Windows utiliza el directorio temporal del sistema.
    """
    if os.name != "nt" and os.path.exists("/tmp"):
        return Path("/tmp")
    return Path(tempfile.gettempdir())


def get_ffmpeg_executable(custom_path: Optional[str] = None) -> str:
    """
    Obtiene la ruta del ejecutable de FFmpeg buscando en:
    1. Argumento custom_path
    2. Variable de entorno FFMPEG_PATH
    3. FFmpeg en el PATH del sistema operativo (/usr/bin/ffmpeg, etc.)
    4. Binario embebido de imageio-ffmpeg
    """
    if custom_path and os.path.isfile(custom_path):
        return custom_path

    env_ffmpeg = os.getenv("FFMPEG_PATH")
    if env_ffmpeg and os.path.isfile(env_ffmpeg):
        return env_ffmpeg

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    if imageio_ffmpeg is not None:
        try:
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass

    raise RuntimeError(
        "No se encontró el ejecutable de FFmpeg en el sistema. "
        "Asegúrese de instalar FFmpeg o configurar la variable FFMPEG_PATH."
    )


def create_temp_workspace(session_id: str) -> Dict[str, Path]:
    """
    Crea un espacio de trabajo aislado en /tmp para la sesión actual.
    Retorna un diccionario con las rutas temporales.
    """
    base_tmp = get_temp_base_dir()
    session_dir = base_tmp / f"voxready_{session_id}"
    frames_dir = session_dir / "frames"

    session_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    return {
        "session_dir": session_dir,
        "video_path": session_dir / f"input_{session_id}.webm",
        "audio_path": session_dir / f"audio_{session_id}.wav",
        "frames_dir": frames_dir,
        "report_path": session_dir / f"report_{session_id}.json",
    }


def extract_audio_pcm16(
    input_video_path: str,
    output_wav_path: str,
    sample_rate: int = 16000,
    channels: int = 1,
    ffmpeg_exe: Optional[str] = None,
) -> bool:
    """
    Extrae el audio de un video (WebM, MP4, etc.) en formato WAV PCM 16-bit 16kHz mono.
    Comando base: ffmpeg -y -i input.webm -vn -acodec pcm_s16le -ar 16000 -ac 1 output.wav
    """
    video_path = Path(input_video_path).resolve()
    output_path = Path(output_wav_path).resolve()

    if not video_path.exists():
        raise FileNotFoundError(f"El archivo de video no existe: {video_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = get_ffmpeg_executable(ffmpeg_exe)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        str(output_path),
    ]

    logger.info(f"Ejecutando extracción de audio PCM16 con FFmpeg a '{output_path}'...")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"Error de FFmpeg al extraer audio: {result.stderr}")
        raise RuntimeError(f"Fallo en extracción de audio con FFmpeg:\n{result.stderr}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        logger.error(f"El archivo de audio de salida no fue creado o está vacío: {output_path}")
        return False

    logger.info(f"Audio PCM16 extraído exitosamente: {output_path} ({output_path.stat().st_size} bytes)")
    return True


def extract_sampled_frames(
    input_video_path: str,
    output_dir: str,
    fps: float = 0.5,
    quality: int = 2,
    ffmpeg_exe: Optional[str] = None,
) -> List[str]:
    """
    Extrae fotogramas muestreados a una tasa fija (por defecto 0.5 FPS = 1 frame cada 2 seg).
    Comando base: ffmpeg -y -i input.webm -vf "fps=0.5" -q:v 2 /tmp/frames/frame_%04d.jpg
    """
    video_path = Path(input_video_path).resolve()
    frames_path = Path(output_dir).resolve()

    if not video_path.exists():
        raise FileNotFoundError(f"El archivo de video no existe: {video_path}")

    frames_path.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = get_ffmpeg_executable(ffmpeg_exe)
    pattern = frames_path / "frame_%04d.jpg"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(video_path),
        "-vf", f"fps={fps}",
        "-q:v", str(quality),
        str(pattern),
    ]

    logger.info(f"Extrayendo fotogramas a {fps} FPS con FFmpeg en '{frames_path}'...")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"Error de FFmpeg al extraer fotogramas: {result.stderr}")
        raise RuntimeError(f"Fallo en extracción de fotogramas con FFmpeg:\n{result.stderr}")

    extracted_frames = sorted(str(p) for p in frames_path.glob("frame_*.jpg"))
    logger.info(f"Fotogramas extraídos exitosamente: {len(extracted_frames)} frames generados.")
    return extracted_frames


def cleanup_temp_files(*paths: str) -> None:
    """
    Eliminación estricta de archivos y carpetas temporales mediante os.remove o shutil.rmtree
    para evitar fugas de memoria en disco dentro de la instancia serverless.
    """
    for item_path in paths:
        if not item_path:
            continue
        try:
            p = Path(item_path).resolve()
            if p.is_file() or p.is_symlink():
                p.unlink(missing_ok=True)
                logger.debug(f"Archivo temporal eliminado: {p}")
            elif p.is_dir():
                shutil.rmtree(str(p), ignore_errors=True)
                logger.debug(f"Directorio temporal eliminado: {p}")
        except Exception as e:
            logger.warning(f"Error al limpiar ruta temporal '{item_path}': {e}")
