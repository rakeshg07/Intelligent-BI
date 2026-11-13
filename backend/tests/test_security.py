"""Tests for Security, Password Hashing, JWT, and Fernet Encryption."""

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)


def test_password_hashing() -> None:
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_lifecycle() -> None:
    payload = {"sub": "user-uuid-1234", "email": "test@example.com"}
    access_token = create_access_token(payload)
    decoded = decode_token(access_token)
    assert decoded["sub"] == "user-uuid-1234"
    assert decoded["email"] == "test@example.com"
    assert decoded["type"] == "access"

    refresh_token = create_refresh_token(payload)
    decoded_refresh = decode_token(refresh_token)
    assert decoded_refresh["sub"] == "user-uuid-1234"
    assert decoded_refresh["type"] == "refresh"


def test_fernet_credential_encryption() -> None:
    raw_secret = "postgresql://user:secretpass@db.internal:5432/analytics"
    encrypted = encrypt_secret(raw_secret)
    assert encrypted != raw_secret
    decrypted = decrypt_secret(encrypted)
    assert decrypted == raw_secret
