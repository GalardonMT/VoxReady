# VoxReady — Backend

API REST de **VoxReady**, plataforma SaaS multi-tenant de entrenamiento de vocería de crisis con evaluación multimodal (voz, imagen, contenido y fusión de empatía). Construida con **FastAPI + SQLAlchemy 2.0 async + PostgreSQL 16** (los tests corren sobre SQLite).

- Prefijo de API: `/v1` · JSON everywhere · fechas ISO 8601 UTC · IDs UUID v4.
- Errores en formato **RFC 7807** (`application/problem+json`) con `correlationId` y cabecera `x-correlation-id` en todas las respuestas.
- 3 roles: `spokesperson` (vocero), `client_admin` (admin del cliente), `master_config` (configurador maestro).
- Los pipelines de IA son **stubs deterministas intercambiables** (ver `app/services/analysis_worker.py`).

## Requisitos

- Python 3.12+ (local) o Docker + Docker Compose (recomendado).

## Arranque rápido con Docker (PostgreSQL 16)

```bash
cd backend
cp .env.example .env
docker compose up --build -d db          # levanta PostgreSQL
docker compose run --rm api alembic upgrade head   # crea el esquema
docker compose run --rm api python -m app.seed     # datos semilla
docker compose up --build api            # API en http://localhost:8000
```

Documentación interactiva: <http://localhost:8000/docs>

## Arranque local (sin Docker, SQLite)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # DATABASE_URL ya apunta a SQLite local
alembic upgrade head                  # crea el esquema (funciona en SQLite y Postgres)
python -m app.seed                    # datos semilla
uvicorn app.main:app --reload         # http://localhost:8000/docs
```

## Autenticación (modo dev)

Con `DEV_AUTH=true` la API acepta tokens HS256 locales y expone `POST /v1/dev/token` para los usuarios semilla:

```bash
curl -X POST http://localhost:8000/v1/dev/token \
  -H "Content-Type: application/json" \
  -d '{"email": "vocero@demo.voxready.io"}'
```

Usuarios semilla: `vocero@demo.voxready.io` (vocero), `admin@demo.voxready.io` (admin del cliente demo), `master@voxready.io` (configurador maestro).

Para producción (Azure AD B2C), configura `DEV_AUTH=false` y `JWKS_URL` / `JWT_ISSUER` / `JWT_AUDIENCE`: la validación RS256 vía JWKS ya está implementada (claims esperados: `sub`, `role`/`extension_role`, `clientId`, `preferredLanguage`).

## Flujo de una sesión de práctica

1. `POST /v1/sessions` (admite cabecera `Idempotency-Key`) → estado `created`.
2. `POST /v1/sessions/{id}/consent` → `consented` (ambas casillas obligatorias).
3. `POST /v1/sessions/{id}/recording-url` → `recording`; devuelve `uploadUrl` firmada (un solo uso, caduca en 15 min), `blobPath`, `expiresAt`, `maxSizeBytes`.
4. El cliente sube el binario con `PUT {uploadUrl}` (endpoint propio que imita un SAS de Azure Blob).
5. `POST /v1/sessions/{id}/finish` → `analyzing` (202) y encola el análisis en el worker asyncio en proceso.
6. `GET /v1/sessions/{id}/analysis` → progreso por pipeline (`content`, `voice`, `image`, `fusion`).
7. `GET /v1/sessions/{id}/report` → informe tipo coach (409 `report_not_ready` hasta terminar). Incluye `recordingUrl` firmada de lectura solo si la política del cliente es `full_recording`.

Máquina de estados: `created → consented → recording → analyzing → completed | failed`.

## Configuración

Todas las variables están documentadas en `.env.example`: base de datos, JWT/JWKS, storage de grabaciones (`STORAGE_DIR`, TTLs, tamaño máximo), webhooks salientes (`WEBHOOK_ENDPOINTS`, firma HMAC-SHA256 en `x-voxready-signature`, máx. 3 reintentos con backoff), worker de análisis y job de retención (intervalo configurable, purga según `retention_policy` con `audit_event`).

## Tests

```bash
cd backend
pytest -x -q        # corre sobre SQLite con datos semilla aislados por test
```

Cobertura: flujo auth (401/403), flujo de sesión completo (incluye idempotencia, `consent_required`, `invalid_content_type`, `blob_missing`, informe y progreso), CRUD de temas (archivado con sesiones), rúbrica (`weights_sum_invalid`, `already_published`, `version_not_found`) y retención (`invalid_policy`, rotación de versiones).

## Migraciones (Alembic)

`alembic upgrade head` aplica la migración inicial `0001_initial`, que materializa las 31 tablas (30 del diccionario de datos + `idempotency_key`). Funciona igual contra SQLite y PostgreSQL; la URL se toma de `DATABASE_URL`.

## Estructura

```
backend/
  app/
    main.py, config.py, db.py, utils.py, seed.py
    models/      # identity, content, sessions, recording, analysis, rubric,
                 # progress, privacy, labeling, translation
    schemas/     # pydantic v2 (requests)
    api/v1/      # routers: identity, scenarios, sessions, progress,
                 # microlessons, schedule, privacy, topics, clients, master,
                 # uploads, dev_auth
    core/        # security, errors, correlation, storage, webhooks
    services/    # session_service, analysis_worker, retention_job, helpers
  alembic/       # env.py async + migración inicial
  tests/         # pytest + httpx AsyncClient sobre SQLite
  requirements.txt, Dockerfile, docker-compose.yml, .env.example, pytest.ini
```

## Notas de diseño

- **Multi-tenancy**: filtrado por `client_id` a nivel aplicación, inyectado desde el JWT (sin RLS de Postgres).
- **Storage**: abstracción `StorageService` con implementación `LocalDiskStorage` (directorio `./storage`); las URLs firmadas usan HMAC con caducidad y la de subida es de un solo uso, imitando el patrón SAS. Enchufar Azure Blob/S3 solo requiere otra implementación de la misma interfaz.
- **Pipelines de IA**: stubs deterministas (hash del `sessionId`) que actualizan progreso real en `analysis_pipeline_result` y generan informe, puntajes por área, progreso, recomendación, caso de etiquetado (reglas `low_confidence` / `borderline` / `random` ~10%) y webhook `session.analysis.completed`.
- **Borrado de temas**: con sesiones asociadas → `archived`; sin sesiones → borrado lógico.
