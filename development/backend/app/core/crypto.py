from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

CURRENT_KEY_VERSION = 1


class MissingTokenEncryptionKeyError(Exception):
    pass


class TokenDecryptionError(Exception):
    pass


def _fernet() -> Fernet:
    if not settings.token_encryption_key:
        raise MissingTokenEncryptionKeyError("MAILY_TOKEN_ENC_KEY is not set")
    return Fernet(settings.token_encryption_key.encode())


def encrypt_token(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt_token(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(ciphertext).decode()
    except InvalidToken as exc:
        raise TokenDecryptionError(str(exc)) from exc
