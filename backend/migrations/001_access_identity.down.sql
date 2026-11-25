-- Solo tras detener/deshabilitar la version que usa estas tablas.
-- No elimina invitaciones ni vinculos ya creados: en ese caso detenerse.
SET XACT_ABORT ON;
SET LOCK_TIMEOUT 5000;
IF ISNULL(CONVERT(int,SESSION_CONTEXT(N'voxready_access_rollback_confirmed')),0)<>1
    THROW 51000,'Reversion no confirmada.',1;
IF DB_NAME()<>CONVERT(nvarchar(128),SESSION_CONTEXT(N'voxready_expected_database'))
 OR SESSION_CONTEXT(N'voxready_expected_database') IS NULL
    THROW 51000,'Destino de reversion no confirmado.',1;
BEGIN TRY
 BEGIN TRANSACTION;
 IF EXISTS (SELECT 1 FROM dbo.pending_access WITH (TABLOCKX,HOLDLOCK))
  OR EXISTS (SELECT 1 FROM dbo.entra_identity WITH (TABLOCKX,HOLDLOCK))
    THROW 51000,'Existen accesos o vinculos: no se eliminara informacion.',1;
 DROP TABLE dbo.pending_access;
 DROP TABLE dbo.entra_identity;
 DROP TABLE dbo.legacy_access_profile;
 COMMIT TRANSACTION;
END TRY
BEGIN CATCH
 IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
