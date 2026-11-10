# Cierre de Tarea 7 — Grabación real y recuperación de SAS

Fecha de verificación local: 2026-11-09
Rama de trabajo: `feat/cola-de-etiquetado`

## Resultado

La cola usa el `RecordingVideoPlayer` compartido para reproducir el medio sellado del caso. El ticket de reproducción se solicita únicamente al abrir el caso, contiene una SAS HTTPS de lectura y se renueva antes de expirar o ante un error de reproducción, con un máximo de dos recuperaciones automáticas.

La renovación conserva la posición observada y remonta el elemento `<video>` de forma controlada. Al cambiar de caso se aborta la solicitud pendiente, se pausa el medio, se elimina el `src` y se limpia el reproductor anterior. La duración persistida se usa como respaldo cuando WebM no informa una duración fiable.

## Controles implementados

1. Estados diferenciados de carga, renovación, archivo no disponible/eliminado, storage no disponible y error de reproducción.
2. Reproducción, pausa, saltos, búsqueda, volumen, velocidad, buffer y pantalla completa continúan en el componente compartido.
3. El frontend valida HTTPS, expiración, `Content-Type` de video y ETag antes de montar el medio.
4. El backend abre la versión exacta cuando existe `versionId` y rechaza diferencias de ETag o `Content-Type` frente a la evidencia sellada.
5. La SAS usa permiso `read`, protocolo HTTPS, expiración de quince minutos y respuesta `Cache-Control: no-store`.
6. La auditoría registra la emisión mediante campos escalares permitidos; no registra la URL, SAS, comentarios, identidad personal ni ruta interna.
7. La evidencia sellada se crea sin sobrescritura. La prueba de aislamiento demuestra que alterar la fuente mutable produce otra evidencia y no cambia los bytes del caso ya sellado.

## Verificación ejecutada

- Frontend completo: `36 passed`.
- Pruebas específicas de cola/reproductor: `12 passed`.
- Backend de contratos, API y store: `17 passed`, `8 skipped` por incompatibilidad local de `TestClient` con Python 3.14.
- Evidencia sellada y aislamiento de sobrescritura: `4 passed`.
- TypeScript y ESLint focal: correctos.
- `next build`: compilación de producción correcta.
- `git diff --check`: correcto; solo aviso informativo de conversión LF/CRLF en un archivo preexistente.

## Límites del entorno

El código y sus contratos quedan completos localmente. El QA real de Chrome/Edge contra Azure —CORS del servicio, respuesta parcial `Range`, búsqueda sobre el blob real y renovación de una SAS expirada— queda **PENDIENTE** para la Tarea 9 porque este entorno no dispone de una instancia desplegada con un caso sellado y credenciales de Azure. Por esa misma razón no se afirma una validación visual E2E real; el resultado de browser QA es **INCONCLUSIVE** hasta ejecutar ese gate.

La suite focal ampliada detectó cuatro fallos previos ajenos a Tarea 7 en contratos de Tarea 2 (`prepare_azure_database.py`, `get_upload_sas_url` y `finish_session`) y un fallo previo del entrypoint canónico del worker. No se modificaron por respetar el alcance de esta tarea.

No se ejecutaron migraciones, escrituras en Azure, despliegues, commits ni push.
