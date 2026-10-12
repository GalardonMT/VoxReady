# Fase 1: temas maestros y escenarios de ejemplo

El script `seed_master_topics.py` implementa las secciones 4.2, 5 y 8 del
plan técnico. Los textos completos en español están en
`master_topics_seed.json`; los códigos persistidos están en inglés técnico.

## Ejecución habitual desde Docker

Desde la raíz, con `.env` configurado:

```powershell
.\docker.ps1 up
.\docker.ps1 verify
.\docker.ps1 test
```

Las migraciones de esquema se ejecutan automáticamente antes de iniciar la API.
El seed se invoca explícitamente con `./docker.ps1 seed`. Los tres ejemplos
ya están cargados en Azure SQL. El flujo habitual no requiere entornos virtuales.
Consulta `DOCKER_AZURE.md` en la raíz.

## Comandos individuales dentro del contenedor

La imagen del backend incluye Python, las dependencias y ODBC 18. Compose
inyecta `SQL_CONNECTION_STRING` desde `.env` en la raíz. No se imprimen credenciales.

```powershell
docker compose run --rm --no-deps init python scripts/seed_master_topics.py --dry-run
docker compose run --rm --no-deps init python scripts/seed_master_topics.py
docker compose run --rm --no-deps init python scripts/seed_master_topics.py --verify-only
```

`--dry-run` valida únicamente los archivos locales. No conecta a Azure SQL ni
prueba la compatibilidad del esquema real. `--verify-only` consulta Azure SQL sin
crear tablas ni insertar registros. Ambos modos son mutuamente excluyentes.

## Garantías y resultado esperado

- Crea `dbo.scenario_question` con PK, dos FK sin borrado en cascada, las dos
  restricciones únicas y el índice `(scenario_id, sequence_no)` del plan.
- Inserta 3 temas globales (`client_id = NULL`), 6 mensajes, 6 líneas rojas,
  24 preguntas maestras, 3 escenarios y 24 asignaciones ordenadas del 1 al 8.
- Asigna los escenarios al cliente activo
  `7D8C0575-196C-40D1-AD7C-08AA2843B4C3`. No crea ni modifica clientes.
- Verifica contenido, estados, pertenencia, códigos técnicos y orden antes del
  commit. Las altas y el DDL participan en una sola transacción; un error
  revierte los cambios. Un bloqueo de aplicación serializa ejecuciones concurrentes.
- Usa UUID deterministas: repetir una ejecución correcta inserta cero registros.
- No borra, archiva, sobrescribe ni reactiva datos existentes. La indicación de
  “limpiar” de la sección 8 se subordina a la política explícita de cero
  eliminación y a la regla de cero regresión. Otros datos de prueba se conservan.
- Si alguien edita o archiva los registros de esta semilla posteriormente,
  la verificación estricta inicial puede fallar. El script conserva esas ediciones
  y revierte cualquier alta de esa ejecución; no debe usarse para restaurar datos.
- Tolera la presencia o ausencia de `question.sort_order`, pues el inventario
  del plan no incluye esa columna. Si existe, la puebla. El orden del escenario
  siempre se guarda en `scenario_question.sequence_no`.
- Si `topic.client_id` o `question.client_id` no admiten `NULL`, migra su
  nulabilidad en la misma transacción para permitir los temas y preguntas
  globales del plan. Conserva las filas y claves foráneas existentes.

En una primera ejecución correcta debe aparecer:

```text
Azure SQL: estructura, contenido, cliente y orden de preguntas verificados.
Registros NUEVOS: topic=3, topic_key_message=6, topic_red_line=6, question=24, scenario=3, scenario_question=24
```

El proceso retorna `0` al verificar correctamente y `1` ante un error.
No avanzar a la Fase 2 hasta que la ejecución real y `--verify-only` terminen
correctamente. Las pruebas locales no certifican Azure SQL.

## Verificación automatizada

```powershell
.\docker.ps1 test
```

El perfil Docker comprueba los endpoints realmente contra Azure SQL y verifica
los contratos existentes de autenticación y análisis. No crea una base local.
Las pruebas unitarias históricas del seed usan un adaptador en memoria; no son
la base de ejecución ni la validación de persistencia del despliegue.

## Estado de verificación en este entorno

El 7 de octubre de 2026 se instaló Microsoft ODBC Driver 18 y se ejecutó
correctamente el seed en `sqldb-voxready`. La primera ejecución insertó
3 temas, 6 mensajes, 6 líneas rojas, 24 preguntas, 3 escenarios y 24 asignaciones.
`--verify-only` pasó y una segunda ejecución insertó cero registros.
Las 11 pruebas locales pasan. No se borraron registros existentes.

## Migraciones de las fases siguientes

Después del seed, antes de ejecutar el backend actualizado:

```powershell
docker compose run --rm --no-deps init python scripts/prepare_azure_database.py
```

Ambas migraciones son aditivas e idempotentes. La primera agrega el orden del
banco y estados para archivar mensajes, líneas rojas y asignaciones sin borrar
filas. Las relaciones retiradas conservan posiciones negativas únicas; las
activas usan la secuencia positiva configurada.

La segunda conserva la PK UUID de `session` y sus claves foráneas. Agrega un
identificador público compatible con el frontend/worker y la clave de
idempotencia por usuario. Usa `session_question`, ya existente, para conservar
el orden y texto de cada entrevista iniciada. La rúbrica publicada se asigna
al crear la sesión. El identificador público sigue `session-{scenarioId}-{epoch}`;
si coincide con otra sesión del mismo segundo, recibe un sufijo único.

Las tres migraciones ya se aplicaron y verificaron contra Azure SQL en este
entorno. El detalle de validación y los límites de E2E están en
`IMPLEMENTACION_GESTION_TEMAS_ESCENARIOS.md`, en la raíz del proyecto.
