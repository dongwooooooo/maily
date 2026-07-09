from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings
from app.domains.identity.schemas import GoogleProfile


class InvalidGoogleIdTokenError(Exception):
    pass


async def verify_google_id_token(id_token: str) -> GoogleProfile:
    """Verify a Google Identity Services ID token and extract the profile.

    Frontend performs the Google sign-in and hands this backend an
    ID token; we verify its signature/audience/expiry against
    Google's certs rather than trusting client-supplied claims.
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
