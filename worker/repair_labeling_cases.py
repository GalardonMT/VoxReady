#!/usr/bin/env python3
"""Repair non-reviewable historical cases from a sealed-evidence manifest."""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from services.db_service import DatabaseService
from services.labeling_runtime import repair_ambiguous_case
from services.recording_evidence import verify_recording_evidence


WRITE_CONFIRMATION = "APPLY_LABELING_RECORDING_REPAIR"
MAX_CASES = 1000


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--confirm-write")
    return parser


def load_manifest(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("El manifiesto no es un JSON legible.") from error
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases or len(cases) > MAX_CASES:
        raise ValueError(f"El manifiesto debe contener entre 1 y {MAX_CASES} casos.")
    normalized_cases = []
    for item in cases:
        if not isinstance(item, dict) or not item.get("caseId"):
            raise ValueError("Cada entrada debe incluir caseId.")
        if not isinstance(item.get("evidence"), dict):
            raise ValueError("Cada entrada debe incluir evidence.")
        try:
            case_id = str(uuid.UUID(str(item["caseId"])))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Cada caseId debe ser un UUID válido.") from None
        normalized_cases.append({"caseId": case_id, "evidence": item["evidence"]})
    case_ids = [item["caseId"] for item in normalized_cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("El manifiesto contiene caseId duplicados.")
    return normalized_cases


def case_identity(cursor, case_id):
    cursor.execute(
        """SELECT lc.session_id,lc.analysis_job_id,s.external_session_id
             FROM dbo.labeling_case AS lc
             JOIN dbo.[session] AS s ON s.id=lc.session_id
            WHERE lc.id=?""",
        case_id,
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"El caso {case_id} no existe.")
    return str(row[2] or row[0]), str(row[1])


def repair_cases(cursor, blob_service, container_name, cases, *, apply):
    results = []
    for item in cases:
        case_id = str(item["caseId"])
        session_id, job_id = case_identity(cursor, case_id)
        evidence = verify_recording_evidence(
            blob_service=blob_service,
            container_name=container_name,
            evidence=item["evidence"],
            expected_session_id=session_id,
            expected_job_id=job_id,
        )
        results.append(
            repair_ambiguous_case(
                cursor,
                case_id,
                evidence,
                materialize=apply,
            )
        )
    return results


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.apply and args.confirm_write != WRITE_CONFIRMATION:
        parser.error(f"--apply exige --confirm-write {WRITE_CONFIRMATION}")
    if args.dry_run and args.confirm_write:
        parser.error("--confirm-write solo se admite con --apply")

    storage_connection = os.getenv("STORAGE_CONNECTION_STRING")
    container_name = (
        os.getenv("STORAGE_CONTAINER_NAME")
        or os.getenv("BLOB_CONTAINER_NAME")
        or "recordings"
    )
    if not storage_connection:
        parser.error("STORAGE_CONNECTION_STRING es obligatoria")
    try:
        cases = load_manifest(args.manifest)
    except ValueError as error:
        parser.error(str(error))

    from azure.storage.blob import BlobServiceClient

    service = DatabaseService()
    connection = None
    try:
        connection = service._get_connection()
        connection.autocommit = False
        cursor = connection.cursor()
        cursor.execute(
            "SET XACT_ABORT ON; SET LOCK_TIMEOUT 30000; "
            "IF @@TRANCOUNT=0 BEGIN TRANSACTION;"
        )
        cursor.execute(
            """DECLARE @result int;
               EXEC @result=sys.sp_getapplock
                    @Resource='voxready-labeling-recording-repair-v1',
                    @LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=30000;
               IF @result<0 THROW 51000,'No se pudo bloquear la reparación',1;"""
        )
        results = repair_cases(
            cursor,
            BlobServiceClient.from_connection_string(storage_connection),
            container_name,
            cases,
            apply=args.apply,
        )
        if args.apply:
            connection.commit()
        else:
            connection.rollback()
        summary = {
            "mode": "apply" if args.apply else "dry-run",
            "cases": len(results),
            "repaired": sum(bool(item.get("repaired")) for item in results),
            "results": results,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, default=str))
        return 0
    except Exception as error:
        if connection:
            connection.rollback()
        print(
            f"ERROR: reparación falló ({type(error).__name__}); transacción revertida.",
            file=sys.stderr,
        )
        return 1
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    sys.exit(main())
