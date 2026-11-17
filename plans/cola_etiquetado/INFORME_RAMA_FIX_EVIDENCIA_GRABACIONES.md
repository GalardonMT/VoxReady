# Informe de cambios de la rama de integridad de grabaciones

Fecha: 13 de noviembre de 2026  
Rama: `fix/cola-etiquetado-evidencia-grabaciones`  
Base: `origin/merge/lineas-rojas-main` en `eeec4e4`

## Resumen ejecutivo

Esta rama corrige la integridad de los casos de la Cola de Etiquetado cuando una entrevista no tiene una grabación sellada y verificable. El objetivo es impedir que un experto revise un caso sin evidencia reproducible, evitar que el worker cree casos incompletos ante errores de almacenamiento y permitir reanudar de forma segura entregas repetidas del mismo trabajo de análisis.

Los casos históricos sin evidencia recuperable se conservan para auditoría, pero no aparecen en **Pendientes** ni pueden abrirse, reservarse o revisarse directamente. No se añadió una sección de interfaz denominada "No revisable".

## Estado de entrega

- Los cambios están locales y sin commit ni push.
- No se ejecutaron migraciones, reparaciones históricas, despliegues ni escrituras en Azure.
- La herramienta de reparación histórica está incluida, pero requiere un manifiesto explícito y confirmación de escritura antes de modificar datos.
- La rama parte de `eeec4e4`; no contiene commits adicionales al momento de este informe.

## Problemas corregidos

| Problema previo | Cambio aplicado | Resultado esperado |
| --- | --- | --- |
| El sellado de la grabación podía fallar y el análisis continuaba. | El sellado se volvió obligatorio antes de continuar el pipeline. | No se materializa un caso etiquetable sin grabación sellada. |
| Existía un fallback SQL directo si fallaba la materialización canónica. | Se eliminó el fallback; solo se usa la creación canónica de `labeling_case`. | No se crean snapshots parciales o inconsistentes. |
| Un reintento podía duplicar o sobrescribir resultados intermedios. | Se serializa por trabajo, se conserva la primera escritura y se reintenta solo ante errores SQL transitorios. | La repetición del mismo trabajo no altera la evidencia original ni duplica pipelines. |
| Un proceso rezagado podía marcar como fallida una sesión o job ya completado. | Se protege la transición terminal y se verifica bajo bloqueo si existe un informe persistido. | Un resultado completado no se degrada por un delivery tardío. |
| Casos históricos parciales podían quedar ocultos en la lista, pero ser accedidos por URL. | La regla de evidencia completa se aplica a listado, detalle, reserva y revisión. | No existe bypass de la cola para revisar evidencia incompleta. |

## Cambios por componente

### Worker y sellado de evidencia

Archivos principales:

- `worker/services/recording_evidence.py`
- `worker/core/pipeline_orchestrator.py`

Cambios:

1. Se exige una grabación WebM o MP4 válida y se descartan tipos de contenido fabricados o rutas no válidas.
2. La evidencia sellada valida ruta, hash SHA-256, tamaño, metadatos de sesión y job, ETag, MIME de video y marca `sealed=true`.
3. Los errores transitorios de Blob se reintentan con backoff acotado. Los errores de integridad, permisos o contenido no se reintentan.
4. El pipeline sella la evidencia antes del análisis restante y agrega `recordingEvidence` al resultado de fusión.
5. Si persiste el informe pero falla una etapa posterior, la sesión se mantiene o restaura como `completed` para permitir que el delivery se reanude.

### Persistencia SQL, reintentos e idempotencia

Archivos principales:

- `worker/services/db_service.py`
- `worker/services/pipeline_results.py`
- `worker/services/job_status.py`

Cambios:

1. `finalize_session_analysis` se serializa por `analysis_job_id` mediante `sp_getapplock` y reutiliza el informe existente del mismo job, sesión y rúbrica.
2. El informe ya persistido no vuelve a crear una nueva versión ni vuelve a actualizar progreso o agenda. Si la sesión había sido degradada por un error anterior, se restaura a `completed` sin repetir esos efectos secundarios.
3. `persist_pipeline_results` usa un bloqueo transaccional por job y `UPDLOCK, HOLDLOCK`. Para cada pipeline: cero registros inserta, uno conserva el resultado original y más de uno falla explícitamente para no ocultar corrupción histórica.
4. Los reintentos están limitados a tres intentos y solo para códigos SQL transitorios conocidos.
5. La transición de job a `completed` es estricta, limpia `failure_reason` y conserva la primera fecha `completed_at`. La transición de limpieza a `failed` es best-effort y no puede sobrescribir un job ya completado.
6. Se eliminó la inserción SQL de fallback de `create_labeling_case_if_needed`; ahora llama únicamente a `ensure_labeling_case_for_report`.

### Cola de etiquetado y protección de rutas directas

Archivos principales:

- `backend/labeling_store.py`
- `backend/metrics_store.py`

Un caso pendiente solo es revisable si cumple todas estas condiciones:

1. No tiene `source_status='ambiguous'`.
2. Su ruta de evidencia comienza con `labeling-evidence/` y no contiene `..`.
3. Tiene SHA-256 de 32 bytes, ETag no vacío y MIME `video/*`.

Esta regla se aplica en el conteo, el listado de Pendientes, el resumen del panel maestro, el detalle, la adquisición de reserva y el envío de una revisión. Los casos ya revisados siguen siendo consultables aunque sean históricos.

El resumen de casos pendientes se corrigió para usar los valores canónicos de `queue_reason`: `critical`, `borderline`, `disparity` y `routine`.

### Reparación controlada de históricos

Archivos principales:

- `worker/services/labeling_runtime.py`
- `worker/repair_labeling_cases.py`

Se incorporó `repair_ambiguous_case`, que puede reparar un caso histórico pendiente con estado `ambiguous` o `partial` solo cuando se entrega evidencia sellada exacta. La reparación:

1. Verifica la grabación contra Azure Blob usando hash, ETag, tamaño, MIME, metadatos de sesión y job y, cuando corresponde, versión del blob.
2. Reconstruye el snapshot desde el informe, áreas, métricas y pipelines existentes.
3. Exige que el snapshot reconstruido sea completo.
4. Usa bloqueo de fila y rechaza conflictos, cambios concurrentes, evidencia distinta, casos ya válidos o casos revisados.
5. Incrementa `content_revision` al actualizar el caso.

El comando se ejecuta con un manifiesto JSON explícito y ofrece dos modos:

```powershell
Set-Location .\worker
python .\repair_labeling_cases.py --dry-run --manifest ..\manifest.json
python .\repair_labeling_cases.py --apply --manifest ..\manifest.json --confirm-write APPLY_LABELING_RECORDING_REPAIR
```

El modo `dry-run` revierte la transacción. El modo `apply` requiere la confirmación literal para evitar una reparación accidental.

## Archivos nuevos

- `worker/services/pipeline_results.py`
- `worker/services/job_status.py`
- `worker/repair_labeling_cases.py`
- `worker/tests/test_pipeline_results.py`
- `worker/tests/test_job_status.py`
- `worker/tests/test_recording_evidence_retry.py`
- `worker/tests/test_repair_labeling_cases.py`

## Pruebas y verificaciones ejecutadas

| Alcance | Resultado |
| --- | --- |
| Pruebas focalizadas del worker: runtime de etiquetado, evidencia, reparación, pipelines, estados y persistencia | 64 aprobadas |
| Pruebas de `backend/labeling_store.py` | 16 aprobadas |
| Verificación focal del resumen de métricas | Aprobada |
| Sintaxis Python de módulos modificados | Correcta |
| `git diff --check` | Sin errores de espacios |
| Auditoría de diseño y concurrencia del diff combinado | Sin bloqueantes P0/P1 conocidos |

## Gates externos pendientes

Estos puntos no son fallos confirmados del cambio; requieren un entorno con servicios reales:

1. Ejecutar las suites completas con las dependencias locales faltantes (`openai`, `pyodbc` y paquetes Azure en el host actual).
2. Ejecutar una prueba end-to-end contra Azure SQL y Azure Blob: entrevista, sellado, análisis, generación de caso, apertura de la cola y reproducción de la grabación.
3. Ejecutar una prueba de concurrencia real en Azure SQL para deliveries simultáneos del mismo `analysis_job_id`.
4. Antes de reparar históricos, generar y revisar el manifiesto de evidencia exacta; no se deben inferir rutas ni fabricar métricas o grabaciones.
5. Tras completar los gates externos, crear commit, subir la rama y abrir un Pull Request hacia la rama que se defina como destino de integración.

## Alcance no realizado

- No se modificó el diseño visual de la Cola de Etiquetado.
- No se creó una vista de "No revisable".
- No se ejecutó reparación de casos históricos en Azure.
- No se aplicaron cambios de esquema ni se modificaron datos de producción.
- No se creó commit, push ni Pull Request.
