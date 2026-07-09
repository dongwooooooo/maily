import pytest
from cryptography.fernet import Fernet

from app.core.config import settings


@pytest.fixture(autouse=True)
def _test_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
