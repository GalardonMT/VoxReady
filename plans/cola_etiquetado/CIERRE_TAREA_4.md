# Cierre Tarea 4 — API master segura

Estado: **completada localmente** en `feat/cola-de-etiquetado`.

## Entregables

1. `backend/schemas/labeling.py` define contratos Pydantic explícitos para lista, detalle, lease, video, revisión, historial, resumen de calidad y `application/problem+json`. Las solicitudes usan `extra="forbid"` y no admiten campos controlados por servidor.
2. `backend/labeling_api.py` expone las rutas canónicas `/api/master/...` y los alias `/v1/api/master/...` mediante un adaptador independiente de credenciales Azure.
3. Una dependencia común resuelve al usuario desde `app_user` y exige `master_config`; no confía en un rol enviado por JWT o navegador.
4. Los endpoints delegan reglas de pertenencia, rangos, precisión, comentarios, leases e idempotencia a `labeling_store`, preservando una capa HTTP delgada.
5. Los errores `403`, `404`, `409`, `410`, `422` y `503` usan un contrato estable con `code`, `correlationId` y contexto seguro.
6. La URL de grabación se emite por 15 minutos, solo lectura y HTTPS, después de verificar la ETag de la evidencia sellada. No existe fallback público y la respuesta usa `Cache-Control: no-store`.
7. La primera confirmación devuelve `201`; un replay con la misma clave y payload devuelve la revisión persistida con `200`.
8. OpenAPI declara DTO públicos y no expone hashes de lease, paths internos, hash de grabación, `analysis_job_id` ni identidad real del vocero.
9. `backend/main.py` integra el router. `LABELING_QUEUE_API_ENABLED=false` permite desactivarlo sin eliminar datos ni tocar endpoints de sesión.

## Rutas

- `GET /api/master/labeling-cases`
- `GET /api/master/labeling-cases/{caseId}`
- `POST|DELETE /api/master/labeling-cases/{caseId}/lease`
- `GET /api/master/labeling-cases/{caseId}/recording-url`
- `POST|GET /api/master/labeling-cases/{caseId}/reviews`
- `GET /api/master/quality-reviews/summary`

Cada ruta tiene el alias equivalente bajo `/v1/api/master`.

## Verificación local

```text
python -m py_compile backend/schemas/labeling.py backend/labeling_api.py backend/main.py
python -m pytest backend/tests/test_labeling_contracts.py backend/tests/test_labeling_api.py backend/tests/test_labeling_store.py -q
15 passed, 8 skipped
git diff --check
```

Las 8 pruebas HTTP con `TestClient` quedan definidas para el runtime backend soportado, pero se omiten en este host Windows con Python 3.14 porque AnyIO queda bloqueado al crear `socketpair`, incluso con una aplicación FastAPI mínima. Los 4 contratos OpenAPI/Pydantic y las 11 pruebas del store sí se ejecutaron y aprobaron.

La suite backend global no llega a colección en el Python del host por dependencias del proyecto ausentes (`PyJWT`, Azure SDK y `pyodbc`). No se aplicó DDL, no se escribió en Azure y no se realizó despliegue, commit ni push.
