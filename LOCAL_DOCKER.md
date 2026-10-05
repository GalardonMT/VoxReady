# VoxReady local con Docker

Este entorno usa PostgreSQL y autenticación demo. Se ejecuta como el proyecto Docker
`voxready-local`, con datos y puertos separados del despliegue Azure existente.
No requiere modificar el `.env` de la raíz.

## Iniciar

Desde la raíz del repositorio, con Docker Desktop encendido:

```powershell
docker compose -p voxready-local -f docker-compose.local.yml up --build -d --wait
```

La primera ejecución crea el volumen de PostgreSQL, aplica `alembic upgrade head`
y carga usuarios, escenarios, preguntas y políticas demo. Las ejecuciones siguientes
conservan la base de datos; la carga demo es idempotente.

- Aplicación: <http://localhost:3100/login>
- API y documentación: <http://localhost:8100/docs>
- Salud de API: <http://localhost:8100/health>
- Vocero demo: `vocero@demo.voxready.io`
- Administrador demo: `admin@demo.voxready.io`
- Configurador maestro demo: `master@voxready.io`

Para probar el flujo del vocero, entra con el correo demo, abre el catálogo, elige
un escenario, pulsa **Comprobar cámara y micrófono**, acepta los permisos del
navegador y marca las dos casillas de consentimiento. **Comenzar sesión** se habilita
cuando ambas comprobaciones están completas. Usa `localhost` para que el navegador
permita solicitar cámara y micrófono.

## Consultar estado y detener

```powershell
docker compose -p voxready-local -f docker-compose.local.yml ps --all
docker compose -p voxready-local -f docker-compose.local.yml logs -f api client
docker compose -p voxready-local -f docker-compose.local.yml down
```

`down` detiene solo este proyecto y conserva sus volúmenes. Para reiniciar sin
reconstruir imágenes:

```powershell
docker compose -p voxready-local -f docker-compose.local.yml up -d --wait
```

Si 3100 u 8100 están ocupados, elige puertos antes de iniciar:

```powershell
$env:VOXREADY_LOCAL_WEB_PORT = '3101'
$env:VOXREADY_LOCAL_API_PORT = '8101'
docker compose -p voxready-local -f docker-compose.local.yml up --build -d --wait
```

Los puertos y CORS se ajustan juntos. El PostgreSQL demo solo es accesible dentro
de la red Docker local. Los puertos web y API se publican únicamente en `127.0.0.1`.

La vista de sesión muestra las preguntas reales asociadas por la API. La grabación
de respuestas y el análisis posterior todavía no están conectados a esa vista.

## Cámara y micrófono

La comprobación solicita cada dispositivo por separado. Si no aparece un cuadro
de permiso, revisa el estado de cada uno: el navegador puede recordar un permiso
anterior o rechazar la solicitud si Windows no ofrece un dispositivo disponible.
Abre **Administrador de dispositivos → Cámaras** y habilita o conecta una cámara
funcional. Revisa también los permisos del sitio `localhost:3100` en el navegador.
El botón **Comenzar sesión** permanece deshabilitado hasta que haya pistas activas
de cámara y micrófono y se marquen ambas casillas de consentimiento.
