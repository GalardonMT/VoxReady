"""Runtime reconciliation is explicit, bounded and transaction-owned."""

from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import reconcile_labeling_runtime as command


class Connection:
    def __init__(self):
        self.cursor_value = MagicMock()
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.close = MagicMock()

    def cursor(self):
        return self.cursor_value


def install_service(monkeypatch, connection):
    service = MagicMock()
    service._get_connection.return_value = connection
    monkeypatch.setattr(command, "DatabaseService", lambda: service)


def test_dry_run_rolls_back_and_never_materializes(monkeypatch, capsys):
    connection = Connection()
    install_service(monkeypatch, connection)
    reconcile = MagicMock(return_value={"scanned": 1, "eligible": 1, "created": 0, "errors": []})
    monkeypatch.setattr(command, "reconcile_completed_reports", reconcile)

    assert command.main(["--dry-run", "--limit", "25"]) == 0

    reconcile.assert_called_once_with(connection.cursor_value, limit=25, materialize=False)
    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()
    connection.close.assert_called_once_with()
    assert '"created": 0' in capsys.readouterr().out


def test_apply_requires_exact_confirmation_and_commits(monkeypatch):
    with pytest.raises(SystemExit):
        command.main(["--apply"])

    connection = Connection()
    install_service(monkeypatch, connection)
    reconcile = MagicMock(return_value={"scanned": 1, "eligible": 1, "created": 1, "errors": []})
    monkeypatch.setattr(command, "reconcile_completed_reports", reconcile)

    assert command.main(
        ["--apply", "--confirm-write", command.WRITE_CONFIRMATION, "--limit", "10"]
    ) == 0
    reconcile.assert_called_once_with(connection.cursor_value, limit=10, materialize=True)
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once_with()
