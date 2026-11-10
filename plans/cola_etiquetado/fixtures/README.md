# Fixtures de contrato de la Cola de Etiquetado

## Propósito y estado

Estos archivos congelan ejemplos sin PII para la Tarea 0. Son artefactos de diseño compartidos por backend y frontend; todavía no representan endpoints implementados. Los DTO usan `camelCase` porque `apiFetch` entrega JSON sin transformar nombres. Los identificadores son UUID ficticios, las fechas están en UTC ISO-8601 y los códigos `CLI-*`, `VOC-*` y `EXP-*` son seudónimos de prueba.

No hay nombres, correos, identificadores B2C, transcripciones, narrativas privadas, rutas internas de Blob ni SAS reales. `fixture-token-not-a-real-secret` y el dominio `.invalid` son marcadores no operativos. Las listas están abreviadas intencionalmente: `total` representa el conjunto completo y `items` solo los casos necesarios para cubrir el contrato.

## Inventario

| Fixture | Cubre |
|---|---|
| `pending-list.json` | Colección pendiente, prioridad crítica y caso bloqueado por otro experto. |
| `reviewed-list.json` | Colección revisada y referencia a la revisión vigente. |
| `detail-complete.json` | Snapshot completo, rúbrica data-driven, métricas observables, configuración no observable y video disponible. |
| `detail-partial.json` | Fuente parcial por evidencia original incierta: métrica `unknown`, `sourceIssues` y valor no editable. |
| `detail-ambiguous.json` | Resultado ambiguo, valores `unknown` y caso no reservable. |
| `detail-locked.json` | Detalle visible en modo lectura durante un lease ajeno. |
| `lease-success.json` | Adquisición o renovación válida con token, generación y tiempos del servidor. |
| `lease-release.json` | Solicitud de liberación voluntaria con token y generación; el endpoint responde `204` sin cuerpo. |
| `recording-url-success.json` | URL temporal de evidencia exacta, fuera del DTO de detalle. La respuesta HTTP deberá usar `Cache-Control: no-store`. |
| `review-submit.json` | Solicitud atómica; no contiene `aiValue`, porque el servidor lo toma del snapshot. |
| `review-response.json` | Revisión persistida con valores IA resueltos por el servidor y deltas. |
| `review-history.json` | Historial inmutable y revisión vigente/sustituida. |
| `quality-summary.json` | Agregados que excluyen valores ambiguos y revisiones sustituidas. |
| `error-409-lease-conflict.json` | Problem Details por reserva ajena; sirve también como conflicto de lease. |
| `error-409-stale-lease.json` | Problem Details `STALE_LEASE` por token o generación obsoletos. |
| `error-410-recording-gone.json` | Medio eliminado por retención, sin borrar la revisión. |
| `error-422-invalid-review.json` | `INVALID_OBSERVATION_VALUE` por tipo o envolvente técnica inválidos. |

## Reglas congeladas que ejercitan los fixtures

- Las colecciones tienen `{items,total,limit}` y admiten como máximo diez elementos en esta etapa.
- Toda lista incluye `latestReview`: es `null` en pendientes y contiene la revisión vigente en revisadas.
- El detalle nunca entrega una SAS ni un `leaseToken`; ambos se obtienen en operaciones separadas.
- Todo detalle usa `rubric: {rubricVersionId,areas}`, `sourceIssues`, `latestReview` y `currentReview`; `sourceStatus` distingue `complete`, `partial` y `ambiguous`.
- `reasonDetail` es una unión discriminada y su `kind` siempre coincide con `queueReason`: `critical` contiene puntaje/umbral/áreas críticas; `borderline` puntaje/centro/semiancho; `disparity` áreas extrema/delta/umbral; `routine` solo la regla de selección. Las anomalías de fuente pertenecen exclusivamente a `sourceIssues`.
- Los estados de lease son `available`, `owned`, `locked_by_other`, `expired` y `not_claimable`.
- `availability` usa exclusivamente `available`, `unknown` o `not_emitted`.
- `metricKind` separa observaciones de configuración. Un valor `unknown`, `not_emitted` o de tipo `configuration` no es editable ni participa en agregados.
- `content.red_line_cap` es configuración, no una observación del caso: queda `not_emitted` y no editable.
- `empathy.victim_recog` queda `not_emitted`, sin valor IA y no editable mientras no exista un productor semántico verificable.
- Toda métrica declara `unit` y `precision` en el nivel superior. Para `metricKind: observation`, `observation` contiene exactamente `valueType`, `canonicalUnit`, `conversion`, `technicalMin` y `technicalMax`, incluso si la disponibilidad es `unknown` o `not_emitted`; para `configuration` o `aggregate_target` es `null`. Las conversiones son `identity`, salvo `voice.phonation_ratio` y `voice.asr_confidence`, que usan `ratio_0_1_to_percent`. `publishedThresholds` solo explica la configuración vigente y no valida la medición.
- Una métrica `not_emitted` esperada por diseño no degrada por sí sola un caso `complete`. `partial` requiere una incertidumbre concreta registrada en `sourceIssues`.
- `recording.durationSeconds` es metadata nullable del medio y no sustituye la duración de la sesión.
- El payload de confirmación no puede declarar valores IA, códigos de experto ni fecha de envío.
- Un valor modificado lleva comentario específico. La revisión se acompaña además de una observación general.
- El historial conserva revisiones sustituidas; solo una es `isCurrent: true`.
- Los errores son RFC 7807/Problem Details con código estable y correlation ID, sin filtrar tokens ni datos personales.

## Divergencias comprobadas con el frontend actual

1. `frontend/src/types/api.ts` modela `LabelingCase` con cuatro áreas fijas y motivos `low_confidence`, `borderline` y `random`; el contrato objetivo usa áreas data-driven y motivos `critical`, `borderline`, `disparity` y `routine`.
2. El tipo actual no contiene estado, fechas, empresa, código seudonimizado, informe exacto, puntaje global, áreas críticas, procedencia, disponibilidad ni lease.
3. La duración actual es `videoDuration: string`; el contrato usa `durationSeconds: number` y deja el formato a la presentación.
4. `rubricService.getLabelingCases()` espera un arreglo desnudo y vuelve a `INITIAL_LABELING_QUEUE` ante errores no relacionados con acceso. El contrato usa colección paginada y prohíbe fallback a mocks.
5. `submitExpertEvaluation()` envía cuatro puntajes y un comentario a `/evaluate`; el contrato requiere lease, generación, revisión optimista, idempotencia, áreas/métricas data-driven e historial inmutable en `/reviews`.
6. `LabelingQueueView.tsx` importa el mock directamente, fija `23 pendientes`, no tiene pestaña Revisadas ni estados de carga/error/vacío/bloqueo y simula el video sin usar `RecordingVideoPlayer`.
7. El aviso actual afirma que la revisión queda encolada para reentrenamiento. La decisión vigente solo guarda evidencia y no dispara entrenamiento.
8. `RecordingVideoPlayer` ya soporta reproducción, pausa, búsqueda, saltos de cinco segundos, buffer, volumen, velocidad y pantalla completa; la integración futura debe entregarle la SAS separada, renovarla con límite y conservar la posición.

## Validación

Desde la raíz del repositorio, todos los fixtures JSON deben parsear sin errores:

```powershell
Get-ChildItem plans\cola_etiquetado\fixtures\*.json | ForEach-Object {
  Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json | Out-Null
}
```

El inventario contiene 17 JSON. La validación de forma contra modelos Pydantic/TypeScript corresponde a las tareas de implementación posteriores; esta tarea no añade tipos ni código productivo.
