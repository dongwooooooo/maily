import pytest
from cryptography.fernet import Fernet

from app.core import crypto
from app.core.config import settings


@pytest.fixture(autouse=True)
def _test_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())


def test_encrypt_then_decrypt_roundtrip() -> None:
    plaintext = "ya29.a0AfH6SMC-example-access-token"

    ciphertext = crypto.encrypt_token(plaintext)
    decrypted = crypto.decrypt_token(ciphertext)

    assert decrypted == plaintext


def test_ciphertext_does_not_contain_plaintext() -> None:
    plaintext = "1//0g-example-refresh-token"

    ciphertext = crypto.encrypt_token(plaintext)

    assert plaintext.encode() not in ciphertext


def test_encrypt_raises_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "token_encryption_key", "")

    with pytest.raises(crypto.MissingTokenEncryptionKeyError):
        crypto.encrypt_token("token")


def test_decrypt_raises_on_garbage_ciphertext() -> None:
    with pytest.raises(crypto.TokenDecryptionError):
        crypto.decrypt_token(b"not-a-real-fernet-token")


def test_decrypt_raises_when_encrypted_with_a_different_key() -> None:
    ciphertext = crypto.encrypt_token("token")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
        with pytest.raises(crypto.TokenDecryptionError):
            crypto.decrypt_token(ciphertext)
