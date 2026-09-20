"""Fail-closed encryption tests."""

import pytest
from cryptography.fernet import Fernet

from app.services import crypto


def test_encrypt_disabled_returns_plaintext(monkeypatch):
    monkeypatch.setattr(crypto.settings, "encryption_enabled", False)
    assert crypto.encrypt_text("secret-profile") == "secret-profile"


def test_encrypt_roundtrip_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(crypto.settings, "encryption_enabled", True)
    monkeypatch.setattr(crypto.settings, "encryption_key", None)
    monkeypatch.setattr(crypto, "_KEY_FILE", tmp_path / ".encryption_key")
    cipher = crypto.encrypt_text('{"email":"jane@example.com"}')
    assert cipher.startswith("gAAAA")
    assert "jane@example.com" not in cipher
    assert crypto.decrypt_text(cipher) == '{"email":"jane@example.com"}'


def test_encrypt_fails_closed_when_key_unavailable(monkeypatch):
    monkeypatch.setattr(crypto.settings, "encryption_enabled", True)

    def _no_key():
        raise crypto.EncryptionError("Encryption is enabled but the cryptography package is not installed")

    monkeypatch.setattr(crypto, "_load_or_create_key", _no_key)
    with pytest.raises(crypto.EncryptionError):
        crypto.encrypt_text("must-not-persist-plaintext")


def test_encrypt_fails_closed_on_runtime_error(monkeypatch):
    monkeypatch.setattr(crypto.settings, "encryption_enabled", True)
    monkeypatch.setattr(crypto, "_load_or_create_key", lambda: Fernet.generate_key())

    class _Boom:
        def encrypt(self, *_a, **_k):
            raise RuntimeError("fernet broken")

    monkeypatch.setattr("cryptography.fernet.Fernet", lambda *_a, **_k: _Boom())
    with pytest.raises(crypto.EncryptionError, match="Failed to encrypt"):
        crypto.encrypt_text("must-not-persist-plaintext")


def test_decrypt_leaves_legacy_plaintext_unchanged(monkeypatch):
    monkeypatch.setattr(crypto.settings, "encryption_enabled", True)
    assert crypto.decrypt_text('{"email":"legacy"}') == '{"email":"legacy"}'
