FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Dependencias del sistema requeridas por MediaPipe (EGL, GL) y OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libegl1 \
    libgles2 \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip==26.2 setuptools==84.1.0 \
    && pip install --no-cache-dir -r requirements.txt

ARG FACE_MODEL_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
ARG FACE_MODEL_SHA256="64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
ARG POSE_MODEL_URL="https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
ARG POSE_MODEL_SHA256="59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"

RUN mkdir -p /opt/mediapipe-models \
    && curl -fsSL --retry 3 "$FACE_MODEL_URL" -o /opt/mediapipe-models/face_landmarker.task \
    && echo "$FACE_MODEL_SHA256  /opt/mediapipe-models/face_landmarker.task" | sha256sum -c - \
    && curl -fsSL --retry 3 "$POSE_MODEL_URL" -o /opt/mediapipe-models/pose_landmarker_lite.task \
    && echo "$POSE_MODEL_SHA256  /opt/mediapipe-models/pose_landmarker_lite.task" | sha256sum -c -

ENV VISION_FACE_MODEL_PATH=/opt/mediapipe-models/face_landmarker.task \
    VISION_POSE_MODEL_PATH=/opt/mediapipe-models/pose_landmarker_lite.task

# Copiar el código fuente; los modelos ya quedaron verificados en la imagen.
COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
