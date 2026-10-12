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
├── dev-tools.ps1         # Script PowerShell de utilidades (Arranque local y logs en vivo de Azure)
├── .env                  # Conexiones locales; archivo ignorado por Git
├── .env.example          # Plantilla de referencia de variables globales
├── .gitignore            # Exclusión de dependencias y artefactos locales
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

## 🛠️ Herramientas de Desarrollo (`dev-tools.ps1`)

Para facilitar el desarrollo local y el monitoreo de la infraestructura en Azure, se incluye un menú interactivo en PowerShell:

```powershell
.\dev-tools.ps1
```

Opciones disponibles:
1. **Iniciar Docker + Azure SQL:** Construye y levanta backend y frontend, con migraciones sobre Azure SQL.
2. **Ver Logs del Worker:** Conecta con `az containerapp logs` para ver en tiempo real el procesamiento multimedia y de IA.
3. **Ver Logs del Backend API:** Muestra las peticiones HTTP entrantes, creación de sesiones y firmas SAS.
4. **Ver Logs de Visión:** Monitorea el análisis de fotogramas en `ca-vision-service`.
5. **Verificar Azure SQL:** Comprueba conexión y esquema desde la imagen del backend.
6. **Ejecutar pruebas:** Corre los tests de API y frontend dentro de Docker.

### Arranque con Docker Compose
El flujo habitual usa Docker conectado a Azure SQL, Blob Storage y Service Bus.
Consulta [DOCKER_AZURE.md](DOCKER_AZURE.md) para configurar, desplegar y verificar.
```bash
docker compose up --build -d --wait --wait-timeout 240
```
- **Frontend:** [http://localhost:3000/login/](http://localhost:3000/login/)
- **Backend (API REST Docs):** [http://localhost:8000/docs](http://localhost:8000/docs)

En PowerShell: `./docker.ps1 up`, `./docker.ps1 verify` y `./docker.ps1 test`.
No requiere entornos virtuales ni una base de datos local.

---

## 🚀 Puesta en Marcha Rápida

### Prerrequisitos
- **Docker Desktop** con motor Linux y Compose 2.20 o posterior.
- **`.env` local configurado** con las conexiones Azure y autenticación Microsoft Entra; no se incluye en Git.
- **Azure CLI (`az`)** solo para consultar logs de Container Apps.

### 1. Iniciar la aplicación con Azure SQL
```bash
docker compose up --build -d --wait --wait-timeout 240
```
Abre en tu navegador: [http://localhost:3000](http://localhost:3000).

### 2. Verificar conexión y ejecutar pruebas
```powershell
.\docker.ps1 verify
.\docker.ps1 test
```
Las pruebas de persistencia usan Azure SQL. El worker mantiene su despliegue
actual en Azure; no se necesita una base local ni un entorno virtual.

---

## 🔐 Configuración de Variables de Entorno

### Variables públicas en `.env` de la raíz (Docker)
```env
NEXT_PUBLIC_API_URL=https://ca-backend-api.victoriousmushroom-8081606f.eastus2.azurecontainerapps.io
NEXT_PUBLIC_BACKEND_API_URL=https://ca-backend-api.victoriousmushroom-8081606f.eastus2.azurecontainerapps.io
NEXT_PUBLIC_DEV_AUTH=false
VOXREADY_DOCKER_API_URL=http://localhost:8000/v1
VOXREADY_DOCKER_REDIRECT_URI=http://localhost:3000
```

### Conexiones del backend en el mismo `.env`
```env
STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=stavoxreadydev;..."
SERVICE_BUS_CONNECTION_STRING="Endpoint=sb://sb-voxready-dev.servicebus.windows.net/;..."
BLOB_CONTAINER_NAME="recordings"
SERVICE_BUS_QUEUE_NAME="analysis-queue"
DEV_AUTH="false"
CORS_ORIGINS="http://localhost:3000,https://jolly-stone-0ead4710f.5.azurestaticapps.net"
```

---

## 🧪 Ejecución de Pruebas

Las pruebas habituales de backend y frontend se ejecutan dentro de Docker:
```powershell
.\docker.ps1 test
```

La API se verifica contra Azure SQL y los datos de prueba se revierten al finalizar.
Los comandos individuales están en [DOCKER_AZURE.md](DOCKER_AZURE.md).

---

## 📄 Licencia

Este proyecto es propiedad confidencial de desarrollo para la plataforma **VoxReady**.
