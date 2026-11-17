# Diagnóstico de esquema, datos y almacenamiento

## 1. Control del documento

- Alcance: Tarea 0 de `PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md`.
- Naturaleza: diagnóstico de solo lectura; no se aplicaron migraciones ni cambios de datos o configuración.
- Entorno SQL observado: `sqldb-voxready`.
- Consulta SQL: 29 de octubre de 2026 a las 01:29 UTC (28 de octubre de 2026 en `America/Santiago`).
- Fuentes: esquema y conteos de Azure SQL, propiedades del servicio Azure Blob y código del repositorio.
- Privacidad: no se consultaron ni registraron nombres, correos, transcripciones, comentarios, identificadores de usuarios, rutas de blobs ni contenidos audiovisuales.

Los resultados vivos son una fotografía puntual. Deben repetirse inmediatamente antes de ejecutar el backfill de la Tarea 1.

## 2. Resumen ejecutivo

| Hallazgo | Resultado comprobado | Consecuencia para la cola |
|---|---:|---|
| Sesiones completadas y no eliminadas | 24 | Universo histórico candidato. |
| Informes totales / actuales | 24 / 24 | Todas las sesiones completadas tienen un informe marcado actual. |
| Candidatos con cadena coherente `session -> report -> analysis_job -> fusion` | 21 | Superan el enlace relacional, pero todavía no son `sourceStatus=complete`. |
| Informes actuales con `analysis_job_id` nulo | 1 | Debe quedar `ambiguous`; no existe vínculo canónico. |
| Informes actuales con `analysis_job_id` huérfano | 1 | Debe quedar `ambiguous`; la fila de job no existe. |
| Informes actuales con job válido pero sin `fusion` | 1 | Debe quedar `ambiguous`; no existe propuesta IA canónica. |
| Sesiones con más de un informe actual | 0 | No hay duplicidad actual en esta fotografía, aunque el esquema no la impide. |
| Jobs con más de un `fusion` | 0 | No hay duplicidad actual en esta fotografía, aunque el esquema no la impide. |
| Filas de `recording` | 0 | La tabla no permite resolver las 24 grabaciones históricas. |
| Blobs inventariados en el contenedor configurado | 87 | Hay medios fuera del inventario SQL; deben resolverse y sellarse explícitamente. |
| Filas de `audit_event` | 0 | El esquema existe, pero aún no hay evidencia de uso en este entorno. |
| Versiones de Blob observadas | 0 | No existe evidencia de versionado habilitado ni de versiones históricas. |
| Retención por borrado de Blob | deshabilitada | Un overwrite o borrado no tiene recuperación demostrada por esta política. |
| CORS del servicio Blob | 2 reglas duplicadas con origen `*` | Debe restringirse al origen desplegado antes del gate de seguridad. |

Conclusión: 21 de 24 sesiones completadas son candidatos relacionalmente coherentes. Los 21 también tienen cuatro áreas distintas y un `fusion.reportId`/`report_id` coincidente, pero ninguno puede declararse `sourceStatus=complete` hasta validar y sellar el medio exacto analizado. Los otros 3 quedan preliminarmente `ambiguous`: uno no tiene `analysis_job_id`, otro tiene una referencia huérfana y el tercero posee un job válido sin `fusion`.

## 3. Inventario del esquema real

### 3.1 `dbo.recording`

Columnas comprobadas:

| Columna | Tipo | Nula |
|---|---|---|
| `id` | `uniqueidentifier` | no |
| `session_id` | `uniqueidentifier` | no |
| `blob_container` | `nvarchar` | no |
| `blob_path` | `nvarchar` | no |
| `content_type` | `nvarchar` | no |
| `duration_seconds` | `int` | sí |
| `status` | `nvarchar` | no |
| `created_at` | `datetime2` | no |

Restricciones comprobadas:

- Clave primaria por `id`.
- Índice único por `session_id`: el modelo permite como máximo una fila de grabación por sesión.
- Llave foránea `recording.session_id -> session.id`.
- No existen campos para `version_id`, ETag, SHA-256, fecha de archivado o borrado.
- La tabla contiene 0 filas. Las 24 sesiones completadas carecen de registro asociado.

Por lo tanto, la tabla actual no es una fuente histórica utilizable. En la reconciliación se debe verificar la ruta real de cada blob y registrar una evidencia nueva e inmutable; no se debe insertar una asociación solo porque exista el patrón nominal `recordings/{session_id}.webm`.

### 3.2 `dbo.audit_event`

Columnas comprobadas:

`id`, `client_id`, `actor_user_id`, `event_type`, `entity_type`, `entity_id`, `detail_json`, `occurred_at`, `created_at`, `updated_at`.

Restricciones comprobadas:

- Clave primaria por `id`.
- Índice no único por `(client_id, event_type, occurred_at)`.
- Llaves foráneas opcionales hacia `client` y `app_user`.
- La tabla contiene 0 filas y no hay tipos de evento observables en datos vivos.

El esquema alcanza para eventos de la cola, pero la implementación debe establecer una lista blanca para `detail_json`; ese campo no debe almacenar SAS, tokens de lease, comentarios completos, nombres, correos ni transcripciones.

### 3.3 `dbo.report`

Columnas comprobadas:

`id`, `session_id`, `rubric_version_id`, `overall_score`, `narrative_strengths`, `narrative_improvements`, `cross_signal_observation`, `version_no`, `is_current`, `generated_at`, `analysis_job_id`.

Restricciones comprobadas:

- Solo existe la clave primaria por `id`.
- Existen llaves foráneas a `session` y `rubric_version`.
- `analysis_job_id` es nullable y no tiene llave foránea a `analysis_job`.
- No hay índice único por `(session_id, version_no)`.
- No hay índice filtrado que garantice una sola fila `is_current=1` por sesión.

El worker inserta cada informe con `version_no=1` e `is_current=1` en `worker/services/db_service.py:335-352`, sin desactivar un informe anterior. El hecho de que hoy no existan duplicados no convierte esa propiedad en una garantía.

### 3.4 `dbo.analysis_pipeline_result`

Columnas comprobadas:

`id`, `analysis_job_id`, `pipeline`, `status`, `summary_json`, `raw_blob_path`, `created_at`, `updated_at`.

Restricciones comprobadas:

- Clave primaria por `id`.
- Llave foránea a `analysis_job`.
- Índice no único por `(analysis_job_id, pipeline)`.
- No existe unicidad para un solo `fusion` por job.

El worker inserta cada resultado sin upsert ni unicidad en `worker/core/pipeline_orchestrator.py:244-259`. En la fotografía actual hay 21 filas `fusion`, ninguna duplicada y ninguna con JSON nulo o inválido.

### 3.5 `dbo.analysis_job` y `dbo.session`

- `analysis_job` referencia a `session` y `rubric_version` y posee un índice no único por `session_id`.
- `session` contiene `started_at`, `finished_at`, `created_at`, `updated_at`, `status` e `is_deleted`, además de sus relaciones de cliente, usuario, escenario y rúbrica.
- No se detectaron discrepancias de sesión o rúbrica entre los informes actuales que sí enlazan a un job.
- No hay sesiones completadas sin informe ni sin un informe marcado actual.

## 4. Diagnóstico cuantificado de informes y `fusion`

| Comprobación | Conteo |
|---|---:|
| Sesiones completadas, no eliminadas | 24 |
| Informes totales | 24 |
| Informes `is_current=1` | 24 |
| Sesiones con múltiples informes actuales | 0 |
| Filas actuales dentro de esas sesiones duplicadas | 0 |
| Informes con `version_no` nulo o menor que 1 | 0 |
| Pares duplicados `(session_id, version_no)` | 0 |
| Sesiones con secuencia de versiones no contigua | 0 |
| Informes actuales con `analysis_job_id` nulo | 1 |
| Informes actuales cuyo `analysis_job_id` no existe | 1 |
| Informes actuales cuyo job pertenece a otra sesión | 0 |
| Discrepancias de rúbrica informe/sesión | 0 |
| Discrepancias de rúbrica informe/job | 0 |
| Filas `fusion` | 21 |
| Jobs con múltiples `fusion` | 0 |
| Informes actuales con `analysis_job_id` no nulo pero sin `fusion` | 2; incluye la referencia huérfana |
| Informes actuales con job válido pero sin `fusion` | 1 |
| Informes actuales con múltiples `fusion` | 0 |
| `fusion` con `summary_json` nulo o inválido | 0 |
| Informes actuales con cantidad de `area_score` distinta de 4 | 0 |
| Informes actuales con cantidad de áreas distintas diferente de 4 | 0 |
| Informes actuales con un área duplicada | 0 |
| Candidatos con cadena report-job y un único `fusion` | 21 |
| Candidatos cuyo `fusion` no contiene `reportId` ni `report_id` | 0 |
| Candidatos cuyo identificador de informe en `fusion` coincide con `report.id` | 21 |
| Candidatos cuyo identificador de informe en `fusion` no coincide | 0 |

Clasificación preliminar obligatoria para el backfill:

1. Candidatos pendientes de validar medio: exactamente 21 cadenas con una sesión completada, un único informe actual, job coherente, cuatro áreas distintas y un único `fusion` válido cuyo identificador interno coincide con `report.id`. Esta evidencia todavía no autoriza `sourceStatus=complete` porque falta demostrar la identidad inmutable del medio analizado.
2. `ambiguous`: 3 informes; uno tiene `analysis_job_id` nulo, otro un identificador de job huérfano y otro un job coherente sin `fusion`. El esquema permite la referencia huérfana porque no existe FK `report.analysis_job_id -> analysis_job.id`.
3. `partial`: 0 casos asignados en esta fotografía. No se usa `partial` para un job sin `fusion`, porque falta por completo la propuesta IA canónica que se pretende revisar.

No se debe interpretar el resultado actual de 0 duplicados como una regla permanente. Las restricciones faltantes y el código de inserción permiten crear duplicados en una reevaluación futura.

## 5. Diagnóstico de grabaciones y Blob Storage

### 5.1 Estado de SQL

- `recording`: 0 filas.
- Sesiones completadas sin fila `recording`: 24.
- Políticas `retention_policy` marcadas actuales: 0.
- La aplicación devuelve por defecto una retención de 30 días cuando no existe política persistida (`backend/spokesperson_store.py:204-207`), pero ese fallback no demuestra que el storage aplique dicha retención.

### 5.2 Estado del servicio Blob

Consulta de propiedades e inventario, sin descargar contenido:

| Propiedad | Resultado |
|---|---|
| Contenedor configurado | existe y es privado (`public_access` ausente) |
| Blobs/entradas actuales inventariados | 87 |
| Entradas con `version_id` | 0 |
| Entradas borradas visibles | 0 |
| `is_versioning_enabled` | no informado por el servicio; no hay evidencia de habilitación |
| Retención de blobs borrados | deshabilitada |
| Retención de contenedores borrados | no informada |
| Change feed | no informado |
| Point-in-time restore | no informado |
| CORS | dos reglas iguales con `allowed_origins=*`, métodos `GET,PUT,OPTIONS`, headers `*` y 3600 s |
| Blob de muestra no identificado | ETag presente, sin `version_id`, tamaño positivo, `Content-Type=video/mp4` |

El muestreo no registró el nombre del blob. El `Content-Type=video/mp4` confirma que no se puede suponer que todo medio histórico sea `.webm`, aunque los endpoints actuales construyen esa extensión de forma fija.

### 5.3 Política de sobrescritura comprobada en código

- La subida directa usa una ruta determinista `recordings/{session_id}.webm` y una SAS con permisos `create` y `write` (`backend/main.py:543-574`). No condiciona la escritura a un ETag previo.
- El worker descarga el blob sin fijar `version_id` ni capturar ETag/SHA-256 (`worker/services/blob_service.py:45-82`).
- El reporte JSON se guarda como `{session_id}_report.json` con `overwrite=True` (`worker/core/pipeline_orchestrator.py:227-239`).
- La variante de `BlobService.upload_report` también usa `overwrite=True` (`worker/services/blob_service.py:84-110`).
- El endpoint de informe busca el `fusion` más reciente por sesión, no el job ligado al `report`, y luego cae al JSON por sesión (`backend/main.py:849-882`).
- El helper interno de reproducción devuelve una URL pública construida cuando falta storage o falla la generación SAS (`backend/main.py:775-795`). Esa ruta de fallback no es aceptable para la cola maestra.

No existe hoy una identidad inmutable del medio analizado. Para T2 se requiere, como condición mínima:

1. calcular SHA-256 de los bytes realmente descargados por el worker;
2. preservar esos mismos bytes mediante una versión de Blob demostrablemente habilitada o una copia sellada de nombre único;
3. guardar ETag y `version_id` cuando existan;
4. prohibir overwrite de la evidencia sellada, incluyendo credenciales y SAS de escritura;
5. asegurar que la retención de evidencia cubra las revisiones confirmadas.

## 6. Consultas SQL reproducibles de solo lectura

Estas consultas no devuelven PII. Deben ejecutarse con una identidad de lectura y repetirse antes del backfill.

```sql
SELECT COUNT_BIG(*) AS completed_sessions
FROM dbo.[session]
WHERE status = 'completed' AND ISNULL(is_deleted, 0) = 0;

SELECT session_id, COUNT_BIG(*) AS current_count
FROM dbo.report
WHERE is_current = 1
GROUP BY session_id
HAVING COUNT_BIG(*) > 1;

SELECT session_id, version_no, COUNT_BIG(*) AS duplicate_count
FROM dbo.report
GROUP BY session_id, version_no
HAVING COUNT_BIG(*) > 1;

SELECT COUNT_BIG(*) AS reports_missing_job
FROM dbo.report AS r
LEFT JOIN dbo.analysis_job AS j ON j.id = r.analysis_job_id
WHERE r.is_current = 1 AND j.id IS NULL;

SELECT analysis_job_id, COUNT_BIG(*) AS fusion_count
FROM dbo.analysis_pipeline_result
WHERE pipeline = 'fusion'
GROUP BY analysis_job_id
HAVING COUNT_BIG(*) <> 1;

SELECT COUNT_BIG(*) AS reports_without_exactly_four_areas
FROM dbo.report AS r
OUTER APPLY (
    SELECT COUNT_BIG(DISTINCT a.rubric_area_id) AS area_count
    FROM dbo.area_score AS a
    WHERE a.report_id = r.id
) AS scores
WHERE r.is_current = 1 AND scores.area_count <> 4;

SELECT COUNT_BIG(*) AS duplicated_report_area_groups
FROM (
    SELECT a.report_id, a.rubric_area_id
    FROM dbo.area_score AS a
    JOIN dbo.report AS r ON r.id = a.report_id AND r.is_current = 1
    GROUP BY a.report_id, a.rubric_area_id
    HAVING COUNT_BIG(*) > 1
) AS duplicated;

SELECT
    SUM(CASE WHEN ISJSON(apr.summary_json) <> 1 THEN 1 ELSE 0 END) AS invalid_json,
    SUM(CASE WHEN ISJSON(apr.summary_json) = 1
              AND COALESCE(JSON_VALUE(apr.summary_json, '$.reportId'),
                           JSON_VALUE(apr.summary_json, '$.report_id')) IS NULL
             THEN 1 ELSE 0 END) AS missing_report_id,
    SUM(CASE WHEN ISJSON(apr.summary_json) = 1
              AND LOWER(COALESCE(JSON_VALUE(apr.summary_json, '$.reportId'),
                                 JSON_VALUE(apr.summary_json, '$.report_id')))
                  = LOWER(CONVERT(nvarchar(36), r.id))
             THEN 1 ELSE 0 END) AS matching_report_id,
    SUM(CASE WHEN ISJSON(apr.summary_json) = 1
              AND COALESCE(JSON_VALUE(apr.summary_json, '$.reportId'),
                           JSON_VALUE(apr.summary_json, '$.report_id')) IS NOT NULL
              AND LOWER(COALESCE(JSON_VALUE(apr.summary_json, '$.reportId'),
                                 JSON_VALUE(apr.summary_json, '$.report_id')))
                  <> LOWER(CONVERT(nvarchar(36), r.id))
             THEN 1 ELSE 0 END) AS mismatching_report_id
FROM dbo.report AS r
JOIN dbo.analysis_job AS j
  ON j.id = r.analysis_job_id AND j.session_id = r.session_id
JOIN dbo.analysis_pipeline_result AS apr
  ON apr.analysis_job_id = j.id AND apr.pipeline = 'fusion'
WHERE r.is_current = 1
  AND (SELECT COUNT_BIG(*) FROM dbo.report AS r2
       WHERE r2.session_id = r.session_id AND r2.is_current = 1) = 1
  AND (SELECT COUNT_BIG(*) FROM dbo.analysis_pipeline_result AS x
       WHERE x.analysis_job_id = j.id AND x.pipeline = 'fusion') = 1;

SELECT
    SUM(CASE WHEN coherent.report_id IS NOT NULL THEN 1 ELSE 0 END) AS coherent_candidate_count,
    COUNT_BIG(*) - SUM(CASE WHEN coherent.report_id IS NOT NULL THEN 1 ELSE 0 END) AS ambiguous_count
FROM dbo.[session] AS s
LEFT JOIN (
    SELECT r.id AS report_id, r.session_id
    FROM dbo.report AS r
    JOIN dbo.analysis_job AS j
      ON j.id = r.analysis_job_id AND j.session_id = r.session_id
    WHERE r.is_current = 1
      AND (SELECT COUNT_BIG(*) FROM dbo.report AS r2
           WHERE r2.session_id = r.session_id AND r2.is_current = 1) = 1
      AND (SELECT COUNT_BIG(*) FROM dbo.analysis_pipeline_result AS apr
           WHERE apr.analysis_job_id = j.id AND apr.pipeline = 'fusion') = 1
) AS coherent ON coherent.session_id = s.id
WHERE s.status = 'completed' AND ISNULL(s.is_deleted, 0) = 0;

SELECT
    (SELECT COUNT_BIG(*) FROM dbo.recording) AS recording_rows,
    (SELECT COUNT_BIG(*) FROM dbo.audit_event) AS audit_rows,
    (SELECT COUNT_BIG(*) FROM dbo.retention_policy WHERE is_current = 1) AS current_retention_policies;
```

Para revalidar el esquema se debe consultar `INFORMATION_SCHEMA.COLUMNS`, `sys.indexes` y `sys.foreign_keys` filtrando exclusivamente las seis tablas inventariadas. No se debe usar un volcado completo de la base.

## 7. Decisiones congeladas a partir del diagnóstico

1. La fuente canónica no puede ser “el último `fusion` de la sesión”. Debe ser el `report` exacto, su `analysis_job_id` válido y exactamente un `fusion` de ese job.
2. `report.analysis_job_id` nulo o huérfano produce `ambiguous`, nunca una unión por proximidad temporal.
3. Un job sin `fusion` produce `ambiguous`; las áreas SQL aisladas no bastan para reconstruir la propuesta IA canónica y ninguna métrica se rellena con defaults.
4. Más de un informe actual, versión duplicada o más de un `fusion` produce `ambiguous` y excluye el caso del backfill automático hasta resolución explícita.
5. La tabla `recording` vacía no se rellenará por inferencia. La existencia, formato, hash y evidencia sellada se verifican por blob.
6. Una ETag del blob mutable no basta. La revisión debe referenciar `version_id` o una copia sellada cuyo overwrite sea imposible.
7. La cola no usará el fallback de URL pública ni una SAS de 60 minutos. El contrato planificado exige una SAS de lectura corta para la evidencia exacta.
8. Las reglas CORS con `*`, la retención deshabilitada y la ausencia de versionado son bloqueos para el gate de storage seguro, no para documentar T0.

## 8. Evidencia pendiente y límites

- `SIN EVIDENCIA`: que Azure Blob versioning esté habilitado. El servicio no devolvió `true` y el inventario contiene 0 entradas con versión.
- `SIN EVIDENCIA`: que exista una política efectiva de retención para grabaciones o futura evidencia; SQL contiene 0 políticas actuales y Blob soft delete está deshabilitado.
- `SIN EVIDENCIA`: que las 87 entradas correspondan una a una con las 24 sesiones completadas. No se expusieron nombres y la tabla `recording` no ofrece el vínculo.
- `SIN EVIDENCIA`: que los bytes analizados por cada uno de los 21 candidatos sean los mismos que hoy serviría Blob. Hasta sellarlos y comprobar su hash, ninguno es `sourceStatus=complete`.
- `SIN EVIDENCIA`: que todos los medios soporten seeking por rangos con su `Content-Type` correcto; solo se inspeccionó metadata de una entrada.
- `POR DEFINIR EN T2`: mecanismo operativo para copia sellada, permisos que impidan overwrite y política de retención de evidencia.
- `POR CORREGIR ANTES DE ACTIVAR`: CORS de Blob restringido a orígenes desplegados y eliminación del fallback público para el endpoint maestro.

## 9. Resultado de este frente de Tarea 0

El inventario y el diagnóstico cuantificado están completos para la fotografía observada. No se modificó el entorno. Existen 21 candidatos con informe, cuatro áreas y `fusion` coherentes, y 3 casos preliminares `ambiguous`; todavía hay 0 casos demostrados como `sourceStatus=complete` porque no existe evidencia audiovisual sellada. Este documento habilita el diseño de T1, pero no autoriza ejecutar migraciones ni backfill. Antes de escribir casos se debe repetir el preflight y clasificar cada fila sin reparación silenciosa.
