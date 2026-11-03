#!/usr/bin/env python3
"""Crea o alinea exclusivamente los usuarios semilla del desarrollo local."""
import json
import os
import uuid

from seed_master_topics import DEMO_CLIENT_ID, SeedError, connect


ALLOWED_ROLES = {"master_config", "client_admin", "spokesperson"}


def load_dev_users():
    raw = os.getenv("DEV_USERS_JSON", "").strip()
    if not raw:
        raise SeedError("DEV_USERS_JSON es obligatorio para crear usuarios de desarrollo.")
    try:
        configured = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SeedError("DEV_USERS_JSON no contiene JSON válido.") from error
    if not isinstance(configured, list) or not configured:
        raise SeedError("DEV_USERS_JSON debe ser una lista no vacía.")

    users = []
    for item in configured:
        if not isinstance(item, dict):
            raise SeedError("Cada usuario de desarrollo debe ser un objeto JSON.")
        email = str(item.get("email", "")).strip().lower()
        display_name = str(item.get("displayName", "")).strip()
        role = str(item.get("role", "")).strip()
        if "@" not in email or not display_name or role not in ALLOWED_ROLES:
            raise SeedError("Cada usuario requiere email, displayName y un role permitido.")
        client_id = None if role == "master_config" else DEMO_CLIENT_ID
        users.append((email, display_name, role, client_id))
    return tuple(users)


def main():
    if os.getenv("DEV_AUTH", "false").strip().lower() != "true":
        raise SeedError("El seed de usuarios requiere DEV_AUTH=true y no se ejecuta en producción.")

    dev_users = load_dev_users()
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

        for email, display_name, role, client_id in dev_users:
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
                user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"voxready-dev-user:{email.casefold()}"))
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
        f"Usuarios semilla de desarrollo verificados: {len(dev_users)}; "
        f"creados={inserted}; actualizados={updated}; sin cambios={unchanged}."
    )
    print("No se modificaron usuarios ajenos al conjunto de desarrollo.")


if __name__ == "__main__":
    try:
        main()
    except SeedError as error:
        raise SystemExit(f"ERROR: {error}") from None
