from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings
from app.domains.identity.schemas import GoogleProfile


class InvalidGoogleIdTokenError(Exception):
    pass


async def verify_google_id_token(id_token: str) -> GoogleProfile:
    """Google Identity Services ID token을 verify하고 profile을 추출한다.

    frontend가 Google sign-in을 수행하고 이 backend에 ID token을 넘긴다. client-supplied claim을
    신뢰하지 않고 Google cert로 signature/audience/expiry를 verify한다.
    """
    try:
        claims = google_id_token.verify_oauth2_token(
            id_token, google_requests.Request(), settings.google_oauth_client_id
        )
    except ValueError as exc:
        raise InvalidGoogleIdTokenError(str(exc)) from exc

    return GoogleProfile(
        google_subject=claims["sub"],
        email=claims["email"],
        display_name=claims.get("name"),
    )
