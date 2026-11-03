# Configuración

La fuente canónica de claves es `.env.example`. Copia el archivo a `.env` en la raíz y sustituye los marcadores. El repositorio no incluye valores de producción.

## Grupos de variables

| Grupo | Variables principales | Observación |
|---|---|---|
| Frontend público | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_AZURE_*`, `VOXREADY_DOCKER_*` | Son visibles en el navegador; no guardar secretos. |
| Autenticación API | `JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`, `CORS_ORIGINS` | Deben corresponder al tenant y API del cliente. |
| Desarrollo local | `DEV_AUTH`, `DEV_AUTH_SECRET`, `DEV_USERS_JSON` | Solo con `ENVIRONMENT=development`. |
| Persistencia | `SQL_CONNECTION_STRING`, `STORAGE_CONNECTION_STRING` | Usar cifrado y credenciales de mínimo privilegio. |
| Rutas Blob | `STORAGE_CONTAINER_NAME`, `STORAGE_RECORDING_PREFIX`, `STORAGE_MICROLESSON_PREFIX`, `STORAGE_REPORT_CONTAINER_NAME`, `STORAGE_REPORT_PREFIX` | No tienen valores implícitos en runtime. |
| Servicios internos | `WORKER_INTERNAL_URL`, `INTERNAL_SERVICE_TOKEN`, `VISION_SERVICE_URL`, `VISION_SERVICE_TOKEN` | Usar endpoints privados y tokens diferentes. |
| IA NVIDIA | `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `LLM_MODEL_NAME`, `NVIDIA_RIVA_*` | El modelo y endpoint deben ser aprobados para el ambiente. |
| Modelos de visión | `VISION_FACE_MODEL_PATH`, `VISION_POSE_MODEL_PATH` | La imagen incluye los modelos Tasks verificados durante el build. Las rutas pueden reemplazarse para una imagen corporativa propia. |
| Límites y vigencia | `MAX_UPLOAD_SIZE_BYTES`, `MICROLESSON_VIDEO_MAX_BYTES`, `UPLOAD_URL_TTL_MINUTES`, `READ_URL_TTL_MINUTES`, `VISION_MAX_*` | Ajustar según política del cliente. |

## Usuarios de desarrollo

`DEV_USERS_JSON` es una lista JSON de usuarios que ya deben existir en la base de datos. Ejemplo con dominios reservados:

```json
[
  {"email":"developer@example.invalid","display_name":"Developer","role":"master_config"}
]
```

El script `backend/scripts/seed_dev_users.py` rechaza roles desconocidos y no contiene correos reales.

## Validación

```powershell
.\scripts\preflight.ps1
docker compose -f docker-compose.azure.yml config --quiet
```

El preflight informa únicamente nombres de claves faltantes; nunca imprime sus valores.

## Integridad de los modelos de visión

El `Dockerfile` de visión descarga los artefactos oficiales Face Landmarker y Pose Landmarker Lite durante la construcción de la imagen. El build falla si sus hashes no coinciden con los valores versionados. Esto evita descargas en ejecución y cambios silenciosos del modelo.
