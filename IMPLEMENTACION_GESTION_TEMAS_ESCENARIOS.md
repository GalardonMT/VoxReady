# Gestión de temas y escenarios: implementación y verificación

Fecha de verificación: 7 de octubre de 2026. Base: `sqldb-voxready`.
Fuente funcional: `PLAN_GESTION_TEMAS_ESCENARIOS.md` suministrado por el usuario.

## Fases y comprobaciones

1. **Seed y Azure SQL:** aplicado y verificado. Tres temas globales, 24 preguntas,
   tres escenarios para el cliente demo y 24 relaciones ordenadas. Reejecución:
   cero registros nuevos. Se conservó el tema y escenario anteriores.
2. **Endpoints maestros:** implementados en `backend/main.py`, con persistencia
   aislada en `backend/master_topics.py`. Autenticación existente y autorización
   desde `app_user`. Prueba real: 12 preguntas, selección de cuatro, reordenación,
   edición manteniendo identidades, archivado/reactivación en cascada, estados
   individuales y rechazo de rol no maestro. Migración aditiva aplicada.
3. **Catálogo y sesiones:** aislamiento por empresa, estados activos de tema y
   escenario, paginación y búsqueda. Sesiones persistentes con rúbrica y claves
   de idempotencia. Se conservan claves UUID existentes mediante un identificador
   público separado. Las preguntas se obtienen en `sequence_no` y se conserva
   una copia del texto y orden en la tabla existente `session_question`.
   Prueba real: dos usuarios del mismo cliente, otro cliente sin acceso,
   persistencia, reintentos y cambios posteriores que no alteran una entrevista
   iniciada. Migración aditiva aplicada.
4. **Tipos y servicios:** tipos técnicos independientes de los tipos españoles
   anteriores; `masterTopicService.ts` usa el cliente HTTP centralizado.
   Diccionarios ES/EN/PT actualizados. TypeScript sin errores.
5. **UI m4/m5:** catálogo con filtros y métricas, confirmación de archivado,
   editor, banco dinámico sin máximo de preguntas y panel dual con ▲/▼.
   Compilación completa Next.js correcta. Vistas m1/m2/m3 y administración
   del cliente conservadas. Las etiquetas técnicas en las nuevas vistas y el
   catálogo del vocero se muestran según el diccionario español del plan.
6. **Verificación:** pruebas automatizadas locales, integración SQL y E2E de
   interfaz. Las pruebas SQL crean sus datos dentro de una transacción y hacen
   rollback al terminar: no dejan temas, cuentas ni sesiones de prueba persistidos.
   La autenticación se simula en las pruebas SQL/UI; los permisos y escrituras
   se comprueban realmente en Azure SQL. Las pruebas de regresión verifican
   firmas JWT, Dev Auth, SAS y contratos de Service Bus/reporte con SDK simulados.

Resultado: 18 pruebas de backend/UI y 10 pruebas existentes de frontend pasan.
La compilación Next.js completa pasa. Lint de los componentes nuevos: cero
errores; la página maestra conserva una advertencia previa por su logotipo `<img>`.
La comprobación final encontró 3 temas globales y los 24 registros del banco y
sus asignaciones; contando los datos anteriores hay 4 temas y 4 escenarios.
No quedaron temas, cuentas ni sesiones persistidos por las pruebas.

**Límite pendiente de E2E:** no se ha realizado un inicio de sesión real en Entra
ni una grabación humana enviada a Container Apps para generar un nuevo reporte
coach. Los manejadores de login, consentimiento, subida, envío al worker y lectura
del reporte se conservaron; sus contratos fueron comprobados automáticamente.
Esto no sustituye la prueba en vivo del último punto de la sección 9.

## Ejecución y pruebas reproducibles

El flujo vigente utiliza Docker y las conexiones Azure de `.env` en la raíz.
Python 3.11, ODBC 18 y las dependencias se instalan dentro de la imagen.
No se crean entornos virtuales ni bases locales para ejecutar o verificar.
Consulta `DOCKER_AZURE.md` para la configuración y el despliegue.

```powershell
.\docker.ps1 up
.\docker.ps1 verify
.\docker.ps1 test
```

Para comprobar estrictamente la semilla original desde Docker:

```powershell
docker compose run --rm --no-deps init python scripts/seed_master_topics.py --verify-only
```

La prueba E2E de interfaz ya realizada usó Chrome temporal y los endpoints
reales sobre Azure SQL con rollback. Sus capturas de QA se conservan en
`scratch/master-editor.png` y `scratch/master-catalog.png`. La verificación
habitual de API y frontend ahora se ejecuta con `docker.ps1 test`.

## Decisiones para conservar integridad

- Ninguna operación nueva ejecuta DELETE, TRUNCATE ni DROP. Las bajas de
  preguntas, mensajes, líneas rojas y asignaciones usan `status='archived'`.
- Una pregunta retirada del banco conserva sus asignaciones preexistentes.
  No puede agregarse a escenarios nuevos hasta reactivarla en el banco.
- Un escenario de tema archivado puede archivarse individualmente; para
  reactivarlo o configurarlo se requiere reactivar primero el tema.
- Las credenciales no se imprimen en consola ni se guardan en documentación.
- La cuenta maestra indicada por el usuario fue habilitada conservando su
  empresa. `/me` y el acceso al catálogo maestro se comprobaron en Azure SQL.
  Cerrar sesión y entrar nuevamente refresca el rol almacenado en el frontend.
- Los alias anteriores `crisis-voceria-01`, `crisis-operativa-02` y
  `crisis-reputacional-03` se resuelven a sus escenarios reales; la autorización
  por empresa también se aplica a estos alias.

Las imágenes y Compose están preparados para desplegar backend y frontend,
con migraciones automáticas en Azure SQL. El worker mantiene su despliegue
existente; no se publicó una actualización de Container Apps.
