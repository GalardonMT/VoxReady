import pytest
from fastapi import HTTPException

import main


def test_internal_service_token_required(monkeypatch):
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "a" * 32)

    with pytest.raises(HTTPException) as missing:
        main.verify_internal_service(None)
    assert missing.value.status_code == 401

    with pytest.raises(HTTPException) as wrong:
        main.verify_internal_service("b" * 32)
    assert wrong.value.status_code == 401

    assert main.verify_internal_service("a" * 32) is None


def test_internal_service_fails_closed_when_unconfigured(monkeypatch):
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "")
    with pytest.raises(HTTPException) as error:
        main.verify_internal_service("a" * 32)
    assert error.value.status_code == 503
