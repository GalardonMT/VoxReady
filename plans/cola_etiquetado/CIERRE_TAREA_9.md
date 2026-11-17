# Cierre de Tarea 9 — Gate local y preparación de activación

Fecha: 2026-11-10
Rama: `feat/cola-de-etiquetado`

## Resultado

La implementación, documentación, rollback y revisión de seguridad quedan preparados localmente. No se declara el gate de datos reales porque la migración Azure requiere autorización expresa y el entorno local no pudo acceder a Docker ni ejecutar ODBC.

## Trabajo cerrado

1. Se integró la migración de etiquetado en `prepare_azure_database.py`: migración solo fuera de `--verify-only` y verificación siempre.
2. La subida de grabación quedó `create-only`; una sesión cerrada recibe `409`.
3. La finalización bloquea la sesión, reutiliza el job activo y falla cerrada con `503` si no puede preparar SQL.
4. Service Bus delega al mismo pipeline canónico que HTTP; el Azure Function heredado queda deshabilitado.
5. Se añadieron flags explícitos de runtime, API y UI, más orden de activación y rollback sin borrar datos.
6. La revisión ECC no encontró exposición de secretos, SQL concatenado, HTML peligroso ni datos sensibles en la superficie de cola.
7. El audit detectó una vulnerabilidad crítica en Next.js y dos altas transitivas. Se actualizó Next.js a `16.4.6` y dependencias; el audit productivo final informa cero vulnerabilidades.

## Evidencia final

- Frontend: `40 passed`; TypeScript y build correctos.
- Backend Docker: `133 passed`, `2 skipped`.
- Worker Docker: `18 passed`.
- Pruebas transaccionales Azure SQL: aprobadas y revertidas al finalizar.
- Migración: aplicada y verificada en `sqldb-voxready`.
- Backfill: 7 casos creados; 17 entrevistas ambiguas o incompletas excluidas.
- Segunda simulación: `alreadyMaterialized=7`, `created=0`.
- Dependencias productivas: cero vulnerabilidades conocidas en `npm audit`.

## Dictamen

El gate técnico y de datos quedó aprobado para entregar la rama. El esquema
legacy se preservó con sufijo `_legacy_v1`; la demo local temporal fue retirada.
No se desplegó la aplicación en Azure.
