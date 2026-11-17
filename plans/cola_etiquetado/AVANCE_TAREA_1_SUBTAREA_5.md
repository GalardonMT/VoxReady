# Avance Tarea 1 — Subtarea 5

## 1. Resultado

- Estado: **Hecho** para la subtarea 5.
- Tarea 1 global: **Parcial**; subtareas 6 a 10 no iniciadas.
- Gate G2: pendiente.
- Rama: `feat/cola-de-etiquetado`.
- No se ejecutó el comando contra Azure SQL ni se modificaron datos.

> Continuidad al 30 de octubre de 2026: las subtareas 6 a 10 ya fueron implementadas. El estado actual, los nuevos recuentos y la escritura protegida están documentados en `AVANCE_TAREA_1_SUBTAREAS_7_10.md`; este archivo conserva la evidencia del checkpoint 1.5.

## 2. Comando creado

Archivo: `backend/scripts/reconcile_labeling_cases.py`.

Uso previsto desde la raíz del repositorio:

```powershell
python backend\scripts\reconcile_labeling_cases.py --dry-run --batch-size 100 --limit 1000
```

Parámetros:

- `--dry-run`: obligatorio en esta etapa; abre únicamente consultas y termina con `rollback`.
- `--batch-size`: entre 1 y 1000; valor por defecto 100.
- `--limit`: máximo total de informes a inspeccionar, entre 1 y 100000; es opcional.

El resumen usa JSON y no contiene IDs, nombres, correos, rutas Blob, transcripciones ni comentarios.

## 3. Comportamiento implementado

1. Valida argumentos antes de importar `pyodbc` o abrir conexión.
2. Falla si no existe `dbo.labeling_case`, porque la reconciliación no puede preceder al esquema.
3. Cuenta informes actuales de sesiones completadas y no eliminadas, casos existentes e informes todavía no materializados.
4. Recorre solo informes no materializados mediante paginación por `(finished_at, report_id)`.
5. Aplica el límite global sin cargar todo el conjunto en memoria.
6. Informa lotes, filas inspeccionadas y filas pendientes de evaluar por las reglas futuras.
7. Ejecuta `rollback` y cierra la conexión aun en errores.
8. No está importado ni llamado por `main.py`, el worker o `prepare_azure_database.py`.

## 4. Bloqueo intencional de escritura

Ejecutar el comando sin `--dry-run` termina con código 2 antes de importar el driver o conectarse. Esta restricción evita crear casos con `source_status` o tratamiento de anomalías inventados.

El modo de aplicación solo podrá habilitarse cuando se implemente:

- subtarea 7: exclusión y registro explícito de relaciones ambiguas o inconsistentes.

La consulta actual excluye sesiones eliminadas como límite de seguridad, pero todavía no produce el inventario de anomalías exigido por la subtarea 7.

## 5. Resumen JSON

Campos principales:

- `completedCurrentReports`;
- `existingCases`;
- `unmaterializedReports`;
- `batches` y `scanned`;
- `pendingRuleEvaluation`;
- `classificationCounts` y `classificationErrors` tras completar la subtarea 6;
- `created`, fijado en 0;
- `writeBlocked`, fijado en `true`;
- `nextRequiredSubtasks`, actualmente fijado en `[7]`.

`unmaterializedReports` representa descubrimiento, no elegibilidad. Ninguna fila se denomina elegible hasta aplicar las reglas de integridad pendientes.

## 6. Verificación ejecutada

- Compilación Python del comando: correcta.
- `--help`: correcto sin requerir `pyodbc`.
- Ejecución sin `--dry-run`: código 2 antes de conectar.
- `--batch-size 0`: código 2 por validación.
- Cursor simulado con `batch-size=2` y `limit=5`: 3 lotes, 5 filas inspeccionadas y 0 creadas.
- Búsqueda de referencias: el comando no forma parte del arranque ni de la preparación del esquema.
- `git diff --check`: correcto.

## 7. Límites

- No se ejecutó un dry-run real porque el esquema aún no fue aplicado y el Python global no contiene `pyodbc`.
- No estima todavía duración ni volumen operativo: corresponde a la subtarea 8.
- La clasificación quedó implementada en la subtarea 6; el registro de anomalías corresponde a la subtarea 7.
- No verifica estructura ni recuentos contra `--verify-only`: corresponde a la subtarea 9.
- No implementa pruebas persistentes de repetición o rollback: corresponde a la subtarea 10.
