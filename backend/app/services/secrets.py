"""Secure storage for API keys — encrypted, never in plain runtime_settings."""

import json
import logging

from app.config import PROJECT_ROOT
from app.services.crypto import EncryptionError, decrypt_text, encrypt_text

logger = logging.getLogger(__name__)
_SECRETS_FILE = PROJECT_ROOT / "data" / "secrets.json"


def _load() -> dict:
    if not _SECRETS_FILE.exists():
        return {}
    try:
        raw = json.loads(_SECRETS_FILE.read_text(encoding="utf-8"))
        return {k: decrypt_text(v) if isinstance(v, str) else v for k, v in raw.items()}
    except EncryptionError:
        raise
    except Exception as exc:
        logger.warning("Could not load secrets: %s", type(exc).__name__)
        return {}


def _save(data: dict) -> None:
    _SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    encrypted = {k: encrypt_text(v) if v else "" for k, v in data.items()}
    _SECRETS_FILE.write_text(json.dumps(encrypted, indent=2), encoding="utf-8")


def get_secret(key: str) -> str | None:
    val = _load().get(key)
    return val or None


def set_secret(key: str, value: str | None) -> None:
    data = _load()
    if value:
        data[key] = value
    elif key in data:
        del data[key]
    _save(data)


def migrate_plaintext_hibp(plain_key: str | None) -> None:
    """Move HIBP key from runtime_settings into encrypted secrets store."""
    if plain_key and not get_secret("hibp_api_key"):
        set_secret("hibp_api_key", plain_key)
