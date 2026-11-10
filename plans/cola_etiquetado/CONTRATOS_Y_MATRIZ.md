# Tarea 0 — Contratos API y matriz de métricas

Estado: **congelado para implementación**, sujeto al diagnóstico de datos de T0.
Alcance: contratos de diseño; este documento no crea endpoints, tablas ni migraciones.

## 1. Evidencia revisada

- El catálogo vigente declara 16 claves y mezcla límites de controles con umbrales de interpretación (`backend/metrics_catalog.py:3-20`).
- El worker persiste `report` y `area_score` antes de insertar los resultados de pipeline (`worker/services/db_service.py:301-371`, `worker/core/pipeline_orchestrator.py:573-593`).
- El informe saneado normaliza visión, audio y juez, pero introduce valores por defecto (`worker/core/report_builder.py:173-326`). Por ello, la presencia de una ruta normalizada no demuestra que la métrica se haya observado.
- El endpoint actual busca el último `fusion` de la sesión, no el `fusion` del `analysis_job_id` del informe (`backend/main.py:849-866`), y puede recurrir a un JSON de Blob sobrescribible por sesión (`backend/main.py:870-880`, `worker/core/pipeline_orchestrator.py:227-238`). Esas fuentes no son evidencia exacta para una revisión.
- El endpoint actual también aplica defaults al puntaje global y a métricas (`backend/main.py:951-978`) e incluye transcripción (`backend/main.py:1006`). Ninguno de esos defaults ni la transcripción entran al contrato de etiquetado.
- Los cuatro puntajes persistidos usan las claves `expression`, `voice`, `coherence` y `empathy` (`worker/core/pipeline_orchestrator.py:489-494`). `tone` es solo una etiqueta histórica de UI y no es una clave canónica.

## 2. Convenciones del contrato

- JSON de red en `camelCase`; Python/SQL pueden usar `snake_case` internamente.
- Identificadores como UUID serializado en texto. `caseNumber` es un identificador legible, no una llave ni un dato de autorización.
- Fechas en ISO-8601 UTC con sufijo `Z`. Duraciones en segundos, no en `mm:ss`.
- Listas con `{ "items": [], "total": 0, "limit": 10 }`; en T0 `limit` solo acepta `1..10`.
- Puntajes de áreas en escala `0..100`. Las métricas conservan su unidad canónica declarada en la matriz.
- El backend calcula `aiValue`, disponibilidad, criticidad, prioridad y códigos seudónimos. El navegador no los declara.
- Los DTO no contienen nombre, correo, identificador B2C, transcripción, narrativa libre del informe, ruta interna de Blob, SAS persistida ni token de otra reserva.
- Los campos marcados **T1** son persistencia nueva requerida por el plan, no evidencia de que ya existan.

## 3. Lista de casos

`GET /api/master/labeling-cases?status=pending|reviewed&limit=10`

```json
{
  "items": [
    {
      "caseId": "11111111-1111-4111-8111-111111111111",
      "caseNumber": "8844",
      "status": "pending",
      "queueReason": "critical",
      "reasonDetail": {
        "kind": "critical",
        "overallScore": 48,
        "overallThreshold": 50,
        "criticalAreaKeys": ["empathy"]
      },
      "client": {
        "code": "CLI-7D31",
        "displayName": "Organización de prueba"
      },
      "speakerCode": "VOC-A19F",
      "scenario": {
        "title": "Crisis reputacional"
      },
      "session": {
        "startedAt": "2026-10-27T14:00:00Z",
        "finishedAt": "2026-10-27T14:04:10Z",
        "durationSeconds": 250.0
      },
      "report": {
        "reportId": "22222222-2222-4222-8222-222222222222",
        "generatedAt": "2026-10-27T14:04:20Z",
        "overallScore": 48
      },
      "criticalAreas": [
        { "areaKey": "empathy", "label": "Empatía", "value": 42 }
      ],
      "lease": {
        "state": "available",
        "ownerCode": null,
        "expiresAt": null
      },
      "latestReview": null
    }
  ],
  "total": 1,
  "limit": 10
}
```

Reglas:

- Pendientes: orden estable `(session.finished_at DESC, case_id DESC)`.
- Revisadas: orden estable `(latestReview.submittedAt DESC, latestReview.reviewId DESC)` y `latestReview` contiene `reviewId`, `reviewNo`, `reviewerCode`, `submittedAt`.
- `criticalAreas` solo contiene áreas bajo 50. `reasonDetail` es un snapshot T1, no se recalcula con umbrales futuros.
- `reasonDetail` es una unión discriminada por `kind`, cuyo valor debe ser igual a `queueReason`: `critical` contiene exactamente `overallScore` numérico, `overallThreshold=50` y `criticalAreaKeys`; `borderline` contiene `overallScore`, `center` y `halfWidth`; `disparity` contiene `minAreaKey`, `maxAreaKey`, `delta` y `threshold`; `routine` contiene `selectionRule`. No se mezclan campos de variantes distintas.
- La clasificación usa prioridad estricta `critical > borderline > disparity > routine`. `critical` aplica si el puntaje global o cualquier área es menor que 50. Si no es crítico, `borderline` aplica cuando `abs(overallScore-50) <= halfWidth`. Si tampoco es límite, `disparity` aplica cuando `max(area)-min(area) >= auditAt`; los empates se resuelven por `areaKey` ascendente. Los valores `halfWidth` y `auditAt` se leen de `gov.borderline_delta` y `gov.disparity_delta` de la misma versión de rúbrica del informe. Si faltan o son inválidos, el caso queda pendiente de evaluación y nunca recibe un default silencioso. Todo informe válido que no cumpla las condiciones anteriores queda `routine`.
- `lease.state`: `available`, `owned`, `locked_by_other`, `expired` o `not_claimable`. `not_claimable` se usa para revisados o fuentes ambiguas. `ownerCode` solo se entrega para una reserva vigente y es seudónimo.
- `latestReview` es una propiedad obligatoria y nullable: `null` en un pendiente nunca revisado y objeto en los revisados.
- `session.durationSeconds` se deriva de `finishedAt - startedAt`; si falta alguno de esos instantes es `null`. No se obtiene de la duración del archivo.

## 4. Detalle de caso

`GET /api/master/labeling-cases/{caseId}` devuelve el elemento de lista y agrega:

```json
{
  "caseId": "11111111-1111-4111-8111-111111111111",
  "caseNumber": "8844",
  "status": "pending",
  "contentRevision": 1,
  "sourceStatus": "complete",
  "sourceIssues": ["metric:empathy.victim_recog:not_emitted"],
  "snapshotSchemaVersion": 1,
  "rubric": {
    "rubricVersionId": "33333333-3333-4333-8333-333333333333",
    "areas": [
      {
        "areaId": "44444444-4444-4444-8444-444444444444",
        "areaKey": "expression",
        "label": "Expresión",
        "aiValue": 85,
        "editable": true
      }
    ]
  },
  "metricGroups": [
    {
      "categoryKey": "voice",
      "label": "Voz",
      "metrics": [
        {
          "metricKey": "voice.wpm",
          "metricKind": "observation",
          "label": "Ritmo de habla",
          "availability": "available",
          "aiValue": 132.4,
          "unit": "WPM",
          "precision": 1,
          "observation": {
            "valueType": "decimal",
            "canonicalUnit": "WPM",
            "conversion": "identity",
            "technicalMin": 0,
            "technicalMax": null
          },
          "editable": true,
          "unavailableReason": null,
          "publishedThresholds": {
            "warningLow": 100,
            "optimalLow": 120,
            "optimalHigh": 150,
            "warningHigh": 170
          }
        }
      ]
    }
  ],
  "recording": {
    "availability": "available",
    "durationSeconds": 249.6
  },
  "lease": {
    "state": "available",
    "ownerCode": null,
    "expiresAt": null
  },
  "latestReview": null,
  "currentReview": null
}
```

`sourceIssues`, `latestReview` y `currentReview` son propiedades obligatorias: la primera es una lista posiblemente vacía y las otras dos son nullable. `latestReview` identifica la última revisión por número; `currentReview` identifica la vigente y normalmente coinciden, pero se mantienen separadas para preservar historial. `recording.durationSeconds` proviene únicamente de metadata de la evidencia sellada y es nullable; jamás se infiere desde `session.durationSeconds`.

Cada elemento de `metrics` incluye `metricKind`. Cuando es `observation`, `observation` es obligatorio y declara `valueType`, `canonicalUnit`, `conversion`, `technicalMin` y `technicalMax` nullable. Para `configuration` o `aggregate_target`, `observation` es `null` y `editable=false`; sus umbrales publicados son contexto, no una observación del caso.

`availability` solo admite:

- `available`: la evidencia original prueba que la medición fue emitida y su conversión es conocida.
- `unknown`: la ruta normalizada contiene un default o falta procedencia suficiente para decidir si se midió.
- `not_emitted`: el pipeline actual no produce una observación equivalente a la definición del catálogo.

Solo `available` puede tener `editable=true`. `unknown` y `not_emitted` llevan `aiValue=null`, `editable=false` y una razón estable.

## 5. Reserva

`POST /api/master/labeling-cases/{caseId}/lease`

Solicitud de adquisición inicial:

```json
{ "leaseToken": null, "leaseGeneration": null }
```

Solicitud de renovación propia:

```json
{
  "leaseToken": "secreto-opaco-de-una-pestaña",
  "leaseGeneration": 3
}
```

Respuesta de adquisición o renovación:

```json
{
  "caseId": "11111111-1111-4111-8111-111111111111",
  "leaseToken": "secreto-opaco-de-una-pestaña",
  "leaseGeneration": 3,
  "contentRevision": 1,
  "expiresAt": "2026-10-27T14:24:30Z",
  "serverTime": "2026-10-27T14:04:30Z",
  "readOnly": false
}
```

El token solo aparece al propietario en esta respuesta. Renovar no incrementa `contentRevision`. Liberar y confirmar exigen token y generación.

`DELETE /api/master/labeling-cases/{caseId}/lease` recibe cuerpo explícito:

```json
{
  "leaseToken": "secreto-opaco-de-una-pestaña",
  "leaseGeneration": 3
}
```

La primera liberación válida responde `204`. Repetir exactamente la liberación después de que esa misma generación ya quedó liberada también responde `204` y no cambia estado. Si el caso ya fue adquirido con una generación posterior, responde `409 STALE_LEASE`; una pestaña anterior nunca puede liberar la reserva nueva.

## 6. URL temporal de grabación

`GET /api/master/labeling-cases/{caseId}/recording-url`

```json
{
  "url": "https://storage.example.invalid/evidence/object.webm?sig=REDACTED",
  "expiresAt": "2026-10-27T14:19:30Z",
  "contentType": "video/webm",
  "durationSeconds": 249.6,
  "etag": "0x8D0000000000000",
  "blobVersionId": "2026-10-27T14:04:05.0000000Z"
}
```

La respuesta usa `Cache-Control: no-store`. `blobVersionId` puede ser `null` cuando el caso referencia una copia sellada única. No se admite una URL pública como fallback.

`durationSeconds` es nullable y se obtiene de metadata de la evidencia sellada. No usa ni recalcula la duración de la sesión.

## 7. Confirmación de revisión

`POST /api/master/labeling-cases/{caseId}/reviews`

```json
{
  "leaseToken": "secreto-opaco-de-una-pestaña",
  "leaseGeneration": 3,
  "expectedContentRevision": 1,
  "idempotencyKey": "55555555-5555-4555-8555-555555555555",
  "supersedesReviewId": null,
  "overallComment": "La evidencia visual justifica un ajuste moderado.",
  "rubricCorrections": [
    {
      "areaId": "44444444-4444-4444-8444-444444444444",
      "correctedValue": 82,
      "comment": "El contacto visual fue intermitente."
    }
  ],
  "metricCorrections": [
    {
      "metricKey": "voice.wpm",
      "correctedValue": 128.0,
      "comment": "Se excluyó el silencio previo a la respuesta."
    }
  ]
}
```

Reglas:

- No acepta `aiValue`, `reviewerId`, `status`, `submittedAt` ni campos de vigencia.
- Debe incluir exactamente todas las áreas editables del snapshot. Una métrica puede omitirse si no se corrige; si se incluye, debe estar `available` y ser editable.
- Si `correctedValue != aiValue`, `comment` es obligatorio después de normalizar espacios.
- Primera revisión: `supersedesReviewId=null`. Una revisión posterior debe apuntar a la revisión vigente del mismo caso.
- Misma `idempotencyKey` y mismo caso devuelve el resultado ya confirmado; una clave reutilizada con payload diferente produce `409`.

Respuesta `201` (o `200` en replay idempotente):

```json
{
  "reviewId": "66666666-6666-4666-8666-666666666666",
  "caseId": "11111111-1111-4111-8111-111111111111",
  "reviewNo": 1,
  "reviewerCode": "EXP-42C1",
  "isCurrent": true,
  "supersedesReviewId": null,
  "submittedAt": "2026-10-27T14:10:00Z",
  "contentRevision": 2,
  "overallComment": "La evidencia visual justifica un ajuste moderado.",
  "rubricCorrections": [
    {
      "areaKey": "expression",
      "aiValue": 85,
      "correctedValue": 82,
      "comment": "El contacto visual fue intermitente."
    }
  ],
  "metricCorrections": [
    {
      "metricKey": "voice.wpm",
      "aiValue": 132.4,
      "correctedValue": 128.0,
      "unit": "WPM",
      "comment": "Se excluyó el silencio previo a la respuesta."
    }
  ]
}
```

`GET /api/master/labeling-cases/{caseId}/reviews` devuelve `{items,total}` con esta misma forma, orden `reviewNo DESC`.

## 8. Resúmenes de calidad

`GET /api/master/quality-reviews/summary`

```json
{
  "period": { "from": "2026-10-01T00:00:00Z", "to": "2026-11-01T00:00:00Z" },
  "currentReviewsOnly": true,
  "reviewedCases": 12,
  "rubricAreas": [
    {
      "areaKey": "expression",
      "sampleCount": 12,
      "meanAiValue": 76.5,
      "meanCorrectedValue": 73.0,
      "meanDelta": -3.5,
      "changedCount": 7
    }
  ],
  "metrics": [
    {
      "metricKey": "voice.wpm",
      "mappingVersion": 1,
      "unit": "WPM",
      "sampleCount": 8,
      "meanAiValue": 141.2,
      "meanCorrectedValue": 137.0,
      "meanDelta": -4.2,
      "changedCount": 3
    }
  ],
  "categories": [
    { "categoryKey": "voice", "reviewedMetricCount": 6, "changedCount": 3 }
  ]
}
```

Los agregados excluyen `unknown`, `not_emitted` y revisiones no vigentes por defecto. No promedian magnitudes de unidades diferentes; la categoría solo cuenta evidencia. Los filtros y la paginación de `GET /api/master/quality-reviews` se congelarán sobre esta misma identidad (`areaKey` o `metricKey + mappingVersion + unit`).

## 9. Matriz de métricas v1

`Ruta original` siempre se evalúa en `analysis_pipeline_result` del mismo `analysis_job_id` que `report`. `Ruta fusion` es solo presentación; nunca prueba disponibilidad por sí sola.

| `metricKey` | `metricKind` | Ruta original del pipeline | Ruta `fusion` normalizada | Tipo y unidad canónica | Conversión y precisión | Envolvente técnica de observación | Editable | Estado v1 |
|---|---|---|---|---|---|---|---|---|
| `voice.wpm` | `observation` | `voice.wpm_global` | `metrics.audio.wpmGlobal` | decimal, WPM | identidad; 1 decimal | `>=0`; máximo operativo POR DEFINIR con datos reales | sí | `available` si la ruta original existe y hubo palabras/duración |
| `voice.filler_density` | `observation` | `voice.densidad_muletillas_pct` | `metrics.audio.densidadMuletillasPct` | decimal, `%` | identidad; 2 decimales | `0..100` | sí | `available` si la ruta original existe; `unknown` en históricos derivados solo del default |
| `voice.prolonged_pause` | `observation` | `voice.pausas_prolongadas` | `metrics.audio.pausasProlongadas` | entero, pausas | identidad; 0 decimales | entero `>=0` | sí | `available` si la ruta original existe |
| `voice.hesitation_pause` | `observation` | `voice.pausas_vacilacion` | `metrics.audio.pausasVacilacion` | entero, pausas | identidad; 0 decimales | entero `>=0` | sí | `available` si la ruta original existe |
| `voice.phonation_ratio` | `observation` | `voice.ratio_fonacion` | `metrics.audio.ratioFonacion` | decimal, `%` | valor original `0..1` multiplicado por 100; 1 decimal | `0..100 %` después de convertir | sí | `available` si la ruta original existe; guardar siempre en `%` |
| `voice.asr_confidence` | `observation` | `voice.score_diccion`, derivado de `words[].confidence` en memoria | `metrics.audio.scoreDiccion` | decimal, `%` | confianza promedio `0..1` por 100; 1 decimal | `0..100` | sí, con reserva | `available` solo si la evidencia original prueba ASR con palabras; si solo existe `score_diccion` sin procedencia, `unknown` |
| `vision.eye_contact` | `observation` | `vision.summary.eye_contact_pct` o `vision.eye_contact_pct` según productor | `metrics.vision.eyeContactPct` | decimal, `%` | identidad; 2 decimales | `0..100` | sí | `available` cuando existe ruta original y hay frames válidos |
| `vision.posture` | `observation` | `vision.summary.shoulder_stability_score` o raíz equivalente | `metrics.vision.shoulderStabilityScore` | decimal, `%` | identidad; 2 decimales | intención `0..100`; rechazar fuera de dominio solo tras validar productor | sí | `available` cuando existe ruta original y hay frames válidos |
| `vision.sway_tolerance` | `observation` | `vision.summary.body_sway_std` o `vision.body_sway_std` | `metrics.vision.bodySwayStd` | decimal, `std` | identidad; 4 decimales | `>=0`; máximo técnico POR DEFINIR con productor/datos | sí | `available` cuando la ruta original existe; cero por normalizador sin fuente es `unknown` |
| `content.red_line_cap` | `configuration` | SIN EVIDENCIA de observación | ninguna | configuración, pts | no aplica | no aplica | no | `not_emitted`; es un techo configurable, no desempeño observado |
| `empathy.victim_recog` | `observation` | SIN EVIDENCIA de una salida equivalente | ninguna | entero, nivel `1..5` | POR DEFINIR; no equiparar a `asertividad_hostilidad.nivel` sin decisión semántica | `1..5` si se crea productor | no en v1 | `not_emitted` |
| `gov.confidence_min` | `configuration` | no aplica | ninguna | configuración, `%` | no aplica | no aplica | no | `not_emitted`; contexto de auditoría |
| `gov.borderline_delta` | `configuration` | no aplica | ninguna | configuración, pts | no aplica | no aplica | no | `not_emitted`; regla de selección |
| `gov.disparity_delta` | `configuration` | no aplica | ninguna | configuración, pts | no aplica | no aplica | no | `not_emitted`; regla de selección |
| `gov.random_sample` | `configuration` | no aplica | ninguna | configuración, `%` | no aplica | no aplica | no | `not_emitted`; regla de muestreo |
| `gov.agreement_target` | `aggregate_target` | no aplica | ninguna | configuración, ratio | no aplica | no aplica | no | `not_emitted`; objetivo agregado IA-humano |

### 9.1 Límites de observación vs. umbrales configurables

Los `min_value`, `max_value` y `thresholds` de `metrics_catalog.py` describen el control del Editor de Métricas y las bandas de interpretación. No son validadores universales de una observación. Ejemplos:

- `voice.wpm` permite configurar `60..220`, pero una medición real fuera de ese intervalo sigue siendo evidencia válida y debe poder revisarse.
- `voice.phonation_ratio` se produce como ratio `0..1`, mientras el catálogo y la UI hablan en porcentaje. El snapshot debe convertir de forma explícita a `%`.
- `vision.sway_tolerance` tiene un control `0.005..0.080`, pero el productor puede emitir `0`; ese valor no se rechaza si la fuente prueba que fue medido.
- Los conteos de pausas no quedan inválidos por superar el máximo del stepper del editor.

La validación de una corrección usa el tipo y la envolvente técnica de esta matriz; los umbrales publicados se muestran como contexto. Todo máximo marcado POR DEFINIR bloquea una regla de rechazo superior hasta analizar datos reales.

## 10. Fuente canónica y clasificación de integridad

La identidad canónica es:

```text
labeling_case.report_id
  -> report.analysis_job_id
  -> analysis_pipeline_result.analysis_job_id
  -> exactamente una fila pipeline='fusion'
```

El snapshot copia, dentro de una misma operación verificable:

1. identidad de cliente, sesión, informe, job y rúbrica;
2. `overall_score` y los cuatro `area_score` del informe;
3. `fusion` exacto del job para valores normalizados;
4. resultados originales `vision`, `voice` y `content_judge` del mismo job para presencia y procedencia;
5. identidad sellada del medio analizado (versión o copia única, hash SHA-256 y ETag).

Clasificación:

- `complete`: todas las identidades coinciden; existe exactamente un `fusion`; su `reportId` coincide; existen las cuatro áreas sin duplicados; la evidencia de medio está sellada. Las métricas no emitidas pueden existir como `not_emitted` sin degradar el caso.
- `partial`: la identidad base y el medio son inequívocos, pero una o más métricas esperadas carecen de procedencia suficiente y quedan `unknown`, no editables. Una métrica conocida como `not_emitted` puede registrarse informativamente en `sourceIssues`, pero no degrada un caso `complete`.
- `ambiguous`: falta `analysis_job_id`, falta `fusion`, hay múltiples `fusion`, el `fusion.reportId` no coincide, existen múltiples informes actuales sin resolución explícita, las áreas son duplicadas/incompletas, o no puede fijarse el medio exacto. No se permite confirmar la revisión. La falta de `fusion` nunca se clasifica como `partial`.

No se usa como fuente canónica `SELECT TOP 1 ... ORDER BY apr.created_at DESC` por sesión, el Blob `{session_id}_report.json`, ni un valor normalizado por default.

## 11. Errores de contrato

Formato `application/problem+json`:

```json
{
  "type": "https://voxready.example/problems/lease-conflict",
  "title": "Caso reservado por otro experto",
  "status": 409,
  "detail": "El caso tiene una reserva vigente y solo puede abrirse en modo lectura.",
  "code": "LEASE_CONFLICT",
  "correlationId": "77777777-7777-4777-8777-777777777777"
}
```

Ejemplos congelados:

| HTTP | `code` | Cuándo aplica | Contexto seguro opcional |
|---|---|---|---|
| 409 | `LEASE_CONFLICT` | reserva vigente de otro experto | `expiresAt`, nunca token ni identidad real |
| 409 | `STALE_LEASE` | token/generación vencidos o de otra pestaña | generación vigente no se expone |
| 409 | `CONTENT_REVISION_CONFLICT` | `expectedContentRevision` obsoleto | `currentContentRevision` |
| 409 | `IDEMPOTENCY_KEY_REUSED` | misma clave con payload diferente | ninguno |
| 409 | `AMBIGUOUS_SOURCE` | snapshot no puede ligarse a evidencia exacta | lista de códigos técnicos sin PII |
| 410 | `RECORDING_RETAINED_OR_DELETED` | la referencia existía, pero el medio ya no está disponible por retención | `retentionState` |
| 422 | `INCOMPLETE_RUBRIC` | faltan áreas editables o hay áreas ajenas al snapshot | `fieldErrors[]` |
| 422 | `METRIC_NOT_EDITABLE` | métrica `unknown`, `not_emitted` o de gobernanza | `metricKey` |
| 422 | `COMMENT_REQUIRED` | cambió el valor sin justificación | `fieldErrors[]` |
| 422 | `INVALID_OBSERVATION_VALUE` | tipo o envolvente técnica inválidos | `metricKey`, `unit` |

Los detalles nunca incluyen comentario completo, transcripción, SAS, token, correo o nombre.

## 12. Decisiones cerradas y pendientes para T1

Decisiones cerradas:

- Wire DTO en `camelCase` y contrato data-driven para áreas/métricas.
- `voice`, no `tone`, es la clave de área canónica.
- Ocho métricas del catálogo tienen mapeo observable directo; `voice.asr_confidence` requiere prueba adicional de procedencia; siete claves son configuración o no tienen productor equivalente.
- Los defaults del normalizador no prueban medición.
- `aiValue` siempre se resuelve en servidor desde el snapshot.
- Transcripción y narrativa libre quedan fuera del contrato inicial.

Pendientes que no se deben resolver inventando:

- El máximo operativo de WPM y `body_sway_std`, luego del diagnóstico real.
- Si se persistirá explícitamente la cantidad de palabras ASR para que `voice.asr_confidence` sea editable sin ambigüedad.
- Un productor semánticamente válido para `empathy.victim_recog`; `asertividad_hostilidad` no se acepta como sustituto implícito.
- Etiquetas localizadas de áreas y categorías: deben provenir de rúbrica/catálogo, no quedar fijadas en el DTO.
