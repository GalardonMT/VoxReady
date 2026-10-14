#!/usr/bin/env python3
"""Crea o alinea exclusivamente los usuarios semilla del desarrollo local."""
import os
import uuid

from seed_master_topics import DEMO_CLIENT_ID, SeedError, connect


DEV_USER_NAMESPACE = uuid.UUID("8de6d91d-465c-4e60-9808-52f81b1b8a20")
DEV_USERS = (
    ("elena.diaz@voxready.ai", "Elena Díaz", "master_config", None),
    ("ana.torres@acme-corp.com", "Ana Torres", "spokesperson", DEMO_CLIENT_ID),
    ("carlos.ruiz@acme-corp.com", "Carlos Ruiz", "client_admin", DEMO_CLIENT_ID),
)


def main():
    if os.getenv("DEV_AUTH", "false").strip().lower() != "true":
        raise SeedError("El seed de usuarios requiere DEV_AUTH=true y no se ejecuta en producción.")

    connection = connect()
    inserted = 0
    updated = 0
    unchanged = 0
    try:
        cursor = connection.cursor()
        cursor.execute("SET XACT_ABORT ON; IF @@TRANCOUNT=0 BEGIN TRANSACTION;")
        cursor.execute(
            "SELECT id FROM dbo.client WHERE id=? AND status='active' AND is_deleted=0",
            DEMO_CLIENT_ID,
        )
        if not cursor.fetchone():
            raise SeedError("Falta el cliente de ejemplo activo; ejecuta primero el seed maestro.")

        for email, display_name, role, client_id in DEV_USERS:
            cursor.execute(
                """SELECT id,client_id,email,display_name,role,preferred_language,is_deleted,deleted_at
                   FROM dbo.app_user WHERE LOWER(LTRIM(RTRIM(email)))=LOWER(?)""",
                email,
            )
            matches = cursor.fetchall()
            if len(matches) > 1:
                raise SeedError(f"Hay usuarios duplicados para el seed {email}.")
            if matches:
                current = matches[0]
                current_client_id = str(current[1]).lower() if current[1] is not None else None
                expected_client_id = str(client_id).lower() if client_id is not None else None
                needs_update = (
                    current_client_id != expected_client_id
                    or current[2] != email
                    or current[3] != display_name
                    or current[4] != role
                    or current[5] != "es"
                    or bool(current[6])
                    or current[7] is not None
                )
                if needs_update:
                    cursor.execute(
                        """UPDATE dbo.app_user SET client_id=?,email=?,display_name=?,role=?,preferred_language='es',
                           is_deleted=0,deleted_at=NULL,updated_at=SYSUTCDATETIME() WHERE id=?""",
                        client_id,
                        email,
                        display_name,
                        role,
                        current[0],
                    )
                    updated += 1
                else:
                    unchanged += 1
            else:
                user_id = str(uuid.uuid5(DEV_USER_NAMESPACE, email.casefold()))
                cursor.execute(
                    """INSERT INTO dbo.app_user(
                       id,client_id,email,display_name,role,preferred_language,is_deleted)
                       VALUES(?,?,?,?,?,'es',0)""",
                    user_id,
                    client_id,
                    email,
                    display_name,
                    role,
                )
                inserted += 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(
        f"Usuarios semilla de desarrollo verificados: {len(DEV_USERS)}; "
        f"creados={inserted}; actualizados={updated}; sin cambios={unchanged}."
    )
    print("No se modificaron usuarios ajenos al conjunto de desarrollo.")


if __name__ == "__main__":
    try:
        main()
    except SeedError as error:
        raise SystemExit(f"ERROR: {error}") from None
