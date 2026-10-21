# Implementación del Editor de métricas

Fecha de ejecución: 21 de octubre de 2026. Alcance: configuración maestra VISUM de VoxReady.

## Resultado

Se incorporó **Editor de métricas** como pestaña de `master_config`. La pantalla
consulta el catálogo y los intervalos desde Azure SQL, organiza las 16 métricas
en cinco categorías y permite crear un borrador, modificar únicamente los
límites, guardarlo, revisar las diferencias y publicar una nueva versión de la
rúbrica. También permite descartar el borrador. Los metadatos de cada métrica
(nombre, explicación, unidad, mínimo, máximo y paso) permanecen fijos.

La publicación deja lista la configuración para una integración posterior. **El
worker no se modificó y todavía no consume estos nuevos intervalos**. Esta
entrega tampoco despliega el frontend ni el backend; el despliegue de esas
aplicaciones es un paso separado.

## Ubicación y funcionamiento

| Capa | Archivos principales | Función |
| --- | --- | --- |
| Pantalla maestra | `frontend/src/app/(master)/master/page.tsx`, `frontend/src/components/master/MetricsEditorView.tsx`, `MetricsEditorView.module.css` | Añade la pestaña y presenta bandas suaves por categoría, controles numéricos y marcadores movibles con teclado o puntero. |
| Cliente y modelo | `frontend/src/services/metricsService.ts`, `metricsModel.ts` | Consulta la API, valida los límites y calcula las diferencias entre versiones. |
| Panel maestro | `frontend/src/components/master/MasterDashboard.tsx` | Muestra la última versión publicada obtenida de la API, con estados de carga y error. |
| API | `backend/main.py`, `backend/metrics_store.py` | Restringe todas las operaciones a `master_config`, controla revisiones y publica transaccionalmente. |
| Catálogo y esquema | `backend/metrics_catalog.py`, `backend/metrics_migration.py`, `backend/scripts/prepare_azure_database.py` | Define los valores iniciales aprobados, crea las tablas y verifica su contenido. |
| Empaquetado y pruebas | `backend/Dockerfile`, `backend/tests/test_metrics_editor.py`, `frontend/tests/metricsModel.test.mjs` | Incluye los módulos y ejecuta comprobaciones de contratos y límites. |

La interfaz muestra las categorías **Voz (6), Video (3), Contenido (1), Empatía
(1) y Gobernanza (5)**. La edición de voz corresponde exclusivamente a español.
Los colores indican zonas críticas, aceptables y óptimas. Los marcadores se
ajustan al paso de cada métrica y no pueden cruzar los límites adyacentes; los
campos numéricos ofrecen una alternativa precisa. Antes de publicar, la pantalla
exige guardar el borrador y muestra cada límite que cambiará.

## Las 16 métricas iniciales

Las claves, los metadatos fijos y los valores iniciales están en
`backend/metrics_catalog.py`. La tabla siguiente resume los límites editables
que se cargaron en la primera versión. Los nombres de los campos son los del
contrato API y se guardan como JSON en SQL.

| Categoría | Métrica (`key`) | Límites iniciales |
| --- | --- | --- |
| Voz | `voice.wpm` | `warningLow=100`, `optimalLow=120`, `optimalHigh=150`, `warningHigh=170` WPM |
| Voz | `voice.filler_density` | `optimalMax=1.5`, `warningMax=3` % |
| Voz | `voice.prolonged_pause` | `optimalMax=1`, `warningMax=3` pausas |
| Voz | `voice.hesitation_pause` | `optimalMax=2`, `warningMax=5` pausas; crítico desde 6 |
| Voz | `voice.phonation_ratio` | `criticalBelow=45`, `optimalLow=60`, `optimalHigh=85` % |
| Voz | `voice.asr_confidence` | `warningLow=70`, `optimalLow=85` % |
| Video | `vision.eye_contact` | `warningLow=50`, `optimalLow=75` % |
| Video | `vision.posture` | `warningLow=50`, `optimalLow=75` % |
| Video | `vision.sway_tolerance` | `optimalMax=0.015`, `warningMax=0.035` std |
| Contenido | `content.red_line_cap` | `cap=20` puntos |
| Empatía | `empathy.victim_recog` | `warningLevel=3`, `optimalLevel=4` (niveles) |
| Gobernanza | `gov.confidence_min` | `warningLow=70`, `optimalLow=85` % |
| Gobernanza | `gov.borderline_delta` | `halfWidth=2` puntos respecto de 50; observación 3 puntos adicionales |
| Gobernanza | `gov.disparity_delta` | `normalBelow=35`, `auditAt=50` puntos |
| Gobernanza | `gov.random_sample` | `rate=10` % |
| Gobernanza | `gov.agreement_target` | `warningLow=0.70`, `optimalLow=0.85` (ratio) |

## Persistencia y versiones

La migración aditiva crea cuatro tablas:

- `rubric_metric_definition`: catálogo de 16 métricas y metadatos fijos.
- `rubric_metric_value`: límites de cada métrica por `rubric_version_id` publicado.
- `rubric_metric_draft`: único borrador activo, versión origen y número de revisión.
- `rubric_metric_draft_value`: límites editables del borrador.

En la primera ejecución, la migración copia la última `rubric_version`
publicada y sus filas de `rubric_area` a nuevos identificadores, conserva sus
pesos y áreas, e inserta los 16 intervalos iniciales en la nueva versión.
No altera las versiones ya publicadas ni las sesiones anteriores. Los nuevos
borradores parten de la última versión publicada. Guardar incrementa la
revisión; publicar comprueba que tanto la revisión como la versión origen
sigan vigentes, crea otra versión publicada y elimina solo el borrador. Descartar
elimina únicamente las filas del borrador. Estas operaciones se realizan dentro
de una transacción y la publicación usa un bloqueo de aplicación en SQL.

La validación del backend exige las 16 claves exactas, los campos de límite
correspondientes, valores finitos dentro del mínimo y máximo, múltiplos del
paso y el orden ascendente cuando hay más de un corte. Las modificaciones
concurrentes devuelven `409` para que la interfaz recargue el estado reciente.

## Contrato API

Todas las rutas requieren token válido y rol `master_config` comprobado contra
la base de datos. Tienen la variante `/v1` que usa el frontend y un alias sin
ese prefijo.

| Método y ruta `/v1` | Resultado |
| --- | --- |
| `GET /api/master/metrics` | Versión publicada y borrador activo, con catálogo y límites. |
| `GET /api/master/metrics/latest` | Última versión publicada y sus 16 límites. |
| `POST /api/master/metrics/draft` | Crea el borrador desde la última publicación (`201`). |
| `PUT /api/master/metrics/draft/{id}` | Guarda `{revision, metrics:[{key, thresholds}]}` y devuelve la nueva revisión. |
| `POST /api/master/metrics/draft/{id}/publish` | Publica `{revision}` y devuelve la nueva versión. |
| `DELETE /api/master/metrics/draft/{id}` | Descarta `{revision}` y devuelve `204`. |

## Migración ejecutada en Azure SQL

Destino autorizado: servidor `sql-voxready-st`, base `sqldb-voxready`.
Se ejecutó `backend/scripts/prepare_azure_database.py` el 21 de octubre de
2026 con ODBC Driver 18. Se utilizó un entorno Python temporal porque Docker
Desktop no tenía el motor Linux disponible. El script terminó con código `0`;
posteriormente `--verify-only` terminó también con código `0`.

La consulta independiente de solo lectura confirmó:

| Comprobación | Resultado |
| --- | --- |
| Versión inicial nueva | `M261021161306-dbd7c`, UUID `4468E0C7-776C-4497-8DBF-68B5D31217BC`, estado `published` |
| Métricas de esa versión | 16 |
| Definiciones de catálogo | 16 |
| Áreas copiadas | 4 |
| Borradores activos | 0 |
| Versión anterior conservada | `v0.4`, UUID `B8AB7DE6-C3A8-4F0F-A9CF-5D3C33484134`, con 4 áreas |

La versión anterior tiene cero filas en `rubric_metric_value` porque precede a
este modelo; sus datos históricos permanecen sin modificar.

## Verificación y límites

- Backend local: **86 pruebas aprobadas, 11 pruebas de Azure omitidas** antes
  de ejecutar la migración. Las pruebas nuevas cubren catálogo, validación,
  autorización y operaciones de versión. El comando del contenedor de pruebas
  ahora incluye `test_metrics_editor.py`.
- Frontend: **3 pruebas del modelo y 2 pruebas de rutas aprobadas**;
  TypeScript y compilación de producción correctos. ESLint: cero errores y
  una advertencia preexistente por `<img>` en la página maestra.
- Azure SQL: migración, verificación del script y consulta independiente
  completadas. No se ejecutó el perfil de pruebas Docker contra Azure porque
  su motor Linux no estaba disponible.
- La inspección visual en navegador local quedó pendiente por falta de
  conectividad entre el navegador de pruebas y el servidor local.
- El frontend y el backend aún deben desplegarse para que la pestaña sea
  accesible en el entorno compartido. El consumo de los intervalos por el
  worker corresponde a una integración posterior.

No se guardaron credenciales, cadenas de conexión ni datos personales en este
documento.
