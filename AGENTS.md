# Instrucciones del proyecto

## Ejecución y datos

- Usar Docker para construir, ejecutar y verificar el proyecto. Comandos:
  `./docker.ps1 up`, `./docker.ps1 verify`, `./docker.ps1 test`.
- Los datos de aplicación se guardan en Azure SQL usando
  `SQL_CONNECTION_STRING` de `.env`. Grabaciones y reportes usan Blob Storage;
  el procesamiento usa Service Bus y el worker existente en Azure.
- No crear entornos Python virtuales locales, bases SQLite de aplicación ni
  contenedores de SQL Server/PostgreSQL para sustituir Azure SQL.
- No usar los antiguos perfiles de demo local como flujo de desarrollo o
  verificación. El Compose predeterminado incluye `docker-compose.azure.yml`.
- Instalar dependencias dentro de las imágenes. Mantener el lockfile del
  frontend sincronizado y usar `npm ci` en Docker.
- Aplicar migraciones aditivas con `scripts/prepare_azure_database.py` en la
  imagen del backend; se comprueba el motor Azure SQL antes de escribir.
- No imprimir conexiones, claves ni el resultado completo de
  `docker compose config`. Usar `docker compose config --quiet`.
- No versionar archivos reales de entorno ni sus variantes. Conservar `.env`,
  `backend/.env` y `frontend/.env.local` localmente como archivos ignorados.
  Solo las plantillas de ejemplo con valores ficticios se incluyen en Git.
  No copiar claves a otros archivos ni imprimir sus valores. Los `.env` se
  excluyen de las imágenes; Compose inyecta las conexiones durante la ejecución.

## Integridad funcional

- Conservar login Microsoft Entra/Dev Auth, grabación, análisis, reporte coach,
  administración del cliente y vistas maestras existentes.
- Ninguna baja borra físicamente registros; usar archivado.
- BD y API usan códigos técnicos en inglés; la interfaz usa las etiquetas
  españolas del diccionario del plan de temas y escenarios.
- Banco de preguntas sin máximo artificial y orden por `sequence_no`.
- Seguir también `frontend/AGENTS.md` al modificar el frontend.

Consulta `DOCKER_AZURE.md` para el flujo vigente de despliegue y pruebas.
