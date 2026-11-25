-- Migracion aditiva revisada: no ejecuta init, no altera perfiles ni contrasenas.
-- Requiere SESSION_CONTEXT(N'voxready_expected_database') con la base confirmada.
SET XACT_ABORT ON;
SET LOCK_TIMEOUT 5000;
IF CONVERT(nvarchar(128),SESSION_CONTEXT(N'voxready_expected_database')) IS NULL
 OR DB_NAME()<>CONVERT(nvarchar(128),SESSION_CONTEXT(N'voxready_expected_database'))
    THROW 51000,'La base no coincide con el destino confirmado.',1;
BEGIN TRY
 BEGIN TRANSACTION;
 IF EXISTS (SELECT 1 FROM sys.objects WHERE schema_id=SCHEMA_ID('dbo')
            AND name IN ('pending_access','entra_identity','legacy_access_profile'))
    THROW 51000,'Hay objetos de acceso previos; revisar sin reemplazarlos.',1;
 IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.app_user')
                AND name='UQ_app_user_id_client' AND is_unique=1 AND is_disabled=0)
    THROW 51000,'Falta la clave compuesta esperada de app_user.',1;
 IF COL_LENGTH('dbo.app_user','email')<>510
    OR CONVERT(nvarchar(128),DATABASEPROPERTYEX(DB_NAME(),'Collation'))<>'SQL_Latin1_General_CP1_CI_AS'
    THROW 51000,'Longitud o colacion distintas de las revisadas.',1;

CREATE TABLE dbo.pending_access (
    id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_pending_access PRIMARY KEY,
    client_id UNIQUEIDENTIFIER NOT NULL,
    role NVARCHAR(30) NOT NULL,
    display_name NVARCHAR(150) NOT NULL,
    expected_email NVARCHAR(255) COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
    created_by UNIQUEIDENTIFIER NOT NULL,
    created_at DATETIME2 NOT NULL CONSTRAINT DF_pending_access_created DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2 NOT NULL CONSTRAINT DF_pending_access_updated DEFAULT SYSUTCDATETIME(),
    token_hash CHAR(64) COLLATE Latin1_General_100_BIN2 NULL,
    expires_at DATETIME2 NULL,
    generation INT NOT NULL CONSTRAINT DF_pending_access_generation DEFAULT 0,
    used_at DATETIME2 NULL,
    completed_user_id UNIQUEIDENTIFIER NULL,
    CONSTRAINT FK_pending_access_client FOREIGN KEY (client_id) REFERENCES dbo.client(id),
    CONSTRAINT FK_pending_access_creator FOREIGN KEY (created_by) REFERENCES dbo.app_user(id),
    CONSTRAINT FK_pending_access_completed FOREIGN KEY (completed_user_id,client_id)
        REFERENCES dbo.app_user(id,client_id),
    CONSTRAINT CK_pending_access_role_email CHECK (
        (role='client_admin' AND expected_email IS NULL) OR
        (role='spokesperson' AND expected_email IS NOT NULL AND LEN(expected_email)>3)),
    CONSTRAINT CK_pending_access_completion CHECK (
        (used_at IS NULL AND completed_user_id IS NULL) OR
        (used_at IS NOT NULL AND completed_user_id IS NOT NULL AND token_hash IS NOT NULL)),
    CONSTRAINT CK_pending_access_token CHECK (
        (token_hash IS NULL AND expires_at IS NULL AND generation=0) OR
        (token_hash IS NOT NULL AND expires_at IS NOT NULL AND generation>0))
);
CREATE UNIQUE INDEX UQ_pending_access_token ON dbo.pending_access(token_hash)
    WHERE token_hash IS NOT NULL;
CREATE UNIQUE INDEX UQ_pending_access_email ON dbo.pending_access(expected_email)
    WHERE expected_email IS NOT NULL AND used_at IS NULL;
CREATE INDEX IX_pending_access_client ON dbo.pending_access(client_id,created_at);

CREATE TABLE dbo.entra_identity (
    tenant_id UNIQUEIDENTIFIER NOT NULL,
    object_id UNIQUEIDENTIFIER NOT NULL,
    user_id UNIQUEIDENTIFIER NOT NULL,
    issuer NVARCHAR(512) COLLATE Latin1_General_100_BIN2 NOT NULL,
    created_at DATETIME2 NOT NULL CONSTRAINT DF_entra_identity_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_entra_identity PRIMARY KEY (tenant_id,object_id),
    CONSTRAINT UQ_entra_identity_user UNIQUE (user_id),
    CONSTRAINT FK_entra_identity_user FOREIGN KEY (user_id) REFERENCES dbo.app_user(id)
);
-- Lista de compatibilidad, NO vinculos inferidos con Entra.
CREATE TABLE dbo.legacy_access_profile (
    user_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_legacy_access_profile PRIMARY KEY,
    recorded_at DATETIME2 NOT NULL CONSTRAINT DF_legacy_access_profile_recorded DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_legacy_access_profile_user FOREIGN KEY (user_id) REFERENCES dbo.app_user(id)
);
INSERT INTO dbo.legacy_access_profile(user_id)
    SELECT id FROM dbo.app_user WHERE is_deleted=0;
 COMMIT TRANSACTION;
END TRY
BEGIN CATCH
 IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
