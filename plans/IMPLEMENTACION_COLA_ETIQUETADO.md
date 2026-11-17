# Implementación — Cola de Etiquetado

Estado al 2026-11-10: implementación local completa; activación Azure pendiente de autorización y gate real.

## 1. Objetivo y límites

La cola permite que expertos `master_config` revisen entrevistas completadas, comparen propuesta IA con calibración experta en cuatro áreas de rúbrica y métricas observables, dejen comentarios y consulten evidencia agregada en los editores. Una revisión no cambia automáticamente pesos, umbrales ni configuraciones publicadas.

Quedan fuera del contrato público nombres, correos, identificadores B2C, transcripciones, rutas internas Blob, hashes, SAS persistidas y tokens de lease.

## 2. Flujo operativo

1. El worker termina un informe y sella la grabación por versión Blob o copia inmutable `overwrite=False`.
2. El runtime crea de forma idempotente un `labeling_case` desde fuentes originales y registra faltantes sin inventar valores.
3. La API lista hasta diez pendientes y diez revisados, ordenados por actividad descendente.
4. Un experto adquiere un lease de veinte minutos; un segundo experto recibe conflicto mientras siga vigente.
5. El experto confirma cuatro áreas, las métricas modificadas y comentarios. La transacción valida lease, generación, revisión de contenido, idempotencia y revisión sustituida.
6. La revisión queda inmutable; una revisión posterior sustituye a la actual sin borrar historial.
7. Los editores consultan agregados por identidad compatible, sin escribir configuración.

## 3. Contratos HTTP

- `GET /api/master/labeling-cases?status=pending|reviewed&limit=10`
- `GET /api/master/labeling-cases/{case_id}`
- `POST /api/master/labeling-cases/{case_id}/lease`
- `DELETE /api/master/labeling-cases/{case_id}/lease`
- `GET /api/master/labeling-cases/{case_id}/recording-url`
- `GET /api/master/labeling-cases/{case_id}/reviews`
- `POST /api/master/labeling-cases/{case_id}/reviews`
- `GET /api/master/quality-reviews/summary`

Todos exigen autorización server-side `master_config`, tienen alias `/v1`, DTO explícito y errores RFC 7807. Los conflictos usan `409`; grabación retenida/eliminada usa `410`; dependencia no disponible usa `503`.

## 4. Persistencia y concurrencia

Tablas aditivas:

- `labeling_case`: snapshot IA, identidad del reporte y medio sellado, estado, lease y revisión de contenido.
- `labeling_review`: cabecera inmutable, idempotencia, revisor seudonimizado y relación de sustitución.
- `labeling_rubric_correction`: propuesta y corrección por área.
- `labeling_metric_correction`: propuesta y corrección por métrica, versión de mapeo y unidad.
- `audit_event`: claim, release, review y acceso a grabación mediante lista blanca.

`UPDLOCK/HOLDLOCK` se usa únicamente en adquisición/renovación de lease, finalización transaccional y confirmación. Índices únicos impiden dos revisiones actuales, números repetidos e idempotencias duplicadas.

## 5. Grabación

La cola nunca reproduce el path mutable de subida. El backend valida versión, ETag y `Content-Type` de la evidencia sellada y emite SAS HTTPS de lectura por quince minutos con `Cache-Control: no-store`. El frontend renueva con tope de dos reintentos, conserva posición y limpia el elemento `<video>` al cambiar de caso.

## 6. Seguridad

- Autenticación Microsoft Entra; `DEV_AUTH` solo en entorno development.
- SAS de subida `create` sin `write`; sesiones cerradas reciben `409`.
- SAS de reproducción solo lectura y para la evidencia exacta.
- Pydantic rechaza campos de propiedad del servidor y normaliza comentarios.
- SQL parametrizado; no se construyen consultas con valores del usuario.
- Auditoría excluye SAS, tokens, comentarios completos, nombres, correos y transcripciones.
- Next.js se actualizó a `16.4.6`; `npm audit --omit=dev --audit-level=high` informa cero vulnerabilidades.

## 7. Activación

Orden obligatorio:

1. Construir artefactos y ejecutar suites soportadas.
2. Ejecutar `python scripts/prepare_azure_database.py --verify-only`.
3. Con autorización expresa, ejecutar la migración aditiva mediante el servicio `init`.
4. Repetir `--verify-only` y pruebas SQL con dos conexiones.
5. Activar `LABELING_RUNTIME_ENABLED=true` en el worker.
6. Activar `LABELING_QUEUE_API_ENABLED=true` en la API.
7. Construir frontend con `NEXT_PUBLIC_LABELING_UI_ENABLED=true`.
8. Ejecutar smoke test con un caso pendiente, uno revisado y grabación sellada real.

No se debe activar runtime antes del esquema ni UI antes de API.

## 8. Rollback operativo

El rollback no elimina tablas ni revisiones:

1. reconstruir frontend con `NEXT_PUBLIC_LABELING_UI_ENABLED=false`;
2. configurar `LABELING_QUEUE_API_ENABLED=false` para cerrar rutas con `503`;
3. configurar `LABELING_RUNTIME_ENABLED=false` para detener nuevas materializaciones;
4. conservar evidencia, revisiones y auditoría para diagnóstico;
5. restaurar flags en orden runtime → API → UI después de corregir y verificar.

## 9. Verificación final

- Frontend: `40 passed`; TypeScript y build Next.js 16.4.6 correctos.
- Backend Docker: `133 passed`, `2 skipped`, incluidas pruebas transaccionales reversibles contra Azure SQL.
- Worker Docker: `18 passed`.
- `npm audit --omit=dev --audit-level=high`: cero vulnerabilidades.
- `prepare_azure_database.py --verify-only`: esquema e integridad confirmados en `sqldb-voxready`.
- Reconciliación: 7 casos materializados; repetición idempotente con 0 casos nuevos.

## 10. Gate de datos aplicado

La migración transaccional se aplicó el 10 de noviembre de 2026. Las tablas
legacy fueron preservadas con sufijo `_legacy_v1`. De 24 entrevistas
completadas, 7 cumplieron el contrato de evidencia y entraron en cola; 17 se
excluyeron por anomalías históricas sin forzar ni reparar datos ambiguos. La
aplicación no fue desplegada en Azure.
