Informe técnico de la rama feat/mi-progreso
1. Estado actual de la rama
La rama está basada en main y contiene:
- Un commit confirmado y publicado:
  - 7add69c fix: endurecer autenticación y aislamiento multitenant
- Los cambios completos de “Mi Progreso” permanecen sin commit, respetando la instrucción de no confirmar cambios sin una segunda autorización.
- Estado de trabajo actual:
  - 15 archivos versionados modificados.
  - 13 archivos nuevos sin seguimiento.
  - No se modificaron archivos .env.
  - No se creó ninguna base local ni entorno virtual.
  - No se hizo borrado físico de información.
El trabajo se divide en dos grandes bloques:
1. Endurecimiento previo de autenticación, Azure SQL y aislamiento multi-tenant.
2. Implementación completa de “Mi Progreso”: migración, API, procesamiento, frontend y pruebas.
2. Arquitectura final
Pantalla Mi Progreso
 ├─ GET /v1/me/progress
 │    └─ session + report + area_score
 │         └─ tendencias, comparación y sesiones recientes
 │
 ├─ GET/POST/PATCH /v1/me/schedule
 │    └─ schedule
 │         ├─ agendar
 │         ├─ editar
 │         ├─ cancelar lógicamente
 │         └─ iniciar práctica
 │              └─ session + session_question
 │
 └─ Sesión terminada por el worker
      ├─ report + area_score
      ├─ actualización de user_area_progress
      └─ schedule pasa automáticamente a completed
Toda consulta o modificación se restringe mediante la combinación:
usuario autenticado + client_id resuelto desde Azure SQL
El frontend nunca envía un user_id o client_id para decidir a quién pertenecen los datos.
3. Endurecimiento de autenticación y aislamiento multi-tenant
Este bloque corresponde al commit 7add69c.
Autenticación
En [backend/main.py (line 67)](C:/Users/julia/VoxReady/backend/main.py:67):
- DEV_AUTH solamente puede habilitarse cuando ENVIRONMENT=development.
- La cuenta Dev Auth se obtiene de DEV_AUTH_TEST_EMAIL.
- Esa dirección debe corresponder a un usuario activo y ya registrado en dbo.app_user.
- Se eliminó el autoaprovisionamiento de usuarios desconocidos.
- El rol y la empresa ya no se toman del token, frontend o almacenamiento local: se resuelven desde Azure SQL.
- Se eliminó el fallback que decodificaba JWT sin verificar la firma.
- Los errores JWT ya no exponen detalles internos.
En [backend/master_topics.py (line 63)](C:/Users/julia/VoxReady/backend/master_topics.py:63):
- resolve_user resuelve al actor por UUID o correo único.
- Rechaza usuarios eliminados, ambiguos o no registrados.
- Exige empresa asignada para operaciones que no sean exclusivas del rol maestro.
- Permite explícitamente el caso de un master_config sin empresa solo donde corresponde.
Dev Auth separado del modo normal
En [docker-compose.local-auth.yml (line 1)](C:/Users/julia/VoxReady/docker-compose.local-auth.yml:1):
- Se creó un override exclusivo para desarrollo local.
- Activa ENVIRONMENT=development y DEV_AUTH=true.
- Exige DEV_AUTH_TEST_EMAIL.
- Publica frontend y API únicamente en 127.0.0.1.
En [docker-compose.azure.yml](C:/Users/julia/VoxReady/docker-compose.azure.yml):
- El Compose normal fuerza DEV_AUTH=false.
- El frontend normal fuerza NEXT_PUBLIC_DEV_AUTH=false.
- El flujo predeterminado continúa usando Azure SQL.
En [docker-compose.yml (line 1)](C:/Users/julia/VoxReady/docker-compose.yml:1):
- Se eliminó el antiguo Compose de demostración con SQLite, bind mounts y uvicorn --reload.
- Ahora incluye directamente docker-compose.azure.yml.
En [docker.ps1](C:/Users/julia/VoxReady/docker.ps1):
- Se agregó el parámetro -LocalDevAuth.
- Todos los comandos usan el conjunto correcto de archivos Compose.
- config --quiet evita imprimir secretos.
Endurecimiento del worker
En [worker/services/db_service.py (line 218)](C:/Users/julia/VoxReady/worker/services/db_service.py:218):
- El worker dejó de seleccionar “el primer escenario activo”.
- Ahora carga el contexto exacto de session_id + job_id.
- Verifica coincidencia entre sesión, usuario, cliente, escenario, rúbrica y job.
- Eliminó UUID y usuarios/clientes predeterminados.
- Ya no crea sesiones artificiales si no encuentra la sesión real.
En [worker/core/pipeline_orchestrator.py (line 276)](C:/Users/julia/VoxReady/worker/core/pipeline_orchestrator.py:276):
- Azure SQL pasó a ser obligatorio para resolver la sesión.
- Se valida que la rúbrica solicitada sea la de la sesión.
- Se valida que el blob sea exactamente recordings/{session_id}.webm.
- Los estados fallidos solo se escriben después de haber identificado una sesión válida.
En [worker/worker.py (line 194)](C:/Users/julia/VoxReady/worker/worker.py:194):
- Los mensajes necesitan session_id, job_id y el blob exacto.
- El escenario, contexto y mensajes clave se leen desde la sesión persistida.
- Ya no se confía en escenario, mensajes o contexto enviados en el evento.
Pruebas y documentación de este bloque
- [backend/tests/test_flow_regression.py](C:/Users/julia/VoxReady/backend/tests/test_flow_regression.py): regresiones de autenticación, acceso y flujo de sesiones.
- [worker/test_session_context.py](C:/Users/julia/VoxReady/worker/test_session_context.py): resolución segura de sesión/job.
- [DOCKER_AZURE.md](C:/Users/julia/VoxReady/DOCKER_AZURE.md): flujo Azure y Dev Auth local.
- [README.md](C:/Users/julia/VoxReady/README.md): documentación actualizada sobre autenticación y procesamiento.
4. Migración aditiva para “Mi Progreso”
La migración se implementó en [progress_migration.py (line 1)](C:/Users/julia/VoxReady/backend/scripts/progress_migration.py:1).
Cambios sobre schedule
Se agregó:
- schedule.session_id UNIQUEIDENTIFIER NULL.
- FK FK_schedule_session hacia dbo.session(id).
- Índice único filtrado UQ_schedule_session:
  - Impide que una misma sesión cumpla más de una agenda.
  - Permite múltiples agendas sin sesión, porque solo indexa valores no nulos.
- Índice IX_schedule_client_user_date:
  - Claves: client_id, user_id, scheduled_date, status.
  - Incluye scenario_id, session_id y updated_at.
No se creó una tabla alternativa ni se modificó destructivamente la tabla existente.
Cambios sobre user_area_progress
Se agregó el índice único:
(user_id, rubric_area_id)
Esto garantiza una sola fila de resumen por usuario y área.
Antes de crear el índice:
- Se comprueba que no existan duplicados.
- Si existen, la migración falla y revierte la transacción.
- No intenta borrar ni combinar silenciosamente datos preexistentes.
Backfill
El backfill:
- Considera únicamente sesiones completed.
- Ignora sesiones con borrado lógico.
- Usa solamente el reporte vigente: report.is_current = 1.
- Elige la última puntuación registrada de cada area_key.
- Calcula:
  - current_value: puntuación de la última sesión.
  - delta: última sesión menos sesión inmediatamente anterior.
  - sessions_count: total histórico de sesiones completadas con informe.
  - last_session_at: fecha de la última sesión.
- Usa MERGE ... WITH (HOLDLOCK) para ser idempotente.
- Actualiza o inserta, pero nunca elimina filas.
Integración con el inicializador
En [prepare_azure_database.py (line 34)](C:/Users/julia/VoxReady/backend/scripts/prepare_azure_database.py:34):
- La migración se ejecuta dentro de la transacción y el bloqueo existentes.
- El DDL se separa por lotes para que Azure SQL recompile después de añadir la columna.
- --verify-only comprueba sin persistir:
  - Tipo y nulabilidad de schedule.session_id.
  - FK activa y confiable.
  - Índices, orden de columnas, includes y filtro.
  - Unicidad de user_area_progress.
La imagen del backend incluye los nuevos archivos desde [backend/Dockerfile (line 26)](C:/Users/julia/VoxReady/backend/Dockerfile:26).
5. API de progreso
La lógica está en [progress_store.py (line 111)](C:/Users/julia/VoxReady/backend/progress_store.py:111).
Endpoint
GET /v1/me/progress?lastN=5
También se conserva el alias /me/progress.
Respuesta
La API entrega:
- sessionsCount: total histórico confirmado.
- trendSessions: sesiones seleccionadas para el gráfico.
- areas: áreas dinámicas encontradas en la rúbrica.
- recentSessions: sesiones recientes con acceso al informe.
Cada área incluye:
{
  "areaKey": "expression",
  "current": 70,
  "change": 8,
  "values": [60, 64, 70]
}
Reglas implementadas
- Solo acepta lastN entre 1 y 20.
- Usa por defecto cinco sesiones.
- Solo considera sesiones completadas con reporte vigente.
- Ordena las sesiones cronológicamente para el gráfico.
- Genera etiquetas S1, S2, etc.
- current corresponde a la última sesión.
- change es:
puntaje última sesión − puntaje sesión anterior
- Si falta un área en alguna sesión, el valor correspondiente es null.
- No une artificialmente los valores faltantes.
- Si existe una sola sesión, el cambio es null.
- Incluso con lastN=1, consulta la sesión anterior para poder calcular el cambio.
- Las fechas se serializan como UTC.
Seguridad
Las consultas:
- Resuelven primero al usuario autenticado en la base.
- Exigen rol spokesperson.
- Exigen empresa asignada.
- Filtran simultáneamente por session.user_id y session.client_id.
- No aceptan identificadores de actor enviados por el frontend.
Los endpoints se registraron en [backend/main.py (line 269)](C:/Users/julia/VoxReady/backend/main.py:269).
6. API de agenda
La persistencia está en [schedule_store.py (line 142)](C:/Users/julia/VoxReady/backend/schedule_store.py:142), con contratos Pydantic en [schemas/schedule.py (line 9)](C:/Users/julia/VoxReady/backend/schemas/schedule.py:9).
Endpoints añadidos
GET    /v1/me/schedule
POST   /v1/me/schedule
PATCH  /v1/me/schedule/{scheduleId}
POST   /v1/me/schedule/{scheduleId}/cancel
POST   /v1/me/schedule/{scheduleId}/start
Consultar calendario
GET /v1/me/schedule recibe:
fromDate
toDate
Devuelve por separado:
- Agendas pendientes o completadas.
- Sesiones reales completadas.
- Escenario practicado.
- Informe vigente.
- Puntaje general.
- Puntajes por área.
El rango:
- Es inclusivo.
- No puede estar invertido.
- No puede superar 366 días.
Los escenarios archivados siguen apareciendo en el historial con:
{
  "status": "archived",
  "available": false
}
Crear una agenda
POST /v1/me/schedule:
- Exige fecha y escenario.
- Solo permite desde hoy hasta doce meses.
- Permite varias prácticas el mismo día.
- No guarda hora.
- Cada registro representa una práctica independiente.
- Solo acepta escenarios activos de la empresa del vocero.
- Valida además que el tema y cliente continúen activos.
Editar una agenda
PATCH /v1/me/schedule/{id}:
- Permite cambiar fecha, escenario o ambos.
- Solo modifica agendas:
  - scheduled.
  - Sin sesión vinculada.
- Usa bloqueos UPDLOCK,HOLDLOCK.
- Repite en el UPDATE las condiciones de usuario, cliente, estado y sesión nula.
Cancelar una agenda
POST /cancel:
- Cambia el estado a cancelled.
- No elimina el registro.
- Solo funciona con agendas pendientes y no iniciadas.
- Una agenda ajena se responde como inexistente, sin revelar que pertenece a otro usuario.
Iniciar una práctica
La lógica está en [schedule_store.py (line 350)](C:/Users/julia/VoxReady/backend/schedule_store.py:350).
Al iniciar:
1. Se valida el UUID.
2. Se resuelve el vocero desde Azure SQL.
3. Se inicia una transacción.
4. Se toma un sp_getapplock exclusivo para la cita.
5. Se vuelve a consultar la agenda filtrando por usuario y cliente.
6. Se crea una sesión real en español.
7. Se copian las preguntas actuales del escenario a session_question.
8. Se vincula schedule.session_id.
9. Se confirma todo como una sola operación.
Puede iniciarse antes, durante o después de la fecha agendada.
El doble clic es idempotente:
- Si la cita ya tiene una sesión, devuelve esa misma sesión.
- No crea una segunda práctica.
7. Reutilización del flujo existente de sesiones
En [spokesperson_store.py](C:/Users/julia/VoxReady/backend/spokesperson_store.py):
Se extrajo create_session_in_transaction.
Antes, create_session contenía toda la creación y administraba su propia conexión. Ahora:
- create_session_in_transaction recibe cursor y perfil ya resuelto.
- Devuelve la respuesta pública y el UUID interno.
- Mantiene las validaciones existentes:
  - idioma permitido;
  - idempotencia;
  - escenario y tema activos;
  - pertenencia al cliente;
  - preguntas activas;
  - rúbrica publicada;
  - snapshot de preguntas.
- El endpoint normal de creación sigue usando esa función.
- El inicio desde agenda puede crear y vincular la sesión en la misma transacción.
Así no se duplicó el flujo existente ni se creó una segunda forma incompatible de generar sesiones.
8. Actualización automática desde el worker
En [worker/services/db_service.py (line 297)](C:/Users/julia/VoxReady/worker/services/db_service.py:297), finalize_session_analysis ahora ejecuta atómicamente:
1. Inserción de report.
2. Inserción de area_score.
3. Cambio de la sesión a completed.
4. Actualización de user_area_progress.
5. Cambio de la agenda vinculada a completed.
6. commit.
Actualización de progreso
USER_AREA_PROGRESS_REFRESH_DML:
- Identifica al actor a partir de la sesión procesada.
- Limita los cálculos al mismo usuario y cliente.
- Usa reportes vigentes y sesiones completadas.
- Calcula el último valor y el inmediatamente anterior por area_key.
- Ejecuta un MERGE sobre user_area_progress.
Cumplimiento de la agenda
LINKED_SCHEDULE_COMPLETE_DML, en [db_service.py (line 102)](C:/Users/julia/VoxReady/worker/services/db_service.py:102):
- Actualiza únicamente la agenda cuyo session_id coincide.
- Comprueba que usuario y cliente sean iguales a los de la sesión.
- Solo cambia agendas todavía scheduled.
- Una práctica del mismo escenario iniciada fuera de la cita no completa otra agenda.
Si falla la actualización del progreso:
- Se revierte informe, áreas, sesión y agenda.
- La sesión se marca después como failed mediante el mecanismo de error existente.
9. Frontend de “Mi Progreso”
La pantalla principal se reemplazó en [ProgressView.tsx (line 52)](C:/Users/julia/VoxReady/frontend/src/components/spokesperson/ProgressView.tsx:52).
Eliminación de datos simulados
Se retiró el uso de INITIAL_PROGRESS.
La pantalla ahora obtiene:
- Progreso desde /me/progress.
- Calendario desde /me/schedule.
- Escenarios desde /scenarios.
Los escenarios se consultan paginando de 100 en 100 hasta recuperar todos los activos de la empresa.
Cliente API
Se creó [progressService.ts (line 81)](C:/Users/julia/VoxReady/frontend/src/services/progressService.ts:81), con contratos TypeScript para:
- Progreso.
- Áreas.
- Puntos del gráfico.
- Sesiones recientes.
- Agenda.
- Historial del calendario.
- Inicio de una cita.
Contiene los métodos:
- getProgress.
- getCalendar.
- createSchedule.
- updateSchedule.
- cancelSchedule.
- startSchedule.
Modelo de presentación
Se creó [progressModel.ts (line 13)](C:/Users/julia/VoxReady/frontend/src/services/progressModel.ts:13):
- Traducción de códigos técnicos de área:
  - expression → Expresión.
  - voice → Tono de voz.
  - coherence → Coherencia.
  - empathy → Empatía.
- Fallback dinámico para áreas futuras.
- Conversión de fechas a zona horaria del navegador.
- Cálculo del rango mensual.
- Validación de fechas agendables.
Gráfico
En [ProgressView.tsx (line 376)](C:/Users/julia/VoxReady/frontend/src/components/spokesperson/ProgressView.tsx:376):
- Usa datos reales.
- Soporta áreas dinámicas.
- Muestra hasta cinco sesiones.
- Conserva las etiquetas S1–S5.
- Cada punto contiene:
  - área;
  - etiqueta;
  - fecha;
  - escenario;
  - puntaje.
- El detalle es accesible mediante foco y <title> SVG.
- Los puntos sin datos no se dibujan.
- Las líneas se dividen en segmentos para no unir artificialmente una ausencia.
- Incluye título y descripción accesibles del gráfico.
- Las cuatro áreas actuales mantienen colores estables.
- Áreas futuras reciben colores adicionales.
Tabla de avance
- “Actual” muestra la puntuación de la última sesión.
- Mejora: flecha ascendente verde y valor positivo.
- Descenso: flecha descendente roja.
- Sin sesión anterior, sin dato o cambio cero: guion.
- El verde se reserva para una mejora.
Calendario
El calendario:
- Comienza el lunes.
- Usa la zona horaria del navegador.
- Distingue:
  - punto naranja: agenda pendiente;
  - punto azul: sesión realizada;
  - contador: varias actividades.
- Permite consultar meses históricos.
- Permite agendar desde hoy hasta doce meses.
- Muestra un panel para el día seleccionado.
- Permite varias prácticas en la misma fecha.
- Identifica agendas anteriores sin completar como “Pendiente atrasada”.
- Muestra escenarios archivados, pero bloquea “Iniciar práctica”.
- Permite cambiar un escenario archivado por uno activo.
- Ofrece:
  - editar;
  - cancelar;
  - iniciar práctica;
  - abrir informe.
Continuación del flujo existente
En [spokesperson/page.tsx (line 61)](/C:/Users/julia/VoxReady/frontend/src/app/(spokesperson\)/spokesperson/page.tsx:61):
- “Ver informe” establece el sessionId real y abre CoachReportView.
- “Iniciar práctica” recupera el SessionSetup.
- Guarda sesión, usuario y cliente en el estado existente.
- Abre la pantalla de consentimiento y comprobación técnica.
- No se creó un flujo paralelo de grabación.
Sesiones recientes
Se añadió una lista debajo de la cuadrícula principal con:
- Escenario.
- Fecha.
- Puntaje general.
- Botón “Ver informe”.
Estados vacíos y errores
Se implementaron:
- “Completa tu primera práctica para comenzar a ver tu progreso”.
- Botón “Elegir escenario”.
- Carga independiente del progreso y calendario.
- Error parcial: si falla una API, las demás secciones siguen funcionando.
- Botón “Reintentar”.
- Error independiente para el catálogo de escenarios.
- Mensajes y controles nuevos en español.
Recomendaciones
El bloque “Recomendaciones para ti”:
- Conserva sus textos.
- Conserva sus tres tarjetas.
- Conserva la navegación a microlecciones.
- No se conectó ni modificó su origen, conforme a lo solicitado.
Estilos
En [globals.css (line 826)](C:/Users/julia/VoxReady/frontend/src/app/globals.css:826):
- Los días ahora son botones accesibles.
- Se añadieron indicadores del calendario.
- Estados de mejora, descenso y neutral.
- Panel del día.
- Formulario de agenda.
- Mensajes de error.
- Lista de sesiones.
- Estado vacío.
- Ajustes responsivos.
- Estados focus-visible.
10. Pruebas añadidas
Backend
[backend/tests/test_progress_migration.py](C:/Users/julia/VoxReady/backend/tests/test_progress_migration.py):
- Migración aditiva e idempotente.
- Protección ante duplicados.
- Backfill con sesiones completadas.
- Verificación de índices y FK.
[backend/tests/test_progress_store.py](C:/Users/julia/VoxReady/backend/tests/test_progress_store.py):
- Cero sesiones.
- Una sesión.
- Comparación con sesión anterior.
- Ventana de cinco y total histórico.
- Áreas faltantes como null.
- Validación de lastN.
- Rol requerido.
- Aislamiento usuario/cliente.
- Serialización UTC.
[backend/tests/test_schedule_store.py](C:/Users/julia/VoxReady/backend/tests/test_schedule_store.py):
- Contratos Pydantic.
- Fechas permitidas.
- Escenarios activos y del mismo cliente.
- Consulta de agenda e historial.
- Rangos inválidos.
- Edición.
- Cancelación lógica.
- Inicio atómico.
- Doble clic idempotente.
- Agenda ajena opaca.
- Rollback ante cambio concurrente.
[backend/tests/test_progress_schedule_routes.py](C:/Users/julia/VoxReady/backend/tests/test_progress_schedule_routes.py):
- Delegación de endpoints.
- Confirmación de que no aceptan user_id o client_id desde el request.
[backend/tests/test_master_topics_azure.py (line 194)](C:/Users/julia/VoxReady/backend/tests/test_master_topics_azure.py:194):
- Persistencia real en Azure SQL.
- Crear, listar, editar y cancelar agendas.
- Inicio idempotente.
- Sesión vinculada en español.
- Progreso con dos sesiones.
- Deltas positivos y negativos.
- Aislamiento entre dos voceros.
- Rollback posterior para no conservar los datos de prueba.
Worker
[worker/tests/test_db_service_progress.py](C:/Users/julia/VoxReady/worker/tests/test_db_service_progress.py):
- Orden transaccional.
- Actualización de progreso.
- Cumplimiento de la agenda vinculada.
- Rollback conjunto ante fallo.
[worker/tests/test_db_service_azure.py](C:/Users/julia/VoxReady/worker/tests/test_db_service_azure.py):
- Compilación real del SQL en Azure.
- Finalización transaccional real.
- Comprobación de sesión, informe, progreso y agenda.
- Rollback final para dejar la base limpia.
Frontend
[frontend/tests/progressModel.test.mjs](C:/Users/julia/VoxReady/frontend/tests/progressModel.test.mjs):
- Etiquetas de las áreas.
- Fallback para áreas futuras.
- Fechas locales.
- Rango del calendario.
- Límite de fechas agendables.
La prueba se agregó al target Docker en [frontend/Dockerfile (line 39)](C:/Users/julia/VoxReady/frontend/Dockerfile:39).
11. Integración Docker y verificación
En [worker/Dockerfile](C:/Users/julia/VoxReady/worker/Dockerfile):
- Se separaron targets base, application, test y runtime.
- El target de pruebas instala pytest.
- Ejecuta las pruebas históricas y las nuevas pruebas del worker.
En [docker-compose.azure.yml (line 86)](C:/Users/julia/VoxReady/docker-compose.azure.yml:86):
- Se añadió test-worker.
- Recibe Azure SQL real.
- Activa las pruebas de integración mediante VOXREADY_TEST_AZURE_SQL=1.
En [docker.ps1](C:/Users/julia/VoxReady/docker.ps1):
- test ahora construye y ejecuta:
  - test-api;
  - test-client;
  - test-worker.
Resultado obtenido
- Build Docker del frontend y backend: correcto.
- Next.js production build y TypeScript: correctos.
- .\docker.ps1 verify: conexión y esquema Azure SQL verificados.
- .\docker.ps1 test:
  - 57 pruebas backend aprobadas.
  - 10 pruebas frontend existentes aprobadas.
  - Nueva prueba del modelo de progreso aprobada.
  - 8 pruebas worker aprobadas.
- git diff --check: sin errores de whitespace.
Se observaron únicamente advertencias no bloqueantes:
- Deprecaciones de dependencias Starlette.
- Advertencia de Node por ausencia de "type": "module" al ejecutar directamente archivos TypeScript.
12. QA manual con Dev Auth
Se levantó el proyecto mediante:
.\docker.ps1 up -LocalDevAuth
Se comprobó:
- Login Dev Auth.
- Acceso del vocero a “Mi Progreso”.
- Carga independiente de progreso, agenda y escenarios.
- Estado vacío.
- Mensaje y botón “Elegir escenario”.
- Semana iniciada en lunes.
- Simbología.
- Selección del día.
- Formulario de fecha y escenario.
- Carga de todos los escenarios activos disponibles.
- Creación de una agenda.
- Aparición inmediata del indicador naranja.
- Panel del día.
- Botones Editar, Cancelar e Iniciar práctica.
- Apertura del modo de edición.
La agenda temporal creada durante el QA se canceló mediante archivado lógico; no se eliminó físicamente.
La cuenta usada por Dev Auth no tenía sesiones reales completadas. Por eso el gráfico poblado no pudo inspeccionarse visualmente con esa cuenta; sus cálculos y contratos sí quedaron cubiertos mediante pruebas unitarias y pruebas reales contra Azure SQL.
13. Documentación modificada
- [VoxReady_API_REST.txt](C:/Users/julia/VoxReady/VoxReady_API_REST.txt): contratos de progreso, agenda, edición, cancelación e inicio.
- [backend/scripts/README.md](C:/Users/julia/VoxReady/backend/scripts/README.md): migración, índices y backfill.
- [DOCKER_AZURE.md](C:/Users/julia/VoxReady/DOCKER_AZURE.md): flujo Azure y Dev Auth local.
- [README.md](C:/Users/julia/VoxReady/README.md): arquitectura de autenticación y procesamiento del worker.
14. Inventario completo de archivos de “Mi Progreso”
Nuevos
- backend/progress_store.py
- backend/schedule_store.py
- backend/schemas/schedule.py
- backend/scripts/progress_migration.py
- backend/tests/test_progress_migration.py
- backend/tests/test_progress_schedule_routes.py
- backend/tests/test_progress_store.py
- backend/tests/test_schedule_store.py
- frontend/src/services/progressModel.ts
- frontend/src/services/progressService.ts
- frontend/tests/progressModel.test.mjs
- worker/tests/test_db_service_azure.py
- worker/tests/test_db_service_progress.py
Modificados para integrar la funcionalidad
- VoxReady_API_REST.txt
- backend/Dockerfile
- backend/main.py
- backend/scripts/README.md
- backend/scripts/prepare_azure_database.py
- backend/spokesperson_store.py
- backend/tests/test_master_topics_azure.py
- docker-compose.azure.yml
- docker.ps1
- frontend/Dockerfile
- frontend/src/app/(spokesperson)/spokesperson/page.tsx
- frontend/src/app/globals.css
- frontend/src/components/spokesperson/ProgressView.tsx
- worker/Dockerfile
- worker/services/db_service.py
15. Situación final
La funcionalidad quedó implementada de extremo a extremo:
- Base de datos y backfill.
- Lectura de progreso.
- Agenda completa.
- Creación y vínculo de sesiones.
- Cumplimiento automático desde el worker.
- Frontend conectado.
- Estados vacíos y errores parciales.
- QA y pruebas Docker.
- Aislamiento multi-tenant.
- Sin borrado físico.
- Sin cambios en “Recomendaciones para ti”.