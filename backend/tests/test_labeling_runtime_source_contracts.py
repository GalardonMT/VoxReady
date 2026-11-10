"""Dependency-free guards for Tarea 2 backend upload/finalization contracts."""

import ast
from pathlib import Path


SOURCE_PATH = Path(__file__).resolve().parents[1] / "main.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def function_source(name):
    node = next(
        item
        for item in TREE.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


def test_recording_upload_is_create_only_and_closed_sessions_fail_conflict():
    source = function_source("get_upload_sas_url")
    assert "BlobSasPermissions(create=True)" in source
    assert "BlobSasPermissions(create=True, write=True)" not in source
    assert "access.get('status')" in source
    assert "status_code=409" in source


def test_finish_locks_session_and_reuses_active_job_without_new_insert():
    source = function_source("finish_session")
    assert "WITH (UPDLOCK,HOLDLOCK)" in source
    assert "status IN ('running','processing')" in source
    active_branch = source.index("if current_status in ('analyzing', 'processing')")
    existing_return = source.index('"analysisId": str(existing_job[0])', active_branch)
    insert = source.index("INSERT INTO analysis_job", active_branch)
    assert existing_return < insert


def test_sql_preparation_failure_is_not_swallowed_as_warning():
    source = function_source("finish_session")
    assert "No se pudo preparar el análisis de forma transaccional." in source
    assert "status_code=503" in source
