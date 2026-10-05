# 🎙️ VoxReady - Plataforma Multimodal de Entrenamiento y Vocería de Crisis

**VoxReady** es una plataforma integral de simulación y entrenamiento de voceros de crisis corporativa, impulsada por inteligencia artificial multimodal. Permite a líderes y portavoces entrenar en escenarios de alta presión, evaluando su desempeño en tres dimensiones clave: **comunicación no verbal (visión)**, **comunicación verbal y prosodia (voz)** y **apego estratégico al mensaje de crisis (LLM Juez)**.

---

## 🏗️ Arquitectura del Repositorio

El proyecto está organizado en una arquitectura de microservicios desacoplada y modular:

```text
voxready/
├── frontend/             # Aplicación Web para el Vocero (Next.js 16 + React 19 + TypeScript)
├── backend/              # API REST Orquestadora (FastAPI en Azure Container Apps: ca-backend-api)
├── worker/               # Procesador Asíncrono de IA (Azure Container Apps: ca-analysis-worker)
├── voxready-vision/      # Microservicio de Visión Computacional (MediaPipe en ca-vision-service)
├── lab-worker/           # Banco de Pruebas y Laboratorio Local (CLI main.py y scripts de prueba)
├── dev-tools.ps1         # Script PowerShell de utilidades (Arranque local y logs en vivo de Azure)
├── .env.example          # Plantilla de variables de entorno globales
├── .gitignore            # Exclusión de binarios, dependencias y secretos
└── README.md             # Documentación maestra del proyecto
```

---

## 🧩 Componentes del Ecosistema

### 1. `frontend/` (Next.js 16, React 19, TypeScript)
* **Onboarding & Selección:** Catálogo dinámico de escenarios de crisis corporativa.
* **Consentimiento Técnico (`TechConsentView`):** Validación en tiempo real de permisos de cámara y micrófono.
* **Sala de Simulación en Vivo (`LiveSessionView`):** 
  - Grabación en flujo continuo y sincronizado (sin saltos temporales ni desincronización).
  - Audio calibrado profesionalmente (sin saturación ni distorsión digital).
  - Cronómetro de sesión y preguntas interactivas del entrevistador de IA.
* **Subida Zero-Proxy:** Envío binario directo desde el navegador hacia Azure Blob Storage mediante SAS Token prefirmado.
* **Reporte y Coaching (`CoachReportView`):** Visualización interactiva con radar de competencias, métricas de contacto visual, WPM, muletillas y resumen ejecutivo.

### 2. `backend/` (FastAPI - `ca-backend-api`)
* **Gestión de Sesiones:** Creación de sesiones y catálogo de crisis.
* **Generación de SAS Tokens:** Endpoint `/api/sessions/{id}/upload-url` para subida directa a Blob Storage sin sobrecargar el backend.
* **Productor de Mensajería:** Publica el evento `SESSION_RECORDING_COMPLETED` en **Azure Service Bus** (`sb-voxready-dev`) para disparar el procesamiento del worker.
* **Consulta de Reportes:** Endpoint `/api/sessions/{id}/report` para entregar el reporte consolidado al frontend.

### 3. `worker/` (Python Serverless - `ca-analysis-worker`)
* **Consumidor de Service Bus:** Escucha la cola `analysis-queue` de forma asíncrona.
* **Procesamiento Multimedia (FFmpeg):** Descarga el video a `/tmp`, extrae el audio en PCM 16-bit 16kHz mono y genera fotogramas clave muestreados a 0.5 FPS.
* **Análisis de Voz y Acústica:** Evaluación de velocidad (WPM), pausas, silencios y dicción con NVIDIA Riva / Parakeet.
* **Análisis de Visión:** Integración vía HTTP con `ca-vision-service` para calcular estabilidad postural, contacto visual y expresiones.
* **LLM Juez de Crisis:** Evaluación cualitativa de apego a mensajes clave institucionales y técnica de *bridging* utilizando **NVIDIA Llama 3.2 90B**.
* **Persistencia:** Almacenamiento en Azure SQL Serverless y respaldo en Azure Blob Storage (`reports/`).

### 4. `voxready-vision/` (FastAPI + MediaPipe - `ca-vision-service`)
* Microservicio dedicado a la visión artificial.
* Procesa los fotogramas extraídos utilizando modelos de MediaPipe (Face Mesh, Pose Landmark Detection) para calificar la presencia y control del vocero.

### 5. `lab-worker/` (Laboratorio Local)
* Espacio de pruebas independiente para ejecutar y depurar algoritmos de análisis multimedia de forma 100% local, sin necesidad de desplegar en Azure.
* Contiene:
  - `main.py`: Orquestador CLI local (`python main.py <video.webm> 0.5`).
  - `separar-audio-video/`: Módulo de prueba de FFmpeg.
  - `video/`: Módulo de prueba de MediaPipe.
  - `voice/`: Módulo de prueba de audio y NVIDIA Riva.
  - `outputs/`: Carpeta donde se guardan los audios extraídos, fotogramas y reportes JSON locales.

---

## 🛠️ Herramientas de Desarrollo (`dev-tools.ps1`)

Para facilitar el desarrollo local y el monitoreo de la infraestructura en Azure, se incluye un menú interactivo en PowerShell:

```powershell
.\dev-tools.ps1
```

Opciones disponibles:
1. **Iniciar Frontend Local:** Entra automáticamente a `frontend/` y levanta el servidor Next.js en `http://localhost:3000`.
2. **Ver Logs del Worker:** Conecta con `az containerapp logs` para ver en tiempo real el procesamiento multimedia y de IA.
3. **Ver Logs del Backend API:** Muestra las peticiones HTTP entrantes, creación de sesiones y firmas SAS.
4. **Ver Logs de Visión:** Monitorea el análisis de fotogramas en `ca-vision-service`.

### Arranque con Docker Compose
Para probar el flujo local con autenticación demo y entorno aislado, consulta [LOCAL_DOCKER.md](LOCAL_DOCKER.md).
Para iniciar el entorno demo aislado:
```bash
docker compose -p voxready-local -f docker-compose.local.yml up --build -d --wait
```
- **Frontend:** [http://localhost:3100/login](http://localhost:3100/login)
- **Backend (API REST Docs):** [http://localhost:8100/docs](http://localhost:8100/docs)

---

## 🚀 Puesta en Marcha Rápida

### Prerrequisitos
- **Node.js 18+** y npm
- **Python 3.10+**
- **Azure CLI (`az`)** autenticado con permisos en la suscripción de desarrollo.

### 1. Iniciar el Frontend
```bash
cd frontend
npm install
npm run dev
```
Abre en tu navegador: [http://localhost:3000](http://localhost:3000).

### 2. Ejecutar Pruebas Locales en `lab-worker/`
```bash
cd lab-worker
pip install -r requirements.txt
python main.py tu_video.webm 0.5
```
Los resultados se generarán en la subcarpeta `lab-worker/outputs/<nombre_video>/`.

---

## 🔐 Configuración de Variables de Entorno

### Frontend (`frontend/.env.local`)
```env
NEXT_PUBLIC_API_URL=https://ca-backend-api.victoriousmushroom-8081606f.eastus2.azurecontainerapps.io
NEXT_PUBLIC_BACKEND_API_URL=https://ca-backend-api.victoriousmushroom-8081606f.eastus2.azurecontainerapps.io
NEXT_PUBLIC_DEV_AUTH=true
```

### Backend (`backend/.env`)
```env
STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=stavoxreadydev;..."
SERVICE_BUS_CONNECTION_STRING="Endpoint=sb://sb-voxready-dev.servicebus.windows.net/;..."
BLOB_CONTAINER_NAME="recordings"
SERVICE_BUS_QUEUE_NAME="analysis-queue"
DEV_AUTH="true"
CORS_ORIGINS="http://localhost:3000,https://jolly-stone-0ead4710f.5.azurestaticapps.net"
```

---

## 🧪 Ejecución de Pruebas

### Backend
```bash
cd backend
pytest -v
```

### Frontend
```bash
cd frontend
npm run build
npm run lint
```

---

## 📄 Licencia

Este proyecto es propiedad confidencial de desarrollo para la plataforma **VoxReady**.
