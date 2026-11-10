# Cierre Tarea 5 — Lista y navegación con datos dinámicos

Estado: **completada localmente** en `feat/cola-de-etiquetado`.

## Entregables

1. `frontend/src/types/api.ts` contiene el contrato tipado de lista de casos, estados, motivo, sesión, informe, alertas, lease y revisión más reciente.
2. `frontend/src/services/labelingService.ts` consulta Pendientes y Revisadas mediante `/api/master/labeling-cases?status=...&limit=10`. Los errores reales se propagan y no existe fallback a mocks.
3. `frontend/src/services/labelingModel.ts` concentra orden estable, límite de diez tarjetas, preservación de selección, alertas y formato local de fecha, hora, duración y puntaje.
4. `LabelingQueueView.tsx` carga ambas vistas, permite alternar Pendientes/Revisadas, conserva el caso seleccionado al actualizar y muestra estados de carga, vacío, error, reintento y actualización.
5. Las tarjetas muestran fecha/hora, duración, puntaje general, escenario y áreas críticas. El panel mantiene la estructura visual de cola izquierda y detalle derecho sin simular una confirmación experta ni una reproducción real, que corresponden a T6 y T7.
6. Se retiraron `INITIAL_LABELING_QUEUE`, el fallback silencioso y los métodos antiguos que apuntaban al endpoint inexistente `/evaluate`.
7. `frontend/tests/labelingModel.test.mjs` cubre orden de pendientes y revisadas, máximo de diez, filtrado, estado vacío, preservación de selección y formatos de tarjeta.

## Verificación

```text
node --experimental-strip-types --test tests/*.test.mjs
28 pruebas aprobadas

npx eslint src/components/master/LabelingQueueView.tsx \
  src/services/labelingService.ts src/services/labelingModel.ts src/types/api.ts
sin errores ni advertencias

npx tsc --noEmit
correcto

npm run build
compilación, TypeScript y exportación estática correctos

git diff --check
correcto
```

El primer build encontró un `EPERM` dentro del artefacto generado `frontend/.next`; se eliminó únicamente ese directorio de compilación y la repetición terminó correctamente.

El lint global conserva errores anteriores fuera del alcance de T5 en componentes de sesión, reportes, avatar, autenticación y `apiClient`. Los archivos modificados por esta tarea pasan ESLint focalizado.

No se realizó commit, push, despliegue ni escritura en Azure.
