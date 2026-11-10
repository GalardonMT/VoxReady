# Cierre de Tarea 3 — store y reglas de dominio

## Estado

`Hecho` en código y pruebas locales. Las once subtareas fueron implementadas sin añadir rutas HTTP, aplicar DDL, escribir datos compartidos, ejecutar reconciliación, desplegar, hacer commit o push.

## Resultado por subtarea

1. Se creó `backend/labeling_store.py` sin dependencia de FastAPI. El llamador conserva la conexión y la transacción.
2. `list_cases` separa `pending` y `reviewed`, valida el estado, limita estrictamente a diez y usa orden estable por finalización o última revisión.
3. `get_case_detail` normaliza el snapshot en cuatro áreas y grupos de métricas, entrega empresa y códigos seudónimos, y excluye correo, nombre del vocero, ruta interna del blob y tokens.
4. La reserva admite adquisición, renovación, liberación, expiración y recuperación. Distingue pestañas por token hash y generación; una pestaña antigua no puede renovar ni liberar una adquisición posterior.
5. `submit_review` crea cabecera y correcciones inmutables dentro de la transacción del llamador. Valida fuente, lease, revisión de contenido, revisión base, áreas completas, métricas disponibles, rangos, precisión y comentarios obligatorios.
6. `quality_summary` calcula evidencia por área, métrica y categoría.
7. Las lecturas de lista, detalle, historial y agregados no usan hints de escritura. `UPDLOCK`/`HOLDLOCK` quedan restringidos a lease y confirmación de revisión.
8. Se registran `labeling_case_claimed`, `labeling_case_released`, `labeling_case_reviewed` y `labeling_recording_accessed` mediante una lista blanca de detalles escalares. No se auditan tokens, SAS, comentarios, nombres, correos ni transcripciones.
9. `lease_generation` solo cambia al adquirir una reserva nueva; heartbeats no cambian `content_revision`. Confirmar incrementa `content_revision`. El submit es idempotente por caso y clave, hash canónico y mismo experto.
10. Los agregados de áreas se agrupan por `rubric_version_id + area_key`; las métricas por `metric_key + mapping_version + unit`. Las categorías solo cuentan evidencia.
11. Cada agregado incluye muestra, medias IA/humana, diferencia media firmada, error absoluto medio y conteos al alza, a la baja, sin cambio y con cambio.

## Invariantes cubiertas

- Límite y orden estable de pendientes y revisados.
- Totales coherentes y filtro de sesiones no eliminadas.
- Estado de lease `available`, `expired`, propio, ajeno o no adquirible.
- Claim/claim entre expertos y entre dos pestañas del mismo experto.
- Renovación seguida de submit.
- Release repetido, reclaim y generación obsoleta.
- Reintento idempotente después de perder la respuesta.
- Conflicto por reutilizar una clave con otro payload o experto.
- Segunda revisión que sustituye la vigencia sin sobrescribir el historial.
- Falla inyectada antes de resolver el caso; el store propaga el error y no confirma ni revierte por su cuenta.
- Ausencia de PII, secretos de lease y rutas internas en detalle y auditoría.

## Verificación local

- `backend/tests/test_labeling_store.py`: 11 pruebas aprobadas.
- Backend focalizado de store, cola y migración: 22 pruebas aprobadas.
- Suite worker: 15 pruebas aprobadas y 2 omitidas por requerir Azure SQL configurado.
- Compilación Python del store y sus pruebas: correcta.
- La medición con `pytest-cov` no está disponible en el Python global porque el plugin no está instalado; no se instaló una dependencia fuera del entorno reproducible del proyecto.
- La suite backend completa no recolecta en el Python global por dependencias ausentes (`PyJWT`, Azure SDK y `pyodbc`). Esto es una limitación del entorno local, no una prueba aprobada; debe repetirse dentro de la imagen backend.

## Seguridad y operación

- Todas las consultas usan parámetros; los fragmentos dinámicos provienen de valores internos previamente validados.
- Los tokens se generan con `secrets`, se persisten solo como SHA-256 y se comparan con `hmac.compare_digest`.
- El store no contiene `commit`, `rollback`, `DELETE` ni `DROP`; el context manager SQL existente decide confirmación o rollback.
- No se exponen algoritmos de autorización mediante seudónimos: los códigos son solo presentación y nunca se usan para permisos.
- La validación concurrente real con dos conexiones Azure SQL permanece como gate de integración de Tarea 9; las pruebas locales usan cursores con estado controlado.
