# Entrega de la rama temas-y-escenarios

## Incluidos

- Código completo del backend y frontend, incluidos los nuevos módulos,
  componentes, tipos, servicios y diccionarios de temas y escenarios.
- `backend/scripts/`: seed, datos de ejemplo, migraciones y preparación Azure.
- `backend/tests/` y `frontend/tests/`: pruebas reproducibles; no forman parte
  de las imágenes finales de ejecución.
- Dockerfiles, `.dockerignore`, `frontend/nginx.conf`, `docker-compose.yml`,
  `docker-compose.azure.yml`, `docker.ps1` y `dev-tools.ps1`.
- `frontend/package-lock.json`, manifiestos de dependencias y configuraciones
  existentes requeridas para construir.
- Worker y servicio de visión existentes, conservados.
- `.gitignore`, `.env.example`, instrucciones y documentación del flujo Azure.

## Fuera de la entrega

- `.env`, `backend/.env`, `frontend/.env.local` y sus variantes reales:
  conservados localmente con sus valores actuales como archivos ignorados.
- `.env.test.local`, archivos de configuración para bases locales y
  `worker/local.settings.json`.
- Entornos virtuales, `node_modules`, `.next`, `out`, `__pycache__`,
  `pytest-cache-files-*`, logs, grabaciones e informes generados.
- `scratch/`, `backend/storage/`, `backend/local_scenario_test/` y bases `*.db`.
- `docker-compose.local.yml`, `backend/Dockerfile.local`,
  `frontend/Dockerfile.local`, `LOCAL_DOCKER.md`, `lab-worker/` y
  `discurso_prueba_entrevista.txt`: retirados del versionado, conservados en disco.

No se borran datos de Azure SQL. Los `.env` quedan fuera de Git y de las imágenes;
Compose entrega sus valores locales al backend en ejecución. La plantilla
`.env.example` contiene valores ficticios y se mantiene versionada.

## Probar después de descargar la rama

En este computador se conservan las configuraciones actuales. En otra copia
del repositorio, prepara `.env` de forma privada usando `.env.example` como
referencia antes de ejecutar Docker. No agregues sus valores reales a Git.

Con Docker Desktop en modo Linux, desde la raíz:

```powershell
.\docker.ps1 up
.\docker.ps1 verify
.\docker.ps1 test
```

Frontend: http://localhost:3000/login/
API: http://localhost:8000/docs

La preparación valida el motor Azure SQL y aplica únicamente migraciones
aditivas. No carga ni restaura ejemplos automáticamente. Las pruebas de
persistencia usan el Azure SQL existente y revierten sus altas al terminar.

Para publicar en un servidor se deben utilizar sus URLs públicas en los
argumentos del frontend y las URI registradas en Microsoft Entra. Este commit
no publica imágenes ni actualiza los servicios de Container Apps por sí mismo.
