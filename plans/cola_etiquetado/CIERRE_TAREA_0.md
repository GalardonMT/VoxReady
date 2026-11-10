# Cierre de Tarea 0 — Contratos y matriz de métricas

## 1. Resultado

- Estado: **Hecho**.
- Fecha de cierre: 28 de octubre de 2026 (`America/Santiago`).
- Rama: `feat/cola-de-etiquetado`.
- Gate alcanzado: **G1 — contratos y matriz revisados**.
- Siguiente tarea habilitada: Tarea 1, **no iniciada**.
- Alcance aplicado: documentación técnica, diagnóstico de solo lectura y fixtures. No se modificó código productivo, esquema, datos ni configuración externa.

## 2. Entregables

1. `CONTRATOS_Y_MATRIZ.md`: DTO de lista, detalle, lease, liberación, grabación, revisión, historial y resúmenes; fuente canónica; errores; matriz de 16 métricas.
2. `DIAGNOSTICO_ESQUEMA_DATOS_STORAGE.md`: inventario real de SQL y Blob, conteos, anomalías, consultas reproducibles y límites de evidencia.
3. `fixtures/`: 17 ejemplos JSON sin PII compartidos por backend y frontend.
4. Este cierre: trazabilidad de las diez subtareas, verificaciones y riesgos que condicionan las tareas posteriores.

## 3. Checklist de subtareas

| # | Subtarea | Estado | Evidencia |
|---|---|---|---|
| 1 | Modelos JSON de lista, detalle, lease, confirmación y resúmenes | Hecho | Contratos secciones 3 a 8 y fixtures. |
| 2 | Matriz `metric_key -> ruta -> unidad -> rango -> editable` | Hecho | Matriz v1 de las 16 claves del catálogo. |
| 3 | Separar límites de observación de umbrales configurables | Hecho | Metadata `observation` separada de `publishedThresholds`. |
| 4 | Confirmar fecha, duración, informe y grabación | Hecho | Fechas desde `session`; duración de tarjeta derivada de sesión; duración del reproductor desde evidencia sellada; informe por `report.id`. |
| 5 | Inventariar `recording`, `audit_event`, Blob, ETag, CORS y overwrite | Hecho | Diagnóstico SQL/Blob y revisión de código. |
| 6 | Auditar informes actuales, versiones y `fusion` | Hecho | Preflight live y consultas reproducibles. |
| 7 | Definir fuente canónica y estados de integridad | Hecho | `report -> analysis_job -> fusion`, cuatro áreas y medio sellado; `complete/partial/ambiguous` sin solapamiento. |
| 8 | Ejemplos `409`, `410` y `422` | Hecho | Problem Details y fixtures de error. |
| 9 | Fixtures sin PII para backend y frontend | Hecho | 17 JSON parseables y lista blanca de campos. |
| 10 | Documentar `unknown` y `not_emitted` | Hecho | Reglas de disponibilidad y matriz por métrica. |

## 4. Decisiones congeladas

- El contrato de red usa `camelCase`, fechas UTC, listas de máximo diez y modelos de entrada estrictos.
- La clave canónica del área es `voice`; `tone` no se persiste como clave.
- `reasonDetail` es una unión discriminada por `queueReason`.
- `aiValue`, disponibilidad, seudónimos y criticidad se resuelven en servidor.
- `availability` solo admite `available`, `unknown` y `not_emitted`.
- Una métrica observable declara unidad canónica, conversión y envolvente técnica separadas de los umbrales del editor.
- Ocho métricas del catálogo tienen mapeo observable directo. `voice.asr_confidence` exige evidencia original adicional; `empathy.victim_recog` no tiene productor equivalente demostrado.
- `content.red_line_cap` y las cinco claves de gobernanza son configuración o contexto, no desempeño editable.
- `complete` exige informe/job/fusion coherentes, cuatro áreas únicas, coincidencia de `reportId` y medio exacto sellado. La falta de `fusion` es `ambiguous`; `partial` se reserva para procedencia opcional `unknown` con identidad base inequívoca.
- La liberación de lease es idempotente para la misma generación y responde `409 STALE_LEASE` si existe una generación posterior.
- La transcripción, narrativa libre, nombres, correos, identificadores B2C, SAS y rutas internas de Blob quedan fuera de los DTO iniciales.

## 5. Fotografía viva del entorno

Consulta read-only realizada el 28 de octubre de 2026 en horario de Santiago:

| Comprobación | Resultado |
|---|---:|
| Sesiones completadas y no eliminadas | 24 |
| Informes actuales | 24 |
| Candidatos con `report -> job -> fusion`, cuatro áreas y `fusion.reportId` coincidente | 21 |
| Preclasificados `ambiguous` | 3 |
| Preclasificados `partial` | 0 |
| Demostrados `sourceStatus=complete` | 0, falta validar y sellar el medio exacto |
| Sesiones con múltiples informes actuales | 0 |
| Jobs con múltiples `fusion` | 0 |
| Filas `recording` / `audit_event` | 0 / 0 |
| Entradas Blob inventariadas | 87 |
| Versiones Blob observadas | 0 |

Las tres anomalías preliminares son: un informe sin `analysis_job_id`, uno con referencia huérfana y uno con job válido sin `fusion`. El resultado es una fotografía puntual y debe repetirse antes de cualquier backfill.

## 6. Verificación ejecutada

- Revisión manual contra `backend/metrics_catalog.py`, `worker/core/report_builder.py`, `worker/services/db_service.py`, `worker/core/pipeline_orchestrator.py`, `backend/main.py` y tipos/vista/servicio frontend.
- Context7: modelos de respuesta y rechazo de campos extra en FastAPI/Pydantic; versiones inmutables y SAS de lectura limitada en Azure Blob.
- SQL y metadata de Blob consultados en modo read-only, sin PII ni descarga audiovisual.
- Fixtures: `17/17` JSON parsean.
- Validación contrato/fixtures: unión discriminada, detalle, lease, metadata de observación, resúmenes y errores con `0` inconsistencias.
- Escaneo de claves prohibidas en fixtures: sin correo, transcripción, B2C, `userId`, rutas Blob, `reviewerId` ni SAS real.
- `git diff --check`: sin errores.
- Revisión adversarial final: **sin P0/P1; G1 aprobado**.

No se ejecutaron suites de producto porque T0 no modifica código ejecutable. Las pruebas de modelos Pydantic/TypeScript y OpenAPI corresponden a T4.

## 7. Riesgos y límites que continúan abiertos

1. Los 21 candidatos relacionalmente coherentes todavía no son casos `complete`: falta demostrar que los bytes disponibles son los analizados y crear evidencia sellada.
2. `recording` está vacío; no se permite reconstruir asociaciones solo por el patrón del nombre del blob.
3. No se observó versionado ni soft delete de Blob. Una ETag sobre un objeto mutable no basta como evidencia inmutable.
4. Blob CORS contiene dos reglas duplicadas con origen `*`; debe restringirse antes del gate de seguridad.
5. El endpoint actual selecciona el último `fusion` por sesión y permite fallback público; la cola no puede reutilizar ese comportamiento.
6. El máximo operativo de WPM y `body_sway_std` no se inventa. La validación superior queda abierta hasta evidencia del productor/datos.
7. `voice.asr_confidence` permanece `unknown` cuando no se demuestra la procedencia desde palabras ASR.
8. No existe política efectiva de retención demostrada para la futura evidencia sellada.

## 8. Condición para iniciar Tarea 1

Tarea 1 puede diseñar y probar localmente un esquema aditivo e idempotente usando estos contratos. No está autorizado aplicar migraciones persistentes, ejecutar backfill, cambiar CORS/retención, hacer commit, push o abrir PR sin la instrucción correspondiente del usuario.
