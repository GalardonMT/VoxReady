# Avance Tarea 1 — Subtarea 6

## 1. Resultado

- Estado: **Hecho** para la subtarea 6.
- Tarea 1 global: **Parcial**; subtareas 7 a 10 no iniciadas.
- Gate G2: pendiente.
- No se crearon casos ni se modificaron datos.

> Continuidad al 30 de octubre de 2026: las subtareas 7 a 10 ya fueron implementadas. Consulte `AVANCE_TAREA_1_SUBTAREAS_7_10.md` para el estado actual; este documento conserva la evidencia del checkpoint 1.6.

## 2. Implementación

`backend/labeling_classification.py` concentra una función pura y determinista. No abre conexiones y no conoce tablas ni HTTP.

El dry-run de `backend/scripts/reconcile_labeling_cases.py` obtiene para cada informe:

- `overall_score`;
- las cuatro áreas desde `area_score` y `rubric_area`;
- `halfWidth` de `gov.borderline_delta`;
- `auditAt` de `gov.disparity_delta`;
- siempre desde la versión de rúbrica asociada al informe.

El resumen agrega `classificationCounts`, `classificationErrors` y `pendingRuleEvaluation`. No muestra identificadores ni valores individuales.

## 3. Prioridad congelada

1. `critical`: global menor que 50 o al menos un área menor que 50.
2. `borderline`: no crítico y `abs(overallScore-50) <= halfWidth`.
3. `disparity`: no crítico ni límite y `max(area)-min(area) >= auditAt`.
4. `routine`: cualquier informe válido restante.

Ninguna categoría excluye un informe por tener buen o mal puntaje. Los errores solo se producen por datos incompletos, inválidos o sin configuración demostrable.

## 4. Contrato `reasonDetail`

- `critical`: `kind`, `overallScore`, `overallThreshold`, `criticalAreaKeys`.
- `borderline`: `kind`, `overallScore`, `center`, `halfWidth`.
- `disparity`: `kind`, `minAreaKey`, `maxAreaKey`, `delta`, `threshold`.
- `routine`: `kind`, `selectionRule`.

El módulo valida que cada variante contenga exactamente esas propiedades. Los empates de mínimo o máximo se resuelven por `areaKey` ascendente.

## 5. Validación fail-closed

- Puntaje global y áreas deben ser números finitos entre 0 y 100.
- Deben existir exactamente `expression`, `voice`, `coherence` y `empathy` sin duplicados.
- `halfWidth` y `auditAt` deben existir en la versión del informe.
- `halfWidth` debe estar en `(0,50]`; `auditAt`, en `(0,100]`.
- No se usan valores de `metrics_catalog.py` como fallback cuando falta persistencia versionada.
- Una entrada inválida incrementa `classificationErrors`; no se clasifica como `routine` por defecto.

## 6. Verificación ejecutada

- Compilación de `labeling_classification.py` y del comando: correcta.
- Casos ejercitados: crítico por global, crítico por área, límite inferior/inclusivo, prioridad límite sobre disparidad, disparidad exactamente al umbral y rutinario.
- Errores ejercitados: configuración ausente, áreas incompletas y puntaje fuera de rango.
- Simulación del dry-run: 5 informes en 3 lotes; 1 por cada categoría, 1 error, 0 creaciones.
- `reasonDetail.kind` y sus propiedades exactas fueron validados por código.

## 7. Límites pendientes

- No se ejecutó contra Azure SQL porque el esquema aún no fue aplicado y el entorno Python global no contiene `pyodbc`.
- La subtarea 7 debe identificar, excluir y contabilizar sesiones eliminadas, informes actuales duplicados, `fusion` ausente/duplicada y relaciones inconsistentes.
- Hasta completar la subtarea 7, el comando sigue rechazando el modo escritura antes de conectar.
- La verificación persistente, estimación y pruebas repetibles corresponden a las subtareas 8 a 10.
