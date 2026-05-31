"""Field-level encryption for sensitive local data."""

import base64
import logging
from pathlib import Path

from app.config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)
_KEY_FILE = PROJECT_ROOT / "data" / ".encryption_key"


def _load_or_create_key() -> bytes:
    if settings.encryption_key:
        raw = settings.encryption_key.encode()
        return base64.urlsafe_b64encode(raw.ljust(32)[:32])
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()
    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        _KEY_FILE.write_bytes(key)
        return key
    except ImportError:
        logger.warning("cryptography not installed — encryption disabled")
        return b""


def encrypt_text(plain: str) -> str:
    if not settings.encryption_enabled or not plain:
        return plain
    try:
        from cryptography.fernet import Fernet
        key = _load_or_create_key()
        if not key:
            return plain
        return Fernet(key).encrypt(plain.encode()).decode()
    except Exception as exc:
        logger.warning("Encrypt failed: %s", exc)
        return plain


def decrypt_text(cipher: str) -> str:
    if not settings.encryption_enabled or not cipher:
        return cipher
    if not cipher.startswith("gAAAA"):
        return cipher
    try:
        from cryptography.fernet import Fernet
        key = _load_or_create_key()
        if not key:
            return cipher
        return Fernet(key).decrypt(cipher.encode()).decode()
    except Exception:
        return cipher
