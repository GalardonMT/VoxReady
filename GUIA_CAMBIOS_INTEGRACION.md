# Guía Técnica de Cambios e Integración: Pipeline Multimodal y Reporte VISUM

Este documento resume los cambios arquitectónicos, relacionales y de frontend implementados en la rama `feature/multimodal-pipeline-visum-report`. Su objetivo es servir como referencia para el equipo de desarrollo a la hora de realizar revisiones de código (Pull Requests) y resolver conflictos durante el *merge*.

---

## 1. Resumen Ejecutivo del Alcance

Se implementó el flujo completo de evaluación multimodal y cierre de sesión de vocería (Opción 1), abarcando:
1. **Desacoplamiento HTTP interno y escalado a 0 réplicas:** El worker de análisis opera como un microservicio FastAPI que escala de 0 a 1 réplica bajo demanda en Azure Container Apps.
2. **Segmentación de turnos y respuestas:** El frontend captura las marcas de tiempo (`turns`) por cada pregunta formulada, y el worker asocia la transcripción fonética palabra por palabra al registro de cada respuesta en la base de datos (`session_question.response_text`).
3. **Eliminación de redundancia de datos:** `session_question` almacena la clave foránea `question_id` y el texto de la respuesta `response_text`, manteniendo `question_text = NULL` para evitar duplicidad con la tabla maestra `question`.
4. **Saneamiento del objeto JSON de reporte:** Se estandarizó la salida del worker eliminando claves duplicadas en español y suprimiendo nodos redundantes en la raíz (`informe_ejecutivo_visum`), conservando la estructura consolidada en `narrative.visum`.
5. **Arquitectura de Interfaz Dual (UX):**
   - Se mantiene la vista previa ejecutiva rápida (`CoachReportView`, pantalla `u6`) con los puntajes globales y por área.
   - Se añade una vista especializada y profunda (`FullVisumReportView`, pantalla `u8`) con el análisis pedagógico completo de VISUM Consulting, métricas de laboratorio (MediaPipe a 2 FPS y Parakeet), evaluación por dimensiones del LLM Juez y transcripción.
6. **Contrato de Ciclo de Vida (`HTTP 409 Conflict`):** El backend retorna `HTTP 409 Conflict` según RFC 7807 mientras el análisis está en curso, adaptado en el cliente para un polling continuo sin errores visuales.

---

## 2. Cambios Detallados por Módulo

### A. Base de Datos Azure SQL (`sqldb-voxready`)

1. **Alteraciones de Esquema:**
   - `report.analysis_job_id` (`UNIQUEIDENTIFIER NULL`): Vincula formalmente el reporte generado con el job de ejecución de análisis.
   - `session_question.response_text` (`NVARCHAR(MAX) NULL`): Almacena la transcripción fonética de la respuesta del vocero para cada pregunta formulada.
   - Script de migración idempotente provisto en `scripts/migrate_turns_schema.py`.

2. **Reglas Críticas de Integridad Relacional para el Merge:**
   - **Tabla `area_score`:** Las columnas válidas son `(id, report_id, rubric_area_id, value)`. **NO existe ni debe agregarse la columna `area`**. El código del área (`expression`, `voice`, `coherence`, `empathy`) se obtiene mediante `JOIN rubric_area ra ON a.rubric_area_id = ra.id`.
   - **Tabla `session_question`:** `question_id` es clave foránea obligatoria hacia `question.id`. El backend valida los UUIDs de las preguntas reales asociadas al escenario antes de insertar para evitar el error `FK_session_question_question` (error 547).
   - **Tabla `analysis_pipeline_result`:** Se registra una fila con `pipeline = 'fusion'`, `status = 'completed'` y el documento JSON saneado completo en `summary_json`.

---

### B. Worker de Análisis (`worker/` - `ca-analysis-worker`)

* **[worker/main.py](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/worker/main.py):**
  - Servicio FastAPI que expone `POST /analyze` (HTTP 202) y ejecuta el pipeline mediante `BackgroundTasks` con cerrojo de concurrencia (`asyncio.Lock`).
* **[worker/core/pipeline_orchestrator.py](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/worker/core/pipeline_orchestrator.py):**
  - Mapeo de palabras con marcas de tiempo (`start`, `end`) provenientes de NVIDIA Parakeet contra los intervalos de cada turno (`start_ms`, `end_ms`).
  - Extracción segura de métricas acústicas (`score_diccion`, `score_fluidez`, `wpm_global`).
  - Mapeo a las 4 áreas de la rúbrica oficial: Expresión (25%), Voz (25%), Coherencia (35%), Empatía (15%).
  - Construcción del reporte saneado mediante `sanitize_report_json` y persistencia en `analysis_pipeline_result` (`pipeline = 'fusion'`).
* **[worker/core/report_builder.py](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/worker/core/report_builder.py):**
  - Nueva función `sanitize_report_json`:
    - Elimina `informe_ejecutivo_visum` de la raíz; preserva `narrative.visum` con `sintesisEjecutiva`, `formulaRecomendada` y `hallazgosTransversales`.
    - Normaliza `metrics.vision` en camelCase (`eyeContactPct`, `shoulderStabilityScore`, `bodySwayStd`, `handsVisiblePct`, `totalFramesAnalyzed`).
    - Normaliza `metrics.audio` y `metrics.judge` con sus 7 dimensiones.
* **[worker/services/db_service.py](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/worker/services/db_service.py):**
  - `update_question_responses`: Actualiza `response_text` por `(session_id, question_id, sequence_no)`.
  - `finalize_session_analysis`: Inserta atómicamente en `report` y en `area_score` (vinculando `rubric_area_id`).

---

### C. Backend API (`backend/` - `ca-backend-api`)

* **[backend/schemas/session.py](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/backend/schemas/session.py):**
  - `TurnInterval`: Soporte dual para marcas temporales usando `AliasChoices('startMs', 'startOffsetMs')` y `AliasChoices('endMs', 'endOffsetMs')`.
* **[backend/services/worker_client.py](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/backend/services/worker_client.py):**
  - Cliente HTTP asíncrono con `timeout = httpx.Timeout(45.0, connect=30.0)` para soportar el arranque en frío (*cold start*) del worker en Container Apps.
* **[backend/main.py](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/backend/main.py):**
  - `POST /v1/sessions/{id}/finish`: Recibe `turns`, sincroniza `session_question`, actualiza la sesión a `analyzing` y despacha la tarea al worker.
  - `GET /v1/sessions/{id}/report`:
    - Si la sesión está en `created`, `analyzing` o `processing`, lanza `HTTPException(409, detail="El análisis de la sesión no ha finalizado")`.
    - Si la sesión está `completed`, extrae el reporte desde `analysis_pipeline_result` (`pipeline = 'fusion'`) o Blob Storage, genera dinámicamente un token SAS de lectura para la grabación (`recordingUrl` con 60 min de vigencia) y devuelve el payload consolidado.

---

### D. Frontend Web (`frontend/` - `spa-voxready-frontend`)

* **[frontend/src/types/api.ts](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/frontend/src/types/api.ts):**
  - Exportadas interfaces `TurnInterval`, `VisumExecutive`, `MetricsSummary` y `FullVisumReport`.
* **[frontend/src/services/sessionService.ts](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/frontend/src/services/sessionService.ts):**
  - `finishSession`: Envía la lista `turns` al backend.
  - `getRawReport`: Captura errores con código `409` y los retorna como `{ status: 'analyzing' }`, evitando que el polling en `AnalyzingView` falle.
  - `getFullVisumReport`: Consulta el payload completo para la nueva vista.
  - `getPlaybackUrl`: Consume la URL SAS generada por el backend.
* **[frontend/src/components/spokesperson/LiveSessionView.tsx](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/frontend/src/components/spokesperson/LiveSessionView.tsx):**
  - Registro cronometrado de cada pregunta (`startOffsetMs`, `endOffsetMs`) respetando pausas de la simulación.
* **[frontend/src/components/spokesperson/CoachReportView.tsx](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/frontend/src/components/spokesperson/CoachReportView.tsx) (`u6`):**
  - Mantiene la vista previa rápida con Score Ring y las 4 notas por área.
  - Añadido botón: `📋 Ver Informe Completo y Correcciones de Visum ➔` que navega a `u8`.
* **[frontend/src/components/spokesperson/FullVisumReportView.tsx](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/frontend/src/components/spokesperson/FullVisumReportView.tsx) (`u8`):**
  - Nueva pantalla dividida en 4 pestañas interactivas:
    1. *Síntesis VISUM:* Diagnóstico, fortalezas, foco de desarrollo, fórmula en 3 pasos, hallazgos y alerta de señal cruzada.
    2. *Métricas de Laboratorio:* Contacto visual, postura/estabilidad, WPM, fonación y muletillas detectadas.
    3. *Juez de Crisis:* Evaluación de las 7 dimensiones con sus criterios pedagógicos.
    4. *Transcripción:* Texto completo del discurso del vocero.
* **[frontend/src/components/spokesperson/HomePracticeView.tsx](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/frontend/src/components/spokesperson/HomePracticeView.tsx) & [page.tsx](file:///c:/Users/vmmc1/OneDrive/Documentos/PCerdo/nvidia/frontend/src/app/%28spokesperson%29/spokesperson/page.tsx):**
  - Agregado `'u8'` al tipo de unión `VoceroScreen` y montaje del componente en el enrutador del vocero.

---

## 3. Consideraciones para el Merge y Resolución de Conflictos

1. **Conflictos en `sessionService.ts`:**
   - Asegurarse de mantener el bloque `try/catch` que intercepta `HTTP 409`. Si se elimina, el componente `AnalyzingView` arrojará un error de conexión durante el análisis.
2. **Conflictos en `page.tsx`:**
   - Verificar que se incluya tanto la pantalla `'u6'` (`CoachReportView`) como la `'u8'` (`FullVisumReportView`). No sustituir una por la otra.
3. **Versiones de Contenedores en Azure Container Apps:**
   - `ca-backend-api`: Desplegado actualmente con `crvoxreadyst.azurecr.io/backend-api:v13`.
   - `ca-analysis-worker`: Desplegado actualmente con `crvoxreadyst.azurecr.io/analysis-worker:v2.10`.
4. **Manejo de Variables de Entorno:**
   - Requiere `STORAGE_CONNECTION_STRING`, `SQL_CONNECTION_STRING`, `NVIDIA_API_KEY` y `NVIDIA_BASE_URL` configuradas en los secretos de Azure Container Apps.
