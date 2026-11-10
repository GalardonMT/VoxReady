# Avance Tarea 1 — Subtareas 1 a 4

## 1. Estado

- Resultado: **Parcial** de Tarea 1; subtareas 1, 2, 3 y 4 terminadas.
- Fecha: 28 de octubre de 2026 (`America/Santiago`).
- Rama: `feat/cola-de-etiquetado`.
- Gate actual: G1 se mantiene; **G2 no alcanzado**.
- No se ejecutó DDL en Azure SQL, no se creó backfill y no se modificaron datos.

## 2. Alcance implementado

| Subtarea | Estado | Evidencia |
|---|---|---|
| 1. Crear `backend/labeling_migration.py` con DDL idempotente | Hecho | `LABELING_SCHEMA_STEPS` usa guardas de catálogos y `migrate(cursor)` no controla la transacción. |
| 2. Integrar en `prepare_azure_database.py` | Hecho | `migrate_labeling(cursor)` se ejecuta después de métricas, bajo `BEGIN TRANSACTION`, `XACT_ABORT` y `sp_getapplock`, antes de `verify` y `commit`. |
| 3. Crear cuatro tablas y llaves foráneas | Hecho | 4 tablas, 14 FKs y checks de integridad. |
| 4. Crear índices de cola, revisión, métricas y áreas | Hecho | 14 índices idempotentes, incluidos índices de identidad en tablas padre. |

## 3. Tablas creadas

### `labeling_case`

- Identifica cliente, sesión, informe, job y versión de rúbrica.
- Conserva motivo de cola, snapshot IA, versión del snapshot y estado de procedencia.
- Reserva el medio exacto mediante path, versión opcional, SHA-256 binario, ETag, tipo y duración.
- Mantiene `lease_generation` separado de `content_revision`.
- El token de lease no se guarda en claro: solo `lock_token_hash BINARY(32)`.
- `source_status='complete'` exige path, hash, ETag y tipo de contenido no vacíos.
- Un caso revisado exige `resolved_by` y `resolved_at`; un pendiente no puede tenerlos.

### `labeling_review`

- Cabecera inmutable con número de revisión, experto, observación general, clave de idempotencia y hash del payload.
- Permite una revisión sucesora y obliga a que la revisión sustituida pertenezca al mismo caso.
- La unicidad filtrada permite como máximo una revisión vigente por caso.

### `labeling_rubric_correction`

- Una fila por revisión y área.
- Valores IA y experto limitados a `0..100`.
- Un cambio de valor exige comentario no vacío.

### `labeling_metric_correction`

- Una fila por revisión y `metric_key`.
- Conserva versión de mapeo y unidad para evitar agregaciones incompatibles.
- Un cambio de valor exige comentario no vacío.

## 4. Integridad relacional

Los índices únicos auxiliares permiten FKs compuestas que impiden crear un caso con identidades mezcladas:

- `(session_id, client_id)` debe coincidir con `session`.
- `(analysis_job_id, session_id, rubric_version_id)` debe coincidir con `analysis_job`.
- `(report_id, session_id, analysis_job_id, rubric_version_id)` debe coincidir con `report`.
- `report_id` es único en `labeling_case`: como máximo un caso por informe.
- La revisión sucesora referencia `(review_id, labeling_case_id)`, evitando sustituir una revisión de otro caso.
- Correcciones de rúbrica y métricas referencian el catálogo correspondiente.

## 5. Índices

- Cola estable: `(status, session_finished_at DESC, id DESC)`.
- Búsqueda y expiración de leases.
- Unicidad por `report_id` y `case_number`.
- Unicidad de `(case, review_no)` y `(case, idempotency_key)`.
- Una sola revisión `is_current=1` mediante índice filtrado.
- Revisiones recientes por `submitted_at DESC`.
- Agregaciones por `rubric_area_id` y por `(metric_key, mapping_version, unit)`.

El DDL crea también cuatro índices únicos de identidad en tablas padre para soportar las FKs compuestas. Como todos incluyen el PK `id`, no reescriben ni reinterpretan datos históricos.

## 6. Seguridad y patrón de migración

- Migración expand-only y forward-only: no contiene `DROP`, `DELETE`, `UPDATE`, `INSERT` ni backfill.
- Cada tabla, FK e índice tiene guarda idempotente sobre `OBJECT_ID`, `sys.foreign_keys` o `sys.indexes`.
- El módulo no abre conexiones ni hace `commit`; hereda la transacción y el lock del preparador.
- La tabla de métricas se prepara antes de crear la FK desde `labeling_metric_correction`.
- No se almacenan tokens de lease en texto, SAS, transcripciones, nombres ni correos.
- Los comentarios no participan en índices y no se copian a auditoría.

## 7. Verificación ejecutada

- `python -m py_compile backend/labeling_migration.py backend/scripts/prepare_azure_database.py`: correcto.
- Auditoría estática del DDL: `4` tablas, `11` pasos, `14` FKs, `14` índices y `0` operaciones DML.
- Orden del preparador: `BEGIN TRANSACTION -> sp_getapplock -> migrate_metrics -> migrate_labeling -> verify -> commit`: correcto.
- `python -m pytest tests/test_microlesson_assignment_migration.py -q`: `3 passed`.
- Validación de fixtures de T0 permanece en `17/17` JSON válidos.
- `git diff --check`: correcto.

Limitaciones del entorno de pruebas:

- La colección que importa `prepare_azure_database.py` no pudo ejecutarse con el Python global porque falta `pyodbc`.
- La suite de métricas/rutas no pudo recolectarse porque falta `azure-storage-blob`.
- Docker Desktop no está activo, por lo que no hubo un contenedor con las dependencias del backend.
- No se instaló software ni se aplicó DDL para evitar ampliar el alcance.

## 8. Fuera de este avance

Quedan expresamente sin iniciar las subtareas 5 a 10:

- comando de backfill/reconciliación y `--dry-run`;
- clasificación y reporte de anomalías durante el backfill;
- estimación de volumen y duración;
- verificación estructural en `--verify-only`;
- pruebas formales de doble ejecución, rollback y backfill repetido.

Por lo anterior, `prepare_azure_database.py --verify-only` todavía no comprueba las tablas de etiquetado y G2 no puede declararse alcanzado.
