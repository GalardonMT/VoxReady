-- Detener primero la version que usa account_choice. No borra ni transforma filas.
SET XACT_ABORT ON;
SET LOCK_TIMEOUT 5000;
IF ISNULL(CONVERT(int,SESSION_CONTEXT(N'voxready_access_rollback_confirmed')),0)<>1
 OR SESSION_CONTEXT(N'voxready_expected_database') IS NULL
 OR DB_NAME()<>CONVERT(nvarchar(128),SESSION_CONTEXT(N'voxready_expected_database'))
 THROW 51000,'Reversion o destino no confirmados.',1;
BEGIN TRY
 BEGIN TRANSACTION;
 IF EXISTS (SELECT 1 FROM dbo.pending_access WITH (TABLOCKX,HOLDLOCK) WHERE account_choice=1)
  THROW 51000,'Hay accesos con eleccion de cuenta; conservar esquema y revisar sin borrar datos.',1;
 ALTER TABLE dbo.pending_access DROP CONSTRAINT CK_pending_access_role_email;
 ALTER TABLE dbo.pending_access WITH CHECK ADD CONSTRAINT CK_pending_access_role_email CHECK (
  (role='client_admin' AND expected_email IS NULL) OR
  (role='spokesperson' AND expected_email IS NOT NULL AND LEN(expected_email)>3));
 ALTER TABLE dbo.pending_access DROP CONSTRAINT DF_pending_access_account_choice;
 ALTER TABLE dbo.pending_access DROP COLUMN account_choice;
 COMMIT TRANSACTION;
END TRY
BEGIN CATCH
 IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
