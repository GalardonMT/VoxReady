# Cierre de Tarea 2 — evidencia canónica y creación runtime

## Estado

`Hecho` en código y pruebas locales simuladas. Las once subtareas fueron implementadas. No se ejecutó DDL, reconciliación con `--apply`, escritura sobre Azure SQL/Blob, despliegue, commit ni push.

## Resultado por subtarea

1. La finalización obtiene un bloqueo transaccional por sesión, calcula `MAX(version_no)+1`, desactiva el informe vigente anterior y crea el nuevo informe como vigente.
2. Informe, cuatro áreas, resultados `vision`, `voice`, `content_judge`, `fusion`, caso, job y sesión se confirman en una sola transacción SQL. El caso se crea antes de marcar job y sesión como completados.
3. La persistencia de `fusion` ya no se reduce a un warning: cualquier fallo revierte la transacción y propaga el error.
4. `ensure_labeling_case_for_report` bloquea y consulta por `report_id`; un reintento devuelve el caso existente sin insertar otro.
5. `ai_snapshot_json` se genera desde las filas originales de los pipelines. Cada métrica declara disponibilidad, procedencia, conversión, unidad, precisión y causa cuando no existe una observación. No se inventan valores.
6. El worker calcula SHA-256 sobre el archivo local exacto que analizó y crea una copia sellada, content-addressed y job-scoped con `overwrite=False`. Verifica hash, tamaño y ETag del blob resultante.
7. Path sellado, version ID cuando existe, SHA-256, ETag, content type y duración quedan en `fusion` y `labeling_case` dentro de la unidad lógica del informe. La API de subida solo admite sesiones `created` y emite SAS con permiso `create`, sin `write`.
8. `worker/reconcile_labeling_runtime.py` ofrece reconciliación explícita, acotada e idempotente. `--dry-run` revierte; `--apply` exige la confirmación literal `APPLY_RUNTIME_LABELING_RECONCILIATION`. No se ejecuta al iniciar servicios.
9. Una reevaluación crea una nueva versión de informe y un nuevo caso por `report_id`; no borra ni modifica el caso del informe anterior. El reconciliador también considera informes completados que ya no son vigentes.
10. El entrypoint canónico es `worker/Dockerfile -> uvicorn main:app -> /analyze -> process_session_pipeline`. `worker.py` delega Service Bus al mismo pipeline. El pipeline divergente interno y `function_app.py` quedan explícitamente deshabilitados.
11. Se cubrieron creación atómica, fallo antes del commit, reintento, versionado de reevaluación, idempotencia, snapshot parcial sin defaults, copia sellada resistente a sobrescritura del origen, reconciliación dry-run/apply y orden de cierre de sesión.

## Archivos principales

- `worker/services/recording_evidence.py`: hash y copia sellada verificable.
- `worker/services/labeling_runtime.py`: snapshot, clasificación, creación idempotente y reconciliación.
- `worker/services/db_service.py`: finalización transaccional y versionada.
- `worker/core/pipeline_orchestrator.py`: sellado antes del análisis y persistencia canónica única.
- `worker/reconcile_labeling_runtime.py`: comando operativo separado.
- `worker/worker.py` y `worker/function_app.py`: convergencia o deshabilitación de entrypoints heredados.
- `backend/main.py`: cierre de subidas y SAS create-only.
- `backend/labeling_migration.py`: unicidad de informe vigente, versión e instancia `fusion`.
- `worker/tests/test_labeling_runtime.py`, `worker/tests/test_db_service_progress.py` y `worker/tests/test_reconcile_labeling_runtime.py`: pruebas focalizadas de Tarea 2.
- `backend/tests/test_flow_regression.py`: contratos de cierre de subida y permisos SAS.

## Feature flag y rollback

- `LABELING_RUNTIME_ENABLED=false` detiene la materialización runtime de `labeling_case` sin deshacer informes ni pipelines.
- El reconciliador nunca se activa implícitamente.
- El esquema es aditivo y este cierre no incluye operaciones `DROP` ni borrado histórico.
- Los blobs sellados que queden huérfanos tras un rollback SQL se conservan; su limpieza futura debe ser un proceso auditado separado.

## Verificación local

- `python -m py_compile`: correcto para módulos y pruebas modificados.
- Suite `worker/tests`: `15 passed, 2 skipped`; los dos omitidos requieren Azure SQL configurado.
- Backend focalizado sin dependencias externas: `11 passed` para contratos fuente, migración y reconciliación.
- `git diff --check`: correcto; solo informa la conversión futura LF/CRLF de un archivo de pruebas.
- `backend/tests/test_flow_regression.py` no pudo recolectarse en el Python global porque no está instalado `PyJWT`. Sus dos contratos nuevos quedaron además cubiertos por guardas estáticas independientes; esto no sustituye ejecutar la suite dentro de la imagen backend.

La prueba real con Azure SQL aislado, Azure Blob y Docker sigue siendo una validación de entorno de Tarea 9. Los resultados locales no se presentan como evidencia de producción.
