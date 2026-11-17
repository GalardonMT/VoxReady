# Tarea 1 — cierre de subtareas 7 a 10

Fecha: 30 de octubre de 2026
Rama: `feat/cola-de-etiquetado`
Estado de implementación: completo
Aplicación persistente: no ejecutada

## 1. Alcance cerrado

Se completaron exclusivamente las subtareas 7 a 10 de la Tarea 1:

1. exclusión y registro de anomalías históricas;
2. estimación de volumen y duración previa al backfill;
3. verificación estructural, recuentos e integridad;
4. pruebas de doble ejecución, rollback y backfill repetido.

No se aplicó DDL, no se ejecutó el backfill sobre Azure SQL y no se inició la
Tarea 2.

## 2. Anomalías y exclusión segura

`backend/scripts/reconcile_labeling_cases.py` inspecciona una fila por sesión
completada, incluidas las eliminadas, y registra códigos técnicos sin nombres,
correos, comentarios, transcripciones ni URLs SAS.

Las siguientes condiciones excluyen la fila sin corregirla:

- `session_deleted`;
- `current_report_missing` o `current_report_multiple`;
- `report_job_missing` o `report_job_orphan`;
- `job_session_mismatch` o `job_rubric_mismatch`;
- `fusion_missing`, `fusion_multiple` o `fusion_json_invalid`;
- `fusion_report_id_missing` o `fusion_report_id_mismatch`;
- `classification_input_invalid`, que cubre áreas o reglas incompletas,
  duplicadas, fuera de rango o no válidas.

El JSON final incluye `anomalyCounts`, `anomalyRows` y hasta cien detalles con
solo `sessionId`, `reportId` y códigos. `anomalyDetailsTruncated=true` indica que
se omitieron detalles por volumen; los recuentos permanecen completos.

## 3. Backfill y evidencia histórica

El modo escritura crea únicamente casos cuya relación
`session -> report -> analysis_job -> fusion` sea inequívoca, cuyo `fusion`
identifique el mismo informe y cuya clasificación sea válida. La inserción
vuelve a comprobar estas relaciones y usa `NOT EXISTS` con
`UPDLOCK,HOLDLOCK`, además del índice único por `report_id`.

Los casos históricos se crean deliberadamente con:

- `source_status='ambiguous'`;
- `sourceIssues=['recording:unsealed_historical']`;
- sin ruta, ETag, hash ni versión de grabación inventados;
- snapshot v1 con el puntaje global y las cuatro áreas observadas;
- métricas vacías hasta que Tarea 2 construya la evidencia exacta.

Por lo tanto, estos casos no son reclamables ni confirmables hasta que Tarea 2
selle el medio y complete el snapshot. Esta decisión preserva el contrato de
evidencia y evita asociar un blob por el patrón de su nombre.

## 4. Modos de ejecución

Preflight completo, solo lectura:

```powershell
python scripts\reconcile_labeling_cases.py --dry-run
```

Preflight acotado para diagnóstico:

```powershell
python scripts\reconcile_labeling_cases.py --dry-run --batch-size 100 --limit 1000
```

El modo escritura existe, pero requiere una confirmación literal y no fue
ejecutado en este avance:

```powershell
python scripts\reconcile_labeling_cases.py --apply --confirm-write APPLY_LABELING_BACKFILL
```

Antes de usarlo sobre una base compartida se exige un dry-run completo, revisión
de anomalías, aplicación autorizada del esquema y una autorización separada del
usuario.

## 5. Estimación previa

El resumen entrega:

- `eligibleCases`;
- `lowerBoundSeconds` y `upperBoundSeconds`;
- `completeInventory`;
- la base explícita de la estimación.

El rango usa 20–100 ms por inserción y 50–250 ms por lote. Es una estimación
operativa conservadora, no una medición de Azure; excluye migración, espera por
locks y contención externa. Solo `completeInventory=true`, obtenido sin
`--limit` o al recorrer todo el inventario, habilita una decisión informada.

## 6. Verificación estructural

`backend/labeling_migration.py` expone `verify(cursor, error_type)` y comprueba
sin escrituras:

- cuatro tablas y sus columnas requeridas;
- catorce índices, incluidos los tres índices padre y el índice filtrado de
  revisión vigente;
- catorce llaves foráneas activas y confiables;
- veinte restricciones `CHECK` activas y confiables;
- ausencia de casos duplicados por informe;
- ausencia de múltiples revisiones vigentes por caso;
- coherencia entre cada caso y su informe exacto.

`prepare_azure_database.py --verify-only` llama esta verificación junto con las
existentes. En una base donde el esquema aún no fue aplicado, debe fallar de
forma explícita; no crea tablas en modo verificación.

## 7. Controles transaccionales

El modo `--apply`:

- inicia una transacción con `XACT_ABORT ON`;
- adquiere el lock compartido del esquema y un `sp_getapplock` exclusivo para
  el backfill, ambos propiedad de la transacción;
- ejecuta la verificación estructural dentro de esa misma transacción antes de
  inspeccionar o insertar;
- verifica el código de retorno y aborta si el lock no fue concedido;
- confirma solo al finalizar todo el recorrido;
- ejecuta rollback ante cualquier error;
- nunca es llamado por el arranque de la aplicación ni por el preparador.

## 8. Pruebas ejecutadas

```text
python -m pytest tests\test_labeling_migration_and_reconciliation.py -q
8 passed in 0.05s

python -m pytest tests\test_labeling_migration_and_reconciliation.py tests\test_microlesson_assignment_migration.py -q
11 passed in 0.05s
```

También pasó `py_compile` para migración, clasificación, reconciliación y
preparador. Se verificó que `--apply` sin la frase exacta finaliza con código 2
antes de conectarse.

La suite backend completa no llegó a ejecutar tests: la recolección terminó con
diez errores por dependencias ausentes en el Python global (`PyJWT`,
`azure-storage-blob` y `pyodbc`). Esta limitación es del entorno actual y no se
presenta como un resultado aprobado. Las suites focalizadas anteriores sí se
recolectaron y ejecutaron completamente.

Las pruebas demuestran localmente:

- DDL protegido e invocable dos veces sin DML, `DROP` o commit interno;
- verificación estructural positiva y rechazo de un índice ausente;
- códigos de anomalías y exclusión;
- dry-run sin inserciones;
- una primera creación y una segunda ejecución sin duplicado;
- rollback sin commit ante error;
- integración de `verify_labeling` en `--verify-only`.

## 9. Evidencia pendiente y gate

Docker Desktop no tenía disponible el engine Linux al cierre. Tampoco se aplicó
el esquema en Azure SQL. Por ello:

- las subtareas 1 a 10 están implementadas y probadas con cursores simulados;
- Tarea 1 queda completa en código;
- G2 permanece pendiente de una prueba real sobre SQL local/efímero;
- G7 y cualquier aplicación persistente permanecen fuera de alcance.

No se confunden los once tests locales con evidencia de ejecución en Docker o
Azure SQL.
