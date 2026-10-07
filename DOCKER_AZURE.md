# Docker conectado a Azure

Este es el flujo habitual del proyecto. Backend y frontend se ejecutan en
contenedores; temas, preguntas, escenarios, usuarios y sesiones se guardan en
Azure SQL. Grabaciones e informes usan Azure Blob Storage y el worker existente
recibe los eventos por Azure Service Bus.

No se necesita instalar Python, Node, ODBC ni crear un entorno virtual en el
equipo. Docker instala las dependencias dentro de las imágenes. Se requiere
Docker Desktop con contenedores Linux y Compose 2.20 o posterior.

## Configuración

Los archivos `.env`, `backend/.env` y `frontend/.env.local` se conservan
localmente con sus valores existentes y quedan ignorados por Git. En una
copia nueva prepara la configuración de forma privada usando `.env.example`,
que solo contiene valores ficticios, como referencia.
La conexión utilizada por Compose es
`SQL_CONNECTION_STRING` en formato ODBC; el inicializador comprueba realmente
que el motor conectado sea Azure SQL antes de aplicar migraciones.

También deben estar configurados `STORAGE_CONNECTION_STRING`,
`SERVICE_BUS_CONNECTION_STRING`, `JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE` y las
variables públicas de Microsoft Entra. Se usan las conexiones Azure existentes
de `.env` en la raíz al ejecutar Compose.
Los archivos `.env` se excluyen de las imágenes; los secretos se pasan al backend
durante la ejecución. El frontend recibe únicamente variables públicas al construir.

Para Docker en este equipo, las URLs son:

```env
VOXREADY_DOCKER_API_URL=http://localhost:8000/v1
VOXREADY_DOCKER_REDIRECT_URI=http://localhost:3000
```

Para desplegar las imágenes en un servidor, configura la URL pública de la API
y del frontend antes de construirlas. No uses `http://api:8000` como URL del
frontend: quien realiza las peticiones es el navegador del usuario.
La URI de retorno debe estar registrada en Microsoft Entra y el origen del
frontend debe estar autorizado en `CORS_ORIGINS`. `DEV_AUTH` y
`NEXT_PUBLIC_DEV_AUTH` respetan `.env`; esta entrega conserva los valores
actuales acordados para las pruebas de la rama.

## Arranque

Desde la raíz:

```powershell
.\docker.ps1 up
```

Equivalente en cualquier terminal:

```bash
docker compose up --build -d --wait --wait-timeout 240
```

Primero se ejecuta `init`, que aplica las migraciones aditivas en Azure SQL.
Solo después de su éxito se inicia la API; el frontend espera su healthcheck.
La preparación no borra registros, no reinicia estados ni carga ejemplos
automáticamente: funciona también después de editar o archivar los temas.

- Frontend: http://localhost:3000/login/
- API: http://localhost:8000/docs
- Estado: `docker compose ps`
- Logs: `docker compose logs -f --tail 100 api client`

`docker-compose.yml` incluye la configuración Azure para que `docker compose`
sin argumentos adicionales use este flujo. También se puede especificar
`-f docker-compose.azure.yml` explícitamente.

## Verificación y pruebas dentro de Docker

Después de construir o arrancar:

```powershell
.\docker.ps1 verify
.\docker.ps1 test
```

Equivalentes:

```bash
docker compose run --rm --no-deps init python scripts/prepare_azure_database.py --verify-only
docker compose --profile test build test-api test-client
docker compose --profile test run --rm --no-deps test-api
docker compose --profile test run --rm --no-deps test-client
```

Las pruebas de API se conectan al mismo Azure SQL y revierten sus altas de prueba
al terminar; no crean una base local ni dejan usuarios o temas de prueba.
Simulan autenticación y SDK externos para verificar autorización, persistencia,
orden, estados y contratos de grabación/análisis sin lanzar un análisis nuevo.
El frontend verifica rutas y comprobaciones de dispositivos dentro de Node en Docker.

## Seed explícito

Los tres ejemplos ya están cargados en Azure SQL. Si necesitas inicializarlos
en una base compatible nueva, ejecuta después de la preparación:

```powershell
.\docker.ps1 seed
```

La comprobación estricta del contenido original es opcional:

```bash
docker compose run --rm --no-deps init python scripts/seed_master_topics.py --verify-only
```

Esta última puede fallar si se editó o archivó un ejemplo; la verificación
normal del despliegue valida el esquema vigente y no restablece ejemplos.

## Imágenes listas para publicar

```powershell
.\docker.ps1 build
```

Genera `voxready-api:latest` y `voxready-client:latest`. Puedes definir
`VOXREADY_IMAGE_TAG` en `.env`. La API incluye Python 3.11 y ODBC 18; el frontend
usa un build con lockfile y entrega su exportación estática con Nginx en el
puerto 3000. Los tests están en etapas separadas de las imágenes finales.

Para desplegar la API por separado, aplica primero la preparación de Azure SQL
con su imagen y las variables de ejecución. Compose ya automatiza este paso.
El worker de Azure se mantiene en su despliegue actual; este Compose levanta
backend y frontend y conecta con sus servicios existentes.

## Detener

```powershell
.\docker.ps1 stop
```

Detiene los contenedores de aplicación. Los datos permanecen en Azure.

## Verificación realizada

El 7 de octubre de 2026 se construyeron y arrancaron ambas imágenes.
Backend y frontend pasan sus healthchecks. Desde Docker se verificaron
`sqldb-voxready`, los tres temas, 24 preguntas y 24 asignaciones; también CORS,
las rutas de login/maestro/admin/vocero y los payloads de navegación de Next.js.
Pasaron 6 pruebas de API/contratos y 10 de frontend dentro de contenedores.
Las imágenes finales no contienen `.env` ni entornos virtuales. El entorno
Python temporal usado antes de adoptar este flujo fue retirado.

El arranque por dependencias sigue la [documentación oficial de Compose](https://docs.docker.com/compose/how-tos/startup-order/).
