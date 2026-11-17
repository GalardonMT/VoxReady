# Mapa ECC para la cola de etiquetado

**Plan:** `plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md`
**Pasos:** 10
**Alcance:** todas las tareas
**Emitidos:** 9 · **Bloqueados:** 1

Este archivo solo enruta cada tarea al comando ECC adecuado. No ejecuta comandos. Cada tarea conserva los gates y criterios del plan principal.

## Resumen

| Paso | Tarea | Etiqueta principal | Comando | Estado |
|---|---|---|---|---|
| 1 | T0 Contratos y matriz | diseño | `/plan` | emitido |
| 2 | T1 Esquema aditivo | base de datos | `/orch-add-feature` | emitido |
| 3 | T2 Evidencia runtime | cambio | `/orch-change-feature` | emitido |
| 4 | T3 Store de dominio | implementación | `/orch-add-feature` | emitido |
| 5 | T4 API master | implementación y seguridad | `/orch-add-feature` | emitido |
| 6 | T5 Lista dinámica | cambio | `/orch-change-feature` | emitido |
| 7 | T6 Lease y formulario | implementación y seguridad | `/orch-add-feature` | emitido |
| 8 | T7 Reproductor y SAS | cambio y seguridad | `/orch-change-feature` | emitido |
| 9 | T8 Evidencia en editores | implementación | `/orch-add-feature` | emitido |
| 10 | T9 Integración y gates | pruebas | `/test-coverage` | BLOQUEADO: el comando no transporta alcance de tarea |

## Paso 1. Tarea 0

```text
/plan "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-1] Tarea 0: congelar contratos de lista, detalle, lease, revisión, evidencia, métricas y video; inventariar reportes, fusion, recording, audit_event y entrypoints activos; Acceptance: matriz de métricas distingue observación de umbral; anomalías históricas quedan cuantificadas; ningún campo depende de mocks o defaults ambiguos"
```

## Paso 2. Tarea 1

```text
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-2] Tarea 1: crear esquema Azure SQL aditivo e idempotente para casos, revisiones y correcciones, más reconciliador explícito con dry-run y lotes; Acceptance: doble ejecución no duplica; verify-only valida restricciones y recuentos; anomalías históricas se reportan sin reescritura silenciosa"
```

## Paso 3. Tarea 2

```text
/orch-change-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-3] Tarea 2: cambiar la finalización de análisis para versionar reportes, persistir fusion coherente, sellar los bytes exactos del video y crear casos runtime idempotentes; Acceptance: fallo intermedio revierte; reintento no duplica; sobrescribir el blob original no altera la evidencia del caso"
```

## Paso 4. Tarea 3

```text
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-4] Tarea 3: implementar labeling_store con listas de diez, detalle seudonimizado, leases por generación, revisiones sucesoras idempotentes y agregados por versión/unidad; Acceptance: carreras claim-renew-release-submit están cubiertas; una sola revisión queda vigente; consultas no exponen PII"
```

## Paso 5. Tarea 4

```text
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-5] Tarea 4: exponer API master tipada para cola, lease, revisiones, medio sellado y resúmenes, con autorización server-side y errores consistentes; Acceptance: roles no master reciben 403; conflictos reciben 409 reproducible; SAS es read-only, no-store, expirable y nunca contiene fallback público"
```

## Paso 6. Tarea 5

```text
/orch-change-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-6] Tarea 5: reemplazar INITIAL_LABELING_QUEUE por labelingService manteniendo el diseño, con pestañas Pendientes/Revisadas, máximo diez y estados de carga, vacío y error; Acceptance: no queda fallback mock; orden y totales coinciden con API; TypeScript, ESLint, pruebas y build pasan"
```

## Paso 7. Tarea 6

```text
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-7] Tarea 6: añadir lease de veinte minutos, formulario data-driven de rúbrica/métricas, submit idempotente e historial inmutable; Acceptance: dos expertos no confirman simultáneamente; pestañas obsoletas no liberan leases nuevos; comentarios son obligatorios para valores modificados"
```

## Paso 8. Tarea 7

```text
/orch-change-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-8] Tarea 7: integrar RecordingVideoPlayer con la versión o copia sellada, renovación SAS acotada y manejo de error/cambio de src; Acceptance: play, pausa, seek y saltos funcionan; renovación conserva posición; una sobrescritura del blob de subida no cambia el video revisado"
```

## Paso 9. Tarea 8

```text
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-9] Tarea 8: añadir evidencia de calidad a editores de rúbrica y métricas sin alterar borradores ni publicaciones; Acceptance: agregados muestran cantidad, diferencia firmada y error absoluto por versión; unidades incompatibles no se mezclan; cada evidencia enlaza al historial del caso"
```

## Paso 10. Tarea 9 bloqueada

```text
BLOQUEADO — /test-coverage no puede transportar el alcance del paso; ejecutar manualmente si se desea: /test-coverage
```

Revisiones manuales adicionales definidas por la tarea:

```text
/security-scan . --format markdown --min-severity medium
/code-review
```

## Ejecución por lotes de los pasos emitidos

El plan principal exige gates entre tareas. Este bloque sirve como referencia copiable, no como autorización para ejecutar todos los pasos sin pausas.

```text
/plan "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-1] Tarea 0: congelar contratos de lista, detalle, lease, revisión, evidencia, métricas y video; inventariar reportes, fusion, recording, audit_event y entrypoints activos; Acceptance: matriz de métricas distingue observación de umbral; anomalías históricas quedan cuantificadas; ningún campo depende de mocks o defaults ambiguos"
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-2] Tarea 1: crear esquema Azure SQL aditivo e idempotente para casos, revisiones y correcciones, más reconciliador explícito con dry-run y lotes; Acceptance: doble ejecución no duplica; verify-only valida restricciones y recuentos; anomalías históricas se reportan sin reescritura silenciosa"
/orch-change-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-3] Tarea 2: cambiar la finalización de análisis para versionar reportes, persistir fusion coherente, sellar los bytes exactos del video y crear casos runtime idempotentes; Acceptance: fallo intermedio revierte; reintento no duplica; sobrescribir el blob original no altera la evidencia del caso"
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-4] Tarea 3: implementar labeling_store con listas de diez, detalle seudonimizado, leases por generación, revisiones sucesoras idempotentes y agregados por versión/unidad; Acceptance: carreras claim-renew-release-submit están cubiertas; una sola revisión queda vigente; consultas no exponen PII"
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-5] Tarea 4: exponer API master tipada para cola, lease, revisiones, medio sellado y resúmenes, con autorización server-side y errores consistentes; Acceptance: roles no master reciben 403; conflictos reciben 409 reproducible; SAS es read-only, no-store, expirable y nunca contiene fallback público"
/orch-change-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-6] Tarea 5: reemplazar INITIAL_LABELING_QUEUE por labelingService manteniendo el diseño, con pestañas Pendientes/Revisadas, máximo diez y estados de carga, vacío y error; Acceptance: no queda fallback mock; orden y totales coinciden con API; TypeScript, ESLint, pruebas y build pasan"
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-7] Tarea 6: añadir lease de veinte minutos, formulario data-driven de rúbrica/métricas, submit idempotente e historial inmutable; Acceptance: dos expertos no confirman simultáneamente; pestañas obsoletas no liberan leases nuevos; comentarios son obligatorios para valores modificados"
/orch-change-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-8] Tarea 7: integrar RecordingVideoPlayer con la versión o copia sellada, renovación SAS acotada y manejo de error/cambio de src; Acceptance: play, pausa, seek y saltos funcionan; renovación conserva posición; una sobrescritura del blob de subida no cambia el video revisado"
/orch-add-feature "[Plan: plans/PLAN_IMPLEMENTACION_COLA_ETIQUETADO.md#step-9] Tarea 8: añadir evidencia de calidad a editores de rúbrica y métricas sin alterar borradores ni publicaciones; Acceptance: agregados muestran cantidad, diferencia firmada y error absoluto por versión; unidades incompatibles no se mezclan; cada evidencia enlaza al historial del caso"
```
