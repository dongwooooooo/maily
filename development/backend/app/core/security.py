import uuid
from datetime import datetime

import jwt

from app.core.config import settings


class MissingJWTSecretError(Exception):
    pass


class InvalidSessionTokenError(Exception):
    pass


def sign_session_token(
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    if not settings.jwt_secret:
        raise MissingJWTSecretError("MAILY_JWT_SECRET is not set")

    payload = {
        "session_id": str(session_id),
        "user_id": str(user_id),
        "workspace_id": str(workspace_id),
        "iss": settings.jwt_issuer,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_session_token(token: str) -> dict:
    if not settings.jwt_secret:
        raise MissingJWTSecretError("MAILY_JWT_SECRET is not set")

    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidSessionTokenError(str(exc)) from exc
