#!/usr/bin/env python3
"""Reconcile completed runtime reports that already carry sealed evidence."""

import argparse
import json
import sys

from services.db_service import DatabaseService
from services.labeling_runtime import reconcile_completed_reports


WRITE_CONFIRMATION = "APPLY_RUNTIME_LABELING_RECONCILIATION"


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-write")
    parser.add_argument("--limit", type=int, default=100)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > 1000:
        parser.error("--limit debe estar entre 1 y 1000")
    if args.apply and args.confirm_write != WRITE_CONFIRMATION:
        parser.error(f"--apply exige --confirm-write {WRITE_CONFIRMATION}")
    if args.dry_run and args.confirm_write:
        parser.error("--confirm-write solo se admite con --apply")

    service = DatabaseService()
    connection = None
    try:
        connection = service._get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SET XACT_ABORT ON; SET LOCK_TIMEOUT 30000; "
            "IF @@TRANCOUNT=0 BEGIN TRANSACTION;"
        )
        cursor.execute(
            """DECLARE @result int;
               EXEC @result=sys.sp_getapplock
                    @Resource='voxready-runtime-labeling-reconcile-v1',
                    @LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=30000;
               IF @result<0 THROW 51000,'No se pudo bloquear la reconciliación runtime',1;"""
        )
        summary = reconcile_completed_reports(
            cursor,
            limit=args.limit,
            materialize=args.apply,
        )
        if args.apply:
            connection.commit()
        else:
            connection.rollback()
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        if connection:
            connection.rollback()
        print(
            f"ERROR: reconciliación runtime falló ({type(error).__name__}); transacción revertida.",
            file=sys.stderr,
        )
        return 1
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    sys.exit(main())
