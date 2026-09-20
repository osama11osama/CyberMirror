"""Field-level encryption for sensitive local data."""

import base64
import logging

from app.config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)
_KEY_FILE = PROJECT_ROOT / "data" / ".encryption_key"


class EncryptionError(RuntimeError):
    """Raised when encryption is required but cannot be applied safely."""


def _load_or_create_key() -> bytes:
    if settings.encryption_key:
        raw = settings.encryption_key.encode()
        return base64.urlsafe_b64encode(raw.ljust(32)[:32])
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        key = _KEY_FILE.read_bytes().strip()
        if not key:
            raise EncryptionError("Encryption key file is empty")
        return key
    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        _KEY_FILE.write_bytes(key)
        return key
    except ImportError as exc:
        raise EncryptionError(
            "Encryption is enabled but the cryptography package is not installed"
        ) from exc


def encrypt_text(plain: str) -> str:
    """Encrypt sensitive text, or return plaintext only when encryption is disabled.

    When ``encryption_enabled`` is true, failures raise ``EncryptionError`` instead
    of silently persisting plaintext.
    """
    if not settings.encryption_enabled or not plain:
        return plain
    try:
        from cryptography.fernet import Fernet
        key = _load_or_create_key()
        if not key:
            raise EncryptionError("Encryption key is unavailable")
        return Fernet(key).encrypt(plain.encode()).decode()
    except EncryptionError:
        raise
    except Exception as exc:
        logger.error("Encrypt failed (%s)", type(exc).__name__)
        raise EncryptionError("Failed to encrypt sensitive local data") from exc


def decrypt_text(cipher: str) -> str:
    """Decrypt ciphertext when encryption is enabled.

    Values that are not Fernet ciphertext are returned unchanged so legacy
    plaintext rows remain readable after enabling encryption.
    """
    if not settings.encryption_enabled or not cipher:
        return cipher
    if not cipher.startswith("gAAAA"):
        return cipher
    try:
        from cryptography.fernet import Fernet
        key = _load_or_create_key()
        if not key:
            raise EncryptionError("Encryption key is unavailable for decrypt")
        return Fernet(key).decrypt(cipher.encode()).decode()
    except EncryptionError:
        raise
    except Exception as exc:
        logger.error("Decrypt failed (%s)", type(exc).__name__)
        raise EncryptionError("Failed to decrypt sensitive local data") from exc
