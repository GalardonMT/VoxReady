# Cierre Tarea 6 — Lease, calibración y revisiones inmutables

Estado: **completada localmente** en `feat/cola-de-etiquetado`.

## Entregables

1. La selección de un caso pendiente obtiene su detalle y adquiere un lease de 20 minutos. Cambiar de caso o desmontar la pantalla libera la reserva en modalidad best-effort.
2. La renovación se intenta únicamente cuando la pestaña está visible, hubo actividad durante los últimos cinco minutos y faltan menos de cinco minutos para expirar. Una renovación fallida conserva el formulario y cambia a modo lectura.
3. Los conflictos `409` no eliminan valores ni comentarios. La pantalla permite copiar un borrador sin token o descartar y recargar el estado vigente.
4. Las cuatro áreas editables de la rúbrica se renderizan desde el detalle del caso. La clave canónica es `voice`, no el alias histórico `tone`.
5. Las métricas observadas disponibles se agrupan por categoría. Gobernanza, configuraciones, agregados y métricas `unknown`/`not_emitted` no se muestran como campos editables.
6. El modelo valida rangos, enteros, precisión, observación general y comentario obligatorio para cada cambio respecto de la propuesta IA.
7. La confirmación envía una sola solicitud con lease, generación, revisión de contenido, clave de idempotencia y revisión sustituida. La clave se conserva tras un error de red y cambia cuando el experto edita el borrador.
8. Al confirmar, el caso pasa a Revisadas y el formulario queda bloqueado. Las revisiones confirmadas se muestran en modo lectura y el historial permanece visible.
9. `Nueva revisión` adquiere una reserva explícita sobre un caso revisado, usa `supersedesReviewId` y crea una sucesora sin modificar ni eliminar la revisión anterior.
10. El endpoint de lease habilita `allow_reviewed=True` únicamente en la operación explícita de reserva; las reglas transaccionales continúan en `labeling_store`.

## Archivos principales

- `frontend/src/components/master/LabelingCaseWorkspace.tsx`
- `frontend/src/services/labelingReviewModel.ts`
- `frontend/src/services/labelingService.ts`
- `frontend/src/types/api.ts`
- `frontend/tests/labelingReviewModel.test.mjs`
- `backend/labeling_api.py`
- `backend/tests/test_labeling_contracts.py`

## Verificación

```text
Frontend completo: 32 pruebas aprobadas
Modelo de etiquetado/revisión: 8 pruebas aprobadas
Backend focalizado: 16 aprobadas, 8 omitidas por TestClient/AnyIO en Python 3.14 Windows
TypeScript: correcto
ESLint focalizado: correcto
Build Next.js de producción: correcto
py_compile backend: correcto
git diff --check: correcto
```

La suite ESLint global conserva errores anteriores fuera de estos archivos. No se realizó prueba manual con dos sesiones master ni conexión Azure SQL real; ambas permanecen en el gate de integración de Tarea 9.

No se ejecutó DDL, commit, push, despliegue ni escritura en Azure.
