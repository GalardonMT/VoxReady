# Auditoría técnica — 3 de noviembre de 2026

## Alcance

Revisión estática y dinámica de la rama de entrega estable: secretos e información embebida, autenticación, autorización, llamadas salientes, CORS, almacenamiento de tokens, dependencias, generación de informes, archivos innecesarios, compilación y pruebas en Docker.

La cola de etiquetado en desarrollo quedó fuera del paquete para no mezclar trabajo incompleto con la versión entregable.

## Correcciones aplicadas

- Se eliminaron IDs de audiencia, endpoints de infraestructura, usuarios de prueba y correos embebidos.
- La validación JWT exige issuer, audience, firma y configuración explícita.
- El modo local usa JWT HMAC con secreto mínimo y solo funciona en desarrollo.
- Se restringió CORS y se añadieron encabezados HTTP defensivos.
- Se retiraron `verify=False` y las descargas de modelos en runtime.
- Se migró visión a MediaPipe Tasks `1.2.2` para retirar una dependencia vulnerable de Protobuf; los modelos oficiales se verifican por SHA-256 durante el build.
- Backend–worker y worker–visión ahora requieren tokens internos independientes.
- Se retiraron rutas heredadas y no desplegadas del worker, dejando una entrada HTTP autenticada.
- Se eliminaron datasets y reportes simulados del flujo de ejecución; un dato ausente ya no se transforma en una puntuación aparentemente real.
- Tokens y perfil del navegador se movieron a `sessionStorage`.
- Se actualizaron dependencias con avisos conocidos y se sincronizó `package-lock.json` para `npm ci` en Docker.
- Se parametrizaron contenedores, prefijos Blob, URLs, modelos, límites y vigencia de SAS.
- Se eliminaron archivos runtime de mock y código duplicado sin uso.

## Verificaciones ejecutadas

| Verificación | Resultado |
|---|---|
| Gitleaks, historial completo | Sin secretos actuales. Dos alertas históricas correspondían a un client ID público de CIAM en scripts eliminados, no a una credencial. |
| Bandit | 0 altos; 23 medios revisados: 22 avisos B608 por SQL dinámico con identificadores/listas cerradas y 1 B104 por el binding intencional del contenedor interno. |
| `pip-audit` | 0 vulnerabilidades conocidas en backend, worker y visión al 3-11-2026. |
| `npm audit` | 0 vulnerabilidades conocidas. |
| Frontend lint | Sin errores ni advertencias. |
| Frontend build | Compilación y exportación estática correctas. |
| Pruebas Docker backend | 76 aprobadas; 10 omitidas por requerir Azure SQL real. |
| Pruebas Docker worker | 8 aprobadas; 2 omitidas por requerir Azure SQL real. |
| Arranque Docker visión | MediaPipe Tasks `1.2.2`, modelos verificados y endpoint de salud correcto. |
| Pruebas frontend | 23 comprobaciones aprobadas. |

Los resultados anteriores deben repetirse después de cualquier cambio de dependencias o despliegue.

## Riesgos residuales y límites

- No se ejecutó una prueba de penetración contra un ambiente desplegado ni un análisis de permisos del tenant Azure.
- Las pruebas omitidas necesitan una base Azure SQL de ensayo autorizada; no se usaron credenciales productivas durante esta auditoría.
- Los hallazgos Bandit de SQL dinámico revisados usan parámetros para datos y nombres de tabla seleccionados por el propio código. Las llamadas a FFmpeg usan listas de argumentos, sin shell. Deben reevaluarse si una futura modificación permite que una entrada del usuario controle identificadores SQL o comandos.
- Los identificadores deterministas de `seed_master_topics.py` son datos de migración versionados, no secretos. Si el cliente no desea ese catálogo inicial, debe sustituirse antes de ejecutar `seed`.
- La seguridad final depende de mínimo privilegio, red privada, rotación de secretos, políticas de almacenamiento y monitoreo del ambiente cloud.

## Criterio de entrega

El paquete contiene código fuente rastreado, documentación, plantillas y pruebas. Excluye `.env`, dependencias instaladas, caches, compilaciones, medios, modelos pesados, logs y archivos temporales. El SHA-256 adjunto permite comprobar que el ZIP descargado no cambió.
