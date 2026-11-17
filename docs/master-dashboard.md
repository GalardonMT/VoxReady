# Panel de inicio del configurador maestro

`GET /api/master/dashboard` y `/v1/api/master/dashboard` usan la conexión Azure
existente (`main.SQL_CONN_STR` → `master_topics.database`). No ejecutan DDL, seeds
ni escrituras. Autenticación: `verify_token`; autorización: usuario activo de
`app_user`, resuelto con `resolve_user(..., master=True)`. Rol y cliente enviados
por el navegador no determinan el acceso. Los errores conservan el contrato
FastAPI `detail` de los endpoints maestros de métricas/clientes (401/403/503).

## Reglas confirmadas durante el ticket

- Clientes: `status='active' AND is_deleted=0`.
- Sesiones: completadas y no eliminadas, por `finished_at`, últimos 7 días
  comparados con los 7 anteriores, en UTC. Intervalos semiabiertos `[from,to)`.
  Se utiliza el reloj UTC de Azure SQL para ambos períodos.
- Con período anterior vacío, la variación es `null` y `changeStatus` vale
  `no_previous_sessions`, incluso si ambos conteos son cero. No se presenta un
  porcentaje sin denominador.
- Pendientes: el mismo `count_cases(status='pending')` utilizado por la cola;
  se excluyen las sesiones eliminadas, sin limitar el total al tamaño de página.
- Versión: la misma `metrics_store.latest_published` del editor de métricas.
  Un esquema/configuración incompletos son un error, no ausencia de publicación.
- Distribución: todo el histórico de sesiones completadas no eliminadas, con un
  único reporte vigente. Se reutiliza el CTE de progreso, con desempate por
  `generated_at DESC,id DESC`. El estado actual del cliente no elimina su historia,
  como en las consultas existentes de progreso y cola.

## Representación estadística

Se conservan los seis intervalos del panel: `[0,50)`, `[50,60)`, `[60,70)`,
`[70,80)`, `[80,90)` y `[90,100]`. Media y desviación estándar poblacional se
calculan en SQL sobre los mismos puntajes no nulos, sin redondear antes de agregar.
Se devuelven todos los intervalos empatados como moda. Sin puntajes: conteos cero,
estadísticas `null`, sin moda. Un puntaje fuera de rango produce 503.

## Definiciones pendientes

No hay una fórmula verificable de acuerdo IA-humano ni kappa. El contrato devuelve
`quality.status='definition_required'` y ambos valores `null`; la interfaz lo
explica en ES/EN/PT. Falta acordar categorías/tolerancias, unidad de comparación,
población y tratamiento de versiones. `gov.agreement_target` es una meta y nunca
se utiliza como medición. No se dispone de wireframe para certificar coincidencia
visual. El editor de rúbricas y la alimentación operativa de la cola permanecen
fuera del alcance de este cambio.

Las pruebas unitarias usan dobles de cursor, sin bases alternativas ni escrituras
en Azure. La prueba Azure de solo lectura es optativa y se habilita explícitamente
con `VOXREADY_DASHBOARD_READONLY_AZURE=1`; nunca crea fixtures persistidos.

## Verificación

- Backend unitario: `python -m pytest tests/test_master_dashboard.py
  tests/test_labeling_store.py tests/test_metrics_editor.py -q -p no:cacheprovider`.
- Azure, con el entorno existente cargado y la habilitación explícita indicada:
  `python -m pytest tests/test_master_dashboard_azure_readonly.py -q -p no:cacheprovider`.
  Se comprueban agregados contra consultas independientes y roles reales de
  `app_user`. El arnés sustituye únicamente la identidad autenticada; no certifica
  un inicio de sesión Microsoft Entra. Las expresiones SQL `VALUES` usadas para
  límites y duplicados son entradas locales de un SELECT, sin registros insertados.
- Frontend: las pruebas `masterDashboardModel.test.mjs` y
  `masterDashboardView.test.mjs` entran en el comando habitual `node
  --experimental-strip-types --test tests/*.test.mjs`. La segunda renderiza el
  TSX real con estados controlados; no es una prueba visual de navegador.
- Compilación: `npm run build` desde `frontend`, con sus dependencias declaradas.
