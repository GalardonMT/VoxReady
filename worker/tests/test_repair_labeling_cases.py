import json
import sys
import types

import pytest

import repair_labeling_cases as command


CASE_ID = "11111111-1111-4111-8111-111111111111"


def evidence():
    return {
        "sealedPath": "labeling-evidence/session/job/hash.webm",
        "sha256": "a" * 64,
        "etag": '"etag"',
        "contentType": "video/webm",
    }


def test_load_manifest_requires_unique_explicit_evidence(tmp_path):
    path = tmp_path / "repair.json"
    path.write_text(
        json.dumps({"cases": [{"caseId": CASE_ID, "evidence": evidence()}]}),
        encoding="utf-8",
    )

    assert command.load_manifest(path) == [
        {"caseId": CASE_ID, "evidence": evidence()}
    ]


def test_load_manifest_rejects_duplicate_cases(tmp_path):
    path = tmp_path / "repair.json"
    item = {"caseId": CASE_ID, "evidence": evidence()}
    path.write_text(json.dumps({"cases": [item, item]}), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicados"):
        command.load_manifest(path)


def test_repair_cases_verifies_identity_before_domain_update(monkeypatch):
    class Cursor:
        def execute(self, *_args):
            return self

        def fetchone(self):
            return ("internal-session", "job-id", "external-session")

    verified = {}

    def verify(**kwargs):
        verified.update(kwargs)
        return {**kwargs["evidence"], "versionId": None}

    monkeypatch.setattr(
        command,
        "verify_recording_evidence",
        verify,
    )
    monkeypatch.setattr(
        command,
        "repair_ambiguous_case",
        lambda _cursor, case_id, _evidence, materialize: {
            "caseId": case_id,
            "repaired": materialize,
        },
    )

    result = command.repair_cases(
        Cursor(),
        object(),
        "recordings",
        [{"caseId": CASE_ID, "evidence": evidence()}],
        apply=True,
    )

    assert result == [{"caseId": CASE_ID, "repaired": True}]
    assert verified["expected_session_id"] == "external-session"
    assert verified["expected_job_id"] == "job-id"


class CommandCursor:
    def __init__(self):
        self.statements = []

    def execute(self, statement, *_params):
        self.statements.append(" ".join(statement.split()).lower())
        return self


class CommandConnection:
    def __init__(self):
        self.autocommit = True
        self.command_cursor = CommandCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.command_cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _install_fake_blob_sdk(monkeypatch):
    blob_module = types.ModuleType("azure.storage.blob")

    class BlobServiceClient:
        @staticmethod
        def from_connection_string(connection_string):
            assert connection_string == "UseDevelopmentStorage=true"
            return object()

    blob_module.BlobServiceClient = BlobServiceClient
    azure_module = types.ModuleType("azure")
    azure_module.__path__ = []
    storage_module = types.ModuleType("azure.storage")
    storage_module.__path__ = []
    monkeypatch.setitem(sys.modules, "azure", azure_module)
    monkeypatch.setitem(sys.modules, "azure.storage", storage_module)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", blob_module)


@pytest.mark.parametrize(("apply", "expected_commit"), [(False, 0), (True, 1)])
def test_main_uses_transaction_applock_and_selected_write_mode(
    tmp_path, monkeypatch, capsys, apply, expected_commit
):
    manifest = tmp_path / "repair.json"
    manifest.write_text(
        json.dumps({"cases": [{"caseId": CASE_ID, "evidence": evidence()}]}),
        encoding="utf-8",
    )
    connection = CommandConnection()

    class DatabaseService:
        def _get_connection(self):
            return connection

    monkeypatch.setattr(command, "DatabaseService", DatabaseService)
    monkeypatch.setattr(
        command,
        "repair_cases",
        lambda _cursor, _blob, container, cases, *, apply: [
            {
                "caseId": cases[0]["caseId"],
                "repaired": apply,
                "container": container,
            }
        ],
    )
    monkeypatch.setenv("STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.delenv("STORAGE_CONTAINER_NAME", raising=False)
    monkeypatch.setenv("BLOB_CONTAINER_NAME", "custom-recordings")
    _install_fake_blob_sdk(monkeypatch)
    argv = ["--apply" if apply else "--dry-run", "--manifest", str(manifest)]
    if apply:
        argv.extend(["--confirm-write", command.WRITE_CONFIRMATION])

    assert command.main(argv) == 0
    assert connection.autocommit is False
    assert connection.commits == expected_commit
    assert connection.rollbacks == (0 if apply else 1)
    assert connection.closed is True
    summary = json.loads(capsys.readouterr().out)
    assert summary["results"][0]["container"] == "custom-recordings"
    sql = " ".join(connection.command_cursor.statements)
    assert "set xact_abort on" in sql
    assert "sys.sp_getapplock" in sql
    assert "@lockowner='transaction'" in sql


def test_main_requires_exact_write_confirmation(tmp_path):
    manifest = tmp_path / "repair.json"
    manifest.write_text(
        json.dumps({"cases": [{"caseId": CASE_ID, "evidence": evidence()}]}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        command.main(["--apply", "--manifest", str(manifest)])


def test_main_rolls_back_the_whole_batch_on_failure(tmp_path, monkeypatch):
    manifest = tmp_path / "repair.json"
    manifest.write_text(
        json.dumps({"cases": [{"caseId": CASE_ID, "evidence": evidence()}]}),
        encoding="utf-8",
    )
    connection = CommandConnection()

    class DatabaseService:
        def _get_connection(self):
            return connection

    monkeypatch.setattr(command, "DatabaseService", DatabaseService)
    monkeypatch.setattr(
        command,
        "repair_cases",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("failure")),
    )
    monkeypatch.setenv("STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    _install_fake_blob_sdk(monkeypatch)

    assert command.main(
        [
            "--apply",
            "--manifest",
            str(manifest),
            "--confirm-write",
            command.WRITE_CONFIRMATION,
        ]
    ) == 1
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
