# VoxReady

VoxReady es una plataforma de entrenamiento de vocería que integra grabación web, análisis de voz, visión computacional y evaluación de contenido. Este repositorio contiene cuatro componentes:

- `frontend/`: Next.js 16, React 19 y TypeScript.
- `backend/`: API FastAPI, autenticación Microsoft Entra y acceso a Azure SQL/Blob Storage.
- `worker/`: análisis multimodal invocado por HTTP interno autenticado.
- `voxready-vision/`: análisis de fotogramas con MediaPipe.

La cola de etiquetado continúa en una rama separada y no forma parte de esta entrega estable.

## Inicio rápido

Requisitos:

- Docker Desktop con contenedores Linux y Docker Compose v2.
- Acceso a una instancia Azure SQL compatible con el esquema del proyecto.
- Recursos y credenciales propios para Microsoft Entra, Azure Blob Storage, NVIDIA y los servicios internos.

1. Copia `.env.example` como `.env`.
2. Reemplaza todos los marcadores por valores del ambiente de destino. Nunca confirmes `.env` en Git.
3. Valida la configuración sin imprimir secretos:

```powershell
.\scripts\preflight.ps1
```

4. Construye e inicia el sistema:

```powershell
.\docker.ps1 up
```

5. Abre `http://localhost:3000/login/`.

La documentación OpenAPI está desactivada de forma predeterminada. Para habilitarla únicamente en desarrollo, configura `ENVIRONMENT=development` y `ENABLE_API_DOCS=true`.

## Autenticación

El modo normal usa Microsoft Entra. Para desarrollo local existe un modo cerrado que solo emite tokens firmados para usuarios ya preasignados en `app_user`:

```powershell
.\docker.ps1 up -LocalDevAuth
```

Este modo requiere `DEV_AUTH_SECRET` de al menos 32 caracteres y `DEV_USERS_JSON`; no crea usuarios automáticamente y está bloqueado cuando `ENVIRONMENT` no es `development`.

## Pruebas

```powershell
.\docker.ps1 test
```

La batería construye imágenes limpias y ejecuta pruebas de backend, frontend y worker. Las pruebas marcadas para Azure SQL solo se ejecutan cuando se entrega un ambiente real de prueba.

Comandos individuales del frontend:

```powershell
Set-Location frontend
npm ci
npm test
npm run lint
npm run build
```

## Seguridad y configuración

- La configuración operativa se obtiene desde variables de entorno; `.env.example` contiene únicamente marcadores y valores locales no secretos.
- Backend, worker y visión se autentican entre sí mediante tokens separados.
- TLS se valida en las llamadas salientes.
- CORS usa una lista explícita de orígenes.
- Los tokens del navegador se guardan en `sessionStorage`, no en `localStorage`.
- El servicio usa MediaPipe Tasks `1.2.2`. Sus modelos oficiales se descargan durante el build y se aceptan solo si coinciden con los SHA-256 fijados; nunca se descargan en runtime.
- Los informes no inventan puntuaciones cuando faltan datos: el procesamiento falla de forma explícita o muestra el dato como no disponible.

Consulta [Configuración](docs/CONFIGURATION.md), [informe de auditoría](docs/TECHNICAL_AUDIT_2026-11-03.md) y [política de seguridad](SECURITY.md).

## Licencia

Software confidencial y propietario de VoxReady. No redistribuir sin autorización.
