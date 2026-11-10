# Cierre de Tarea 8 — Evidencia en editores

Fecha de verificación local: 2026-11-09
Rama de trabajo: `feat/cola-de-etiquetado`

## Resultado

Los editores de Rúbrica y Métricas incorporan un panel compartido de **Revisión de calidad** en modo de solo lectura. El panel consume el resumen agregado de revisiones confirmadas y los comentarios actuales de los últimos casos revisados, sin escribir ni derivar cambios sobre formularios, borradores, pesos, umbrales o versiones publicadas.

## Subtareas completadas

1. Editor de Rúbrica: evidencia por área y versión de rúbrica, con cantidad de casos, diferencia media, distribución al alza/a la baja/sin cambio y comentarios específicos recientes.
2. Editor de Métricas: evidencia separada por categoría, métrica, versión de mapeo y unidad.
3. Gobernanza queda excluida de la calibración y aparece únicamente como contexto de selección y acuerdo.
4. Filtros disponibles para 7, 30, 90 días y todo el historial; el límite superior del período es exclusivo.
5. Cada comentario permite abrir el caso revisado correspondiente en la Cola de Etiquetado.
6. El flujo de crear, guardar, revisar, publicar o descartar borradores permanece separado del panel de evidencia.
7. Abrir o filtrar evidencia mantiene su estado dentro del panel y no modifica los valores del editor.
8. Las agregaciones no mezclan versiones de rúbrica, versiones de mapeo ni unidades incompatibles.

## Seguridad y alcance

- Solo se consultan revisiones actuales mediante `currentReviewsOnly=true`.
- Los comentarios se obtienen por los endpoints master existentes, protegidos por el rol `master_config`.
- No se exponen SAS, rutas Blob, transcripciones, nombres, correos ni tokens.
- El panel declara explícitamente que la evidencia no modifica configuración publicada.

## Verificación

- Suite frontend completa: `40 passed`.
- Suite específica de cola/evidencia: `16 passed`.
- Backend focal de contratos, API, agregación y store: `17 passed`, `8 skipped` por la incompatibilidad local ya documentada de `TestClient` con Python 3.14.
- TypeScript: correcto.
- ESLint focal: sin errores; permanece un aviso preexistente por `<img>` en la cabecera maestra.
- Build de producción Next.js: correcto.
- Context7: patrones React 19 de efectos con limpieza y estado independiente aplicados al panel.

## Límites

La validación visual con datos reales y el recorrido integrado de navegación quedan para el gate de la Tarea 9, porque este entorno no contiene una base Azure migrada y poblada con revisiones reales. No se ejecutaron migraciones, escrituras Azure, despliegues, commits ni push.
