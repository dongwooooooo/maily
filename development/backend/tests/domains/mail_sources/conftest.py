import pytest
from cryptography.fernet import Fernet

from app.core.config import settings


@pytest.fixture(autouse=True)
def _test_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-at-least-32-bytes-long")
