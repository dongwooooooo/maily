import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core import security
from app.core.config import settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-at-least-32-bytes-long")


def test_sign_and_verify_roundtrip_returns_claims() -> None:
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    issued_at = _now()
    expires_at = issued_at + timedelta(hours=12)

    token = security.sign_session_token(
        user_id=user_id, workspace_id=workspace_id, issued_at=issued_at, expires_at=expires_at
    )
    claims = security.verify_session_token(token)

    assert claims["user_id"] == str(user_id)
    assert claims["workspace_id"] == str(workspace_id)
    assert claims["iss"] == settings.jwt_issuer


def test_verify_rejects_expired_token() -> None:
    issued_at = _now() - timedelta(hours=2)
    expired_at = issued_at + timedelta(hours=1)

    token = security.sign_session_token(
        user_id=uuid.uuid4(), workspace_id=uuid.uuid4(), issued_at=issued_at, expires_at=expired_at
    )

    with pytest.raises(security.InvalidSessionTokenError):
        security.verify_session_token(token)


def test_verify_rejects_foreign_issuer() -> None:
    payload = {
        "user_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "iss": "not-maily",
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(hours=1)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    with pytest.raises(security.InvalidSessionTokenError):
        security.verify_session_token(token)


def test_sign_raises_when_secret_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "")

    with pytest.raises(security.MissingJWTSecretError):
        security.sign_session_token(
            user_id=uuid.uuid4(), workspace_id=uuid.uuid4(), issued_at=_now(), expires_at=_now()
        )
