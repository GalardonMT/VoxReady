-- Amplia la modalidad de invitacion; conserva perfiles y todos los campos previos.
SET XACT_ABORT ON;
SET LOCK_TIMEOUT 5000;
IF SESSION_CONTEXT(N'voxready_expected_database') IS NULL
 OR DB_NAME()<>CONVERT(nvarchar(128),SESSION_CONTEXT(N'voxready_expected_database'))
 THROW 51000,'Destino no confirmado.',1;
BEGIN TRY
 BEGIN TRANSACTION;
 IF OBJECT_ID('dbo.pending_access','U') IS NULL
  OR COL_LENGTH('dbo.pending_access','account_choice') IS NOT NULL
  OR NOT EXISTS (SELECT 1 FROM sys.check_constraints
     WHERE parent_object_id=OBJECT_ID('dbo.pending_access') AND name='CK_pending_access_role_email'
       AND is_disabled=0 AND is_not_trusted=0)
  THROW 51000,'Esquema inesperado o migracion ya aplicada.',1;
 DECLARE @rows bigint;
 SELECT @rows=COUNT_BIG(*) FROM dbo.pending_access WITH (TABLOCKX,HOLDLOCK);
 ALTER TABLE dbo.pending_access ADD account_choice bit NOT NULL
  CONSTRAINT DF_pending_access_account_choice DEFAULT(0) WITH VALUES;
 ALTER TABLE dbo.pending_access DROP CONSTRAINT CK_pending_access_role_email;
 EXEC(N'ALTER TABLE dbo.pending_access WITH CHECK ADD CONSTRAINT CK_pending_access_role_email CHECK (
   (role=''client_admin'' AND expected_email IS NULL) OR
   (role=''spokesperson'' AND ((expected_email IS NULL AND account_choice=1)
        OR (expected_email IS NOT NULL AND LEN(expected_email)>3))))');
 ALTER TABLE dbo.pending_access CHECK CONSTRAINT CK_pending_access_role_email;
 COMMIT TRANSACTION;
END TRY
BEGIN CATCH
 IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
