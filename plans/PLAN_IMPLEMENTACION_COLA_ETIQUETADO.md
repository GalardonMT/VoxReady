# Plan de implementación de la cola de etiquetado

## 1. Control del plan

- Estado: Tareas 0 a 3 completas en código. Tarea 3 concentra lectura, leases, revisión inmutable, auditoría y agregados en un store sin FastAPI, verificado con pruebas locales. La concurrencia real en SQL aislado, Azure Blob y Docker permanece para Tarea 9. No se aplicó DDL, reconciliación persistente ni despliegue.
- Rama de trabajo: `feat/cola-de-etiquetado`.
- Base verificada: `main` y `feat/metrics-editor` apuntaban al commit `3ab3240` al crear la rama.
- Fecha del plan: 27 de octubre de 2026.
- Modalidad: una sola rama, tareas ejecutadas como checkpoints revisables. No se inicia una tarea posterior sin validar la anterior.
- Despliegue, migración persistente, commit, push y PR: requieren autorización explícita en el avance correspondiente.

Este archivo es la fuente de verdad del alcance. Si una decisión cambia, se debe actualizar primero la sección 16, "Registro de cambios del plan", y después la tarea afectada.

## 2. Objetivo

Reemplazar la información simulada de la Cola de Etiquetado por un flujo dinámico y auditable, exclusivo para `master_config`, que:

1. Muestre las diez entrevistas completadas más recientes que todavía no tengan una revisión confirmada.
2. Permita consultar también las diez revisiones confirmadas más recientes en una vista separada.
3. Presente la grabación, los datos de la sesión, el informe exacto, los cuatro puntajes de rúbrica y las métricas técnicas disponibles.
4. Permita a un experto corregir puntajes de rúbrica y métricas individuales, junto con observaciones generales y específicas.
5. Guarde la revisión de forma atómica e inmutable, ligada al informe y a la versión de rúbrica evaluados.
6. Evite ediciones simultáneas mediante una reserva renovable de veinte minutos y control de versión al guardar.
7. Muestre evidencia agregada de las revisiones en el Editor de Rúbrica y en el Editor de Métricas, sin cambiar automáticamente pesos, umbrales ni versiones publicadas.
8. Conserve las correcciones para una exportación o proceso de entrenamiento posterior, separado y auditable.
9. Cree casos nuevos de forma idempotente cada vez que se finalice un informe elegible, además de reconciliar el histórico existente.
10. Preserve un snapshot verificable de la propuesta IA y del medio evaluado para que una revisión nunca dependa de un JSON sobrescrito o ambiguo.

## 3. Decisiones cerradas

Estas decisiones no se vuelven a discutir durante la implementación salvo que aparezca evidencia técnica nueva:

- Entran todas las sesiones completadas que tengan un informe actual, no solo muestras o casos críticos.
- La cola pendiente muestra un máximo de diez casos, ordenados por `session.finished_at DESC`.
- Una revisión confirmada sale de Pendientes y aparece en Revisadas.
- La vista Revisadas muestra inicialmente las diez revisiones más recientes.
- Se considera crítico un puntaje global inferior a 50 o cualquier área inferior a 50.
- La revisión corrige puntajes del caso; no modifica ponderaciones globales de la rúbrica.
- Las métricas se revisan individualmente. Las categorías son agrupaciones visuales, no puntajes nuevos almacenados.
- Gobernanza explica por qué un caso requiere atención, pero no se calibra como desempeño del vocero.
- El frontend muestra empresa y un código seudonimizado del vocero, nunca nombre ni correo.
- Las políticas vigentes permiten que `master_config` consulte las grabaciones para control de calidad y generación de evidencia de entrenamiento.
- Puede haber más de un experto. Abrir un caso intenta reservarlo por veinte minutos.
- Otro experto puede ver un caso reservado, pero solo en modo lectura.
- La reserva se renueva mientras la pestaña esté visible y exista actividad reciente del usuario; la inactividad deja expirar la reserva.
- Una revisión confirmada es inmutable. Una corrección posterior debe generar una nueva revisión, sin sobrescribir la anterior.
- Las revisiones de un caso forman un historial numerado; solo una se marca como vigente para los agregados por defecto.
- Confirmar una revisión solo guarda evidencia. No dispara reentrenamiento ni cambia configuraciones publicadas.
- Las observaciones no se envían al vocero ni al administrador cliente.
- La propuesta IA se obtiene siempre en servidor desde el snapshot del caso. El navegador nunca puede declarar el `ai_value` original.
- El token de lease es específico de una adquisición y de una pestaña. Renovar no cambia la revisión de contenido del caso.

## 4. Fuera de alcance

- Reentrenar, afinar o desplegar modelos.
- Modificar automáticamente pesos de rúbrica o umbrales de métricas.
- Enviar notificaciones de revisión a voceros o administradores cliente.
- Crear una puntuación artificial para la categoría Gobernanza.
- Inventar valores para métricas que el worker no produzca.
- Rediseñar visualmente la Cola de Etiquetado.
- Convertir el Editor de Rúbrica completo a persistencia si ello no es necesario para mostrar la evidencia de calidad.
- Desplegar a producción o aplicar migraciones a Azure SQL sin una aprobación específica.
- Eliminar revisiones, informes, sesiones o grabaciones históricas.

## 5. Línea base comprobada

- `LabelingQueueView.tsx` importa `INITIAL_LABELING_QUEUE`, simula el reproductor y solo cambia estado local.
- `rubricService.ts` declara rutas de cola, pero la vista no las usa y el backend no implementa actualmente esos contratos.
- `RecordingVideoPlayer.tsx` ya ofrece reproducción, pausa, búsqueda, saltos de cinco segundos, buffer, volumen, velocidad y pantalla completa.
- El informe de sesión ya entrega puntaje global, áreas, narrativa, métricas y una URL temporal de grabación.
- El catálogo maestro contiene 16 configuraciones agrupadas en Voz, Video, Contenido, Empatía y Gobernanza. No todas representan una medición por caso.
- El documento de modelo de datos define `labeling_case` y `labeling_correction`, pero el repositorio no contiene una migración ni un store de cola.
- El Editor de Métricas es versionado. El Editor de Rúbrica mantiene actualmente estado local.
- El flujo actual puede guardar `report` antes que `analysis_pipeline_result.fusion`, y los JSON de Blob se nombran por sesión. La implementación debe corregir esta ambigüedad antes de llamar "exacta" a la evidencia de un caso.
- El worker actual no garantiza todavía una sola fila `is_current=1` ni un `version_no` creciente por sesión; el plan incluye un preflight y una corrección transaccional para informes futuros, sin reescribir silenciosamente el histórico.

## 6. Arquitectura objetivo

```text
sesión completada
    -> informe, áreas y fusion exacta persistidos de forma coherente
    -> snapshot versionado de propuesta IA y medio
    -> creación runtime idempotente de labeling_case
    -> GET cola pendiente, máximo 10
    -> experto abre el caso
    -> reserva de 20 minutos
    -> detalle + SAS de video de solo lectura
    -> calibración de rúbrica + métricas + observaciones
    -> confirmación atómica e inmutable
    -> caso pasa a revisado
    -> agregados de calidad disponibles para ambos editores
    -> exportación de entrenamiento futura y separada
```

La API de cola será la única superficie usada por esta pantalla. El frontend no compondrá el caso consultando por separado endpoints de sesiones, informes y grabaciones. Un reconciliador idempotente cubrirá casos históricos u omisiones operativas, pero no sustituirá la creación runtime.

La activación se controla por etapas:

1. Crear y verificar esquema, sin escrituras de casos.
2. Activar `LABELING_QUEUE_WRITES_ENABLED` para creación runtime.
3. Ejecutar reconciliación/backfill explícito, primero en `--dry-run` y por lotes.
4. Activar `LABELING_QUEUE_API_ENABLED`.
5. Activar la vista frontend solo después del smoke test de API.

El rollback desactiva UI, API y escrituras en ese orden. No elimina tablas ni revisiones.

## 7. Modelo de datos propuesto

### 7.1 `labeling_case`

Registro de una versión concreta de informe que debe revisarse.

| Campo | Propósito |
|---|---|
| `id` | GUID interno. |
| `case_number` | Número legible y estable mostrado como `Caso #...`. |
| `client_id` | Tenant propietario; requerido para filtros, auditoría y aislamiento. |
| `session_id` | Sesión evaluada. |
| `report_id` | Informe exacto revisado; obligatorio para evitar ambigüedad tras una reevaluación. |
| `analysis_job_id` | Job exacto que produjo el informe y su resultado `fusion`. |
| `rubric_version_id` | Versión aplicada al informe. |
| `queue_reason` | `critical`, `borderline`, `disparity` o `routine`. |
| `reason_detail_json` | Snapshot de puntajes y reglas que explican la clasificación. |
| `ai_snapshot_json` | Áreas y métricas originales, con procedencia y disponibilidad explícita. No contiene valores inventados. |
| `snapshot_schema_version` | Versión del contrato usado para interpretar el snapshot. |
| `source_status` | `complete`, `partial` o `ambiguous`; controla qué valores pueden editarse. |
| `recording_evidence_path` | Ruta de la versión inmutable o copia sellada creada desde los mismos bytes que analizó el worker. |
| `recording_version_id` | Versión exacta de Blob cuando el storage tenga versionado habilitado. |
| `recording_sha256` | Hash calculado por el worker sobre el archivo descargado y usado para analizar; identifica la evidencia sellada. |
| `recording_etag` | ETag de la evidencia inmutable, útil como comprobación adicional pero nunca como única garantía. |
| `status` | `pending` o `reviewed`. La reserva no cambia este estado. |
| `lock_owner_id` | Experto que posee la reserva activa. |
| `lock_token` | Token aleatorio de la reserva; nunca se registra en logs. |
| `lock_acquired_at` | Inicio de la reserva. |
| `lock_expires_at` | Expiración de la reserva, veinte minutos después de la última renovación válida. |
| `lease_generation` | Cambia solo al adquirir una nueva reserva; evita que una pestaña vieja libere o renueve una posterior. |
| `content_revision` | Control optimista del estado/revisión; no cambia por heartbeats del lease. |
| `resolved_by` | Experto que confirmó la revisión vigente. |
| `resolved_at` | Momento de confirmación en UTC. |
| auditoría estándar | `created_at`, `updated_at`. |

Restricciones e índices:

- Una fila por `report_id` mediante índice único.
- Consistencia obligatoria entre caso, informe, job, sesión, cliente y versión de rúbrica.
- Llaves foráneas a cliente, sesión, informe, rúbrica y usuarios expertos.
- Índice de cola por `(status, created_at DESC)` y soporte al orden por finalización de sesión.
- Validaciones para impedir locks vencidos incoherentes y estados desconocidos.
- La reevaluación de una sesión crea otro informe y, por lo tanto, un caso independiente.

Prioridad de etiqueta de tarjeta, sin excluir casos:

1. `critical`: puntaje global menor a 50 o al menos un área menor a 50.
2. `borderline`: sin condición crítica y con puntaje dentro de la ventana publicada alrededor de 50.
3. `disparity`: sin condiciones anteriores y con diferencia entre áreas igual o superior al umbral publicado.
4. `routine`: todos los demás casos completados.

La etiqueta se calcula al crear el caso y queda en el snapshot; un cambio futuro de umbrales no reescribe el motivo histórico.

### 7.2 `labeling_review`

Cabecera inmutable de una revisión confirmada.

- `id`, `labeling_case_id`, `reviewer_id`, `review_no`.
- `overall_comment` con longitud limitada y texto normalizado.
- `supersedes_review_id` opcional para una nueva revisión que sustituye la vigencia de otra sin editarla.
- `is_current` para seleccionar la revisión vigente sin borrar el historial.
- `idempotency_key` generado por el cliente y único por caso para recuperar un submit cuya respuesta se perdió.
- `submitted_at`, `created_at`.
- Índice único por `(labeling_case_id, review_no)` y por `(labeling_case_id, idempotency_key)`.
- Como máximo una revisión `is_current=1` por caso.

### 7.3 `labeling_rubric_correction`

Una fila por área revisada:

- `review_id`, `rubric_area_id`.
- `corrected_value`, entre 0 y 100. El `ai_value` se copia en servidor desde `ai_snapshot_json` y se persiste junto a la corrección.
- `comment` opcional; será obligatorio en el contrato cuando el valor cambie.
- Índice único por `(review_id, rubric_area_id)`.

No se fijarán cuatro columnas en la tabla. La relación seguirá siendo data-driven con `rubric_area`.

### 7.4 `labeling_metric_correction`

Una fila por métrica técnica disponible y revisada:

- `review_id`, `metric_key` con referencia al catálogo maestro.
- `corrected_value` numérico con precisión suficiente para porcentajes, ratios y conteos. El `ai_value` se resuelve en servidor desde el snapshot.
- `comment` opcional; obligatorio si existe cambio.
- Índice único por `(review_id, metric_key)`.

Solo se incluyen métricas que tengan evidencia real en el pipeline original. Una clave normalizada con `0` o `100` no prueba que haya sido medida, porque el normalizador histórico usa defaults. Los históricos ambiguos se devuelven como `unknown` y quedan en solo lectura.

### 7.5 Auditoría

Se amplían los tipos de `audit_event` para registrar, como mínimo:

- `labeling_case_claimed`.
- `labeling_case_released`.
- `labeling_case_reviewed`.
- `labeling_recording_accessed` cuando se emite una URL SAS.

Los detalles no incluirán comentarios completos, SAS, tokens, nombres, correos ni datos biométricos.

## 8. Contrato de métricas por caso

Antes de implementar el formulario se construirá una tabla de mapeo verificable entre `metric_key`, la fuente original del pipeline y la ruta normalizada del informe. Reglas:

- Voz, Video, Contenido y Empatía pueden contener métricas revisables si el worker las emite.
- Gobernanza es de solo lectura y describe reglas de auditoría.
- `content.red_line_cap` es un umbral de configuración, no una medición; no se presenta como valor obtenido por el vocero.
- Si una definición del catálogo no tiene evidencia equivalente en el informe, se muestra `No disponible en este informe` y no puede corregirse.
- Los rangos del Editor de Métricas describen umbrales configurables, no el dominio válido de una observación. No se reutilizan para rechazar una medición real.
- Cada métrica observable declara por separado tipo, unidad canónica, conversión, precisión, procedencia y envolvente de validación técnica.
- Las conversiones se prueban explícitamente; por ejemplo, un ratio `0..1` no se compara ni guarda como porcentaje `0..100` sin conversión declarada.
- La API devuelve metadatos de observación separados de los umbrales publicados.
- El resumen por categoría se calcula para presentación; no se persiste como una nueva verdad.
- `ai_value` y disponibilidad se calculan en el servidor. El payload del navegador contiene únicamente la corrección propuesta y el comentario.
- Para históricos, la disponibilidad se confirma contra resultados originales de pipeline. Si esto no es posible, la métrica queda `unknown`, no editable y excluida de agregados.

El resultado de esta tarea será una matriz mantenida junto al código y cubierta por pruebas. No se aprobará el formulario si depende de valores por defecto silenciosos.

## 9. Contrato API propuesto

Todas las rutas exigen autenticación y rol `master_config` mediante una dependencia centralizada.

| Método y ruta | Responsabilidad |
|---|---|
| `GET /api/master/labeling-cases?status=pending&limit=10` | Últimos diez pendientes, ordenados por finalización descendente. |
| `GET /api/master/labeling-cases?status=reviewed&limit=10` | Últimas diez revisiones confirmadas. |
| `GET /api/master/labeling-cases/{case_id}` | Detalle completo, lock, rúbrica, métricas y disponibilidad de grabación. |
| `POST /api/master/labeling-cases/{case_id}/lease` | Adquirir o renovar una reserva propia. Devuelve token, revisión y expiración. |
| `DELETE /api/master/labeling-cases/{case_id}/lease` | Liberación voluntaria y best-effort. |
| `GET /api/master/labeling-cases/{case_id}/recording-url` | SAS de solo lectura y corta duración para el blob exacto. |
| `POST /api/master/labeling-cases/{case_id}/reviews` | Crea una revisión inmutable e idempotente; puede ser la primera o una nueva revisión que sustituye la vigencia anterior. |
| `GET /api/master/labeling-cases/{case_id}/reviews` | Historial de revisiones del caso. |
| `GET /api/master/quality-reviews/summary` | Agregados por área, métrica, categoría y período. |
| `GET /api/master/quality-reviews` | Evidencia reciente y filtros usados por los editores. |

### 9.1 Respuestas y errores relevantes

- `401`: token inválido o ausente.
- `403`: rol distinto de `master_config`.
- `404`: caso o grabación inexistente/no visible.
- `409`: reserva activa de otro experto, lease/generación obsoletos, revisión base desactualizada o conflicto de vigencia.
- `410`: grabación eliminada por retención, si se puede distinguir de una ausencia accidental.
- `422`: valores fuera de rango, métricas desconocidas, áreas incompletas o comentario requerido ausente.
- `503`: almacenamiento temporalmente no disponible; nunca se entrega una URL pública de fallback.

Los modelos de entrada y salida serán explícitos y filtrarán cualquier campo no autorizado. Las listas devuelven `items`, `total` y un orden estable: pendientes por `(finished_at DESC, case_id DESC)` y revisadas por `(submitted_at DESC, review_id DESC)`. `limit` queda acotado a diez en esta etapa.

## 10. Reglas de reserva y concurrencia

1. Abrir un caso pendiente ejecuta `POST .../lease`.
2. Si no existe una reserva activa, el backend asigna veinte minutos y devuelve un `lock_token`, `lease_generation` y expiración. El detalle general nunca incluye el token.
3. Si el mismo experto ya posee la reserva, la operación es idempotente y puede renovarla.
4. Si otro experto posee una reserva vigente, se responde `409`; el detalle sigue disponible en modo lectura.
5. El frontend renueva cada cinco minutos solo si la pestaña está visible y hubo actividad durante los últimos diez minutos. Renovar exige propietario, token y generación vigentes, usa el reloj UTC del servidor y no cambia `content_revision`.
6. Navegar a otro caso intenta liberar la reserva anterior. Liberar exige token y generación; una pestaña obsoleta no puede liberar una reserva nueva. El backend nunca depende de esa liberación para recuperar el caso: la expiración es la garantía.
7. Confirmar exige `lock_token`, `lease_generation`, `expected_content_revision` e `idempotency_key` válidos.
8. La transacción de confirmación toma bloqueo SQL sobre el caso, vuelve a comprobar reserva, estado y revisión, inserta cabecera e hijos, marca el caso `reviewed`, limpia la reserva y registra auditoría.
9. Dos confirmaciones simultáneas con distintas claves solo pueden producir una revisión vigente; la otra recibe `409`. Repetir la misma `idempotency_key` devuelve la revisión ya creada.
10. Un heartbeat vencido nunca puede revivir una reserva que ya fue adquirida con otra generación.

## 11. Seguridad y privacidad

- Autorizar cada endpoint en backend; ocultar botones en frontend no cuenta como control de acceso.
- Consultas parametrizadas y transacciones con alcance mínimo.
- Respuestas sin nombre, correo, identificador B2C ni texto privado innecesario.
- Código seudonimizado estable generado en servidor; no exponer el algoritmo ni usarlo como autorización.
- SAS restringida a lectura sobre un único blob y con expiración objetivo de quince minutos.
- Preferir SAS por delegación de usuario cuando la identidad administrada del entorno lo permita. Mientras se use clave de cuenta, esta permanece solo en backend/Key Vault.
- No registrar SAS, `lock_token`, cadenas de conexión, transcripciones completas ni comentarios completos.
- Validar CORS del servicio Blob para el origen desplegado y comprobar `Content-Type` real del video.
- Respetar estados `available`, `archived` y `deleted`; una revisión permanece consultable aunque el medio ya no exista.
- React presenta comentarios como texto, sin `dangerouslySetInnerHTML`.
- La API de grabación valida la relación `case -> report -> session -> recording`; no basta recibir un `session_id` arbitrario.
- La respuesta de SAS incluye `expiresAt`, usa `Cache-Control: no-store` y no permite ciclos ilimitados de renovación.
- El worker fija la identidad del medio al descargarlo para análisis. Si Blob versioning está habilitado, persiste y reproduce esa versión exacta. Si no lo está, sube los mismos bytes descargados a una ruta única de evidencia por job/informe, con `overwrite=False`, hash SHA-256 y permisos que las SAS de subida del vocero no pueden modificar.
- El reproductor recibe SAS únicamente de la versión o copia sellada. El path mutable `recordings/{session_id}.webm` no se usa como evidencia de revisión.
- Antes de servir el medio, el backend comprueba la existencia y metadatos de la evidencia inmutable. Un ETag del blob mutable no se considera garantía suficiente.
- Las subidas a una sesión cerrada se rechazan. Esta regla se prueba antes de usar la ruta como evidencia inmutable.
- La retención y supresión deben alcanzar también la copia/version de evidencia; conservar el hash no autoriza conservar el video cuando corresponde purgarlo.
- Las rutas de cola no tendrán fallback a datos mock cuando exista un error de autorización o servidor.
- La identidad `master_config` se resuelve contra `app_user` vigente en cada operación; no basta confiar en un rol textual del frontend.
- Los DTO de cola usan lista blanca. La transcripción y narrativa libre quedan fuera del contrato inicial para reducir PII; cualquier incorporación posterior requiere revisión explícita.

## 12. Experiencia de usuario

El diseño visual actual se conserva. Los cambios funcionales son:

- Pestañas `Pendientes` y `Revisadas`, con sus contadores reales.
- Diez tarjetas como máximo por pestaña durante esta etapa.
- Tarjeta con número, fecha/hora, duración, escenario, puntaje general, motivo y áreas críticas.
- Selección inicial del primer caso disponible.
- Estados visibles de carga, vacío, error, bloqueado por otro experto y grabación no disponible.
- Caso reservado por otro experto: controles deshabilitados y texto `En revisión por otro experto`.
- Contador de expiración de la reserva propia.
- Reproductor real reutilizado dentro del contenedor visual existente.
- Sección Rúbrica con las áreas de la versión aplicada, no etiquetas fijas inventadas.
- Sección Métricas agrupada por Voz, Video, Contenido y Empatía; Gobernanza se muestra como contexto de auditoría.
- Diferencia IA/experto visible en cada valor.
- Observación general y comentario específico requerido cuando cambie un valor.
- Una sola confirmación para toda la revisión.
- Vista Revisadas de solo lectura con valores IA, correcciones, diferencias, comentarios, experto, fecha e historial. La acción explícita `Nueva revisión` crea otra revisión inmutable y requiere un lease nuevo.
- Después de confirmar, el caso desaparece de Pendientes y se incorpora a Revisadas sin recargar toda la aplicación.
- Al renovar una SAS, el reproductor conserva la posición y limita los reintentos automáticos.

## 13. Tareas y subtareas

### Tarea 0. Congelar contratos y matriz de métricas

**Objetivo:** convertir este plan en contratos técnicos ejecutables antes de modificar el esquema.

**Dependencias:** ninguna.

**Estado:** Hecho el 28 de octubre de 2026. Gate G1 alcanzado tras revisión adversarial sin hallazgos P0/P1.

**Entregables:**

- `plans/cola_etiquetado/CONTRATOS_Y_MATRIZ.md`.
- `plans/cola_etiquetado/DIAGNOSTICO_ESQUEMA_DATOS_STORAGE.md`.
- `plans/cola_etiquetado/fixtures/` con 17 fixtures JSON sin PII.
- `plans/cola_etiquetado/CIERRE_TAREA_0.md` con checklist, pruebas, límites y riesgos.

**Subtareas:**

1. Definir modelos JSON de lista, detalle, lease, confirmación y resúmenes.
2. Construir la matriz `metric_key -> ruta del informe -> unidad -> rango -> editable`.
3. Separar límites de observación de los umbrales configurables del catálogo.
4. Confirmar los campos exactos disponibles para fecha, duración, informe y grabación.
5. Inventariar tablas reales `recording` y `audit_event`, versionado de Blob, ETag, CORS y política de sobrescritura.
6. Auditar duplicados `report.is_current=1`, números de versión y resultados `fusion` ausentes/duplicados antes de diseñar el backfill.
7. Definir la fuente canónica: `report -> analysis_job -> fusion`, snapshot y tratamiento `complete/partial/ambiguous`.
8. Definir ejemplos de `409`, `410` y `422`.
9. Crear fixtures sin PII para backend y frontend.
10. Documentar qué métricas quedan `unknown` o `not_emitted` y por qué.

**Verificación:** revisión manual del contrato contra `metrics_catalog.py`, `report_builder.py`, `main.py` y tipos frontend.

**Criterio de salida:** ninguna propiedad del formulario depende de un valor mock, un default histórico ambiguo o un mapeo implícito; existe un diagnóstico cuantificado del esquema/datos actuales.

**Rollback:** solo documentación y fixtures; se revierten sin efecto en datos.

### Tarea 1. Crear esquema aditivo e idempotente

**Objetivo:** incorporar tablas, restricciones, índices y backfill sin alterar informes ni sesiones existentes.

**Dependencias:** Tarea 0.

**Estado:** Completa en código al 30 de octubre de 2026. Subtareas 1 a 10 implementadas; la validación local usa cursores simulados. No se aplicó la migración en Azure SQL y G2 sigue pendiente de una prueba real en SQL local/efímero.

**Entregables de este avance:**

- `backend/labeling_migration.py` con DDL aditivo e idempotente para cuatro tablas, sus llaves foráneas e índices.
- Integración de `migrate_labeling(cursor)` en `backend/scripts/prepare_azure_database.py`, dentro de la transacción y lock de esquema existentes.
- `plans/cola_etiquetado/AVANCE_TAREA_1_SUBTAREAS_1_4.md` con decisiones, pruebas y límites.
- `backend/scripts/reconcile_labeling_cases.py` con `--dry-run`, lotes, límite y resumen JSON; el modo escritura quedó habilitado en las subtareas 7 a 10 con confirmación literal, transacción y lock exclusivo.
- `plans/cola_etiquetado/AVANCE_TAREA_1_SUBTAREA_5.md` con alcance, uso y verificaciones.
- `backend/labeling_classification.py` con clasificación determinista y `reasonDetail` contractual, sin defaults históricos.
- Integración de conteos `critical`, `borderline`, `disparity`, `routine` y errores en el dry-run; entradas inválidas se excluyen y registran sin defaults.
- `plans/cola_etiquetado/AVANCE_TAREA_1_SUBTAREA_6.md` con reglas, pruebas y límites.
- Reconciliación con registro de anomalías, estimación previa, escritura transaccional confirmada e idempotencia por `report_id`.
- `verify_labeling` integrado en `prepare_azure_database.py --verify-only`, con verificación de tablas, índices, llaves, checks e integridad de filas.
- `backend/tests/test_labeling_migration_and_reconciliation.py` con ocho pruebas focalizadas.
- `plans/cola_etiquetado/AVANCE_TAREA_1_SUBTAREAS_7_10.md` con decisiones, uso, pruebas y límites.

**Subtareas:**

1. Crear `backend/labeling_migration.py` con DDL idempotente.
2. Integrarla en `backend/scripts/prepare_azure_database.py` dentro de la transacción y lock de esquema existentes.
3. Crear las cuatro tablas propuestas y sus llaves foráneas.
4. Crear índices de cola, revisión, métricas y áreas.
5. Crear un comando separado de backfill/reconciliación con `--dry-run`, lotes, límite y resumen; no ejecutarlo implícitamente al arrancar la aplicación.
6. Clasificar cada caso como crítico, límite, disparidad o rutinario sin excluir ninguno.
7. Excluir sesiones eliminadas y registrar, sin corregir, sesiones con múltiples informes actuales, fusion ausente/duplicada o relaciones inconsistentes.
8. Estimar volumen y duración del backfill antes de ejecutarlo sobre una base compartida.
9. Añadir verificación estructural, recuentos de elegibles/creados/omitidos y controles de integridad a `--verify-only` y al comando de reconciliación.
10. Añadir pruebas unitarias de doble ejecución, rollback y backfill repetido.

**Verificación:** pruebas de migración locales con cursores simulados y `prepare_azure_database.py --verify-only`. La aplicación persistente en Azure es un gate separado.

**Criterio de salida:** una segunda ejecución no modifica datos; existe exactamente un caso por informe elegible e inequívoco; las anomalías históricas quedan reportadas y no reescritas.

**Rollback:** la implementación no incluye `DROP`. Ante fallo se revierte la transacción completa; no se borran tablas históricas.

### Tarea 2. Asegurar evidencia canónica y creación runtime

**Objetivo:** garantizar que cada nuevo informe elegible produzca un caso con propuesta IA y medio verificables, sin depender únicamente del backfill.

**Dependencias:** Tareas 0 y 1.

**Subtareas:**

1. Corregir la finalización futura de informes para calcular `version_no`, desactivar el informe actual anterior e insertar el nuevo bajo bloqueo transaccional.
2. Persistir el resultado `fusion` exacto y el informe de forma coherente antes de marcar la sesión como completada y crear el caso.
3. Evitar que un fallo al persistir `fusion` quede reducido a un warning mientras el caso aparece como completo.
4. Crear `ensure_labeling_case_for_report` dentro del flujo runtime con idempotencia por `report_id`.
5. Generar `ai_snapshot_json` desde evidencia original, con disponibilidad y procedencia por métrica.
6. Durante la descarga del worker, calcular SHA-256 y fijar el medio exacto: versión de Blob o copia sellada única creada desde los bytes analizados, nunca desde una lectura posterior.
7. Persistir path/version/hash de evidencia en la misma unidad lógica del informe/caso y rechazar nuevas subidas cuando la sesión ya esté cerrada.
8. Crear un reconciliador idempotente para reportes completados que el flujo runtime no haya materializado.
9. Definir la política cuando una reevaluación crea un informe nuevo: el caso anterior conserva su historia y el informe nuevo genera otro caso.
10. Inventariar los entrypoints activos del worker y aplicar la garantía al camino canónico; los caminos heredados deben delegar o quedar explícitamente deshabilitados, no divergir.
11. Añadir pruebas de fallo entre report/fusion/caso, reintento, reevaluación, sobrescritura del blob mutable y sesión completada después de la migración.

**Verificación:** pruebas unitarias y de integración del worker/servicio de datos, incluyendo una falla inyectada antes del commit.

**Criterio de salida:** una sesión no se presenta como caso completo sin fuente exacta; cada informe futuro elegible crea exactamente un caso; un reintento no duplica nada y sobrescribir el blob original no cambia la evidencia reproducida.

**Rollback:** desactivar escrituras runtime mediante feature flag y conservar esquema/datos; el reconciliador no se ejecuta automáticamente durante el rollback.

### Tarea 3. Implementar store y reglas de dominio

**Objetivo:** concentrar consultas y transacciones de cola en un módulo testeable, sin SQL disperso en las rutas.

**Dependencias:** Tareas 1 y 2.

**Subtareas:**

1. Crear `backend/labeling_store.py`.
2. Implementar listado pendiente y revisado con límite máximo de diez.
3. Implementar detalle con seudónimo, informe, áreas y métricas normalizadas.
4. Implementar adquisición, renovación, liberación y expiración de lease.
5. Implementar confirmación inmutable y atómica.
6. Implementar agregados de acuerdo IA-humano por área y métrica.
7. Usar `UPDLOCK` y `HOLDLOCK` solo en operaciones que cambian lease o revisión.
8. Añadir eventos de auditoría sin datos sensibles.
9. Separar `lease_generation` de `content_revision` y hacer idempotente el submit por clave.
10. Agrupar áreas por `area_key` y versión; agrupar métricas por `metric_key`, versión de mapeo y unidad.
11. Calcular cantidad, diferencia media firmada, error absoluto medio y distribución al alza/a la baja; no usar solo una media que pueda cancelarse.

**Verificación:** pruebas unitarias de orden estable, totales, límite, exclusión de revisados, expiración, claim/claim, renew/submit, release/reclaim, dos pestañas del mismo experto, doble submit, rollback y ausencia de PII.

**Criterio de salida:** las invariantes de negocio se pueden demostrar sin levantar FastAPI.

**Rollback:** retirar el módulo y dejar el esquema sin uso; no eliminar datos.

### Tarea 4. Exponer API master segura

**Objetivo:** publicar los contratos de lista, detalle, lease, video, revisión y evidencia.

**Dependencias:** Tareas 0 y 3.

**Subtareas:**

1. Crear esquemas Pydantic en `backend/schemas/labeling.py`.
2. Crear una dependencia reutilizable que exija `master_config`.
3. Añadir endpoints canónicos `/api/master/...` y alias `/v1/api/master/...` solo si la convención actual lo exige.
4. Validar rangos, pasos, comentarios y pertenencia de áreas/métricas al informe y catálogo.
5. Implementar errores `403`, `404`, `409`, `410`, `422` y `503` con respuestas consistentes.
6. Emitir SAS de lectura por caso, sin URL pública de respaldo.
7. Añadir pruebas de contrato y matriz de roles para vocero, admin cliente y master.
8. Comprobar que OpenAPI no expone campos internos ni tokens.
9. Implementar respuesta idempotente cuando una confirmación fue aplicada pero el cliente perdió la respuesta.
10. Añadir `Cache-Control: no-store` y `expiresAt` al contrato de video.

**Verificación:** `pytest` focalizado en rutas y store, seguido por la suite backend completa.

**Criterio de salida:** solo `master_config` puede leer o modificar la cola y todos los conflictos devuelven un estado reproducible.

**Rollback:** eliminar rutas y conservar datos; los endpoints de sesión existentes permanecen intactos.

### Tarea 5. Sustituir mocks en la lista y navegación

**Objetivo:** conectar la pantalla existente a la API sin cambiar su diseño.

**Dependencias:** Tareas 0 y 4.

**Subtareas:**

1. Extender tipos en `frontend/src/types/api.ts`.
2. Crear `frontend/src/services/labelingService.ts` y retirar el fallback mock para errores reales.
3. Actualizar `LabelingQueueView.tsx` para cargar Pendientes y Revisadas.
4. Mantener un máximo de diez tarjetas por vista.
5. Añadir estados de carga, vacío, error y reintento.
6. Mostrar fecha/hora local, duración, puntaje y alertas críticas.
7. Preservar selección al refrescar cuando el caso aún exista.
8. Añadir pruebas de transformación de datos, orden y estados vacíos.

**Verificación:** TypeScript, ESLint, pruebas frontend y build de producción.

**Criterio de salida:** no existe importación de `INITIAL_LABELING_QUEUE` en la pantalla ni fallback silencioso a datos simulados.

**Rollback:** volver al componente previo sin afectar backend o base.

### Tarea 6. Integrar lease, formulario y revisión inmutable

**Objetivo:** completar la segunda opinión experta con concurrencia segura.

**Dependencias:** Tareas 4 y 5.

**Subtareas:**

1. Adquirir lease al seleccionar un pendiente.
2. Implementar renovación condicionada por visibilidad y actividad.
3. Mostrar expiración y modo lectura cuando otro experto posea el lease.
4. Renderizar áreas de rúbrica data-driven.
5. Renderizar métricas disponibles por categoría, excluyendo Gobernanza como campo editable.
6. Validar límites y exigir comentario al modificar un valor.
7. Enviar una única solicitud de confirmación con `lock_token`, `lease_generation`, `expected_content_revision` e `idempotency_key`.
8. Manejar `409` sin perder el contenido local hasta que el experto decida descartarlo o copiarlo.
9. Mover el caso a Revisadas tras éxito.
10. Mostrar revisiones confirmadas en modo lectura e impedir su edición directa.
11. Permitir `Nueva revisión` como operación explícita que crea una fila sucesora y conserva todo el historial.

**Verificación:** pruebas de reducer/modelo de formulario, conflictos y transiciones; prueba manual con dos sesiones master simultáneas.

**Criterio de salida:** dos expertos no pueden confirmar el mismo caso y una revisión confirmada no se puede editar desde la UI ni la API.

**Rollback:** deshabilitar edición manteniendo la consulta de casos.

### Tarea 7. Integrar grabación real y recuperación de SAS

**Objetivo:** reproducir la grabación con pausa, búsqueda y saltos confiables dentro del diseño actual.

**Dependencias:** Tareas 4 y 5. Puede desarrollarse en paralelo con la Tarea 6 si no se tocan las mismas secciones del componente.

**Subtareas:**

1. Reutilizar `RecordingVideoPlayer` en la tarjeta de detalle.
2. Obtener la SAS solo al abrir un caso y renovarla después de una expiración autorizada.
3. Mantener duración persistida como respaldo para WebM.
4. Mostrar carga, buffer, error, archivo eliminado y storage no disponible.
5. Pausar y limpiar el reproductor al cambiar de caso.
6. Verificar `Content-Type`, CORS y lectura por rangos en el entorno configurado.
7. Emitir SAS solo para la versión/copia sellada ligada al caso, nunca para el path mutable de subida.
8. Auditar la emisión de SAS sin registrar la URL.
9. Añadir `onError`, reset controlado al cambiar `src`, restauración de posición tras renovar y tope de reintentos.
10. Probar que una SAS de escritura antigua puede alterar el blob original sin alterar el medio reproducido por el caso, incluso después de emitir la SAS de lectura.

**Verificación:** pruebas del componente y QA real en Chrome/Edge: reproducir, pausar, avanzar, retroceder, arrastrar, cambiar velocidad y renovar URL.

**Criterio de salida:** el usuario puede buscar cualquier punto disponible del video sin descargarlo mediante el backend ni exponer credenciales.

**Rollback:** ocultar el reproductor y conservar el resto de la revisión.

### Tarea 8. Mostrar evidencia en los editores

**Objetivo:** convertir las revisiones en información accionable sin alterar configuraciones publicadas.

**Dependencias:** Tareas 3, 4 y 6.

**Subtareas:**

1. Añadir un panel de `Revisión de calidad` al Editor de Rúbrica.
2. Mostrar por área: casos, promedio de diferencia, distribución al alza/a la baja y comentarios recientes.
3. Añadir un panel equivalente al Editor de Métricas por métrica y categoría.
4. Excluir Gobernanza de la calibración y usarla como contexto de selección/acuerdo.
5. Añadir filtros básicos por período y enlace al caso revisado.
6. Mantener separado el flujo de crear/guardar/publicar borradores.
7. Comprobar que abrir evidencia no modifica el formulario del editor.
8. Mostrar versión de rúbrica/mapeo y no mezclar métricas con unidades incompatibles.

**Verificación:** pruebas de agregación backend, presentación frontend y regresión del editor versionado de métricas.

**Criterio de salida:** los expertos pueden justificar una futura decisión de configuración con evidencia, pero ninguna revisión cambia pesos o umbrales.

**Rollback:** retirar los paneles sin tocar revisiones almacenadas.

### Tarea 9. Integración, seguridad, documentación y gate de datos reales

**Objetivo:** demostrar que el flujo completo es seguro, reproducible y operable antes de migrar o publicar.

**Dependencias:** Tareas 1 a 8.

**Subtareas:**

1. Ejecutar pruebas backend, frontend y worker existentes más las nuevas.
2. Ejecutar TypeScript, ESLint y build de producción.
3. Ejecutar `git diff --check` y revisar archivos fuera de alcance.
4. Probar dos expertos, expiración de veinte minutos, conflicto de revisión y renovación.
5. Probar roles no autorizados y ausencia de PII en respuestas/logs.
6. Probar grabación disponible, expirada, archivada, eliminada y storage caído.
7. Ejecutar revisión de seguridad ECC sobre backend y frontend.
8. Realizar revisión adversarial de código y de migración.
9. Crear `IMPLEMENTACION_COLA_ETIQUETADO.md` con contratos, esquema, pruebas, límites y operación.
10. Preparar evidencia de `--verify-only` y solicitar autorización antes de aplicar Azure SQL.
11. Tras la migración autorizada, repetir `--verify-only` y smoke test con casos reales.
12. Ejecutar pruebas SQL con dos conexiones contra una base aislada compatible, cubriendo locks, restricciones y rollback por fallo intermedio.
13. Validar el plan de activación: esquema primero, escrituras runtime después, API, y finalmente UI.
14. Validar rollback operativo desactivando escrituras/UI mediante feature flags sin eliminar revisiones.

**Verificación final recomendada:**

```powershell
.\docker.ps1 build
.\docker.ps1 verify
.\docker.ps1 test
git diff --check
```

Si Docker no está disponible, se documentará el bloqueo y se ejecutarán equivalentes locales con los runtimes del repositorio, sin afirmar que Docker pasó.

**Criterio de salida:** pruebas aprobadas, revisión de seguridad sin hallazgos críticos, migración verificada y evidencia real de un caso pendiente y uno revisado.

**Rollback:** no desplegar; revertir la activación de rutas/UI. Las migraciones son aditivas y los datos de revisión no se eliminan.

## 14. Dependencias y orden

```text
T0 Contratos
  -> T1 Esquema
       -> T2 Evidencia canónica y creación runtime
            -> T3 Store
                 -> T4 API
                      -> T5 Lista dinámica
                      -> T7 Video
                      -> T6 Lease y formulario
                 -> T8 Evidencia en editores

T5 + T6 + T7 + T8 -> T9 Integración y gates
```

Paralelismo seguro:

- Tarea 7 puede avanzar junto con Tarea 6 después de estabilizar Tareas 4 y 5.
- La parte backend de Tarea 8 puede avanzar junto con Tareas 5 a 7 después de Tarea 4.
- No se ejecutan trabajos paralelos sobre el mismo archivo sin acordar primero la división.

## 15. Gates de avance

| Gate | Condición | Autoriza pasar a |
|---|---|---|
| G0 | Plan aprobado y rama correcta. | Tarea 0 |
| G1 | Contratos y matriz de métricas revisados. | Tarea 1 |
| G2 | Migración idempotente probada localmente; sin aplicación persistente. | Tarea 2 |
| G3 | Evidencia canónica y creación runtime pasan fallos/reintentos; la versión/copia sellada resiste sobrescritura del blob original. | Tarea 3 |
| G4 | Store y API pasan seguridad de roles y concurrencia. | Frontend dinámico |
| G5 | Cola, formulario y video pasan QA funcional. | Paneles y E2E |
| G6 | Suite, SQL aislado, medio inmutable, build, revisión de seguridad y documentación aprobados. | Solicitar migración Azure |
| G7 | Usuario autoriza migración; aplicación y `--verify-only` pasan. | Commit/push/PR, si se solicitan |

## 16. Protocolo de cambios del plan

Cada modificación debe registrar:

| Fecha | Tarea | Cambio | Motivo | Aprobado por |
|---|---|---|---|---|
| 2026-10-27 | Todas | Plan inicial con cola de diez pendientes/revisados, lease de veinte minutos y revisiones inmutables. | Decisiones del usuario. | Usuario |
| 2026-10-27 | T0-T9 | Se añadió evidencia canónica, creación runtime, revisiones sucesoras, lease por generación, validación de observaciones separada de umbrales, feature flags y pruebas SQL aisladas. | Revisión adversarial ECC. | Pendiente de aprobación del usuario |
| 2026-10-28 | T0 | Se congelaron contratos, matriz de 16 métricas, diagnóstico live read-only y 17 fixtures sin PII; se corrigieron discrepancias hasta una revisión sin P0/P1. | Ejecución solicitada por el usuario y cierre de G1. | Usuario |
| 2026-10-28 | T1.1-T1.4 | Se creó el esquema aditivo de la cola y se integró en la transacción protegida del preparador; no se incluyó backfill, verificación estructural ni aplicación persistente. | Alcance parcial solicitado por el usuario. | Usuario |
| 2026-10-28 | T1.5 | Se añadió el comando separado de reconciliación con dry-run, lotes, límite y resumen sin PII; el modo escritura falla cerrado hasta implementar clasificación y anomalías. | Alcance parcial solicitado por el usuario. | Usuario |
| 2026-10-28 | T1.6 | Se implementó la clasificación priorizada con umbrales de la versión del informe y se incorporaron conteos al dry-run; faltas de evidencia fallan cerrado. | Alcance parcial solicitado por el usuario. | Usuario |
| 2026-10-30 | T1.7-T1.10 | Se añadieron anomalías fail-closed, estimación previa, backfill transaccional idempotente, verificación estructural y pruebas de doble ejecución/rollback/repetición. Los históricos quedan `ambiguous` hasta sellar evidencia en Tarea 2. | Cierre de las subtareas restantes solicitado por el usuario. | Usuario |
| 2026-10-30 | T2.1-T2.11 | Se implementó finalización versionada y atómica, snapshot desde evidencia original, copia de grabación sellada por hash, creación runtime/reconciliación idempotentes, cierre de subidas y convergencia de entrypoints. | Cierre completo de Tarea 2 solicitado por el usuario. | Usuario |
| 2026-10-30 | T3.1-T3.11 | Se creó el store de dominio con listas y detalle normalizados, lease generacional, revisión inmutable e idempotente, auditoría segura y agregados por identidad compatible. | Cierre completo de Tarea 3 solicitado por el usuario. | Usuario |

Reglas:

1. No editar criterios ya implementados sin registrar el cambio.
2. Una nueva dependencia entre tareas debe aparecer también en la sección 14.
3. Un cambio de esquema requiere actualizar DDL, verificación, rollback y documentación.
4. Un cambio de alcance que implique notificaciones, entrenamiento automático o datos personales requiere nueva aprobación.

## 17. Formato de reporte por avance

Al cerrar cada tarea se informará:

1. Estado: `Hecho`, `Parcial` o `Bloqueado`.
2. Archivos modificados.
3. Contratos o decisiones aplicadas.
4. Pruebas ejecutadas y resultado exacto.
5. Evidencia pendiente y limitaciones.
6. Riesgos descubiertos.
7. Gate alcanzado.
8. Próxima tarea propuesta, sin iniciarla automáticamente.

No se marcará `Hecho` si falta comprobar el artefacto real, la prueba declarada o el gate correspondiente.

## 18. Referencias técnicas verificadas

- FastAPI: autorización mediante dependencias, modelos Pydantic explícitos y `409 Conflict` para conflictos de estado/concurrencia.
- Next.js 16: la vista interactiva puede seguir como Client Component con carga, error y limpieza explícitos; no es obligatorio añadir SWR para este alcance.
- Azure Blob Storage: acceso del navegador con SAS de duración limitada; CORS por servicio, `Content-Type` correcto y comprobación de lectura parcial para búsqueda del video.
- Repositorio: se preservan los patrones actuales de migración aditiva, transacción, `--verify-only`, rol `master_config` y editor de métricas versionado.
